"""
Habilitations du personnel (tâche 19) : matrice « utilisateur × analyse ».

Lecture : responsables / admin voient tout ; les autres voient leurs propres habilitations.
Écriture : responsables / admin.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLES_RESPONSABLES, current_user
from app.models import AuditLog
from app.services.habilitations import etat

router = APIRouter(prefix="/api/habilitations", tags=["habilitations"])


class HabilitationIn(BaseModel):
    user_id: int
    nom_analyse: str = Field(min_length=1, max_length=150)
    section: str = Field(pattern="^(SMA|SCHA|SSA)$")
    date_qualification: date
    date_echeance: date | None = None
    observations: str | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.date_echeance and self.date_echeance < self.date_qualification:
            raise ValueError("L'échéance doit suivre la date de qualification.")
        return self


def _exiger_responsable(user):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux responsables.")


async def habilitations(db, user: dict, user_id: int | None = None, section: str | None = None) -> list[dict]:
    if user["role"] not in ROLES_RESPONSABLES:
        user_id = user["id"]          # chacun ne voit que les siennes
    r = await db.execute(text("""
        SELECT h.id, h.user_id, u.nom AS utilisateur, u.role, h.nom_analyse, h.section,
               h.date_qualification, h.date_echeance, h.habilite_par, h.observations
        FROM habilitations h JOIN users u ON u.id = h.user_id
        WHERE (CAST(:u AS INTEGER) IS NULL OR h.user_id = :u) AND (CAST(:s AS VARCHAR) IS NULL OR h.section = :s)
        ORDER BY u.nom, h.section, h.nom_analyse"""), {"u": user_id, "s": section})
    return [{**dict(x), "etat": etat(dict(x))} for x in r.mappings().all()]


@router.get("")
async def liste(user_id: int | None = None, section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await habilitations(db, user, user_id, section)


@router.get("/utilisateurs")
async def utilisateurs(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Comptes habilitables (liste de choix de l'écran, sans passer par /api/admin/users réservé à l'admin)."""
    _exiger_responsable(user)
    r = await db.execute(text("SELECT id, nom, role FROM users ORDER BY nom"))
    return [dict(x) for x in r.mappings().all()]


async def _verifier(db, p: HabilitationIn, sauf_id: int | None = None):
    if not (await db.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": p.user_id})).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Utilisateur inconnu.")
    doublon = await db.execute(text("""
        SELECT 1 FROM habilitations WHERE user_id = :u AND section = :s
          AND lower(btrim(nom_analyse)) = lower(btrim(:a)) AND (CAST(:id AS INTEGER) IS NULL OR id <> :id)"""),
        {"u": p.user_id, "s": p.section, "a": p.nom_analyse, "id": sauf_id})
    if doublon.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet utilisateur a deja une habilitation pour cette analyse.")


@router.post("", status_code=status.HTTP_201_CREATED)
async def creer(p: HabilitationIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    _exiger_responsable(user)
    await _verifier(db, p)
    r = await db.execute(text("""
        INSERT INTO habilitations (user_id, nom_analyse, section, date_qualification, date_echeance, habilite_par, observations)
        VALUES (:u, :a, :s, :dq, :de, :par, :obs) RETURNING id"""),
        {"u": p.user_id, "a": p.nom_analyse.strip(), "s": p.section, "dq": p.date_qualification,
         "de": p.date_echeance, "par": user["username"], "obs": (p.observations or "").strip() or None})
    hid = r.scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="HABILITATION", table_cible="habilitations", cle=str(hid),
                    details=f"user {p.user_id} : {p.nom_analyse.strip()} ({p.section})"))
    await db.commit()
    return {"id": hid}


@router.patch("/{hid}")
async def modifier(hid: int, p: HabilitationIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    _exiger_responsable(user)
    await _verifier(db, p, hid)
    r = await db.execute(text("""
        UPDATE habilitations SET user_id = :u, nom_analyse = :a, section = :s, date_qualification = :dq,
               date_echeance = :de, observations = :obs WHERE id = :id RETURNING id"""),
        {"u": p.user_id, "a": p.nom_analyse.strip(), "s": p.section, "dq": p.date_qualification,
         "de": p.date_echeance, "obs": (p.observations or "").strip() or None, "id": hid})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Habilitation introuvable.")
    db.add(AuditLog(utilisateur=user["username"], action="HABILITATION", table_cible="habilitations", cle=str(hid),
                    details="modifiee"))
    await db.commit()
    return {"id": hid}


@router.delete("/{hid}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer(hid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    _exiger_responsable(user)
    r = await db.execute(text("DELETE FROM habilitations WHERE id = :id RETURNING id"), {"id": hid})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Habilitation introuvable.")
    db.add(AuditLog(utilisateur=user["username"], action="HABILITATION", table_cible="habilitations", cle=str(hid),
                    details="retiree"))
    await db.commit()
