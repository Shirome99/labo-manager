"""
Équipements et étalonnage (tâche 17).

Lecture : tout utilisateur connecté (un rôle de section voit sa section et les équipements communs).
Création / modification : responsables (admin, responsable). Suppression : admin, seulement
si l'équipement n'a ni historique ni utilisation (sinon : le désactiver).
Événements (étalonnage, vérification, maintenance, panne, réparation) : responsables et
analystes de la section de l'équipement. Un étalonnage / une vérification conforme met à jour
la date correspondante de l'équipement si elle est plus récente.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLE_SECTION, ROLES_RESPONSABLES, current_user
from app.models import AuditLog
from app.services.equipements import etat_echeances

router = APIRouter(prefix="/api/equipements", tags=["equipements"])

COLONNES = """id, code, designation, numero_serie, section, emplacement, date_dernier_etalonnage,
              periodicite_etalonnage_mois, date_derniere_verification, periodicite_verification_mois,
              actif, observations"""


class EquipementIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    designation: str = Field(min_length=1, max_length=200)
    numero_serie: str | None = None
    section: str | None = Field(None, pattern="^(SMA|SCHA|SSA)$")
    emplacement: str | None = None
    date_dernier_etalonnage: date | None = None
    periodicite_etalonnage_mois: int | None = Field(None, ge=1, le=240)
    date_derniere_verification: date | None = None
    periodicite_verification_mois: int | None = Field(None, ge=1, le=240)
    actif: bool = True
    observations: str | None = None


class EvenementIn(BaseModel):
    type_evenement: str = Field(pattern="^(Étalonnage|Vérification|Maintenance|Panne|Réparation)$")
    date_evenement: date
    resultat: str | None = Field(None, pattern="^(Conforme|Non conforme)$")
    description: str | None = None


def _vide(v):
    return (str(v).strip() or None) if v is not None else None


def _avec_echeances(x) -> dict:
    d = dict(x)
    d.update(etat_echeances(d))
    return d


def _exiger_responsable(user: dict):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve aux responsables.")


def _filtre_section(user: dict) -> tuple[str, dict]:
    """Un rôle de section voit sa section et les équipements communs (section NULL)."""
    s = ROLE_SECTION.get(user["role"])
    return ("(section IS NULL OR section = :sec_user)", {"sec_user": s}) if s else ("TRUE", {})


async def _charger(db, eq_id: int, user: dict) -> dict:
    cond, p = _filtre_section(user)
    r = await db.execute(text(f"SELECT {COLONNES} FROM equipements WHERE id = :id AND {cond}"), {"id": eq_id, **p})
    x = r.mappings().first()
    if not x:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipement introuvable.")
    return dict(x)


@router.get("")
async def liste(section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"),
                actifs: bool = False,
                user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    cond, p = _filtre_section(user)
    if section:   # équipements de la section + communs (liste de choix d'une fiche)
        cond += " AND (section IS NULL OR section = :sec)"
        p["sec"] = section
    if actifs:
        cond += " AND actif"
    r = await db.execute(text(f"SELECT {COLONNES} FROM equipements WHERE {cond} ORDER BY code"), p)
    return [_avec_echeances(x) for x in r.mappings().all()]


@router.get("/alertes")
async def alertes(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Équipements actifs dont l'étalonnage ou la vérification est échu ou à moins de 30 jours."""
    return [e for e in await liste(None, True, user, db) if e["statut_echeance"] in ("échu", "proche")]


@router.post("", status_code=status.HTTP_201_CREATED)
async def creer(p: EquipementIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    _exiger_responsable(user)
    if (await db.execute(text("SELECT 1 FROM equipements WHERE code = :c"), {"c": p.code.strip()})).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce code d'equipement existe deja.")
    valeurs = {**p.model_dump(), "code": p.code.strip(), "designation": p.designation.strip(),
               "numero_serie": _vide(p.numero_serie), "emplacement": _vide(p.emplacement),
               "observations": _vide(p.observations)}
    r = await db.execute(text("""
        INSERT INTO equipements (code, designation, numero_serie, section, emplacement, date_dernier_etalonnage,
            periodicite_etalonnage_mois, date_derniere_verification, periodicite_verification_mois, actif, observations)
        VALUES (:code, :designation, :numero_serie, :section, :emplacement, :date_dernier_etalonnage,
            :periodicite_etalonnage_mois, :date_derniere_verification, :periodicite_verification_mois, :actif, :observations)
        RETURNING id"""), valeurs)
    eq_id = r.scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="CREATE", table_cible="equipements", cle=p.code.strip()))
    await db.commit()
    return await _charger_avec(db, eq_id, user)


async def _charger_avec(db, eq_id, user):
    return _avec_echeances(await _charger(db, eq_id, user))


