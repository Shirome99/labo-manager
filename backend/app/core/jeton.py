"""
Authentification par jeton (démonstration en ligne : front sur github.io, API sur onrender.com).

Le front et l'API sont alors sur deux sites différents : le cookie de session deviendrait un
cookie tiers, bloqué par Brave et Safari. `POST /api/auth/login` renvoie donc aussi un jeton
signé (itsdangerous, clé SECRET_KEY), que le front envoie dans `Authorization: Bearer <jeton>`.
Le cookie de session reste le mode normal du serveur local.

Règles (mêmes que la session) :
- validité `settings.duree_jeton_min` minutes (SESSION_INACTIVITE_MIN par défaut) : sans activité,
  le jeton expire (inactivité) ; le front le renouvelle pendant l'activité (`/api/auth/renouveler`) ;
- durée totale bornée par SESSION_MAX_AGE depuis la connexion (`debut`, conservé au renouvellement) ;
- le renouvellement relit le compte en base : un compte supprimé ou verrouillé n'est pas renouvelé,
  un changement de rôle est pris en compte (au plus tard à l'expiration du jeton).
"""
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.requests import Request

from app.core.config import settings

_serialiseur = URLSafeTimedSerializer(settings.SECRET_KEY, salt="lims-jeton-api")
_ABSENT = object()


def creer_jeton(user: dict, debut: float | None = None) -> str:
    return _serialiseur.dumps({"id": user["id"], "username": user["username"], "role": user["role"],
                               "debut": debut or time.time()})


def lire_jeton(jeton: str) -> dict | None:
    """Contenu du jeton, ou None s'il est invalide, expiré, ou au-delà de la durée maximale."""
    try:
        donnees = _serialiseur.loads(jeton, max_age=settings.duree_jeton_min * 60)
    except BadSignature:            # SignatureExpired en hérite
        return None
    if time.time() - float(donnees.get("debut", 0)) > settings.SESSION_MAX_AGE:
        return None
    return donnees


def jeton_requete(request: Request) -> str | None:
    entete = request.headers.get("authorization") or ""
    if entete[:7].lower() == "bearer ":
        return entete[7:].strip() or None
    return None


def utilisateur_requete(request: Request) -> dict | None:
    """
    Utilisateur de la requête : celui du jeton s'il y en a un (même invalide : alors None),
    sinon celui de la session. Mémorisé pour la requête (current_user, get_db).
    """
    deja = getattr(request.state, "lims_utilisateur", _ABSENT)
    if deja is not _ABSENT:
        return deja
    jeton = jeton_requete(request)
    if jeton:
        d = lire_jeton(jeton)
        user = {"id": d["id"], "username": d["username"], "role": d["role"]} if d else None
    else:
        user = request.session.get("user") if "session" in request.scope else None
    request.state.lims_utilisateur = user
    return user
