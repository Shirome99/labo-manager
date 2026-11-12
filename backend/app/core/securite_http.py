"""
Middleware de sécurité HTTP (tâche 12) :

- Protection CSRF : sur les requêtes qui modifient des données (POST, PUT, PATCH,
  DELETE) vers /api, une en-tête `Origin` (ou à défaut `Referer`) étrangère est
  refusée (403). Est acceptée : l'hôte lui-même, ou une origine de
  `settings.ORIGINES_AUTORISEES`. Sans Origin ni Referer (client non navigateur :
  curl, scripts), la requête passe : un navigateur envoie toujours Origin sur
  une requête intersite. S'ajoute au cookie SameSite=Lax.
- Expiration après inactivité : si la dernière activité de la session date de plus
  de `settings.SESSION_INACTIVITE_MIN` minutes, la session est vidée et l'API
  répond 401. Les appels automatiques (notifications) ne comptent pas comme activité.

Doit être ajouté AVANT SessionMiddleware dans main.py (SessionMiddleware l'englobe).
"""
import time
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

METHODES_ECRITURE = {"POST", "PUT", "PATCH", "DELETE"}
# Appels automatiques du front : ils ne prolongent pas la session
CHEMINS_PASSIFS = {"/api/notifications"}


def origines_autorisees() -> set[str]:
    # + origines CORS de la démonstration en ligne (front GitHub Pages)
    return {o.strip().rstrip("/") for o in settings.ORIGINES_AUTORISEES.split(",") if o.strip()}         | set(settings.origines_cors)


def origine_acceptee(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return True
    p = urlsplit(source)
    if not p.scheme or not p.netloc:          # « null », valeur illisible
        return False
    if p.netloc.lower() == (request.headers.get("host") or "").lower():
        return True
    return f"{p.scheme}://{p.netloc}".lower() in {o.lower() for o in origines_autorisees()}


class SecuriteMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        chemin = request.url.path
        if chemin.startswith("/api/"):
            if request.method in METHODES_ECRITURE and not origine_acceptee(request):
                return JSONResponse({"detail": "Origine de la requête refusée (protection CSRF)."},
                                    status_code=403)

            session = request.session
            if session.get("user"):
                maintenant = time.time()
                derniere = session.get("activite", maintenant)
                if maintenant - derniere > settings.SESSION_INACTIVITE_MIN * 60:
                    session.clear()
                    if chemin != "/api/auth/login":
                        return JSONResponse(
                            {"detail": "Session expirée après inactivité. Reconnectez-vous."},
                            status_code=401)
                elif chemin not in CHEMINS_PASSIFS:
                    session["activite"] = maintenant
        return await call_next(request)
