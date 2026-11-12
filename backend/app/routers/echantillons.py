import csv
import io
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION
from app.models import Echantillon, AuditLog
from app.schemas import EchantillonIn, EchantillonOut
from app.services.etiquettes import generer_etiquettes
from app.services.paiements import facturation_active, recalculer_echantillons
from app.services.reception import liste_non_conformites

router = APIRouter(prefix="/api/echantillons", tags=["echantillons"])

SECTION_COL = {"SMA": Echantillon.sma, "SCHA": Echantillon.scha, "SSA": Echantillon.ssa}


async def _audit(db, user, action, cle, details=None):
    db.add(AuditLog(utilisateur=user["username"], action=action,
                    table_cible="echantillons", cle=cle, details=details))


def _valider_section_unique(data: dict) -> None:
    """Un echantillon appartient a UNE seule section (SMA, SCHA ou SSA)."""
    choisies = [s for s in ("sma", "scha", "ssa") if data.get(s) == "Yes"]
    if len(choisies) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Choisissez une section (SMA, SCHA ou SSA).")
    if len(choisies) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Un echantillon ne peut appartenir qu'a une seule section.")


def montant(v) -> float | None:
    """Montant saisi (texte Access ou nombre) -> float ; None si illisible ou vide."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _valider_decision(data: dict) -> None:
    """« Accepté sous réserve » et « Refusé » exigent un motif."""
    if data.get("decision_reception") in ("Accepté sous réserve", "Refusé") \
            and not (data.get("motif_decision") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Le motif est obligatoire pour la decision « {data['decision_reception']} ».")


def refuser_si_refuse(ech) -> None:
    """Un échantillon refusé à la réception ne reçoit pas de fiche de traitement (409)."""
    if getattr(ech, "decision_reception", None) == "Refusé":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Echantillon refuse a la reception : aucune fiche de traitement possible.")


async def _next_num(db: AsyncSession, section: str | None = None) -> str:
    """
    Numero automatique au format AAAA-SECTION-NNNN (ex. 2026-SSA-0001).
    Sequence propre a chaque section, remise a zero chaque annee.
    On lit le plus grand numero existant pour ce prefixe et on ajoute 1
    (robuste aux suppressions, contrairement a un simple COUNT).
    """
    annee = date.today().year
    sec = section or "GEN"
    prefix = f"{annee}-{sec}-"
    res = await db.execute(
        select(Echantillon.num_echantillon)
        .where(Echantillon.num_echantillon.like(f"{prefix}%"))
    )
    maxseq = 0
    motif = re.compile(rf"^{annee}-{sec}-0*(\d+)$")
    for (num,) in res.all():
        m = motif.match((num or "").strip())
        if m:
            maxseq = max(maxseq, int(m.group(1)))
    return f"{prefix}{maxseq + 1:04d}"


class FiltresListe:
    """
    Filtres communs a la liste et a l'export (memes parametres, meme requete).
    Tous appliques cote serveur.
    """

    def __init__(
        self,
        section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
        q: str | None = None,
        statut: str | None = None,
        du: date | None = Query(None, description="Reception a partir du (inclus)"),
        au: date | None = Query(None, description="Reception jusqu'au (inclus)"),
        fabricant: str | None = None,
        organisme: str | None = None,
        retard: bool = Query(False, description="Seulement les echantillons en retard"),
        decision: str | None = Query(None, pattern="^(Accepté|Accepté sous réserve|Refusé)$",
                                     description="Decision de reception"),
        paiement: str | None = Query(None, pattern="^(Non concerné|Non payé|À payer|Partiellement payé|Payé|Exonéré|Avoir total)$",
                                     description="Statut du paiement"),
    ):
        self.section, self.q, self.statut = section, q, statut
        self.du, self.au = du, au
        self.fabricant, self.organisme = fabricant, organisme
        self.retard = retard
        self.decision = decision
        self.paiement = paiement


DELAI_DEFAUT = 15  # jours, si la section n'a pas de ligne dans ref_delais


async def _delais(db: AsyncSession) -> dict[str, int]:
    """Delai de traitement (jours) par section, depuis ref_delais (migration 013)."""
    r = await db.execute(text("SELECT section, jours FROM ref_delais"))
    d = {row.section: row.jours for row in r}
    return {s: d.get(s, DELAI_DEFAUT) for s in SECTION_COL}


def _cond_retard(delais: dict[str, int], sections=None):
    """
    En retard : pas encore 'Rapport émis' et recu depuis plus de N jours
    (N propre a la section). Sans date de reception : non compte.
    """
    maintenant = datetime.now()
    par_section = [
        and_(SECTION_COL[s] == "Yes",
             Echantillon.date_reception < maintenant - timedelta(days=delais[s]))
        for s in (sections or SECTION_COL)
    ]
    # Un échantillon refusé à la réception ne sera jamais traité : jamais « en retard »
    return and_(or_(Echantillon.statut.is_(None), Echantillon.statut != "Rapport émis"),
                or_(Echantillon.decision_reception.is_(None), Echantillon.decision_reception != "Refusé"),
                or_(*par_section))


def _requete_liste(f: FiltresListe, user: dict, delais: dict[str, int] | None = None, sans_statut: bool = False):
    stmt = select(Echantillon)
    role_section = ROLE_SECTION.get(user["role"])
    effective = role_section or f.section
    if role_section and f.section and f.section != role_section:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Section non autorisee pour votre role.")
    if effective:
        stmt = stmt.where(SECTION_COL[effective] == "Yes")
    if f.q:
        like = f"%{f.q}%"
        stmt = stmt.where(or_(
            Echantillon.num_echantillon.ilike(like),
            Echantillon.nature.ilike(like),
            Echantillon.fabricant.ilike(like),
            Echantillon.client_nom.ilike(like),
        ))
    if f.statut and not sans_statut:
        stmt = stmt.where(Echantillon.statut == f.statut)
    if f.du:
        stmt = stmt.where(Echantillon.date_reception >= f.du)
    if f.au:
        # borne incluse : tout le jour "au"
        stmt = stmt.where(Echantillon.date_reception < f.au + timedelta(days=1))
    if f.fabricant:
        stmt = stmt.where(Echantillon.fabricant.ilike(f"%{f.fabricant}%"))
    if f.organisme:
        stmt = stmt.where(Echantillon.organisme_preleveur.ilike(f"%{f.organisme}%"))
    if f.retard and delais:
        stmt = stmt.where(_cond_retard(delais))
    if f.decision == "Accepté":     # non renseigné (échantillons antérieurs) = accepté
        stmt = stmt.where(or_(Echantillon.decision_reception.is_(None),
                              Echantillon.decision_reception == "Accepté"))
    elif f.decision:
        stmt = stmt.where(Echantillon.decision_reception == f.decision)
    if f.paiement == "Non concerné":   # non renseigné = non concerné (valeur affichée par défaut)
        stmt = stmt.where(or_(Echantillon.payement.is_(None), Echantillon.payement == "",
                              Echantillon.payement == "Non concerné"))
    elif f.paiement in ("Non payé", "À payer"):   # « À payer » : ancienne valeur saisie à la main
        stmt = stmt.where(Echantillon.payement.in_(("Non payé", "À payer")))
    elif f.paiement:
        stmt = stmt.where(Echantillon.payement == f.paiement)
    return stmt.order_by(Echantillon.ordre.desc())


# Tri de la liste paginée : clés autorisées -> colonnes (jamais de colonne libre)
TRIS = {
    "ordre": Echantillon.ordre,
    "num_echantillon": Echantillon.num_echantillon,
    "date_reception": Echantillon.date_reception,
    "statut": Echantillon.statut,
    "nature": Echantillon.nature,
}


@router.get("")
async def liste(
    f: FiltresListe = Depends(),
    page: int | None = Query(None, ge=1, description="Pagination serveur : numéro de page (sans page : liste complète)"),
    taille: int = Query(50, ge=1, le=500),
    tri: str = Query("ordre", pattern="^(ordre|num_echantillon|date_reception|statut|nature)$"),
    ordre: str = Query("desc", pattern="^(asc|desc)$"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste filtrée. Avec `page` (écran Échantillons, tâche 30) : une page triée côté serveur,
    le total et les compteurs par statut (calculés avec tous les filtres sauf le statut) :
    {lignes, total, page, taille, compteurs}. Sans `page` : liste complète (compatibilité).
    """
    delais = await _delais(db) if f.retard else None
    if page is None:
        lignes = (await db.execute(_requete_liste(f, user, delais))).scalars().all()
        return [EchantillonOut.model_validate(e) for e in lignes]

    filtree = _requete_liste(f, user, delais).order_by(None)
    sous = _requete_liste(f, user, delais, sans_statut=True).order_by(None).subquery()
    compteurs = {s or "Non renseigné": n for s, n in (await db.execute(
        select(sous.c.statut, func.count()).group_by(sous.c.statut))).all()}
    total = await db.scalar(select(func.count()).select_from(filtree.subquery()))
    col = TRIS[tri]
    cle = col.asc().nulls_last() if ordre == "asc" else col.desc().nulls_last()
    stmt = filtree.order_by(cle, Echantillon.ordre.desc()).limit(taille).offset((page - 1) * taille)
    lignes = (await db.execute(stmt)).scalars().all()
    return {"lignes": [EchantillonOut.model_validate(e) for e in lignes], "total": total,
            "page": page, "taille": taille, "compteurs": compteurs}


