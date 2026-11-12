from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION, ROLES_GLOBAUX, ROLES_RESPONSABLES
from app.models import Echantillon, AuditLog, TRAITEMENT_MODELS
from app.routers.echantillons import refuser_si_refuse
from app.services.paiements import exiger_paiement
from app.services.equipements import contestation_fiche, date_analyse, equipement_par_code
from app.services.reactifs import codes as codes_lots, refus_lots
from app.schemas import (
    TraitementSMAIn, TraitementSCHAIn, TraitementSSAIn,
    TraitementSMAOut, TraitementSCHAOut, TraitementSSAOut,
)

router = APIRouter(prefix="/api/traitement", tags=["traitement"])

SECTION_ATTR = {"SMA": "sma", "SCHA": "scha", "SSA": "ssa"}
IN_SCHEMA = {"SMA": TraitementSMAIn, "SCHA": TraitementSCHAIn, "SSA": TraitementSSAIn}
OUT_SCHEMA = {"SMA": TraitementSMAOut, "SCHA": TraitementSCHAOut, "SSA": TraitementSSAOut}


def _check_role(user: dict, section: str):
    role = user["role"]
    if role in ROLES_GLOBAUX or ROLE_SECTION.get(role) == section:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        f"Votre role ne donne pas acces a la section {section}.")


async def _load(db: AsyncSession, section: str, num: str):
    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    if getattr(ech, SECTION_ATTR[section]) != "Yes":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Cet echantillon n'est pas assigne a la section {section}.")
    Model = TRAITEMENT_MODELS[section]
    res = await db.execute(select(Model).where(Model.num_echantillon == num))
    return ech, res.scalar_one_or_none()


@router.get("/{section}/{num}")
async def lire(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(user, section)
    ech, trt = await _load(db, section, num)
    out = OUT_SCHEMA[section]
    return {
        "echantillon": {
            "num_echantillon": ech.num_echantillon,
            "nature": ech.nature,
            "date_reception": ech.date_reception,
            "fabricant": ech.fabricant,
            "statut": ech.statut,
        },
        "traitement": out.model_validate(trt) if trt else None,
        # Équipement hors étalonnage / en panne à la date de l'analyse (tâche 17)
        "contestable": await contestation_fiche(db, section, trt),
    }


@router.post("/{section}")
async def upsert(
    payload: dict,
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_role(user, section)
    data = IN_SCHEMA[section](**payload)  # validation par section
    ech, trt = await _load(db, section, data.num_echantillon)
    refuser_si_refuse(ech)

    Model = TRAITEMENT_MODELS[section]
    values = data.model_dump()

    # Équipement utilisé : s'il change, il doit exister, être actif et appartenir à la section
    code = (values.get("equipement_utilise") or "").strip() or None
    values["equipement_utilise"] = code
    if code and code != (getattr(trt, "equipement_utilise", None) if trt else None):
        eq = await equipement_par_code(db, code)
        if not eq or not eq["actif"] or eq["section"] not in (None, section):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Equipement « {code} » inconnu, inactif ou d'une autre section.")

    # Lots de réactifs / milieux (tâche 20) : codes séparés par des virgules ; un lot nouvellement
    # choisi doit exister, être actif, de la section (ou commun) et non périmé à la date de l'analyse
    lots = codes_lots(values.get("lot_reactif"))
    values["lot_reactif"] = ", ".join(lots) or None
    if values["lot_reactif"] and len(values["lot_reactif"]) > 120:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trop de lots sur la fiche (120 caractères au plus).")
    anciens = set(codes_lots(getattr(trt, "lot_reactif", None) if trt else None))
    nouveaux = [c for c in lots if c not in anciens]
    if nouveaux:
        jour = values.get("date_mise_en_analyse") or await date_analyse(
            db, section, SimpleNamespace(num_echantillon=data.num_echantillon, date_mise_en_analyse=None))
        refus = await refus_lots(db, section, nouveaux, jour)
        if refus:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lot(s) refusé(s) : " + " ; ".join(refus) + ".")

    if trt is None:
        # Facturation (tâche 38) : paiement éventuellement exigé avant la mise en analyse
        await exiger_paiement(db, data.num_echantillon, "mise_en_analyse")
        trt = Model(**values, saisi_par=user["username"])
        db.add(trt)
        action = "CREATE"
    else:
        if trt.valide_par:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Fiche deja validee - modification interdite.")
        for k, v in values.items():
            setattr(trt, k, v)
        trt.saisi_par = user["username"]
        action = "UPDATE"

    if ech.statut in (None, "Reçu"):
        ech.statut = "En cours"

    db.add(AuditLog(utilisateur=user["username"], action=action,
                    table_cible=Model.__tablename__, cle=data.num_echantillon))
    await db.commit()
    await db.refresh(trt)
    return OUT_SCHEMA[section].model_validate(trt)


@router.post("/{section}/{num}/valider")
async def valider(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Seul un responsable peut valider une fiche.")
    ech, trt = await _load(db, section, num)
    if trt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune fiche a valider.")
    if ech.statut != "À valider":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "La fiche doit d'abord etre soumise a validation par l'analyste.")
    if trt.saisi_par == user["username"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Le double regard impose un valideur different du saisisseur.")

    trt.valide_par = user["username"]
    trt.date_validation = datetime.now(timezone.utc)
    ech.statut = "Validé"

    db.add(AuditLog(utilisateur=user["username"], action="VALIDATE",
                    table_cible=TRAITEMENT_MODELS[section].__tablename__, cle=num))
    await db.commit()
    await db.refresh(trt)
    return OUT_SCHEMA[section].model_validate(trt)


@router.post("/{section}/{num}/soumettre")
async def soumettre(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """L'analyste soumet sa fiche a la validation d'un responsable (-> "À valider")."""
    _check_role(user, section)
    ech, trt = await _load(db, section, num)
    refuser_si_refuse(ech)
    if trt is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Saisissez la fiche avant de la soumettre a validation.")
    if ech.statut in ("Validé", "Rapport émis"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "La fiche est deja validee.")
    ech.statut = "À valider"
    db.add(AuditLog(utilisateur=user["username"], action="SOUMETTRE",
                    table_cible=TRAITEMENT_MODELS[section].__tablename__, cle=num))
    await db.commit()
    await db.refresh(trt)
    return OUT_SCHEMA[section].model_validate(trt)


@router.post("/{section}/{num}/refuser")
async def refuser(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    payload: dict = Body(default={}),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Un responsable renvoie la fiche a l'analyste (-> "En cours"), avec motif optionnel."""
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Seul un responsable peut renvoyer une fiche.")
    ech, trt = await _load(db, section, num)
    if trt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune fiche a renvoyer.")
    if ech.statut != "À valider":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Seule une fiche soumise (À valider) peut etre renvoyee.")
    motif = (payload or {}).get("motif") or None
    trt.valide_par = None
    trt.date_validation = None
    ech.statut = "En cours"
    db.add(AuditLog(utilisateur=user["username"], action="REFUSER",
                    table_cible=TRAITEMENT_MODELS[section].__tablename__, cle=num,
                    details=motif))
    await db.commit()
    await db.refresh(trt)
    return OUT_SCHEMA[section].model_validate(trt)
