"""
Journal d'audit des données (table audit_donnees, alimentée par des triggers PostgreSQL).
Lecture seule, réservée à l'administrateur.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import require_admin

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])


@router.get("/tables")
async def tables(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Tables présentes dans le journal (pour le filtre)."""
    r = await db.execute(text("SELECT DISTINCT table_nom FROM audit_donnees ORDER BY 1"))
    return [x[0] for x in r.all()]


@router.get("")
async def journal(
    table: str | None = None,
    utilisateur: str | None = None,
    num: str | None = Query(None, description="N° d'échantillon (recherche partielle)"),
    operation: str | None = Query(None, pattern="^(INSERT|UPDATE|DELETE)$"),
    du: date | None = None,
    au: date | None = None,
    limite: int = Query(50, ge=1, le=500),
    decalage: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    conditions, params = [], {}
    if table:
        conditions.append("table_nom = :table")
        params["table"] = table
    if utilisateur:
        conditions.append("utilisateur ILIKE :utilisateur")
        params["utilisateur"] = f"%{utilisateur}%"
    if num:
        conditions.append("num_echantillon ILIKE :num")
        params["num"] = f"%{num}%"
    if operation:
        conditions.append("operation = :operation")
        params["operation"] = operation
    if du:
        conditions.append("horodatage >= :du")
        params["du"] = du
    if au:   # borne incluse : jusqu'à la fin de la journée
        conditions.append("horodatage < :au")
        params["au"] = au + timedelta(days=1)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total = (await db.execute(text(f"SELECT count(*) FROM audit_donnees {where}"), params)).scalar_one()
    r = await db.execute(text(f"""
        SELECT id, table_nom, operation, cle, num_echantillon, avant, apres,
               utilisateur, source, horodatage
        FROM audit_donnees {where}
        ORDER BY id DESC
        LIMIT :limite OFFSET :decalage
    """), {**params, "limite": limite, "decalage": decalage})
    return {"total": total, "lignes": [dict(x) for x in r.mappings().all()]}
