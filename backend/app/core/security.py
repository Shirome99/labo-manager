import bcrypt
from fastapi import Depends, HTTPException, Request, status

from app.core.jeton import jeton_requete, utilisateur_requete

# Rôles : les 5 de Labo Manager + « responsable » (validation et émission)
ROLES = ("admin", "responsable", "sma", "scha", "ssa", "user")
ROLE_SECTION = {"sma": "SMA", "scha": "SCHA", "ssa": "SSA"}
# Rôles autorisés à valider, renvoyer, émettre un rapport et lancer un erratum
ROLES_RESPONSABLES = ("admin", "responsable")
# Rôles qui voient toutes les sections
ROLES_GLOBAUX = ("admin", "responsable", "user")
# Facturation (bloc P) : bulletins et encaissements = accueil (user) et admin ;
# exonérations, avoirs, annulations d'encaissement = ROLES_RESPONSABLES ; rôles de section : statut seulement
ROLES_FACTURATION = ("admin", "user")


MDP_LONGUEUR_MIN = 10
MDP_REGLE = "Le mot de passe doit contenir au moins 10 caractères, dont des lettres et des chiffres."


def mot_de_passe_conforme(mdp: str) -> bool:
    """Au moins 10 caractères, avec au moins une lettre et au moins un chiffre."""
    return (len(mdp or "") >= MDP_LONGUEUR_MIN
            and any(c.isalpha() for c in mdp) and any(c.isdigit() for c in mdp))


def exiger_mot_de_passe_conforme(mdp: str) -> None:
    if not mot_de_passe_conforme(mdp):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MDP_REGLE)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def current_user(request: Request) -> dict:
    """Utilisateur connecté : jeton `Authorization: Bearer` (démonstration en ligne), sinon session cookie signée."""
    user = utilisateur_requete(request)
    if not user:
        if jeton_requete(request):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée. Reconnectez-vous.")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé à l'administrateur")
    return user


def require_section(section: str):
    """
    Garde d'accès à une section. admin, responsable et user voient tout ;
    un rôle sectionnel n'accède qu'à sa propre section.
    Reprend exactement la règle de Labo Manager.
    """
    def _guard(user: dict = Depends(current_user)) -> dict:
        role = user["role"]
        if role in ROLES_GLOBAUX or ROLE_SECTION.get(role) == section:
            return user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Votre rôle ne donne pas accès à la section {section}.",
        )
    return _guard
