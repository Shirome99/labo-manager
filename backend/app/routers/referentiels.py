from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION, ROLES_GLOBAUX
from app.models import (
    AuditLog, Echantillon, RefAnalyse, RefCategorie,
    RefCritereMicro, ResultatAnalyse,
)
from app.services.seuils import evaluer_lignes
from app.routers.echantillons import refuser_si_refuse
from app.core.config import settings
from app.services.facturation import synchroniser as synchroniser_facturation
from app.services.paiements import recalculer_echantillons as recalculer_paiement
from app.services.habilitations import analyses_non_habilitees

router = APIRouter(prefix="/api", tags=["referentiels"])

SECTION_ATTR = {"SMA": "sma", "SCHA": "scha", "SSA": "ssa"}


def _parse_date(valeur):
    """Convertit une date texte en objet date, quel que soit le format navigateur."""
    if valeur is None:
        return None
    if isinstance(valeur, (date, datetime)):
        return valeur
    s = str(valeur).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ============================================================
#  Referentiels (lecture seule)
# ============================================================

@router.get("/ref/categories")
async def categories(q: str | None = None, user: dict = Depends(current_user),
                     db: AsyncSession = Depends(get_db)):
    stmt = select(RefCategorie).order_by(RefCategorie.libelle)
    if q:
        stmt = stmt.where(RefCategorie.libelle.ilike(f"%{q}%"))
    res = await db.execute(stmt)
    return [{"id": c.id, "libelle": c.libelle, "domaine": c.domaine}
            for c in res.scalars().all()]


@router.get("/ref/natures")
async def natures(q: str | None = None, user: dict = Depends(current_user),
                  db: AsyncSession = Depends(get_db)):
    sql = "SELECT id, libelle FROM ref_natures"
    params = {}
    if q:
        sql += " WHERE libelle ILIKE :q"
        params["q"] = f"%{q}%"
    sql += " ORDER BY libelle"
    res = await db.execute(text(sql), params)
    return [{"id": row.id, "libelle": row.libelle} for row in res.mappings().all()]


@router.get("/ref/fabricants")
async def fabricants(q: str | None = None, user: dict = Depends(current_user),
                     db: AsyncSession = Depends(get_db)):
    sql = "SELECT id, libelle, ville FROM ref_fabricants"
    params = {}
    if q:
        sql += " WHERE libelle ILIKE :q"; params["q"] = f"%{q}%"
    sql += " ORDER BY libelle"
    res = await db.execute(text(sql), params)
    return [{"id": r.id, "libelle": r.libelle, "ville": r.ville} for r in res.mappings().all()]


@router.get("/ref/organismes")
async def organismes(q: str | None = None, user: dict = Depends(current_user),
                     db: AsyncSession = Depends(get_db)):
    sql = "SELECT id, libelle, ville FROM ref_organismes"
    params = {}
    if q:
        sql += " WHERE libelle ILIKE :q"; params["q"] = f"%{q}%"
    sql += " ORDER BY libelle"
    res = await db.execute(text(sql), params)
    return [{"id": r.id, "libelle": r.libelle, "ville": r.ville} for r in res.mappings().all()]