@router.patch("/{eq_id}")
async def modifier(eq_id: int, p: EquipementIn, user: dict = Depends(current_user),
                   db: AsyncSession = Depends(get_db)):
    _exiger_responsable(user)
    actuel = await _charger(db, eq_id, user)
    if p.code.strip() != actuel["code"]:
        if (await db.execute(text("SELECT 1 FROM equipements WHERE code = :c"), {"c": p.code.strip()})).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Ce code d'equipement existe deja.")
    await db.execute(text("""
        UPDATE equipements SET code = :code, designation = :designation, numero_serie = :numero_serie,
            section = :section, emplacement = :emplacement, date_dernier_etalonnage = :date_dernier_etalonnage,
            periodicite_etalonnage_mois = :periodicite_etalonnage_mois,
            date_derniere_verification = :date_derniere_verification,
            periodicite_verification_mois = :periodicite_verification_mois, actif = :actif, observations = :observations
        WHERE id = :id"""),
        {**p.model_dump(), "code": p.code.strip(), "designation": p.designation.strip(),
         "numero_serie": _vide(p.numero_serie), "emplacement": _vide(p.emplacement),
         "observations": _vide(p.observations), "id": eq_id})
    db.add(AuditLog(utilisateur=user["username"], action="UPDATE", table_cible="equipements", cle=p.code.strip()))
    await db.commit()
    return await _charger_avec(db, eq_id, user)


@router.delete("/{eq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer(eq_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Suppression reservee a l'administrateur.")
    eq = await _charger(db, eq_id, user)
    n_ev = (await db.execute(text("SELECT count(*) FROM equipement_evenements WHERE equipement_id = :id"),
                             {"id": eq_id})).scalar_one()
    n_util = (await db.execute(text("""
        SELECT (SELECT count(*) FROM traitement_sma WHERE equipement_utilise = :c)
             + (SELECT count(*) FROM traitement_scha WHERE equipement_utilise = :c)
             + (SELECT count(*) FROM traitement_ssa WHERE equipement_utilise = :c)"""), {"c": eq["code"]})).scalar_one()
    if n_ev or n_util:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Equipement avec historique ou deja utilise : desactivez-le plutot que de le supprimer.")
    await db.execute(text("DELETE FROM equipements WHERE id = :id"), {"id": eq_id})
    db.add(AuditLog(utilisateur=user["username"], action="DELETE", table_cible="equipements", cle=eq["code"]))
    await db.commit()


@router.get("/{eq_id}/evenements")
async def evenements(eq_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _charger(db, eq_id, user)
    r = await db.execute(text("""
        SELECT id, type_evenement, date_evenement, resultat, description, saisi_par, cree_le
        FROM equipement_evenements WHERE equipement_id = :id ORDER BY date_evenement DESC, id DESC
    """), {"id": eq_id})
    return [dict(x) for x in r.mappings().all()]


@router.post("/{eq_id}/evenements", status_code=status.HTTP_201_CREATED)
async def ajouter_evenement(eq_id: int, p: EvenementIn, user: dict = Depends(current_user),
                            db: AsyncSession = Depends(get_db)):
    eq = await _charger(db, eq_id, user)   # un rôle de section n'atteint que sa section et les communs
    if user["role"] == "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Lecture seule pour ce role.")
    if p.date_evenement > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date de l'evenement ne peut pas etre dans le futur.")
    if p.type_evenement in ("Étalonnage", "Vérification") and not p.resultat:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indiquez le resultat (Conforme / Non conforme).")
    r = await db.execute(text("""
        INSERT INTO equipement_evenements (equipement_id, type_evenement, date_evenement, resultat, description, saisi_par)
        VALUES (:id, :type, :d, :res, :desc, :par) RETURNING id"""),
        {"id": eq_id, "type": p.type_evenement, "d": p.date_evenement, "res": p.resultat,
         "desc": _vide(p.description), "par": user["username"]})
    ev_id = r.scalar_one()
    # Étalonnage / vérification conforme : la date de l'équipement suit le plus récent
    colonne = {"Étalonnage": "date_dernier_etalonnage", "Vérification": "date_derniere_verification"}.get(p.type_evenement)
    if colonne and p.resultat == "Conforme" and (eq[colonne] is None or p.date_evenement > eq[colonne]):
        await db.execute(text(f"UPDATE equipements SET {colonne} = :d WHERE id = :id"),
                         {"d": p.date_evenement, "id": eq_id})
    db.add(AuditLog(utilisateur=user["username"], action="EVENEMENT", table_cible="equipements", cle=eq["code"],
                    details=f"{p.type_evenement} du {p.date_evenement:%d/%m/%Y}" + (f" : {p.resultat}" if p.resultat else "")))
    await db.commit()
    return {"id": ev_id, **(await _charger_avec(db, eq_id, user))}
