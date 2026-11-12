import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.jeton import creer_jeton, jeton_requete, lire_jeton
from app.core.security import (
    current_user, exiger_mot_de_passe_conforme, hash_password, verify_password,
)
from app.models import AuditLog, User
from app.schemas import ConnexionOut, LoginIn, MotDePasseChange, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _tracer_connexion(db: AsyncSession, nom: str) -> None:
    """Les écritures faites pendant la connexion sont attribuées à ce nom dans audit_donnees."""
    await db.execute(text("SELECT set_config('lims.utilisateur', :u, true)"),
                     {"u": f"connexion:{nom}"[:100]})


def _heure(d: datetime) -> str:
    return d.astimezone().strftime("%H:%M")


@router.post("/login", response_model=ConnexionOut)
async def login(payload: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    # La colonne reelle est `nom` (pas `username`)
    res = await db.execute(select(User).where(User.nom == payload.username))
    user = res.scalar_one_or_none()
    maintenant = datetime.now(timezone.utc)
    await _tracer_connexion(db, payload.username)

    if not user:
        db.add(AuditLog(utilisateur=payload.username[:100], action="ECHEC_CONNEXION",
                        table_cible="users", cle=payload.username[:100], details="compte inconnu"))
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")

    # Compte verrouillé : refusé, même avec le bon mot de passe
    if user.verrouille_jusqu and user.verrouille_jusqu > maintenant:
        db.add(AuditLog(utilisateur=user.nom, action="ECHEC_CONNEXION", table_cible="users",
                        cle=user.nom, details="compte verrouillé"))
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Compte verrouillé jusqu'à {_heure(user.verrouille_jusqu)} "
                            "après plusieurs échecs de connexion.")

    if not verify_password(payload.password, user.password):
        user.echecs_connexion = (user.echecs_connexion or 0) + 1
        details = f"mot de passe incorrect ({user.echecs_connexion}/{settings.VERROU_ECHECS})"
        db.add(AuditLog(utilisateur=user.nom, action="ECHEC_CONNEXION", table_cible="users",
                        cle=user.nom, details=details))
        if user.echecs_connexion >= settings.VERROU_ECHECS:
            user.verrouille_jusqu = maintenant + timedelta(minutes=settings.VERROU_MINUTES)
            user.echecs_connexion = 0
            db.add(AuditLog(utilisateur=user.nom, action="VERROUILLAGE", table_cible="users",
                            cle=user.nom, details=f"verrouillé {settings.VERROU_MINUTES} min "
                                                  f"après {settings.VERROU_ECHECS} échecs"))
            await db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Compte verrouillé jusqu'à {_heure(user.verrouille_jusqu)} "
                                "après plusieurs échecs de connexion.")
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")

    # Succès : le compteur repart à zéro
    if user.echecs_connexion or user.verrouille_jusqu:
        user.echecs_connexion = 0
        user.verrouille_jusqu = None
        await db.commit()

    request.session["user"] = {
        "id": user.id,
        "username": user.nom,
        "role": user.role,
    }
    request.session["activite"] = time.time()
    # Jeton pour un front servi sur un autre site (démonstration en ligne) ; ignoré en local
    return ConnexionOut(id=user.id, username=user.nom, role=user.role,
                        jeton=creer_jeton(request.session["user"]), jeton_duree=settings.duree_jeton_min * 60)


@router.post("/renouveler", response_model=ConnexionOut)
async def renouveler(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Nouveau jeton pendant l'activité (le front l'appelle avant l'expiration). Le compte est relu :
    supprimé → 401, verrouillé → 403, rôle mis à jour. La date de connexion est conservée
    (durée maximale SESSION_MAX_AGE).
    """
    d = lire_jeton(jeton_requete(request) or "")
    if not d:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée. Reconnectez-vous.")
    compte = await db.get(User, d["id"])
    if not compte or compte.nom != d["username"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée. Reconnectez-vous.")
    if compte.verrouille_jusqu and compte.verrouille_jusqu > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Compte verrouillé jusqu'à {_heure(compte.verrouille_jusqu)}.")
    user = {"id": compte.id, "username": compte.nom, "role": compte.role}
    return ConnexionOut(**user, jeton=creer_jeton(user, debut=d["debut"]),
                        jeton_duree=settings.duree_jeton_min * 60)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    request.session.clear()


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return UserOut(**user)


@router.post("/mot-de-passe", status_code=status.HTTP_204_NO_CONTENT)
async def changer_mot_de_passe(payload: MotDePasseChange, user: dict = Depends(current_user),
                               db: AsyncSession = Depends(get_db)):
    """Chaque utilisateur peut changer son propre mot de passe (mot de passe actuel exigé)."""
    compte = await db.get(User, user["id"])
    if not compte or not verify_password(payload.actuel, compte.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect.")
    exiger_mot_de_passe_conforme(payload.nouveau)
    if payload.nouveau == payload.actuel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Le nouveau mot de passe doit être différent de l'actuel.")
    compte.password = hash_password(payload.nouveau)
    db.add(AuditLog(utilisateur=user["username"], action="MOT_DE_PASSE", table_cible="users",
                    cle=compte.nom, details="changé par l'utilisateur"))
    await db.commit()
