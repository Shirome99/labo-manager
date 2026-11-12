"""Export Excel / CSV de la liste : contenu relu, mêmes filtres que la liste."""
import csv
import io

from openpyxl import load_workbook

from tests.conftest import creer_echantillon

FABRICANT = "Fromagerie Export Test"


async def _jeu(clients):
    nums = []
    for i, section in enumerate(("SMA", "SMA", "SCHA")):
        e = await creer_echantillon(clients["util1"], section, fabricant=FABRICANT, nature=f"Nature export {i}",
                                    date_reception=f"2026-07-0{i + 1}T10:00", total="120", montant_paye=50,
                                    payement="Partiellement payé", num_quittance=f"Q-{i}")
        nums.append(e["num_echantillon"])
    return nums


async def test_export_csv(clients):
    nums = await _jeu(clients)
    r = await clients["util1"].get("/api/echantillons/export", params={"format": "csv", "fabricant": FABRICANT})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith("﻿".encode())               # BOM : accents corrects dans Excel
    lignes = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert sorted(l["N° Échantillon"] for l in lignes) == sorted(nums)
    l0 = next(l for l in lignes if l["N° Échantillon"] == nums[0])
    assert l0["Section"] == "SMA" and l0["Nature"] == "Nature export 0" and l0["Date réception"].startswith("2026-07-01")
    assert l0["Statut de paiement"] == "Partiellement payé" and float(l0["Reste dû"]) == 70 and l0["N° quittance"] == "Q-0"
    assert float(l0["Montant"]) == 120 and float(l0["Payé"]) == 50
    assert l0["Décision de réception"] == "Accepté"


async def test_export_xlsx_memes_lignes_que_la_liste(clients):
    await _jeu(clients)
    filtres = {"fabricant": FABRICANT, "section": "SMA", "du": "2026-07-01", "au": "2026-07-31"}
    liste = (await clients["util1"].get("/api/echantillons", params=filtres)).json()
    r = await clients["util1"].get("/api/echantillons/export", params={"format": "xlsx", **filtres})
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    entetes = [c.value for c in ws[1]]
    assert entetes[:4] == ["N° Échantillon", "Date réception", "Section", "Statut"]
    lignes = [dict(zip(entetes, [c.value for c in row])) for row in ws.iter_rows(min_row=2)]
    assert sorted(l["N° Échantillon"] for l in lignes) == sorted(e["num_echantillon"] for e in liste)
    assert lignes and all(l["Section"] == "SMA" and l["Fabricant ou propriétaire"] == FABRICANT for l in lignes)


async def test_export_filtre_decision(clients):
    e = await creer_echantillon(clients["util1"], "SSA", fabricant=FABRICANT + " R", decision_reception="Refusé",
                                motif_decision="Température", nc_temperature=True, temperature_reception=12.5)
    r = await clients["util1"].get("/api/echantillons/export",
                                   params={"format": "csv", "decision": "Refusé", "fabricant": FABRICANT + " R"})
    lignes = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert [l["N° Échantillon"] for l in lignes] == [e["num_echantillon"]]
    assert lignes[0]["Motif de la décision"] == "Température" and lignes[0]["T° à réception (°C)"] == "12.5"
    assert "Température" in lignes[0]["Non-conformités"]
