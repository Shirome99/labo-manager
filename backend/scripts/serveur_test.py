"""
Serveur de l'application sur la base de test, pour les tests de bout en bout (tâche 28).

Prépare la base de test (suppression, migrations, comptes de test : voir
preparer_base_test.py), puis sert l'application et le front construit (frontend/dist)
sur http://127.0.0.1:<port>. Lancé automatiquement par Playwright (frontend/playwright.config.js).

Usage (depuis backend/) :
    python scripts/serveur_test.py [--port 8020] [--base labo_test] [--sans-preparation] [--volume 22000]
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ap = argparse.ArgumentParser(description="Serveur de l'application sur la base de test.")
ap.add_argument("--port", type=int, default=8020)
ap.add_argument("--base", default="labo_test")
ap.add_argument("--sans-preparation", action="store_true", help="garde la base de test telle quelle")
ap.add_argument("--volume", type=int, default=0, help="ajoute N échantillons réalistes (remplir_volume.py)")
args = ap.parse_args()

# La base doit être choisie avant d'importer l'application (moteur créé à l'import)
from app.core.config import settings  # noqa: E402
from scripts.preparer_base_test import preparer, verifier_nom  # noqa: E402

verifier_nom(args.base)
settings.DATABASE_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + "/" + args.base
os.environ["DATABASE_URL"] = settings.DATABASE_URL
settings.ENVIRONNEMENT = "test"            # bandeau « Environnement de test », route d'erreur de test
settings.LOG_DIR = Path(__file__).resolve().parents[1] / "tests" / "resultats" / "logs"

if not args.sans_preparation:
    asyncio.run(preparer(args.base))
if args.volume:
    from scripts.remplir_volume import remplir  # noqa: E402
    asyncio.run(remplir(args.base, args.volume, 5, 2026))

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