# Colonnes de l'export (libelle, attribut)
COLONNES_EXPORT = [
    ("N° Échantillon", "num_echantillon"),
    ("Date réception", "date_reception"),
    ("Section", None),
    ("Statut", "statut"),
    ("Nature", "nature"),
    ("Catégorie", "categorie"),
    ("N° de lot", "num_lot"),
    ("Fabricant ou propriétaire", "fabricant"),
    ("Organisme préleveur", "organisme_preleveur"),
    ("Réf. fiche de prélèvement", "ref_fiche_prelevement"),
    ("Client", "client_nom"),
    ("Statut de paiement", "payement"),
    ("Montant", "total"),
    ("Payé", "montant_paye"),
    ("Reste dû", "__reste__"),
    ("Mode de paiement", "mode_paiement"),
    ("Date de paiement", "date_payement"),
    ("N° quittance", "num_quittance"),
    ("Date quittance", "date_quittance"),
    ("Décision de réception", "decision_reception"),
    ("Motif de la décision", "motif_decision"),
    ("T° à réception (°C)", "temperature_reception"),
    ("Non-conformités", "__nc__"),
]


def _valeur_export(e: Echantillon, attr: str | None):
    if attr is None:
        return ", ".join(s for s, a in (("SMA", e.sma), ("SCHA", e.scha), ("SSA", e.ssa)) if a == "Yes")
    if attr == "__nc__":
        return ", ".join(liste_non_conformites(e))
    if attr == "__reste__":
        total = montant(e.total)
        return None if total is None else max(total - (montant(e.montant_paye) or 0), 0)
    v = getattr(e, attr)
    if isinstance(v, datetime):
        return v.date() if v.time() == datetime.min.time() else v
    return v


