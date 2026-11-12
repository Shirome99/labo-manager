"""Sécurité des comptes, CSRF, journal d'audit inviolable, habilitations."""
import asyncpg
import pytest

from tests.conftest import connecter, corps_echantillon, dossier


async def _compte(clients, nom, mdp="Motdepasse2026", role="sma"):
    r = await clients["admin_t"].post("/api/admin/users", json={"username": nom, "password": mdp, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("mdp", ["court1", "sanschiffreslongs", "1234567890123"])
async def test_regle_de_mot_de_passe(clients, mdp):
    r = await clients["admin_t"].post("/api/admin/users", json={"username": f"faible_{len(mdp)}", "password": mdp})
    assert r.status_code == 400 and "10 caractères" in r.json()["detail"]


async def test_verrouillage_apres_5_echecs(app, clients):
    await _compte(clients, "verrou_t")
    c = await connecter(app, None)
    codes = [(await c.post("/api/auth/login", json={"username": "verrou_t", "password": "faux"})).status_code
             for _ in range(5)]
    assert codes == [401, 401, 401, 401, 403]
    r = await c.post("/api/auth/login", json={"username": "verrou_t", "password": "Motdepasse2026"})
    assert r.status_code == 403 and "verrouillé" in r.json()["detail"]
    uid = next(u["id"] for u in (await clients["admin_t"].get("/api/admin/users")).json() if u["username"] == "verrou_t")
    assert (await clients["admin_t"].post(f"/api/admin/users/{uid}/deverrouiller")).status_code == 200
    assert (await c.post("/api/auth/login", json={"username": "verrou_t", "password": "Motdepasse2026"})).status_code == 200
    await c.aclose()


async def test_changement_de_mot_de_passe(app, clients):
    await _compte(clients, "mdp_t")
    c = await connecter(app, None)
    await c.post("/api/auth/login", json={"username": "mdp_t", "password": "Motdepasse2026"})
    assert (await c.post("/api/auth/mot-de-passe", json={"actuel": "faux", "nouveau": "Nouveau2026x"})).status_code == 400
    assert (await c.post("/api/auth/mot-de-passe", json={"actuel": "Motdepasse2026", "nouveau": "court"})).status_code == 400
    assert (await c.post("/api/auth/mot-de-passe", json={"actuel": "Motdepasse2026", "nouveau": "Nouveau2026x"})).status_code == 204
    await c.aclose()
    c = await connecter(app, None)
    assert (await c.post("/api/auth/login", json={"username": "mdp_t", "password": "Motdepasse2026"})).status_code == 401
    assert (await c.post("/api/auth/login", json={"username": "mdp_t", "password": "Nouveau2026x"})).status_code == 200
    await c.aclose()


@pytest.mark.parametrize("entetes,attendu", [
    ({"Origin": "http://site-malveillant.example"}, 403),
    ({"Referer": "http://site-malveillant.example/page"}, 403),
    ({"Origin": "http://testserver"}, 201),
    ({"Origin": "http://localhost:5173"}, 201),
    ({}, 201),
])
async def test_csrf_origine(clients, entetes, attendu):
    r = await clients["util1"].post("/api/echantillons", json=corps_echantillon("SMA"), headers=entetes)
    assert r.status_code == attendu


async def test_sans_session_401(clients):
    for url in ("/api/echantillons", "/api/notifications", "/api/requetes/catalogue", "/api/travail"):
        assert (await clients[None].get(url)).status_code == 401


# ---------------------------------------------------------------- audit

async def test_audit_ecriture_par_l_application(clients, db):
    num = await dossier(clients, "SMA", "saisi")
    lignes = await db.fetch("""SELECT table_nom, operation, utilisateur, source FROM audit_donnees
                               WHERE num_echantillon = $1 ORDER BY id""", num)
    assert ("echantillons", "INSERT", "util1", "application") in [tuple(l) for l in lignes]
    assert ("traitement_sma", "INSERT", "sma1", "application") in [tuple(l) for l in lignes]


async def test_audit_ecriture_hors_application(clients, db):
    num = await dossier(clients, "SMA", "recu")
    await db.execute("""UPDATE echantillons SET "N° de lot" = 'LOT-HORS-APPLI' WHERE "N° Echantillon" = $1""", num)
    l = await db.fetchrow("""SELECT utilisateur, source, avant, apres FROM audit_donnees
                             WHERE num_echantillon = $1 AND operation = 'UPDATE' ORDER BY id DESC LIMIT 1""", num)
    assert l["utilisateur"].startswith("pg:") and l["source"] == "base" and "LOT-HORS-APPLI" in l["apres"]


@pytest.mark.parametrize("sql", ["DELETE FROM audit_donnees", "UPDATE audit_donnees SET utilisateur = 'x'",
                                 "TRUNCATE audit_donnees"])
async def test_audit_inviolable(db, sql):
    with pytest.raises(asyncpg.PostgresError, match="ajout seul"):
        await db.execute(sql)


async def test_audit_ne_copie_pas_le_mot_de_passe(clients, db):
    await _compte(clients, "audit_mdp_t")
    apres = await db.fetchval("""SELECT apres FROM audit_donnees WHERE table_nom = 'users' AND operation = 'INSERT'
                                 ORDER BY id DESC LIMIT 1""")
    assert "audit_mdp_t" in apres and "mot_de_passe" not in apres and "$2b$" not in apres


# ---------------------------------------------------------------- habilitations

async def test_resultat_refuse_sans_habilitation(clients):
    num = await dossier(clients, "SMA", "saisi")
    r = await clients["sma1"].put(f"/api/resultats/SMA/{num}",
                                  json=[{"analyse_effectuee": "Escherichia coli", "rp1": "<10", "rp2": "<10", "rp3": "15",
                                         "rp4": "<10", "rp5": "<10", "date_analyse": "2026-09-16"},
                                        {"analyse_effectuee": "Listeria monocytogenes", "rp1": "Abs"}])
    assert r.status_code == 403 and "Listeria" in r.json()["detail"]


async def test_habilitation_echue_refusee(clients, db):
    uid = await db.fetchval("SELECT id FROM users WHERE nom = 'sma1'")
    r = await clients["resp1"].post("/api/habilitations", json={"user_id": uid, "nom_analyse": "Levures", "section": "SMA",
                                                                "date_qualification": "2020-01-01", "date_echeance": "2021-01-01"})
    assert r.status_code == 201
    num = await dossier(clients, "SMA", "saisi")
    r = await clients["sma1"].put(f"/api/resultats/SMA/{num}", json=[{"analyse_effectuee": "Levures", "rp1": "12"}])
    assert r.status_code == 403
