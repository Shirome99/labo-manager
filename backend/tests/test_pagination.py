"""Pagination serveur (tâche 30) : liste des échantillons et détail des requêtes."""
import pytest

from tests.conftest import creer_echantillon

FAB = "Pagination Test"


@pytest.fixture(scope="module")
async def jeu_pagination(clients):
    nums = []
    for i in range(23):
        e = await creer_echantillon(clients["util1"], "SCHA", fabricant=FAB, nature=f"Nature P{i:02d}",
                                    date_reception=f"2023-05-{i + 1:02d}T10:00")
        nums.append(e["num_echantillon"])
    return nums


async def test_pages_et_total(clients, jeu_pagination):
    vus = []
    for page in (1, 2, 3):
        r = (await clients["util1"].get("/api/echantillons", params={"fabricant": FAB, "page": page, "taille": 10})).json()
        assert r["total"] == 23 and r["page"] == page
        vus += [e["num_echantillon"] for e in r["lignes"]]
    assert len(vus) == 23 and sorted(vus) == sorted(jeu_pagination)       # aucune ligne perdue ni répétée
    assert vus[0] == jeu_pagination[-1]                                    # plus récent d'abord (n° d'ordre)


async def test_tri_serveur(clients, jeu_pagination):
    r = (await clients["util1"].get("/api/echantillons", params={"fabricant": FAB, "page": 1, "taille": 5,
                                                                 "tri": "date_reception", "ordre": "asc"})).json()
    assert [e["nature"] for e in r["lignes"]] == [f"Nature P{i:02d}" for i in range(5)]
    r = (await clients["util1"].get("/api/echantillons", params={"fabricant": FAB, "page": 1, "taille": 5,
                                                                 "tri": "nature", "ordre": "desc"})).json()
    assert r["lignes"][0]["nature"] == "Nature P22"
    assert (await clients["util1"].get("/api/echantillons", params={"page": 1, "tri": "mot_de_passe"})).status_code == 422


async def test_compteurs_par_statut_sans_filtre_statut(clients, jeu_pagination):
    num = jeu_pagination[0]
    assert (await clients["scha1"].post("/api/traitement/SCHA", json={"num_echantillon": num})).status_code == 200
    r = (await clients["util1"].get("/api/echantillons", params={"fabricant": FAB, "statut": "En cours", "page": 1})).json()
    assert r["total"] == 1 and r["lignes"][0]["num_echantillon"] == num
    assert r["compteurs"] == {"Reçu": 22, "En cours": 1}


async def test_recherche_et_droits(clients, jeu_pagination):
    r = (await clients["util1"].get("/api/echantillons", params={"q": "nature p1", "page": 1})).json()
    assert r["total"] == 10                                     # P10 à P19 (insensible à la casse)
    assert (await clients["sma1"].get("/api/echantillons", params={"fabricant": FAB, "page": 1})).json()["total"] == 0
    assert (await clients["scha1"].get("/api/echantillons", params={"fabricant": FAB, "page": 1})).json()["total"] == 23
    assert (await clients["util1"].get("/api/echantillons", params={"page": 1, "taille": 501})).status_code == 422


async def test_sans_page_liste_complete(clients, jeu_pagination):
    r = (await clients["util1"].get("/api/echantillons", params={"fabricant": FAB})).json()
    assert isinstance(r, list) and len(r) == 23


async def test_detail_requete_pagine(clients, jeu_pagination):
    d = {"jeu": "echantillons", "filtres": {"fabricant": [FAB]}, "mesures": ["nb_echantillons"]}
    pages = [(await clients["util1"].post("/api/requetes/detail", json={"definition": d, "page": p, "taille": 10})).json()
             for p in (1, 2, 3)]
    assert all(p["total"] == 23 for p in pages)
    nums = [l["num"] for p in pages for l in p["lignes"]]
    assert sorted(nums) == sorted(jeu_pagination)
    r = await clients["util1"].post("/api/requetes/detail", json={"definition": d, "page": 0})
    assert r.status_code == 400