@router.get("/export")
async def exporter(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    f: FiltresListe = Depends(),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export de la liste avec exactement les memes filtres que GET /api/echantillons."""
    delais = await _delais(db) if f.retard else None
    rows = (await db.execute(_requete_liste(f, user, delais))).scalars().all()
    entetes = [c[0] for c in COLONNES_EXPORT]
    lignes = [[_valeur_export(e, attr) for _, attr in COLONNES_EXPORT] for e in rows]
    nom = f"echantillons_{date.today().isoformat()}"

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")  # ; : ouverture directe dans Excel FR
        w.writerow(entetes)
        for l in lignes:
            w.writerow(["" if v is None else (v.isoformat() if hasattr(v, "isoformat") else v) for v in l])
        contenu = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM pour les accents
        return Response(contenu, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nom}.csv"'})

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Échantillons"
    ws.append(entetes)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="00875A")
    for l in lignes:
        ws.append(l)
    for col in ws.columns:
        largeur = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(largeur + 2, 10), 50)
        for c in col[1:]:
            if isinstance(c.value, (date, datetime)):
                c.number_format = "DD/MM/YYYY" if not isinstance(c.value, datetime) else "DD/MM/YYYY HH:MM"
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nom}.xlsx"'})


@router.get("/stats")
async def stats(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    out = {}
    for name, col in SECTION_COL.items():
        res = await db.execute(select(func.count()).select_from(Echantillon).where(col == "Yes"))
        out[f"total{name}"] = res.scalar_one()
    total = await db.execute(select(func.count()).select_from(Echantillon))
    out["total"] = total.scalar_one()
    return out


@router.get("/dashboard")
async def dashboard(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Statistiques enrichies pour le tableau de bord."""
    role_section = ROLE_SECTION.get(user["role"])

    def _scope(stmt):
        if role_section:
            return stmt.where(SECTION_COL[role_section] == "Yes")
        return stmt

    out = {}
    for name, col in SECTION_COL.items():
        r = await db.execute(select(func.count()).select_from(Echantillon).where(col == "Yes"))
        out[f"total{name}"] = r.scalar_one()
    r = await db.execute(_scope(select(func.count()).select_from(Echantillon)))
    out["total"] = r.scalar_one()

    # Repartition par statut
    r = await db.execute(_scope(select(Echantillon.statut, func.count()).group_by(Echantillon.statut)))
    par_statut = {(row[0] or "Recu"): row[1] for row in r.all()}
    out["parStatut"] = par_statut

    out["enCours"] = par_statut.get("En cours", 0) + par_statut.get("Recu", 0) + par_statut.get("Reçu", 0)
    out["aValider"] = par_statut.get("A valider", 0) + par_statut.get("À valider", 0)
    out["termines"] = par_statut.get("Valide", 0) + par_statut.get("Validé", 0) \
        + par_statut.get("Rapport emis", 0) + par_statut.get("Rapport émis", 0)

    # ---- Pilotage par section : statuts, a valider, retards ----
    delais = await _delais(db)
    visibles = [role_section] if role_section else list(SECTION_COL)
    out["sections"] = []
    for sec in visibles:
        col = SECTION_COL[sec]
        r = await db.execute(select(Echantillon.statut, func.count())
                             .where(col == "Yes").group_by(Echantillon.statut))
        statuts = {(row[0] or "Reçu"): row[1] for row in r.all()}
        r = await db.execute(select(func.count()).select_from(Echantillon)
                             .where(_cond_retard(delais, [sec])))
        out["sections"].append({
            "section": sec,
            "total": sum(statuts.values()),
            "parStatut": statuts,
            "aValider": statuts.get("À valider", 0),
            "retards": r.scalar_one(),
            "delai": delais[sec],
        })

    def _resume(e):
        sec = next((s for s, a in (("SMA", e.sma), ("SCHA", e.scha), ("SSA", e.ssa)) if a == "Yes"), None)
        return {"num_echantillon": e.num_echantillon, "nature": e.nature, "statut": e.statut,
                "section": sec, "payement": e.payement,
                "date_reception": str(e.date_reception) if e.date_reception else None,
                "jours": (datetime.now() - e.date_reception).days if e.date_reception else None}

    r = await db.execute(_scope(select(Echantillon).where(Echantillon.statut == "À valider"))
                         .order_by(Echantillon.date_reception.asc().nulls_last()).limit(10))
    out["listeAValider"] = [_resume(e) for e in r.scalars().all()]
    r = await db.execute(select(Echantillon).where(_cond_retard(delais, visibles))
                         .order_by(Echantillon.date_reception.asc()).limit(10))
    out["listeRetards"] = [_resume(e) for e in r.scalars().all()]
    out["retards"] = sum(s["retards"] for s in out["sections"])

    r = await db.execute(_scope(select(Echantillon)).order_by(Echantillon.ordre.desc()).limit(5))
    out["recents"] = [
        {"num_echantillon": e.num_echantillon, "nature": e.nature, "statut": e.statut,
         "date_reception": str(e.date_reception) if e.date_reception else None,
         "sma": e.sma, "scha": e.scha, "ssa": e.ssa, "payement": e.payement}
        for e in r.scalars().all()
    ]
    return out


@router.get("/{num}/facturation")
async def facturation(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """
    Montant calculé à partir des analyses effectuées (lignes de résultats) et de la grille
    ref_tarifs : une ligne de résultats = une analyse facturée, au prix de son tarif actif
    (même nom, même section). Les analyses sans tarif sont signalées.
    """
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    # Facturation (bloc P) : les rôles de section ne voient que le statut de paiement, pas les montants
    if ROLE_SECTION.get(user["role"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Les montants ne sont visibles que de l'accueil, des responsables et de l'admin.")
    r = await db.execute(text("""
        SELECT r.section, btrim(r.analyse_effectuee) AS analyse, tp.prix
        FROM resultats_analyses r
        LEFT JOIN ref_tarifs t
               ON lower(btrim(t.nom_analyse)) = lower(btrim(r.analyse_effectuee))
              AND t.section = r.section AND t.actif
        LEFT JOIN ref_tarifs_prix tp
               ON tp.tarif_id = t.id AND tp.date_debut <= CURRENT_DATE
              AND (tp.date_fin IS NULL OR tp.date_fin >= CURRENT_DATE)
        WHERE r.num_echantillon = :num AND coalesce(btrim(r.analyse_effectuee), '') <> ''
        ORDER BY r.section, r.id
    """), {"num": num})
    lignes = [{"section": x.section, "analyse": x.analyse,
               "prix": float(x.prix) if x.prix is not None else None} for x in r]
    par_section: dict[str, dict] = {}
    for l in lignes:
        p = par_section.setdefault(l["section"], {"nb": 0, "montant": 0.0})
        p["nb"] += 1
        p["montant"] += l["prix"] or 0
    return {
        "num": num,
        "lignes": lignes,
        "par_section": par_section,
        "total": round(sum(p["montant"] for p in par_section.values()), 2),
        "sans_tarif": [f"{l['analyse']} ({l['section']})" for l in lignes if l["prix"] is None],
    }


@router.get("/{num}/etiquette")
async def etiquettes(
    num: str,
    largeur: float | None = Query(None, ge=20, le=150, description="Largeur de l'étiquette (mm)"),
    hauteur: float | None = Query(None, ge=10, le=100, description="Hauteur de l'étiquette (mm)"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """PDF d'étiquettes : une par prélèvement de la section (Nbre Prlvmts), Code 128 du n°."""
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    sections = [s for s, col in (("SMA", "sma"), ("SCHA", "scha"), ("SSA", "ssa"))
                if getattr(ech, col) == "Yes"]
    role_section = ROLE_SECTION.get(user["role"])
    if role_section and role_section not in sections:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cet echantillon n'appartient pas a votre section.")
    section = sections[0] if sections else "—"
    nombre = (getattr(ech, f"nbre_prlvmts_{section.lower()}", None) if sections else None) or 1
    pdf = generer_etiquettes(
        num=ech.num_echantillon, section=section, nature=ech.nature,
        date_reception=ech.date_reception.strftime("%d/%m/%Y") if ech.date_reception else None,
        nombre=min(int(nombre), 200),
        largeur_mm=largeur or settings.ETIQUETTE_LARGEUR_MM,
        hauteur_mm=hauteur or settings.ETIQUETTE_HAUTEUR_MM,
    )
    nom = f"Etiquettes_{num}.pdf".replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nom}"',
                             "X-Etiquettes": str(min(int(nombre), 200))})


@router.get("/{num}", response_model=EchantillonOut)
async def detail(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    return ech


@router.post("", response_model=EchantillonOut, status_code=status.HTTP_201_CREATED)
async def creer(payload: EchantillonIn, user: dict = Depends(current_user),
                db: AsyncSession = Depends(get_db)):
    data = payload.model_dump()
    _valider_section_unique(data)
    if not data.get("decision_reception"):
        data["decision_reception"] = "Accepté"
    _valider_decision(data)
    auto = not data.get("num_echantillon")
    # Section retenue (unique, garantie par _valider_section_unique) -> entre dans le numero
    section = next((s for s in ("SMA", "SCHA", "SSA") if data.get(s.lower()) == "Yes"), None)

    # Numero manuel : on verifie juste qu'il n'existe pas deja.
    if not auto:
        exists = await db.execute(
            select(Echantillon).where(Echantillon.num_echantillon == data["num_echantillon"]))
        if exists.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f'Le numero "{data["num_echantillon"]}" existe deja.')

    # Numero automatique : on regenere et on reessaie en cas de collision
    # (deux receptions simultanees pourraient viser le meme numero).
    for _ in range(5):
        if auto:
            data["num_echantillon"] = await _next_num(db, section)
        ech = Echantillon(**data)
        if not ech.statut:
            ech.statut = "Reçu"
        db.add(ech)
        await _audit(db, user, "CREATE", ech.num_echantillon)
        try:
            await db.commit()
            await db.refresh(ech)
            return ech
        except IntegrityError:
            await db.rollback()
            if not auto:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    f'Le numero "{data["num_echantillon"]}" existe deja.')
            # sinon : boucle -> nouveau numero
    raise HTTPException(status.HTTP_409_CONFLICT,
                        "Impossible de generer un numero unique, reessayez.")


@router.put("/{num}", response_model=EchantillonOut)
async def modifier(num: str, payload: EchantillonIn, user: dict = Depends(current_user),
                   db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    donnees = payload.model_dump(exclude={"num_echantillon"})
    _valider_section_unique(donnees)
    _valider_decision(donnees)
    for k, v in donnees.items():
        setattr(ech, k, v)
    # Facturation (bloc P) : les champs de paiement d'un échantillon facturé sont calculés, jamais saisis
    await db.flush()
    if await facturation_active(db, num):
        await recalculer_echantillons(db, [num])
    await _audit(db, user, "UPDATE", num)
    await db.commit()
    await db.refresh(ech)
    return ech


@router.delete("/{num}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer(num: str, user: dict = Depends(current_user),
                    db: AsyncSession = Depends(get_db)):
    if user["role"] not in ("admin", "user"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Suppression non autorisee.")
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Introuvable.")
    # Facturation (tâche 36) : un échantillon porté par un bulletin (même brouillon) n'est pas supprimé
    r = await db.execute(text(
        "SELECT f.numero, f.statut FROM factures_echantillons fe JOIN factures f ON f.id = fe.facture_id "
        "WHERE fe.num_echantillon = :n LIMIT 1"), {"n": num})
    lie = r.first()
    if lie:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Cet échantillon figure sur le bulletin {lie.numero or '(brouillon)'} : "
                            "il ne peut pas être supprimé." + (" Retirez-le d'abord du brouillon." if lie.statut == "brouillon" else ""))
    r = await db.execute(text("SELECT 1 FROM exonerations WHERE num_echantillon = :n LIMIT 1"), {"n": num})
    if r.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet échantillon a fait l'objet d'une exonération : "
                                                      "il ne peut pas être supprimé.")
    await db.delete(ech)
    await _audit(db, user, "DELETE", num)
    await db.commit()


# ---------- Transitions de statut ----------
# Ordre officiel du cycle de vie (aligne sur la contrainte CHECK de la base)
STATUTS = ["Reçu", "En cours", "À valider", "Validé", "Rapport émis"]


@router.patch("/{num}/statut", response_model=EchantillonOut)
async def changer_statut(
    num: str,
    payload: dict,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stepper manuel de statut : réservé à l'admin.
    Il ne mène jamais à « Validé » ni à « Rapport émis » (seuls les circuits dédiés
    y mènent : validation à double regard, émission du rapport), et ne fait pas
    sortir un dossier de « Rapport émis » (passer par l'erratum).
    """
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Le changement manuel de statut est reserve a l'administrateur.")
    nouveau = (payload or {}).get("statut")
    if nouveau not in STATUTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Statut invalide. Valeurs possibles : {', '.join(STATUTS)}.")
    if nouveau in ("Validé", "Rapport émis"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "« Validé » et « Rapport émis » ne s'obtiennent que par la validation "
                            "de la fiche et l'emission du rapport.")

    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')

    # Controle d'acces sectionnel
    role_section = ROLE_SECTION.get(user["role"])
    if role_section and getattr(ech, {"SMA": "sma", "SCHA": "scha", "SSA": "ssa"}[role_section]) != "Yes":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Cet echantillon n'appartient pas a votre section.")

    ancien = ech.statut
    if ancien == "Rapport émis":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Rapport emis : pour rouvrir le dossier, lancez un erratum.")
    ech.statut = nouveau
    await _audit(db, user, "STATUT", num, details=f"{ancien} -> {nouveau}")
    await db.commit()
    await db.refresh(ech)
    return ech


@router.get("/{num}/complet")
async def detail_complet(num: str, user: dict = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    """Echantillon + ses fiches de traitement par section (pour la page de detail)."""
    from app.models import TRAITEMENT_MODELS

    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')

    sections = {"SMA": ech.sma, "SCHA": ech.scha, "SSA": ech.ssa}
    traitements = {}
    for sec, actif in sections.items():
        if actif != "Yes":
            continue
        Model = TRAITEMENT_MODELS[sec]
        r = await db.execute(select(Model).where(Model.num_echantillon == num))
        trt = r.scalar_one_or_none()
        traitements[sec] = {
            "existe": trt is not None,
            "saisi_par": getattr(trt, "saisi_par", None) if trt else None,
            "valide_par": getattr(trt, "valide_par", None) if trt else None,
        }

    return {
        "echantillon": EchantillonOut.model_validate(ech).model_dump(),
        "sections_actives": [s for s, a in sections.items() if a == "Yes"],
        "traitements": traitements,
    }
