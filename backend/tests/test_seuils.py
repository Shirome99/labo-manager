"""Seuils SMA : lecture des valeurs (<10, Abs, 10³…), classement m / M, verdict n / c."""
import math

import pytest

from app.services.seuils import classer, evaluer_lignes, lire_seuil, lire_valeur, trouver_critere
from tests.conftest import creer_echantillon


@pytest.mark.parametrize("texte,attendu", [
    ("150", {"type": "num", "val": 150.0, "op": None}),
    ("<10", {"type": "num", "val": 10.0, "op": "<"}),
    ("> 300", {"type": "num", "val": 300.0, "op": ">"}),
    ("10³", {"type": "num", "val": 1000.0, "op": None}),
    ("10²", {"type": "num", "val": 100.0, "op": None}),
    ("1,5x10^3", {"type": "num", "val": 1500.0, "op": None}),
    ("2.10^3", {"type": "num", "val": 2000.0, "op": None}),
    ("1.5x10(3)", {"type": "num", "val": 1500.0, "op": None}),
    ("Abs", {"type": "absence"}),
    ("Absence", {"type": "absence"}),
    ("Négatif", {"type": "absence"}),
    ("Présence", {"type": "presence"}),
    ("Positif", {"type": "presence"}),
    ("Indénombrable", {"type": "num", "val": math.inf, "op": None}),
    ("", None),
    (None, None),
    ("illisible", None),
])
def test_lire_valeur(texte, attendu):
    assert lire_valeur(texte) == attendu


@pytest.mark.parametrize("texte,attendu", [
    ("m=10(2) ufc/g", {"type": "num", "val": 100.0}),
    ("M=10(3) ufc/g", {"type": "num", "val": 1000.0}),
    ("m=10 ufc/g", {"type": "num", "val": 10.0}),
    ("absence/25 g", {"type": "absence"}),
    ("", None),
])
def test_lire_seuil(texte, attendu):
    assert lire_seuil(texte) == attendu


M100, M1000, ABSENCE = {"type": "num", "val": 100.0}, {"type": "num", "val": 1000.0}, {"type": "absence"}


@pytest.mark.parametrize("valeur,m,gm,classe", [
    ("<10", M100, M1000, "ok"),
    ("100", M100, M1000, "ok"),          # égal à m : satisfaisant
    ("<100", M100, M1000, "ok"),         # strictement inférieur à 100
    (">100", M100, M1000, "marginal"),
    ("150", M100, M1000, "marginal"),
    ("10³", M100, M1000, "marginal"),    # égal à M
    ("1,5x10^3", M100, M1000, "depasse"),
    ("Indénombrable", M100, M1000, "depasse"),
    ("150", M100, None, "depasse"),      # pas de M : au-delà de m = dépassé
    ("Abs", M100, M1000, "ok"),
    ("Présence", M100, M1000, "illisible"),
    ("Abs", ABSENCE, ABSENCE, "ok"),
    ("Présence", ABSENCE, ABSENCE, "depasse"),
    ("<10", ABSENCE, ABSENCE, "ok"),
    ("20", ABSENCE, ABSENCE, "depasse"),
    ("n'importe quoi", M100, M1000, "illisible"),
])
def test_classer(valeur, m, gm, classe):
    assert classer(lire_valeur(valeur), m, gm) == classe


CRITERES = [
    {"id": 1, "parametre": "Salmonella", "n": "n =5", "c": "c=0", "m": "absence/25g", "M": "absence/25g"},
    {"id": 2, "parametre": "E.coli", "n": "n =5", "c": "c=2", "m": "m=10(2) ufc/g", "M": "M=10(3) ufc/g"},
]


def test_rapprochement_analyse_critere():
    assert trouver_critere("Escherichia coli", CRITERES)["id"] == 2
    assert trouver_critere("Salmonelles", CRITERES)["id"] == 1
    assert trouver_critere("Levures et moisissures", CRITERES) is None


@pytest.mark.parametrize("rps,verdict", [
    (["<10", "<10", "50", "<10", "<10"], "Conforme"),
    (["150", "200", "<10", "<10", "<10"], "Conforme"),        # 2 marginaux, c = 2
    (["150", "200", "300", "<10", "<10"], "Non conforme"),    # 3 marginaux > c
    (["2.10^3", "<10", "<10", "<10", "<10"], "Non conforme"),  # > M
    (["<10", "illisible", "<10", "<10", "<10"], "À vérifier"),
])
def test_verdict_plan_a_trois_classes(rps, verdict):
    ligne = {"analyse_effectuee": "Escherichia coli", **{f"rp{i + 1}": v for i, v in enumerate(rps)}}
    ev = evaluer_lignes([ligne], CRITERES)
    assert ev["lignes"][0]["verdict"] == verdict and ev["conclusion"] == verdict


def test_conclusion_globale_et_ligne_sans_critere():
    ev = evaluer_lignes([{"analyse_effectuee": "Salmonella", "rp1": "Abs"},
                         {"analyse_effectuee": "E. coli", "rp1": "5x10^3"},
                         {"analyse_effectuee": "Levures", "rp1": "12"}], CRITERES)
    assert [l["verdict"] for l in ev["lignes"]] == ["Conforme", "Non conforme", None]
    assert ev["conclusion"] == "Non conforme"


async def test_evaluation_par_l_api(clients, db):
    """Les critères de la catégorie en base sont appliqués aux résultats saisis (route d'évaluation)."""
    categorie = await db.fetchval("SELECT categorie_produit FROM ref_criteres_micro WHERE parametre = 'E.coli'")
    num = (await creer_echantillon(clients["util1"], "SMA", categorie=categorie))["num_echantillon"]
    lignes = [{"analyse_effectuee": "Escherichia coli", "rp1": "<10", "rp2": "1,5x10^3"}]
    r = await clients["sma1"].post(f"/api/resultats/SMA/{num}/evaluation", json=lignes)
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["lignes"][0]["rps"] == {"rp1": "ok", "rp2": "depasse"} and ev["conclusion"] == "Non conforme"
