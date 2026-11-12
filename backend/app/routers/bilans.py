"""
Bilan mensuel (tâche 24) : génération PDF / Excel archivée, historique, modèle paramétrable.

Droits : tout utilisateur connecté peut générer un bilan ; un rôle de section ne peut le faire
que pour sa section (et ne voit que les bilans de sa section). Le modèle est modifiable par l'admin.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLE_SECTION, current_user, require_admin
from app.models import AuditLog
from app.services import bilan as service

router = APIRouter(prefix="/api/bilans", tags=["bilans"])
MEDIA = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class GenerationIn(BaseModel):
    mois: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    section: str | None = Field(None, pattern="^(SMA|SCHA|SSA)$")
    format: str = Field("pdf", pattern="^(pdf|xlsx)$")


class BlocIn(BaseModel):
    id: int | None = None
    type_bloc: str = Field(pattern="^(synthese|requete)$")
    titre: str = Field(min_length=1, max_length=150)
    requete_id: int | None = None
    actif: bool = True


def _section_autorisee(user: dict, section: str | None) -> str | None:
    rs = ROLE_SECTION.get(user["role"])
    if rs and section not in (None, rs):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Section non autorisée pour votre rôle.")
    return rs or section


@router.post("/generer")
async def generer(p: GenerationIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    section = _section_autorisee(user, p.section)
    r = await service.generer(db, service.lire_mois(p.mois), section, p.format, user)
    db.add(AuditLog(utilisateur=user["username"], action="BILAN_MENSUEL", table_cible="bilans_mensuels",
                    cle=str(r["id"]), details=f"{p.mois} {section or 'toutes'} {p.format} v{r['version']}"))
    await db.commit()
    return Response(r["contenu"], media_type=MEDIA[p.format], headers={
        "Content-Disposition": f'attachment; filename="{r["nom_fichier"]}"',
        "X-Bilan-Id": str(r["id"]), "X-Bilan-SHA256": r["sha256"], "X-Bilan-Version": str(r["version"])})


@router.post("/apercu")
async def apercu(p: GenerationIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Contenu calculé du bilan (sans fichier ni archive) : affichage et contrôle des chiffres."""
    section = _section_autorisee(user, p.section)
    return await service.calculer(db, service.lire_mois(p.mois), section, user)


@router.get("/historique")
async def historique(mois: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                     user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rs = ROLE_SECTION.get(user["role"])
    r = await db.execute(text("""
        SELECT id, to_char(mois, 'YYYY-MM') AS mois, section, format, version, taille, sha256, auteur, source, genere_le
        FROM bilans_mensuels
        WHERE (CAST(:m AS DATE) IS NULL OR mois = CAST(:m AS DATE))
          AND (CAST(:rs AS VARCHAR) IS NULL OR section = :rs)
        ORDER BY mois DESC, coalesce(section, ''), format, version DESC"""),
        {"m": service.lire_mois(mois) if mois else None, "rs": rs})
    return [{**dict(x), "genere_le": x.genere_le.isoformat()} for x in r.mappings().all()]


@router.get("/fichier/{bid}")
async def fichier(bid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(text("""SELECT to_char(mois, 'YYYY-MM') AS mois, section, format, version, pdf
        FROM bilans_mensuels WHERE id = :id"""), {"id": bid})).mappings().first()
    rs = ROLE_SECTION.get(user["role"])
    if r is None or (rs and r["section"] != rs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilan introuvable.")
    nom = f"bilan_{r['mois']}_{r['section'] or 'toutes'}_v{r['version']}.{r['format']}"
    return Response(bytes(r["pdf"]), media_type=MEDIA[r["format"]],
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.get("/modele")
async def lire_modele(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await service.modele(db)


@router.put("/modele")
async def enregistrer_modele(blocs: list[BlocIn] = Body(...), user: dict = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    """Remplace la composition : blocs dans l'ordre de la liste (mise à jour, ajout, retrait)."""
    if sum(1 for b in blocs if b.type_bloc == "synthese") > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La synthèse ne peut figurer qu'une fois.")
    for b in blocs:
        if (b.type_bloc == "requete") != (b.requete_id is not None):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"« {b.titre} » : choisissez une requête enregistrée.")
        if b.requete_id is not None:
            q = (await db.execute(text("SELECT visibilite FROM requetes_enregistrees WHERE id = :id"),
                                  {"id": b.requete_id})).first()
            if q is None or q[0] != "partagée":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"« {b.titre} » : la requête doit exister et être partagée.")
    existants = {x["id"] for x in await service.modele(db)}
    gardes = {b.id for b in blocs if b.id}
    if gardes - existants:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bloc inconnu.")
    for bid in existants - gardes:
        await db.execute(text("DELETE FROM bilan_modele WHERE id = :id"), {"id": bid})
    for i, b in enumerate(blocs, 1):
        params = {"o": i, "t": b.type_bloc, "ti": b.titre.strip(), "r": b.requete_id, "a": b.actif, "id": b.id}
        if b.id:
            await db.execute(text("""UPDATE bilan_modele SET ordre = :o, type_bloc = :t, titre = :ti, requete_id = :r,
                                     actif = :a WHERE id = :id"""), params)
        else:
            await db.execute(text("""INSERT INTO bilan_modele (ordre, type_bloc, titre, requete_id, actif)
                                     VALUES (:o, :t, :ti, :r, :a)"""), params)
    db.add(AuditLog(utilisateur=user["username"], action="BILAN_MODELE", table_cible="bilan_modele",
                    cle=None, details=f"{len(blocs)} bloc(s)"))
    await db.commit()
    return await service.modele(db)
