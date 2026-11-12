"""
Facturation et paiement (bloc P).

Préfixe : /api/facturation
  GET  /parametres            réglages (taux de TVA, étape de paiement exigée, seuil des impayés) — tout connecté
  PUT  /parametres            modification — admin
  GET  /tarifs?date=&section= grille à une date (prix à renseigner = prix null) — tout connecté
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLES_FACTURATION, ROLES_GLOBAUX, ROLES_RESPONSABLES, current_user, require_admin
from app.models import AuditLog
from app.services import bulletins, exports_facturation, facturation as fact, paiements

router = APIRouter(prefix="/api/facturation", tags=["facturation"])


class ParametresIn(BaseModel):
    taux_tva: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    etape_paiement: str = Field(pattern="^(" + "|".join(fact.ETAPES_PAIEMENT) + ")$")
    seuil_impayes_jours: int = Field(ge=1, le=365)


@router.get("/parametres")
async def lire_parametres(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await fact.lire_parametres(db)
    return {**p, "etapes": [{"value": k, "label": v} for k, v in fact.ETAPES_PAIEMENT.items()]}


@router.put("/parametres")
async def modifier_parametres(p: ParametresIn, admin: dict = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    for cle, valeur in p.model_dump().items():
        await fact.ecrire_parametre(db, f"facturation.{cle}", valeur, admin["username"])
    db.add(AuditLog(utilisateur=admin["username"], action="UPDATE", table_cible="parametres",
                    cle="facturation", details=f"TVA {p.taux_tva} %, étape {p.etape_paiement}, "
                                               f"impayés {p.seuil_impayes_jours} j"))
    await db.commit()
    return await fact.lire_parametres(db)


@router.get("/tarifs")
async def grille(date_ref: date | None = Query(None, alias="date"),
                 section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                 user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    lignes = await fact.grille_a_date(db, date_ref, section)
    return [{"id": x["tarif_id"], "nom_analyse": x["nom_analyse"], "section": x["section"],
             "prix": x["prix"] if x["actif"] else None, "par_prelevement": x["par_prelevement"],
             "a_valider": x["a_valider"], "actif": x["actif"]} for x in lignes]


# ------------------------------------------------------------------
#  Lignes facturables d'un échantillon (tâche 35)
#    GET    /echantillons/{num}              lignes, totaux par section, total — rôles globaux
#    POST   /echantillons/{num}/synchroniser lignes automatiques depuis les résultats — accueil, admin
#    POST   /echantillons/{num}/lignes       ligne manuelle (analyse de la grille ou frais divers)
#    PATCH  /lignes/{id}                     quantité, prix unitaire, libellé
#    DELETE /lignes/{id}
# ------------------------------------------------------------------
def exiger_global(user: dict):
    if user["role"] not in ROLES_GLOBAUX:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "La facturation n'est visible que de l'accueil, des responsables et de l'admin.")


def exiger_facturation(user: dict):
    if user["role"] not in ROLES_FACTURATION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'accueil (réception) et à l'administrateur.")


async def _echantillon(db, num: str):
    r = await db.execute(text('SELECT "N° Echantillon" AS num FROM echantillons WHERE "N° Echantillon" = :n'),
                         {"n": num})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Échantillon « {num} » introuvable.')


async def _ligne_modifiable(db, ligne_id: int) -> dict:
    l = await fact.ligne(db, ligne_id)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ligne introuvable.")
    if ligne_id in await fact.lignes_verrouillees(db, l["num_echantillon"]):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Cette ligne figure sur un bulletin émis : elle ne peut plus être modifiée (faire un avoir).")
    return l


async def facturation_echantillon(db, num: str) -> dict:
    lignes = await fact.lignes_echantillon(db, num)
    verrou = await fact.lignes_verrouillees(db, num)
    for l in lignes:
        l["verrouillee"] = l["id"] in verrou
    etat = await paiements.etat_echantillon(db, num)
    return {"num": num, "lignes": lignes, **fact.totaux(lignes), "paiement": etat}


@router.get("/echantillons/{num}")
async def lignes_echantillon(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_global(user)
    await _echantillon(db, num)
    return await facturation_echantillon(db, num)


@router.post("/echantillons/{num}/synchroniser")
async def synchroniser(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    await _echantillon(db, num)
    res = await fact.synchroniser(db, num, user["username"])
    await paiements.recalculer_echantillons(db, [num])
    if res["ajoutees"] or res["retirees"]:
        db.add(AuditLog(utilisateur=user["username"], action="FACTURATION", table_cible="factures_lignes", cle=num,
                        details=f"synchronisation : +{len(res['ajoutees'])} / -{len(res['retirees'])}"))
    await db.commit()
    return {**res, **await facturation_echantillon(db, num)}


class LigneIn(BaseModel):
    section: str | None = Field(None, pattern="^(SMA|SCHA|SSA)$")
    analyse: str = Field(min_length=1, max_length=150)
    quantite: Decimal | None = Field(None, gt=0, le=10_000, max_digits=10, decimal_places=2)
    prix_unitaire: Decimal | None = Field(None, ge=0, le=1_000_000, max_digits=12, decimal_places=2)


class LigneModif(BaseModel):
    analyse: str | None = Field(None, min_length=1, max_length=150)
    quantite: Decimal | None = Field(None, gt=0, le=10_000, max_digits=10, decimal_places=2)
    prix_unitaire: Decimal | None = Field(None, ge=0, le=1_000_000, max_digits=12, decimal_places=2)


@router.post("/echantillons/{num}/lignes", status_code=status.HTTP_201_CREATED)
async def ajouter_ligne(num: str, p: LigneIn, user: dict = Depends(current_user),
                        db: AsyncSession = Depends(get_db)):
    """Analyse de la grille (prix du jour, figé) ou frais divers (sans section, prix saisi)."""
    exiger_facturation(user)
    await _echantillon(db, num)
    if p.section is None and p.prix_unitaire is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indiquez le montant des frais divers.")
    lid = await fact.creer_ligne(db, num, p.section, p.analyse, user["username"], "manuelle",
                                 quantite=p.quantite, prix_unitaire=p.prix_unitaire)
    await paiements.recalculer_echantillons(db, [num])
    db.add(AuditLog(utilisateur=user["username"], action="CREATE", table_cible="factures_lignes", cle=num,
                    details=f"{p.analyse.strip()} ({p.section or 'divers'})"))
    await db.commit()
    return {"id": lid, **await facturation_echantillon(db, num)}


@router.patch("/lignes/{ligne_id}")
async def modifier_ligne(ligne_id: int, p: LigneModif, user: dict = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    l = await _ligne_modifiable(db, ligne_id)
    await fact.modifier_ligne(db, ligne_id, user["username"], quantite=p.quantite, prix_unitaire=p.prix_unitaire,
                              analyse=p.analyse, prix_fourni="prix_unitaire" in p.model_fields_set)
    await paiements.recalculer_echantillons(db, [l["num_echantillon"]])
    db.add(AuditLog(utilisateur=user["username"], action="UPDATE", table_cible="factures_lignes",
                    cle=l["num_echantillon"], details=f"ligne {ligne_id}"))
    await db.commit()
    return await facturation_echantillon(db, l["num_echantillon"])


@router.delete("/lignes/{ligne_id}")
async def supprimer_ligne(ligne_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    l = await _ligne_modifiable(db, ligne_id)
    await db.execute(text("DELETE FROM factures_lignes WHERE id = :id"), {"id": ligne_id})
    await paiements.recalculer_echantillons(db, [l["num_echantillon"]])
    db.add(AuditLog(utilisateur=user["username"], action="DELETE", table_cible="factures_lignes",
                    cle=l["num_echantillon"], details=f"{l['analyse']} ({l['section'] or 'divers'})"))
    await db.commit()
    return await facturation_echantillon(db, l["num_echantillon"])


# ------------------------------------------------------------------
#  Bulletins et avoirs (tâche 36)
#    GET   /factures                    liste (filtres) — rôles globaux
#    POST  /factures                    brouillon pour des échantillons d'un même client — accueil, admin
#    GET   /factures/{id}               détail (lignes vivantes si brouillon, figées sinon)
#    PATCH /factures/{id}               échantillons / client d'un brouillon (409 si émis)
#    POST  /factures/{id}/emettre       numéro, copie figée, PDF archivé
#    POST  /factures/{id}/annuler       abandon d'un brouillon (un bulletin émis : avoir)
#    GET   /factures/{id}/pdf           PDF archivé (émis) ou aperçu « BROUILLON »
#    POST  /factures/{id}/avoir         avoir (lignes ou montant, motif) — responsables
#    GET   /echantillons/{num}/factures bulletins et avoirs d'un échantillon
# ------------------------------------------------------------------
class FactureIn(BaseModel):
    echantillons: list[str] = Field(min_length=1, max_length=200)
    client_nom: str | None = Field(None, max_length=255)
    client_adresse: str | None = Field(None, max_length=1000)


class FactureModif(BaseModel):
    echantillons: list[str] | None = Field(None, min_length=1, max_length=200)
    client_nom: str | None = Field(None, max_length=255)
    client_adresse: str | None = Field(None, max_length=1000)


class AvoirIn(BaseModel):
    motif: str = Field(min_length=1, max_length=1000)
    details: list[int] | None = None
    montant: Decimal | None = Field(None, gt=0, le=10_000_000, max_digits=12, decimal_places=2)


def _resume(f: dict) -> dict:
    return {k: f[k] for k in ("id", "numero", "type", "statut", "client_nom", "total_ht", "montant_tva", "total_ttc",
                              "date_emission", "cree_par", "cree_le", "emise_par", "facture_origine_id", "motif",
                              "sha256") if k in f}


@router.get("/factures")
async def liste_factures(statut: str | None = Query(None, pattern="^(brouillon|émis|annulé)$"),
                         type_: str | None = Query(None, alias="type", pattern="^(facture|avoir)$"),
                         paiement: str | None = Query(None, pattern="^(" + "|".join(bulletins.STATUTS_PAIEMENT) + ")$"),
                         section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                         client: str | None = None, q: str | None = None,
                         du: date | None = None, au: date | None = None,
                         page: int = Query(1, ge=1), taille: int = Query(50, ge=1, le=500),
                         user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Bulletins et avoirs, avec leur statut de paiement ; période sur la date d'émission (création pour un brouillon)."""
    exiger_global(user)
    filtre_section = ""
    if section:   # colonne choisie dans une liste fermée, jamais une valeur saisie
        filtre_section = f"""AND EXISTS (SELECT 1 FROM factures_echantillons fe JOIN echantillons e
                                ON e."N° Echantillon" = fe.num_echantillon
                                WHERE fe.facture_id = l.id AND e.{paiements.COLONNE_SECTION[section]} = 'Yes')"""
    where = f"""WHERE (CAST(:st AS TEXT) IS NULL OR l.statut = :st) AND (CAST(:ty AS TEXT) IS NULL OR l.type = :ty)
          AND (CAST(:pa AS TEXT) IS NULL OR l.statut_paiement = :pa)
          AND (CAST(:cl AS TEXT) IS NULL OR l.client_nom ILIKE '%' || :cl || '%')
          AND (CAST(:q AS TEXT) IS NULL OR l.numero ILIKE '%' || :q || '%' OR l.echantillons ILIKE '%' || :q || '%')
          AND (CAST(:du AS DATE) IS NULL OR coalesce(l.date_emission, l.cree_le::date) >= :du)
          AND (CAST(:au AS DATE) IS NULL OR coalesce(l.date_emission, l.cree_le::date) <= :au)
          {filtre_section}"""
    p = {"st": statut, "ty": type_, "pa": paiement, "cl": client, "q": q, "du": du, "au": au}
    base = f"FROM ({paiements.SQL_BULLETINS}) l {where}"
    r = await db.execute(text(f"SELECT count(*) AS n, coalesce(sum(l.reste), 0) AS reste {base}"), p)
    agg = r.mappings().one()
    r = await db.execute(text(f"""
        SELECT l.* {base}
        ORDER BY coalesce(l.emise_le, l.cree_le) DESC, l.id DESC
        LIMIT :lim OFFSET :off
    """), {**p, "lim": taille, "off": (page - 1) * taille})
    return {"lignes": [dict(x) for x in r.mappings().all()], "total": agg["n"], "reste_total": agg["reste"],
            "page": page, "taille": taille}