@router.get("/ref/types-echantillon")
async def types_echantillon(user: dict = Depends(current_user),
                            db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT id, libelle FROM ref_types_echantillon ORDER BY libelle"))
    return [{"id": r.id, "libelle": r.libelle} for r in res.mappings().all()]


@router.get("/ref/soustypes-echantillon")
async def soustypes_echantillon(type_id: int | None = Query(None),
                                user: dict = Depends(current_user),
                                db: AsyncSession = Depends(get_db)):
    sql = "SELECT id, libelle, type_id FROM ref_soustypes_echantillon"
    params = {}
    if type_id is not None:
        sql += " WHERE type_id = :tid"
        params["tid"] = type_id
    sql += " ORDER BY libelle"
    res = await db.execute(text(sql), params)
    return [{"id": r.id, "libelle": r.libelle, "type_id": r.type_id}
            for r in res.mappings().all()]


@router.get("/ref/analyses")
async def analyses(section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                   q: str | None = None,
                   user: dict = Depends(current_user),
                   db: AsyncSession = Depends(get_db)):
    stmt = select(RefAnalyse).order_by(RefAnalyse.nom_analyse)
    if section:
        stmt = stmt.where(RefAnalyse.section == section)
    if q:
        stmt = stmt.where(RefAnalyse.nom_analyse.ilike(f"%{q}%"))
    res = await db.execute(stmt.limit(300))
    return [{"id": a.id, "nom": a.nom_analyse, "methode": a.reference_methode,
             "section": a.section, "delai": a.delai_execution}
            for a in res.scalars().all()]


@router.get("/ref/criteres")
async def criteres(categorie: str, user: dict = Depends(current_user),
                   db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(RefCritereMicro)
        .where(RefCritereMicro.categorie_produit == categorie)
        .order_by(RefCritereMicro.numero_ordre)
    )
    return [{"critere": c.critere, "parametre": c.parametre,
             "n": c.n, "c": c.c, "m": c.m, "M": c.grand_m}
            for c in res.scalars().all()]


async def _criteres_micro(db: AsyncSession, categorie: str | None) -> list[dict]:
    if not categorie:
        return []
    res = await db.execute(
        select(RefCritereMicro)
        .where(RefCritereMicro.categorie_produit == categorie)
        .order_by(RefCritereMicro.numero_ordre))
    return [{"id": c.id, "parametre": c.parametre, "n": c.n, "c": c.c, "m": c.m, "M": c.grand_m}
            for c in res.scalars().all()]


# ============================================================
#  Resultats d'analyses (bloc IV) — colonnes conformes a Access
#  SMA  : RP1-5
#  SCHA : RP1-9 + moyenne + conclusion + responsable
#  SSA  : resultat + criteres_interpretation + positifs/negatif/douteux
#  Acces en SQL direct : fonctionne des que la migration 011 est passee,
#  sans dependre du modele ORM.
# ============================================================

def _check_role(user: dict, section: str):
    role = user["role"]
    if role in ROLES_GLOBAUX or ROLE_SECTION.get(role) == section:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        f"Votre role ne donne pas acces a la section {section}.")


# Toutes les colonnes de resultats (communes + specifiques)
_COLS = [
    "analyse_effectuee", "reference_methode", "volume_ensemence", "nombre_analyses",
    "date_analyse", "date_sortie",
    "rp1", "rp2", "rp3", "rp4", "rp5", "rp6", "rp7", "rp8", "rp9",
    "moyenne", "conclusion",
    "resultat_analyse", "criteres_interpretation",
    "nbre_positifs", "nbre_negatif", "nbre_douteux",
    "responsable_analyse", "nbre_prelevements",
]
_TEXT_COLS = {
    "analyse_effectuee", "reference_methode", "volume_ensemence",
    "rp1", "rp2", "rp3", "rp4", "rp5", "rp6", "rp7", "rp8", "rp9",
    "moyenne", "conclusion", "resultat_analyse", "criteres_interpretation",
    "responsable_analyse",
}
_INT_COLS = {"nombre_analyses", "nbre_positifs", "nbre_negatif", "nbre_douteux", "nbre_prelevements"}
_DATE_COLS = {"date_analyse", "date_sortie"}


