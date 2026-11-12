from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import require_admin, hash_password, exiger_mot_de_passe_conforme
from app.models import User, AuditLog
from app.schemas import MotDePasseReset, UserCreate, UserOut, RoleUpdate

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.nom, role=u.role, email=u.email,
                   verrouille_jusqu=u.verrouille_jusqu)


@router.get("", response_model=list[UserOut])
async def liste(admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).order_by(User.nom))
    return [_out(u) for u in res.scalars().all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def creer(payload: UserCreate, admin: dict = Depends(require_admin),
                db: AsyncSession = Depends(get_db)):
    exiger_mot_de_passe_conforme(payload.password)
    # email est NOT NULL en base : on genere une valeur par defaut si absente
    email = (payload.email or "").strip()
    if not email:
        base = payload.username.strip().lower().replace(" ", ".")
        email = f"{base}@lrarvy.local"

    # nom unique
    exists = await db.execute(select(User).where(User.nom == payload.username))
    if exists.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce nom d'utilisateur existe deja.")

    # email unique (souvent contraint en base)
    dup_email = await db.execute(select(User).where(User.email == email))
    if dup_email.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"L'email '{email}' est deja utilise. Renseignez un email different.")

    user = User(
        nom=payload.username,
        email=email,
        password=hash_password(payload.password),
        created_at=datetime.now(),
        role=payload.role,
    )
    db.add(user)
    db.add(AuditLog(utilisateur=admin["username"], action="CREATE",
                    table_cible="users", cle=payload.username))
    await db.commit()
    await db.refresh(user)
    return _out(user)


@router.patch("/{user_id}/role", response_model=UserOut)
async def changer_role(user_id: int, payload: RoleUpdate,
                       admin: dict = Depends(require_admin),
                       db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")

    user.role = payload.role
    db.add(AuditLog(utilisateur=admin["username"], action="UPDATE",
                    table_cible="users", cle=user.nom,
                    details=f"role -> {payload.role}"))
    await db.commit()
    await db.refresh(user)
    return _out(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer(user_id: int, admin: dict = Depends(require_admin),
                    db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    if user.id == admin["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Vous ne pouvez pas supprimer votre propre compte.")

    nom = user.nom
    await db.delete(user)
    db.add(AuditLog(utilisateur=admin["username"], action="DELETE",
                    table_cible="users", cle=nom))
    await db.commit()


@router.post("/{user_id}/mot-de-passe", status_code=status.HTTP_204_NO_CONTENT)
async def reinitialiser_mot_de_passe(user_id: int, payload: MotDePasseReset,
                                     admin: dict = Depends(require_admin),
                                     db: AsyncSession = Depends(get_db)):
    """L'admin réinitialise le mot de passe d'un compte (et le déverrouille)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    exiger_mot_de_passe_conforme(payload.nouveau)
    user.password = hash_password(payload.nouveau)
    user.echecs_connexion = 0
    user.verrouille_jusqu = None
    db.add(AuditLog(utilisateur=admin["username"], action="MOT_DE_PASSE",
                    table_cible="users", cle=user.nom, details="réinitialisé par l'administrateur"))
    await db.commit()


@router.post("/{user_id}/deverrouiller", response_model=UserOut)
async def deverrouiller(user_id: int, admin: dict = Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    user.echecs_connexion = 0
    user.verrouille_jusqu = None
    db.add(AuditLog(utilisateur=admin["username"], action="DEVERROUILLAGE",
                    table_cible="users", cle=user.nom))
    await db.commit()
    await db.refresh(user)
    return _out(user)