@router.get("/impayes")
async def impayes(au: date | None = None, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Reste dû par client et par ancienneté (0-30, 31-60, 61-90, plus de 90 jours depuis l'émission)."""
    exiger_global(user)
    return await paiements.impayes_par_client(db, au)


@router.get("/caisse")
async def caisse(du: date | None = None, au: date | None = None, user: dict = Depends(current_user),
                 db: AsyncSession = Depends(get_db)):
    """Journal de caisse : encaissements valides de la période (aujourd'hui par défaut), totaux par mode."""
    exiger_global(user)
    du = du or date.today()
    au = au or du
    if au < du:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fin de la période précède son début.")
    return await paiements.journal_caisse(db, du, au)


@router.get("/caisse/export")
async def caisse_export(du: date | None = None, au: date | None = None,
                        format_: str = Query("xlsx", alias="format", pattern="^(xlsx|pdf)$"),
                        user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    j = await caisse(du, au, user, db)
    agent = user["username"]
    if format_ == "pdf":
        contenu, media = exports_facturation.pdf_caisse(j, agent), "application/pdf"
    else:
        contenu = exports_facturation.excel_caisse(j, agent)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    db.add(AuditLog(utilisateur=agent, action="EXPORT_CAISSE", table_cible="paiements", cle=f"{j['du']}..{j['au']}",
                    details=f"{format_} : {j['nb']} encaissement(s), {j['total']}"))
    await db.commit()
    nom = f"journal-caisse-{j['du']}" + (f"-{j['au']}" if j["au"] != j["du"] else "") + f".{format_}"
    return Response(contenu, media_type=media, headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.post("/factures", status_code=status.HTTP_201_CREATED)
async def creer_facture(p: FactureIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    fid = await bulletins.creer_brouillon(db, p.echantillons, user["username"], p.client_nom, p.client_adresse)
    db.add(AuditLog(utilisateur=user["username"], action="CREATE", table_cible="factures", cle=str(fid),
                    details="brouillon : " + ", ".join(p.echantillons)))
    await db.commit()
    return await bulletins.contenu(db, fid)


@router.get("/factures/{fid}")
async def detail_facture(fid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_global(user)
    return await bulletins.contenu(db, fid)


@router.patch("/factures/{fid}")
async def modifier_facture(fid: int, p: FactureModif, user: dict = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    await bulletins.modifier_brouillon(db, fid, p.echantillons, p.client_nom, p.client_adresse)
    db.add(AuditLog(utilisateur=user["username"], action="UPDATE", table_cible="factures", cle=str(fid)))
    await db.commit()
    return await bulletins.contenu(db, fid)


@router.post("/factures/{fid}/emettre")
async def emettre_facture(fid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    c = await bulletins.emettre(db, fid, user["username"])
    await paiements.recalculer_echantillons(db, c["echantillons"])
    c = await bulletins.contenu(db, fid)
    db.add(AuditLog(utilisateur=user["username"], action="EMETTRE", table_cible="factures", cle=str(fid),
                    details=f"{c['numero']} : {c['total_ttc']}"))
    await db.commit()
    return c


@router.post("/factures/{fid}/annuler")
async def annuler_facture(fid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    await bulletins.annuler_brouillon(db, fid, user["username"])
    db.add(AuditLog(utilisateur=user["username"], action="ANNULER", table_cible="factures", cle=str(fid)))
    await db.commit()
    return await bulletins.contenu(db, fid)


@router.get("/factures/{fid}/pdf")
async def pdf_facture(fid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """PDF archivé, octet pour octet, pour un bulletin ou un avoir émis ; aperçu non archivé pour un brouillon."""
    exiger_global(user)
    f = await bulletins.facture(db, fid)
    if f["statut"] == "émis":
        pdf, sha = await bulletins.pdf_archive(db, fid)
        nom = f["numero"]
    else:
        pdf = await bulletins.generer_pdf(db, await bulletins.contenu(db, fid))
        sha, nom = "", f"brouillon-{fid}"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nom}.pdf"', "X-Facture-SHA256": sha})


@router.post("/factures/{fid}/avoir", status_code=status.HTTP_201_CREATED)
async def avoir(fid: int, p: AvoirIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Les avoirs sont réservés aux responsables et à l'admin.")
    c = await bulletins.creer_avoir(db, fid, p.motif, user["username"], p.details, p.montant)
    await paiements.recalculer_echantillons(db, c["echantillons"])
    db.add(AuditLog(utilisateur=user["username"], action="AVOIR", table_cible="factures", cle=str(fid),
                    details=f"{c['numero']} : {c['total_ttc']} — {p.motif.strip()}"))
    await db.commit()
    return c


@router.get("/echantillons/{num}/factures")
async def factures_echantillon(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_global(user)
    r = await db.execute(text("""
        SELECT f.id FROM factures f JOIN factures_echantillons fe ON fe.facture_id = f.id
        WHERE fe.num_echantillon = :n AND f.statut <> 'annulé' ORDER BY f.id
    """), {"n": num})
    out = []
    for (fid,) in r.all():
        c = await bulletins.contenu(db, fid)
        out.append(_resume(c) | {"net": c["net"]})
    return out


# ------------------------------------------------------------------
#  Encaissements, quittances, exonérations (tâche 37)
#    POST /factures/{id}/paiements        encaissement (trop-perçu sur confirmation) — accueil, admin
#    POST /paiements/{id}/annuler         annulation avec motif — responsables
#    GET  /paiements/{id}/quittance       reçu PDF archivé
#    POST /factures/{id}/exonerer         exonération d'un bulletin — responsables
#    POST /echantillons/{num}/exonerer    exonération d'un échantillon — responsables
#    POST /exonerations/{id}/annuler      annulation avec motif — responsables
# ------------------------------------------------------------------
def exiger_responsable(user: dict, quoi: str):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{quoi} : réservé aux responsables et à l'admin.")


class PaiementIn(BaseModel):
    date_paiement: date
    montant: Decimal = Field(gt=0, le=10_000_000, max_digits=12, decimal_places=2)
    mode: str = Field(pattern="^(" + "|".join(paiements.MODES) + ")$")
    reference: str | None = Field(None, max_length=120)
    banque: str | None = Field(None, max_length=120)
    numero_quittance: str | None = Field(None, max_length=40)
    observation: str | None = Field(None, max_length=1000)
    confirmer_trop_percu: bool = False


class MotifIn(BaseModel):
    motif: str = Field(min_length=1, max_length=1000)


class ExonerationIn(BaseModel):
    type: str = Field(pattern="^(" + "|".join(paiements.TYPES_EXONERATION) + ")$")
    motif: str = Field(min_length=1, max_length=1000)


@router.post("/factures/{fid}/paiements", status_code=status.HTTP_201_CREATED)
async def encaisser(fid: int, p: PaiementIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_facturation(user)
    c = await paiements.encaisser(db, fid, user["username"], p.date_paiement, p.montant, p.mode, p.reference,
                                  p.banque, p.numero_quittance, p.observation, p.confirmer_trop_percu)
    db.add(AuditLog(utilisateur=user["username"], action="ENCAISSEMENT", table_cible="paiements",
                    cle=str(c["paiement_id"]), details=f"{c['numero']} : {p.montant} ({p.mode}), quittance "
                                                       f"{c['numero_quittance']}"))
    await db.commit()
    return c


@router.post("/paiements/{pid}/annuler")
async def annuler_paiement(pid: int, p: MotifIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_responsable(user, "Annuler un encaissement")
    c = await paiements.annuler_paiement(db, pid, p.motif, user["username"])
    db.add(AuditLog(utilisateur=user["username"], action="ANNULER_ENCAISSEMENT", table_cible="paiements",
                    cle=str(pid), details=p.motif.strip()))
    await db.commit()
    return c


@router.get("/paiements/{pid}/quittance")
async def quittance(pid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    exiger_global(user)
    pdf, sha, numero = await paiements.quittance_pdf(db, pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="quittance-{numero}.pdf"', "X-Quittance-SHA256": sha})


@router.post("/factures/{fid}/exonerer")
async def exonerer_facture(fid: int, p: ExonerationIn, user: dict = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    exiger_responsable(user, "Exonération")
    c = await paiements.exonerer_facture(db, fid, p.type, p.motif, user["username"])
    db.add(AuditLog(utilisateur=user["username"], action="EXONERATION", table_cible="factures", cle=str(fid),
                    details=f"{p.type} — {p.motif.strip()}"))
    await db.commit()
    return c


@router.post("/echantillons/{num}/exonerer")
async def exonerer_echantillon(num: str, p: ExonerationIn, user: dict = Depends(current_user),
                               db: AsyncSession = Depends(get_db)):
    exiger_responsable(user, "Exonération")
    await _echantillon(db, num)
    await paiements.exonerer_echantillon(db, num, p.type, p.motif, user["username"])
    db.add(AuditLog(utilisateur=user["username"], action="EXONERATION", table_cible="echantillons", cle=num,
                    details=f"{p.type} — {p.motif.strip()}"))
    await db.commit()
    return await facturation_echantillon(db, num)


@router.post("/exonerations/{eid}/annuler")
async def annuler_exoneration(eid: int, p: MotifIn, user: dict = Depends(current_user),
                              db: AsyncSession = Depends(get_db)):
    exiger_responsable(user, "Annuler une exonération")
    e = await paiements.annuler_exoneration(db, eid, p.motif, user["username"])
    db.add(AuditLog(utilisateur=user["username"], action="ANNULER_EXONERATION", table_cible="exonerations",
                    cle=str(eid), details=p.motif.strip()))
    await db.commit()
    if e["facture_id"]:
        return await bulletins.contenu(db, e["facture_id"])
    return await facturation_echantillon(db, e["num_echantillon"])
