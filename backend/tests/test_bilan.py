"""Bilan mensuel et exports du reporting : chiffres = requêtes et SQL direct, archivage versionné."""
import hashlib
import io

import pytest
from openpyxl import load_workbook

from tests.conftest import creer_echantillon, dossier

MOIS = "2024-03"


@pytest.fixture(scope="module")
async def mars_2024(clients):
    for i in range(5):
        await creer_echantillon(clients["util1"], ("SMA", "SCHA")[i % 2], date_reception=f"2024-03-{i + 3:02d}T08:00")
    await dossier(clients, "SMA", "soumis", date_reception="2024-03-20T08:00")
    await creer_echantillon(clients["util1"], "SMA", date_reception="2024-02-10T08:00")   # mois précédent


async def test_synthese_egale_sql(clients, db, mars_2024):
    b = (await clients["admin_t"].post("/api/bilans/apercu", json={"mois": MOIS})).json()
    s = {x["cle"]: x for x in b["synthese"]}
    recus = await db.fetchval("""SELECT count(*) FROM echantillons
                                 WHERE "Date reception" >= '2024-03-01' AND "Date reception" < '2024-04-01'""")
    assert s["recus"]["valeur"] == recus == 6
    assert s["recus"]["precedent"] == await db.fetchval(
        """SELECT count(*) FROM echantillons WHERE "Date reception" >= '2024-02-01' AND "Date reception" < '2024-03-01'""")
    assert s["a_valider"]["valeur"] == 1 and s["en_cours"]["valeur"] == 5


async def test_blocs_egaux_aux_requetes(clients, mars_2024):
    b = (await clients["admin_t"].post("/api/bilans/apercu", json={"mois": MOIS})).json()
    blocs = [x for x in b["blocs"] if x["type"] == "requete"]
    assert blocs
    for x in blocs:
        r = (await clients["admin_t"].post("/api/requetes/executer", json=x["definition"])).json()
        assert r["lignes"] == x["resultat"]["lignes"] and r["totaux"] == x["resultat"]["totaux"], x["titre"]


async def test_bilan_section_pour_un_analyste(clients, db, mars_2024):
    assert (await clients["sma1"].post("/api/bilans/apercu", json={"mois": MOIS, "section": "SCHA"})).status_code == 403
    b = (await clients["sma1"].post("/api/bilans/apercu", json={"mois": MOIS})).json()
    assert b["section"] == "SMA"
    assert {x["cle"]: x["valeur"] for x in b["synthese"]}["recus"] == await db.fetchval(
        """SELECT count(*) FROM echantillons WHERE "SMA" = 'Yes'
           AND "Date reception" >= '2024-03-01' AND "Date reception" < '2024-04-01'""")


@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
async def test_archivage_versionne(clients, mars_2024, fmt):
    versions = []
    for _ in range(2):
        r = await clients["resp1"].post("/api/bilans/generer", json={"mois": MOIS, "format": fmt})
        assert r.status_code == 200
        assert hashlib.sha256(r.content).hexdigest() == r.headers["x-bilan-sha256"]
        archive = await clients["resp1"].get(f"/api/bilans/fichier/{r.headers['x-bilan-id']}")
        assert archive.content == r.content
        versions.append(int(r.headers["x-bilan-version"]))
    assert versions[1] == versions[0] + 1
    hist = (await clients["resp1"].get("/api/bilans/historique", params={"mois": MOIS})).json()
    assert {h["version"] for h in hist if h["format"] == fmt} >= set(versions)


async def test_bilan_excel_synthese(clients, mars_2024):
    r = await clients["resp1"].post("/api/bilans/generer", json={"mois": MOIS, "format": "xlsx"})
    wb = load_workbook(io.BytesIO(r.content))
    texte = [[c for c in row if c is not None] for row in wb.worksheets[0].iter_rows(values_only=True)]
    ligne = next(l for l in texte if l and l[0] == "Échantillons reçus")
    assert ligne[1] == 6


async def test_export_requete_excel_et_pdf(clients, db):
    d = {"jeu": "echantillons", "regroupements": ["section"], "mesures": ["nb_echantillons"]}
    r = await clients["admin_t"].post("/api/requetes/export", params={"format": "xlsx"}, json={"definition": d})
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Résultat", "Paramètres", "Détail"} <= set(wb.sheetnames)
    valeurs = [row for row in wb["Résultat"].iter_rows(values_only=True) if row and row[0] == "Total"]
    assert valeurs and valeurs[0][1] == await db.fetchval("SELECT count(*) FROM echantillons")
    r = await clients["admin_t"].post("/api/requetes/export", params={"format": "pdf"}, json={"definition": d})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
