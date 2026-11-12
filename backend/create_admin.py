"""
Crée le premier compte admin (installation, voir docs/deploiement.md).

Usage (depuis backend/, venv activé) :
    python create_admin.py <nom> [email]          # le mot de passe est demandé deux fois, sans écho
    python create_admin.py <nom> <motdepasse> [email]   # ancien usage (le mot de passe reste dans l'historique)

Le mot de passe doit respecter la règle de l'application (au moins 10 caractères, lettres et chiffres).
Si l'email est omis, il est généré : <nom>@lrarvy.local (la colonne email est NOT NULL en base).
La base est celle de DATABASE_URL (backend/.env ou variable d'environnement).
"""
import asyncio
import getpass
import sys
from datetime import datetime

from sqlalchemy import select

from app.core.db import SessionLocal, transmettre_utilisateur
from app.core.security import MDP_REGLE, hash_password, mot_de_passe_conforme
from app.models import User


async def main(nom: str, password: str, email: str | None = None) -> int:
    email = email or f"{nom.strip().lower().replace(' ', '.')}@lrarvy.local"
    if not mot_de_passe_conforme(password):
        print(MDP_REGLE)
        return 1

    async with SessionLocal() as db:
        transmettre_utilisateur(db, "installation")      # tracé dans le journal d'audit
        # Le nom doit etre unique (c'est l'identifiant de connexion)
        existant = await db.execute(select(User).where(User.nom == nom))
        if existant.scalar_one_or_none():
            print(f"Le compte '{nom}' existe deja.")
            return 1

        # L'email est probablement unique en base : on verifie aussi
        doublon_email = await db.execute(select(User).where(User.email == email))
        if doublon_email.scalar_one_or_none():
            print(f"L'email '{email}' est deja utilise. Passe un autre email en 3e argument.")
            return 1

        db.add(User(
            nom=nom,
            email=email,
            password=hash_password(password),
            created_at=datetime.now(),
            role="admin",
        ))
        await db.commit()
        print(f"Compte admin cree : nom='{nom}'  email='{email}'")
        return 0


def _arguments(args: list[str]) -> tuple[str, str, str | None]:
    nom = args[0]
    reste = args[1:]
    # Ancien usage : <nom> <motdepasse> [email] ; nouvel usage : <nom> [email] (mot de passe demandé)
    if reste and "@" not in reste[0]:
        return nom, reste[0], reste[1] if len(reste) > 1 else None
    mdp = getpass.getpass("Mot de passe : ")
    if getpass.getpass("Confirmation : ") != mdp:
        print("Les deux saisies ne correspondent pas.")
        sys.exit(1)
    return nom, mdp, reste[0] if reste else None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(asyncio.run(main(*_arguments(sys.argv[1:]))))
