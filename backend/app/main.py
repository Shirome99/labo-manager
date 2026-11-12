from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import VERSION, settings
from app.core.db import engine
from app.core.journal import JournalMiddleware, configurer_journaux, donnees_invalides, journal
from app.core.securite_http import SecuriteMiddleware
from app.routers import (
    admin, admin_referentiels, audit, auth, bilans, cq, echantillons, equipements, facturation, habilitations, notifications, rapports,
    reactifs, referentiels, requetes, traitements, travail,
)
from app.services import sante

# Configuration (backend/.env) : en production, refus de démarrer avec la clé secrète par défaut
settings.verifier_production()
configurer_journaux()

app = FastAPI(title="LIMS LRARVY", version=VERSION)
app.add_exception_handler(RequestValidationError, donnees_invalides)

# Sécurité HTTP (CSRF par Origin/Referer, expiration après inactivité).
# Ajouté AVANT SessionMiddleware : la session l'englobe et lui est donc accessible.
app.add_middleware(SecuriteMiddleware)

# Session cookie signée — équivalent express-session, avec expiration
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",                 # protection CSRF de base
    https_only=settings.SESSION_HTTPS,  # SESSION_HTTPS=1 quand l'appli est servie en HTTPS
)

# Journal des requêtes et erreurs inattendues (JSON avec référence)
app.add_middleware(JournalMiddleware)

# Démonstration en ligne (front GitHub Pages, autre site) : CORS, ajouté en tout dernier (le plus
# extérieur) pour que toutes les réponses, erreurs comprises, portent les en-têtes CORS.
# Sans CORS_ORIGINS (serveur local), rien n'est ajouté.
if settings.origines_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origines_cors,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "X-Rapport-Numero", "X-Rapport-SHA256", "X-Facture-SHA256",
                        "X-Bilan-Id", "X-Bilan-Version", "X-Bilan-SHA256", "X-Etiquettes"],
        max_age=600,
    )

app.include_router(auth.router)
app.include_router(echantillons.router)
app.include_router(traitements.router)
app.include_router(admin.router)
app.include_router(rapports.router)
app.include_router(referentiels.router)
app.include_router(admin_referentiels.router)
app.include_router(notifications.router)
app.include_router(audit.router)
app.include_router(travail.router)
app.include_router(equipements.router)
app.include_router(cq.router)
app.include_router(habilitations.router)
app.include_router(requetes.router)
app.include_router(bilans.router)
app.include_router(reactifs.router)
app.include_router(facturation.router)


@app.get("/api/health")
async def health():
    """
    État du serveur (supervision, mise à jour) : version, base de données et migrations,
    dernière sauvegarde réussie (journal de sauvegarde.ps1). 503 si la base est inaccessible.
    """
    etat = {"status": "ok", "version": VERSION, "environnement": settings.ENVIRONNEMENT}
    try:
        etat["base"] = await sante.etat_base(engine)
    except Exception:
        journal.exception("Base de données inaccessible (/api/health)")
        etat["status"] = "erreur"
        etat["base"] = {"ok": False, "message": "Base de données inaccessible."}
    etat["sauvegarde"] = sante.derniere_sauvegarde(settings.SAUVEGARDE_DIR)
    return JSONResponse(jsonable_encoder(etat), status_code=200 if etat["base"]["ok"] else 503)


@app.get("/api/version")
async def version():
    """Version et environnement (public : affichés en bas du menu et, en test, dans un bandeau)."""
    return {"version": VERSION, "environnement": settings.ENVIRONNEMENT}


if settings.ENVIRONNEMENT == "test":
    @app.get("/api/test/erreur")
    async def erreur_provoquee():
        """Environnement de test seulement : erreur volontaire (contrôle du journal et du message)."""
        raise RuntimeError("Erreur provoquée volontairement (test de la gestion des erreurs)")


journal.info("Application démarrée (environnement %s, base %s)", settings.ENVIRONNEMENT, settings.nom_base)


# ---- Sert le build React (un seul service à administrer sur le serveur local) ----
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        return FileResponse(DIST / "index.html")
