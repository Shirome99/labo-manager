"""Circuit des statuts : saisie, soumission, validation à double regard, renvoi ; stepper manuel."""
import pytest

from tests.conftest import dossier


async def statut(clients, num):
    return (await clients["admin_t"].get(f"/api/echantillons/{num}")).json()["statut"]


async def test_premiere_saisie_passe_en_cours(clients):
    num = await dossier(clients, "SMA", "saisi")
    assert await statut(clients, num) == "En cours"


async def test_soumettre_puis_valider(clients, db):
    num = await dossier(clients, "SMA", "soumis")
    assert await statut(clients, num) == "À valider"
    r = await clients["resp1"].post(f"/api/traitement/SMA/{num}/valider")
    assert r.status_code == 200 and r.json()["valide_par"] == "resp1"
    assert await statut(clients, num) == "Validé"
    actions = [x["action"] for x in await db.fetch("SELECT action FROM audit_log WHERE cle = $1 ORDER BY id", num)]
    assert actions[-2:] == ["SOUMETTRE", "VALIDATE"]


async def test_soumission_sans_fiche_refusee(clients):
    num = await dossier(clients, "SCHA", "recu")
    r = await clients["scha1"].post(f"/api/traitement/SCHA/{num}/soumettre")
    assert r.status_code == 400


async def test_validation_exige_une_fiche_soumise(clients):
    num = await dossier(clients, "SMA", "saisi")
    r = await clients["resp1"].post(f"/api/traitement/SMA/{num}/valider")
    assert r.status_code == 409


@pytest.mark.parametrize("saisisseur", ["resp1", "admin_t"])
async def test_double_regard(clients, saisisseur):
    """Le valideur doit être différent du saisisseur, y compris pour l'admin."""
    num = await dossier(clients, "SSA", "soumis", analyste=saisisseur)
    r = await clients[saisisseur].post(f"/api/traitement/SSA/{num}/valider")
    assert r.status_code == 409 and "double regard" in r.json()["detail"]
    r = await clients["resp2"].post(f"/api/traitement/SSA/{num}/valider")
    assert r.status_code == 200


async def test_renvoi_avec_motif(clients, db):
    num = await dossier(clients, "SMA", "soumis")
    r = await clients["resp1"].post(f"/api/traitement/SMA/{num}/refuser", json={"motif": "Compléter les dates"})
    assert r.status_code == 200 and r.json()["valide_par"] is None
    assert await statut(clients, num) == "En cours"
    assert await db.fetchval("SELECT details FROM audit_log WHERE cle = $1 AND action = 'REFUSER'", num) == "Compléter les dates"
    # notification « fiche renvoyée » pour l'analyste de la section
    n = (await clients["sma1"].get("/api/notifications")).json()
    assert n["renvoyees"] >= 1
    # renvoi d'une fiche non soumise : refusé
    r = await clients["resp1"].post(f"/api/traitement/SMA/{num}/refuser", json={})
    assert r.status_code == 409


async def test_fiche_validee_non_modifiable(clients):
    num = await dossier(clients, "SMA", "valide")
    r = await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num, "observations": "x"})
    assert r.status_code == 409
    r = await clients["sma1"].post(f"/api/traitement/SMA/{num}/soumettre")
    assert r.status_code == 409


# ---------------------------------------------------------------- stepper manuel (admin)

@pytest.mark.parametrize("cible,attendu", [("Validé", 409), ("Rapport émis", 409), ("À valider", 200),
                                           ("Inconnu", 400)])
async def test_stepper_admin(clients, cible, attendu):
    num = await dossier(clients, "SMA", "saisi")
    r = await clients["admin_t"].patch(f"/api/echantillons/{num}/statut", json={"statut": cible})
    assert r.status_code == attendu


async def test_stepper_ne_sort_pas_de_rapport_emis(clients):
    num = await dossier(clients, "SMA", "emis")
    r = await clients["admin_t"].patch(f"/api/echantillons/{num}/statut", json={"statut": "En cours"})
    assert r.status_code == 409
