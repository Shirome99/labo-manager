"""Démonstration en ligne : jeton Authorization: Bearer, URL Neon, clé secrète hors local."""
import time

import pytest
from itsdangerous import TimestampSigner

from app.core import jeton as module_jeton
from app.core.config import SECRET_KEY_DEFAUT, Settings, preparer_url
from tests.conftest import MOT_DE_PASSE, connecter


class _SansCookie:
    """Client neuf à chaque appel : les cookies posés par /login ne servent jamais (seul le jeton compte)."""
    def __init__(self, app):
        self.app = app

    def __getattr__(self, methode):
        async def appel(*a, **k):
            c = await connecter(self.app, None)
            try:
                return await getattr(c, methode)(*a, **k)
            finally:
                await c.aclose()
        return appel


@pytest.fixture
def clients(app):
    return {None: _SansCookie(app)}


async def _jeton(clients, nom="util1"):
    r = await clients[None].post("/api/auth/login", json={"username": nom, "password": MOT_DE_PASSE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["jeton_duree"] > 0
    return d["jeton"]


def _bearer(j):
    return {"Authorization": f"Bearer {j}"}


async def test_connexion_par_jeton(clients):
    j = await _jeton(clients)
    r = await clients[None].get("/api/auth/me", headers=_bearer(j))
    assert r.status_code == 200 and r.json()["username"] == "util1"
    # Le jeton suffit, sans cookie : liste paginée et fichier (export) accessibles
    r = await clients[None].get("/api/echantillons?page=1&taille=5", headers=_bearer(j))
    assert r.status_code == 200 and "total" in r.json()


async def test_jeton_invalide_ou_absent(clients):
    j = await _jeton(clients)
    r = await clients[None].get("/api/auth/me", headers=_bearer(j + "x"))
    assert r.status_code == 401 and "Session expirée" in r.json()["detail"]
    r = await clients[None].get("/api/auth/me")
    assert r.status_code == 401


async def test_jeton_expire(clients, monkeypatch):
    # Jeton signé il y a une heure (validité : SESSION_INACTIVITE_MIN = 30 min par défaut)
    ancien = time.time() - 3600
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: int(ancien))
    j = module_jeton.creer_jeton({"id": 1, "username": "util1", "role": "user"})
    monkeypatch.undo()
    r = await clients[None].get("/api/auth/me", headers=_bearer(j))
    assert r.status_code == 401
    r = await clients[None].post("/api/auth/renouveler", headers=_bearer(j))
    assert r.status_code == 401


async def test_duree_maximale(clients, db):
    uid = await db.fetchval("SELECT id FROM users WHERE nom = 'util1'")
    # Connexion il y a plus de SESSION_MAX_AGE : refusé même si le jeton vient d'être renouvelé
    j = module_jeton.creer_jeton({"id": uid, "username": "util1", "role": "user"}, debut=time.time() - 9 * 3600)
    assert (await clients[None].get("/api/auth/me", headers=_bearer(j))).status_code == 401


async def test_renouvellement_relit_le_compte(clients, db):
    j = await _jeton(clients, "resp2")
    await db.execute("UPDATE users SET role = 'user' WHERE nom = 'resp2'")
    try:
        r = await clients[None].post("/api/auth/renouveler", headers=_bearer(j))
        assert r.status_code == 200
        assert r.json()["role"] == "user"
        r2 = await clients[None].get("/api/auth/me", headers=_bearer(r.json()["jeton"]))
        assert r2.json()["role"] == "user"
        # Compte verrouillé : pas de renouvellement
        await db.execute("UPDATE users SET verrouille_jusqu = now() + interval '10 minutes' WHERE nom = 'resp2'")
        assert (await clients[None].post("/api/auth/renouveler", headers=_bearer(j))).status_code == 403
    finally:
        await db.execute("UPDATE users SET role = 'responsable', verrouille_jusqu = NULL WHERE nom = 'resp2'")


async def test_jeton_d_un_compte_supprime(clients):
    j = module_jeton.creer_jeton({"id": 999999, "username": "fantome", "role": "admin"})
    assert (await clients[None].post("/api/auth/renouveler", headers=_bearer(j))).status_code == 401


@pytest.mark.parametrize("url, attendu, options", [
    ("postgresql://u:p@ep-a-1.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
     "postgresql+asyncpg://u:p@ep-a-1.eu-central-1.aws.neon.tech/neondb", {"ssl": "require"}),
    ("postgres://u:p@ep-a-1-pooler.eu.neon.tech/db?sslmode=require",
     "postgresql+asyncpg://u:p@ep-a-1-pooler.eu.neon.tech/db", {"ssl": "require", "statement_cache_size": 0}),
    ("postgresql+asyncpg://postgres@localhost:5432/labo", "postgresql+asyncpg://postgres@localhost:5432/labo", {}),
])
def test_url_neon(url, attendu, options):
    assert preparer_url(url) == (attendu, options)


@pytest.mark.parametrize("env, refuse", [("production", True), ("demo", True), ("local", False),
                                         ("developpement", False), ("test", False)])
def test_cle_par_defaut_hors_local(env, refuse):
    s = Settings(ENVIRONNEMENT=env, SECRET_KEY=SECRET_KEY_DEFAUT, _env_file=None)
    if refuse:
        with pytest.raises(RuntimeError):
            s.verifier_production()
    else:
        s.verifier_production()
