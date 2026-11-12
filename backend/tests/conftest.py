"""
Tests automatisés du backend (tâche 27).

À chaque session de tests, la base de test est **supprimée puis reconstruite de zéro**
par les migrations (`scripts/migrer.py`), puis reçoit des comptes de test pour chaque
rôle et des habilitations. Les tests créent ensuite leurs propres échantillons par l'API.

La base de test s'appelle `labo_test` (variable LIMS_BASE_TEST pour une autre) ; le
script refuse de toucher à la base de l'application (`labo`).

Lancement : backend/scripts/tester.ps1 (ou `python -m pytest` depuis backend/).
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

# --- La base de test doit être choisie AVANT d'importer l'application (moteur créé à l'import)
from app.core.config import settings as _settings_initiaux  # noqa: E402

BASE_TEST = os.getenv("LIMS_BASE_TEST", "labo_test")
_BASE_APPLI = _settings_initiaux.DATABASE_URL.rsplit("/", 1)
if BASE_TEST == _BASE_APPLI[1].split("?")[0] or BASE_TEST in ("labo", "postgres"):
    raise RuntimeError(f"Base de test refusée : {BASE_TEST} (jamais la base de l'application).")
URL_TEST = _BASE_APPLI[0] + "/" + BASE_TEST
os.environ["DATABASE_URL"] = URL_TEST
_settings_initiaux.DATABASE_URL = URL_TEST
os.environ.setdefault("HABILITATIONS_OBLIGATOIRES", "1")
# Environnement de test : route d'erreur provoquée, journaux dans tests/resultats/logs
_settings_initiaux.ENVIRONNEMENT = "test"
_settings_initiaux.LOG_DIR = RACINE / "tests" / "resultats" / "logs"

import asyncpg  # noqa: E402
import httpx  # noqa: E402

from scripts.preparer_base_test import COMPTES, MOT_DE_PASSE, preparer  # noqa: E402,F401


def _url_asyncpg(base: str) -> str:
    return URL_TEST.replace("postgresql+asyncpg://", "postgresql://", 1).rsplit("/", 1)[0] + "/" + base


def pytest_sessionstart(session):
    asyncio.run(preparer(BASE_TEST))


def pytest_collection_modifyitems(items):
    # Une seule boucle d'événements pour toute la session : le pool de connexions de
    # l'application (créé à l'import) reste attaché à cette boucle.
    marque = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if asyncio.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(marque, append=False)


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="session")
def app():
    from app.main import app as application
    return application


async def connecter(app, nom: str | None) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=60)
    if nom:
        r = await c.post("/api/auth/login", json={"username": nom, "password": MOT_DE_PASSE})
        assert r.status_code == 200, (nom, r.status_code, r.text)
    return c


@pytest.fixture(scope="session")
async def clients(app):
    """Un client HTTP connecté par compte de test : clients['sma1'], clients['resp1']..."""
    cs = {nom: await connecter(app, nom) for nom in COMPTES}
    cs[None] = await connecter(app, None)   # sans session
    yield cs
    for c in cs.values():
        await c.aclose()


@pytest.fixture(scope="session")
async def db():
    """Connexion directe (asyncpg) à la base de test, pour les contrôles en SQL."""
    conn = await asyncpg.connect(_url_asyncpg(BASE_TEST))
    yield conn
    await conn.close()


# ------------------------------------------------------------------ aides

SECTIONS = ("SMA", "SCHA", "SSA")


def corps_echantillon(section: str = "SMA", **kw) -> dict:
    corps = {s.lower(): ("Yes" if s == section else "No") for s in SECTIONS}
    corps.update({"date_reception": "2026-09-15T09:30", "nature": "Fromage frais", "fabricant": "Laiterie Test",
                  "organisme_preleveur": "ONSSA Tanger", f"nbre_prlvmts_{section.lower()}": 2})
    corps.update(kw)
    return corps


async def creer_echantillon(client, section: str = "SMA", **kw) -> dict:
    r = await client.post("/api/echantillons", json=corps_echantillon(section, **kw))
    assert r.status_code == 201, r.text
    return r.json()


FICHE = {"SMA": {"date_mise_en_analyse": "2026-09-16", "conformite": "Conforme"},
         "SCHA": {"date_mise_en_analyse": "2026-09-16", "conformite": "Conforme"},
         "SSA": {"date_mise_en_analyse": "2026-09-16"}}
LIGNE = {"SMA": {"analyse_effectuee": "Escherichia coli", "rp1": "<10", "rp2": "<10", "rp3": "15", "rp4": "<10", "rp5": "<10",
                 "date_analyse": "2026-09-16"},
         "SCHA": {"analyse_effectuee": "Histamine", "rp1": "12", "moyenne": "12", "conclusion": "Conforme",
                  "date_analyse": "2026-09-16"},
         "SSA": {"analyse_effectuee": "Brucellose", "resultat_analyse": "Négatif", "nbre_positifs": 0, "nbre_negatif": 5,
                 "date_analyse": "2026-09-16"}}


async def dossier(clients, section: str = "SMA", etape: str = "valide", analyste: str | None = None, **kw) -> str:
    """
    Crée un échantillon et le fait avancer dans le circuit :
    'recu' -> 'saisi' (fiche + résultats) -> 'soumis' -> 'valide' -> 'emis'.
    Renvoie le n° d'échantillon.
    """
    analyste = analyste or section.lower() + "1"
    num = (await creer_echantillon(clients["util1"], section, **kw))["num_echantillon"]
    if etape == "recu":
        return num
    a = clients[analyste]
    r = await a.post(f"/api/traitement/{section}", json={"num_echantillon": num, **FICHE[section]})
    assert r.status_code == 200, r.text
    r = await a.put(f"/api/resultats/{section}/{num}", json=[LIGNE[section]])
    assert r.status_code == 200, r.text
    if etape == "saisi":
        return num
    r = await a.post(f"/api/traitement/{section}/{num}/soumettre")
    assert r.status_code == 200, r.text
    if etape == "soumis":
        return num
    r = await clients["resp1"].post(f"/api/traitement/{section}/{num}/valider")
    assert r.status_code == 200, r.text
    if etape == "valide":
        return num
    r = await clients["resp1"].get(f"/api/rapports/{section}/{num}")
    assert r.status_code == 200, r.text
    return num
