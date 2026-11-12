"""Rapport d'essai : verrou avant validation, rapport figé, numérotation officielle, erratum."""
import hashlib
import re
from datetime import date

import pytest

from tests.conftest import dossier

CODE = {"SMA": "MA", "SCHA": "CH", "SSA": "SA"}


@pytest.mark.parametrize("etape", ["recu", "saisi", "soumis"])
async def test_verrou_avant_validation(clients, etape):
    num = await dossier(clients, "SMA", etape)
    r = await clients["resp1"].get(f"/api/rapports/SMA/{num}")
    assert r.status_code == (400 if etape == "recu" else 409)   # 400 : aucune fiche


@pytest.mark.parametrize("section", ["SMA", "SCHA", "SSA"])
async def test_emission_numero_officiel_et_statut(clients, section):
    num = await dossier(clients, section, "valide")
    r = await clients["resp1"].get(f"/api/rapports/{section}/{num}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert re.fullmatch(rf"\d{{4}}/{CODE[section]}/{date.today().year}", r.headers["x-rapport-numero"])
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-rapport-sha256"]
    assert (await clients["admin_t"].get(f"/api/echantillons/{num}")).json()["statut"] == "Rapport émis"


async def test_emission_reservee_aux_responsables(clients):
    num = await dossier(clients, "SMA", "valide")
    for nom in ("util1", "sma1"):
        assert (await clients[nom].get(f"/api/rapports/SMA/{num}")).status_code == 403
    assert (await clients["resp2"].get(f"/api/rapports/SMA/{num}")).status_code == 200
    # une fois émis, le rapport se lit par tous les rôles qui voient la section
    assert (await clients["util1"].get(f"/api/rapports/SMA/{num}")).status_code == 200
    assert (await clients["sma1"].get(f"/api/rapports/SMA/{num}")).status_code == 200
    assert (await clients["ssa1"].get(f"/api/rapports/SMA/{num}")).status_code == 403


async def test_rapport_fige(clients, db):
    """Deux téléchargements identiques ; une modification des données ne change pas le PDF émis."""
    num = await dossier(clients, "SCHA", "emis")
    a = await clients["resp1"].get(f"/api/rapports/SCHA/{num}")
    await db.execute("""UPDATE echantillons SET "Nature de l'échantillon" = 'Nature modifiée après émission'
                        WHERE "N° Echantillon" = $1""", num)
    b = await clients["util1"].get(f"/api/rapports/SCHA/{num}")
    assert a.content == b.content and a.headers["x-rapport-sha256"] == b.headers["x-rapport-sha256"]
    assert await db.fetchval("SELECT count(*) FROM rapports_emis WHERE num_echantillon = $1", num) == 1


async def test_numeros_officiels_uniques_et_croissants(clients, db):
    n1 = (await clients["resp1"].get(f"/api/rapports/SSA/{await dossier(clients, 'SSA', 'valide')}")).headers["x-rapport-numero"]
    n2 = (await clients["resp1"].get(f"/api/rapports/SSA/{await dossier(clients, 'SSA', 'valide')}")).headers["x-rapport-numero"]
    assert int(n2[:4]) == int(n1[:4]) + 1
    assert await db.fetchval("SELECT count(*) = count(DISTINCT numero) FROM rapports_emis")


async def test_erratum_version_2(clients, db):
    num = await dossier(clients, "SMA", "emis")
    v1 = await clients["resp1"].get(f"/api/rapports/SMA/{num}")
    # motif obligatoire, responsables seulement
    assert (await clients["resp1"].post(f"/api/rapports/SMA/{num}/erratum", json={})).status_code == 400
    assert (await clients["sma1"].post(f"/api/rapports/SMA/{num}/erratum", json={"motif": "x"})).status_code == 403
    r = await clients["resp1"].post(f"/api/rapports/SMA/{num}/erratum", json={"motif": "Erreur de saisie RP3"})
    assert r.status_code == 200 and r.json()["statut"] == "En cours"
    assert (await clients["resp1"].post(f"/api/rapports/SMA/{num}/erratum", json={"motif": "bis"})).status_code == 409
    # pendant l'erratum, la version 1 reste servie
    assert (await clients["util1"].get(f"/api/rapports/SMA/{num}")).content == v1.content
    # correction, soumission, validation par un autre responsable, nouvelle émission
    r = await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num, "observations": "corrigé"})
    assert r.status_code == 200
    assert (await clients["sma1"].post(f"/api/traitement/SMA/{num}/soumettre")).status_code == 200
    assert (await clients["resp2"].post(f"/api/traitement/SMA/{num}/valider")).status_code == 200
    v2 = await clients["resp1"].get(f"/api/rapports/SMA/{num}")
    assert v2.status_code == 200 and v2.headers["x-rapport-numero"] != v1.headers["x-rapport-numero"]
    hist = (await clients["resp1"].get(f"/api/rapports/historique/{num}")).json()
    par_version = {h["version"]: h for h in hist}
    assert par_version[1]["statut"] == "annulé" and par_version[2]["statut"] == "valide"
    assert par_version[2]["remplace_id"] == par_version[1]["id"]
    ancien = await clients["resp1"].get(f"/api/rapports/fichier/{par_version[1]['id']}")
    assert hashlib.sha256(ancien.content).hexdigest() == v1.headers["x-rapport-sha256"]
