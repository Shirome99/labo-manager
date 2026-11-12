"""
Journaux applicatifs et gestion uniforme des erreurs (tâche 29).

- Journaux dans `settings.LOG_DIR` : `lims.log`, un fichier par jour (rotation à minuit,
  fichiers `lims.log.AAAA-MM-JJ`), conservés `LOG_RETENTION_JOURS` jours (90 par défaut).
  Chaque requête API y laisse une ligne (méthode, chemin, statut, durée, utilisateur).
- Toute erreur renvoie un JSON `{"detail": "<message en français>"}` sans trace technique :
  * données invalides (422) : message lisible, détail par champ dans `erreurs` ;
  * erreur inattendue (500) : référence affichée à l'utilisateur, trace complète dans le
    journal avec la même référence.
"""
import logging
import secrets
import time
from logging.handlers import TimedRotatingFileHandler

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings

journal = logging.getLogger("lims")
acces = logging.getLogger("lims.acces")

FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"


def configurer_journaux() -> None:
    """Fichier journal quotidien (idempotent : un seul gestionnaire même si appelé deux fois)."""
    if any(getattr(h, "_lims", False) for h in journal.handlers):
        return
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fichier = TimedRotatingFileHandler(settings.LOG_DIR / "lims.log", when="midnight",
                                       backupCount=settings.LOG_RETENTION_JOURS, encoding="utf-8")
    fichier.setFormatter(logging.Formatter(FORMAT))
    fichier._lims = True
    journal.addHandler(fichier)
    journal.setLevel(logging.INFO)
    # Erreurs du serveur web (démarrage, arrêt, exceptions non rattachées à une requête)
    for nom in ("uvicorn.error",):
        logging.getLogger(nom).addHandler(fichier)


# ---------------------------------------------------------------------------
# Données invalides (422)
# ---------------------------------------------------------------------------
MESSAGES = {
    "missing": "champ obligatoire",
    "string_too_short": "texte trop court",
    "string_too_long": "texte trop long",
    "string_pattern_mismatch": "format invalide",
    "string_type": "texte attendu",
    "int_parsing": "nombre entier attendu",
    "int_type": "nombre entier attendu",
    "float_parsing": "nombre attendu",
    "decimal_parsing": "nombre attendu",
    "bool_parsing": "oui / non attendu",
    "date_from_datetime_parsing": "date invalide (AAAA-MM-JJ)",
    "date_parsing": "date invalide (AAAA-MM-JJ)",
    "datetime_parsing": "date et heure invalides",
    "datetime_from_date_parsing": "date et heure invalides",
    "literal_error": "valeur non autorisée",
    "enum": "valeur non autorisée",
    "greater_than_equal": "valeur trop petite",
    "less_than_equal": "valeur trop grande",
    "greater_than": "valeur trop petite",
    "less_than": "valeur trop grande",
    "json_invalid": "contenu JSON invalide",
    "list_type": "liste attendue",
    "dict_type": "objet attendu",
    "model_attributes_type": "objet attendu",
}


def _champ(loc) -> str:
    parties = [str(x) for x in loc if x not in ("body", "query", "path")]
    return ".".join(parties) or "requête"


async def donnees_invalides(request: Request, exc: RequestValidationError) -> JSONResponse:
    erreurs = [{"champ": _champ(e.get("loc", ())), "message": MESSAGES.get(e.get("type"), "valeur invalide")}
               for e in exc.errors()]
    resume = " ; ".join(f"{e['champ']} : {e['message']}" for e in erreurs[:5])
    if len(erreurs) > 5:
        resume += f" (et {len(erreurs) - 5} autre(s))"
    return JSONResponse(status_code=422, content={"detail": f"Données invalides — {resume}.", "erreurs": erreurs})


# ---------------------------------------------------------------------------
# Journal des requêtes et erreurs inattendues (500)
# ---------------------------------------------------------------------------
def nouvelle_reference() -> str:
    return secrets.token_hex(4).upper()


class JournalMiddleware:
    """
    Middleware ASGI le plus extérieur : mesure chaque requête /api et l'écrit dans le
    journal ; transforme toute exception non prévue en 500 JSON avec une référence.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        debut = time.perf_counter()
        etat = {"statut": None}

        async def envoyer(message):
            if message["type"] == "http.response.start":
                etat["statut"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, envoyer)
        except Exception:
            ref = nouvelle_reference()
            journal.exception("Erreur inattendue [ref %s] %s %s (utilisateur %s)",
                              ref, scope.get("method"), scope.get("path"), _utilisateur(scope))
            if etat["statut"] is not None:      # réponse déjà commencée : on ne peut que couper
                raise
            etat["statut"] = 500
            reponse = JSONResponse(status_code=500, content={
                "detail": f"Erreur interne du serveur (référence {ref}). L'incident est enregistré dans le "
                          "journal ; communiquez cette référence à l'administrateur.",
                "reference": ref})
            await reponse(scope, receive, send)
        finally:
            chemin = scope.get("path", "")
            if chemin.startswith("/api/"):
                duree = (time.perf_counter() - debut) * 1000
                acces.info("%s %s %s %.0f ms %s", scope.get("method"), chemin, etat["statut"], duree,
                           _utilisateur(scope))


def _utilisateur(scope) -> str:
    try:
        return ((scope.get("session") or {}).get("user") or {}).get("username") or "-"
    except Exception:  # noqa: BLE001 - session illisible : on journalise sans utilisateur
        return "-"
