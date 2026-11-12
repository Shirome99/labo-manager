"""
Contrôles qualité internes (tâche 18).

Lecture : tout utilisateur connecté (un rôle de section ne voit que sa section).
Séries (création / modification) : responsables. Mesures : responsables et analystes
de la section de la série (pas le rôle user).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLE_SECTION, ROLES_RESPONSABLES, current_user
from app.models import AuditLog
from app.services.controles_qualite import analyser

router = APIRouter(prefix="/api/cq", tags=["controles-qualite"])

TYPES = "^(Témoin positif|Témoin négatif|Blanc|Duplicata|Matériau de référence)$"


class SerieIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=150)
    section: str = Field(pattern="^(SMA|SCHA|SSA)$")
    methode: str = Field(min_length=1, max_length=150)
    type_controle: str = Field(pattern=TYPES)
    nature: str = Field("quantitatif", pattern="^(quantitatif|qualitatif)$")
    unite: str | None = None
    moyenne_ref: float | None = None
    ecart_type_ref: float | None = Field(None, gt=0)
    resultat_attendu: str | None = None
    actif: bool = True


class MesureIn(BaseModel):
    date_mesure: date
    valeur: float | None = None
    resultat: str | None = None
    commentaire: str | None = None

    @model_validator(mode="after")
    def _une_valeur(self):
        if self.valeur is None and not (self.resultat or "").strip():
            raise ValueError("Saisissez une valeur ou un résultat.")
        return self


def _verifier_section(user: dict, section: str):
    s = ROLE_SECTION.get(user["role"])
    if s and s != section:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Serie introuvable.")


async def _serie(db, serie_id: int, user: dict) -> dict:
    r = await db.execute(text("SELECT * FROM cq_series WHERE id = :id"), {"id": serie_id})
    s = r.mappings().first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Serie introuvable.")
    _verifier_section(user, s["section"])
    return dict(s)


async def _mesures(db, serie_id: int) -> list[dict]:
    r = await db.execute(text("""
        SELECT id, date_mesure, valeur, resultat, commentaire, saisi_par FROM cq_mesures
        WHERE serie_id = :id ORDER BY date_mesure, id"""), {"id": serie_id})
    return [{**dict(x), "valeur": float(x["valeur"]) if x["valeur"] is not None else None} for x in r.mappings().all()]


async def series_avec_analyse(db, user: dict, section: str | None = None) -> list[dict]:
    s_user = ROLE_SECTION.get(user["role"])
    r = await db.execute(text("""
        SELECT * FROM cq_series
        WHERE (CAST(:su AS VARCHAR) IS NULL OR section = :su) AND (CAST(:s AS VARCHAR) IS NULL OR section = :s)
        ORDER BY section, methode, libelle"""), {"su": s_user, "s": section})
    sortie = []
    for s in r.mappings().all():
        s = dict(s)
        mesures = await _mesures(db, s["id"])
        a = analyser(s, mesures)
        sortie.append({**_propre(s), "n_mesures": len(mesures),
                       "derniere_mesure": mesures[-1]["date_mesure"] if mesures else None,
                       "nb_alertes": len(a["alertes"]), "alerte_active": a["alerte_active"],
                       "derniere_alerte": a["alertes"][-1] if a["alertes"] else None})
    return sortie


def _propre(s: dict) -> dict:
    return {**s, "moyenne_ref": float(s["moyenne_ref"]) if s["moyenne_ref"] is not None else None,
            "ecart_type_ref": float(s["ecart_type_ref"]) if s["ecart_type_ref"] is not None else None}


@router.get("/series")
async def liste(section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await series_avec_analyse(db, user, section)


@router.post("/series", status_code=status.HTTP_201_CREATED)
async def creer_serie(p: SerieIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux responsables.")
    existe = await db.execute(text(
        "SELECT 1 FROM cq_series WHERE section = :section AND methode = :methode AND libelle = :libelle"),
        {"section": p.section, "methode": p.methode.strip(), "libelle": p.libelle.strip()})
    if existe.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette serie existe deja pour cette methode.")
    r = await db.execute(text("""
        INSERT INTO cq_series (libelle, section, methode, type_controle, nature, unite, moyenne_ref,
                               ecart_type_ref, resultat_attendu, actif)
        VALUES (:libelle, :section, :methode, :type_controle, :nature, :unite, :moyenne_ref,
                :ecart_type_ref, :resultat_attendu, :actif) RETURNING id"""),
        {**p.model_dump(), "libelle": p.libelle.strip(), "methode": p.methode.strip()})
    sid = r.scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="CREATE", table_cible="cq_series", cle=str(sid),
                    details=f"{p.section} / {p.methode} / {p.libelle}"))
    await db.commit()
    return await detail(sid, user, db)


@router.patch("/series/{serie_id}")
async def modifier_serie(serie_id: int, p: SerieIn, user: dict = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux responsables.")
    await _serie(db, serie_id, user)
    await db.execute(text("""
        UPDATE cq_series SET libelle = :libelle, section = :section, methode = :methode, type_controle = :type_controle,
            nature = :nature, unite = :unite, moyenne_ref = :moyenne_ref, ecart_type_ref = :ecart_type_ref,
            resultat_attendu = :resultat_attendu, actif = :actif WHERE id = :id"""),
        {**p.model_dump(), "libelle": p.libelle.strip(), "methode": p.methode.strip(), "id": serie_id})
    db.add(AuditLog(utilisateur=user["username"], action="UPDATE", table_cible="cq_series", cle=str(serie_id)))
    await db.commit()
    return await detail(serie_id, user, db)


@router.get("/series/{serie_id}")
async def detail(serie_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    s = await _serie(db, serie_id, user)
    return {"serie": _propre(s), **analyser(s, await _mesures(db, serie_id))}


@router.post("/series/{serie_id}/mesures", status_code=status.HTTP_201_CREATED)
async def ajouter_mesure(serie_id: int, p: MesureIn, user: dict = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    s = await _serie(db, serie_id, user)
    if user["role"] == "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Lecture seule pour ce role.")
    if not s["actif"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Serie inactive.")
    if p.date_mesure > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date de mesure ne peut pas etre dans le futur.")
    if s["nature"] == "quantitatif" and p.valeur is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Valeur numerique obligatoire pour une serie quantitative.")
    if s["nature"] == "qualitatif" and not (p.resultat or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Resultat obligatoire pour une serie qualitative.")
    r = await db.execute(text("""
        INSERT INTO cq_mesures (serie_id, date_mesure, valeur, resultat, commentaire, saisi_par)
        VALUES (:sid, :d, :v, :res, :com, :par) RETURNING id"""),
        {"sid": serie_id, "d": p.date_mesure, "v": p.valeur, "res": (p.resultat or "").strip() or None,
         "com": (p.commentaire or "").strip() or None, "par": user["username"]})
    mid = r.scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="MESURE_CQ", table_cible="cq_mesures", cle=str(mid),
                    details=f"serie {serie_id} : {p.valeur if p.valeur is not None else p.resultat}"))
    await db.commit()
    d = await detail(serie_id, user, db)
    derniere = next((x for x in d["points"] if x["id"] == mid), None)
    return {**d, "mesure_id": mid, "alerte_mesure": derniere["regles"] if derniere else []}