@router.get("/resultats/{section}/{num}")
async def lire_resultats(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(user, section)
    cols = ", ".join(["id"] + _COLS + ["saisi_par"])
    res = await db.execute(
        text(f"SELECT {cols} FROM resultats_analyses "
             "WHERE num_echantillon = :num AND section = :sec ORDER BY id"),
        {"num": num, "sec": section},
    )
    return [dict(row) for row in res.mappings().all()]


@router.put("/resultats/{section}/{num}")
async def enregistrer_resultats(
    lignes: list[dict],
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(user, section)

    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    if getattr(ech, SECTION_ATTR[section]) != "Yes":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Cet echantillon n'est pas assigne a la section {section}.")
    refuser_si_refuse(ech)

    def _txt(v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    cols_sql = ", ".join(["num_echantillon", "section"] + _COLS + ["saisi_par"])
    params_sql = ", ".join([":num_echantillon", ":section"]
                           + [f":{c}" for c in _COLS] + [":saisi_par"])
    insert = text(f"INSERT INTO resultats_analyses ({cols_sql}) VALUES ({params_sql})")

    # Préparation des lignes (normalisées comme elles seront stockées)
    a_inserer = []
    for ligne in lignes:
        # Une ligne compte si elle porte une analyse ou (SSA) un resultat
        if not (_txt(ligne.get("analyse_effectuee")) or _txt(ligne.get("resultat_analyse"))):
            continue

        params = {"num_echantillon": num, "section": section, "saisi_par": user["username"]}
        for c in _COLS:
            v = ligne.get(c)
            if c in _DATE_COLS:
                params[c] = _parse_date(v)
            elif c in _INT_COLS:
                params[c] = _int(v)
            else:
                params[c] = _txt(v)
        # SSA : recopier le resultat dans rp1 pour compat rapport PDF actuel
        if section == "SSA" and not params.get("rp1"):
            params["rp1"] = params.get("resultat_analyse")
        a_inserer.append(params)

    # Habilitations (tâche 19) : toute ligne nouvelle ou modifiée exige que l'utilisateur
    # soit habilité et à jour pour son analyse (les lignes inchangées ne sont pas re-contrôlées)
    if settings.HABILITATIONS_OBLIGATOIRES:
        def _signature(p):
            return tuple(None if p.get(c) is None else str(p.get(c)).strip() for c in _COLS)
        r = await db.execute(text(f"SELECT {', '.join(_COLS)} FROM resultats_analyses "
                                  "WHERE num_echantillon = :num AND section = :sec"), {"num": num, "sec": section})
        existantes = {_signature(dict(x)) for x in r.mappings().all()}
        nouvelles = [p for p in a_inserer if _signature(p) not in existantes]
        if any(not p.get("analyse_effectuee") for p in nouvelles):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Indiquez l'analyse effectuee pour chaque resultat (controle des habilitations).")
        refusees = await analyses_non_habilitees(db, user["id"], section,
                                                 [p["analyse_effectuee"] for p in nouvelles])
        if refusees:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Vous n'etes pas habilite (ou votre habilitation n'est pas a jour) pour : "
                                + ", ".join(f"« {a} »" for a in refusees) + ".")

    # On remplace toutes les lignes de la section pour cet echantillon
    await db.execute(
        text("DELETE FROM resultats_analyses WHERE num_echantillon = :num AND section = :sec"),
        {"num": num, "sec": section},
    )
    n = 0
    for params in a_inserer:
        await db.execute(insert, params)
        n += 1
    # Facturation (tâche 35) : lignes automatiques alignées sur les analyses saisies (prix du jour, figé)
    await synchroniser_facturation(db, num, user["username"])
    await recalculer_paiement(db, [num])

    db.add(AuditLog(utilisateur=user["username"], action="RESULTATS",
                    table_cible="resultats_analyses", cle=num,
                    details=f"{section} : {n} ligne(s)"))
    await db.commit()
    out = {"enregistre": True, "lignes": n}
    if section == "SMA":
        # comparaison aux criteres m / M de la categorie (signalement des depassements)
        out["evaluation"] = evaluer_lignes(lignes, await _criteres_micro(db, ech.categorie))
    return out


# ---------- SMA : depassements de seuils ----------
@router.post("/resultats/SMA/{num}/evaluation")
async def evaluer_resultats_sma(
    lignes: list[dict],
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare les RP saisis (non encore enregistres) aux criteres m / M de la categorie."""
    _check_role(user, "SMA")
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    return {"categorie": ech.categorie,
            **evaluer_lignes(lignes, await _criteres_micro(db, ech.categorie))}


@router.post("/resultats/SMA/{num}/conformite")
async def reporter_conformite_sma(
    payload: dict,
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reporte la conclusion proposee dans le champ `conformite` de la fiche SMA,
    sans toucher au reste de la fiche (ni a saisi_par : double regard preserve).
    """
    _check_role(user, "SMA")
    valeur = str((payload or {}).get("conformite") or "").strip()
    if valeur not in ("Conforme", "Non conforme"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Valeur attendue : Conforme ou Non conforme.")
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    if ech.statut in ("À valider", "Validé", "Rapport émis"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Fiche verrouillee (statut « {ech.statut} ») : modification impossible.")
    r = await db.execute(
        text("UPDATE traitement_sma SET conformite = :v, updated_at = now() "
             "WHERE num_echantillon = :num AND valide_par IS NULL RETURNING id"),
        {"v": valeur, "num": num})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Aucune fiche de traitement SMA modifiable : creez d'abord la fiche.")
    db.add(AuditLog(utilisateur=user["username"], action="UPDATE", table_cible="traitement_sma",
                    cle=num, details=f"conformite -> {valeur} (proposee par les seuils)"))
    await db.commit()
    return {"conformite": valeur}
