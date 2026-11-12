"""Moteur de requêtes : totaux comparés à du SQL direct, catalogue fermé (400), droits (403)."""
from collections import Counter
from datetime import date

import pytest

from app.services.requetes import DIMENSIONS, JEUX, periode_relative
from tests.conftest import creer_echantillon, dossier

NR = "Non renseigné"


@pytest.fixture(scope="module")
async def jeu_requetes(clients, db):
    """Échantillons d'octobre 2025 aux attributs variés (dont valeurs vides), et quelques dossiers analysés."""
    types = await db.fetch("SELECT id, libelle FROM ref_types_echantillon ORDER BY id LIMIT 2")
    for i in range(12):
        section = ("SMA", "SCHA", "SSA")[i % 3]
        await creer_echantillon(clients["util1"], section, date_reception=f"2025-10-{i + 1:02d}T08:00",
                                fabricant=(None if i % 4 == 0 else f"Fab R{i % 3}"),
                                organisme_preleveur=("SVO Tétouan" if i % 2 else None),
                                type_echantillon=types[i % 2]["id"] if i % 5 else None)
    for s in ("SMA", "SCHA", "SSA"):
        await dossier(clients, s, "valide", date_reception="2025-10-20T08:00")
    return types


async def ex(client, definition, attendu=200):
    r = await client.post("/api/requetes/executer", json=definition)
    assert r.status_code == attendu, r.text
    return r.json()


def par(res, cle, mesure="nb_echantillons"):
    return {l[cle]: l[mesure] for l in res["lignes"]}


async def test_total_par_section_egal_sql(clients, db, jeu_requetes):
    res = await ex(clients["admin_t"], {"jeu": "echantillons", "regroupements": ["section"], "mesures": ["nb_echantillons"]})
    total = await db.fetchval("SELECT count(*) FROM echantillons")
    assert res["totaux"]["nb_echantillons"] == total == sum(par(res, "section").values())
    for s in ("SMA", "SCHA", "SSA"):
        n = await db.fetchval(f'SELECT count(*) FROM echantillons WHERE "{s}" = \'Yes\'')
        assert par(res, "section").get(s, 0) == n


async def test_fabricant_sur_une_periode_avec_non_renseigne(clients, db, jeu_requetes):
    res = await ex(clients["admin_t"], {"jeu": "echantillons", "filtres": {"du": "2025-10-01", "au": "2025-10-31"},
                                        "regroupements": ["fabricant"], "mesures": ["nb_echantillons"]})
    lignes = await db.fetch("""SELECT "Fabricant ou Propriétaire" f FROM echantillons
                               WHERE "Date reception" >= '2025-10-01' AND "Date reception" < '2025-11-01'""")
    attendu = Counter((l["f"] or "").strip() or NR for l in lignes)
    assert par(res, "fabricant") == dict(attendu) and attendu[NR] >= 3


async def test_type_par_mois_et_sous_totaux(clients, db, jeu_requetes):
    res = await ex(clients["admin_t"], {"jeu": "echantillons",
                                        "filtres": {"section": ["SMA"], "du": "2025-10-01", "au": "2025-10-31"},
                                        "regroupements": ["type", "mois"], "mesures": ["nb_echantillons"]})
    lignes = await db.fetch("""SELECT t.libelle FROM echantillons e LEFT JOIN ref_types_echantillon t ON t.id = e."Type d'échantillon"
                               WHERE e."SMA" = 'Yes' AND e."Date reception" >= '2025-10-01' AND e."Date reception" < '2025-11-01'""")
    attendu = Counter(l["libelle"] or NR for l in lignes)
    assert {l["type"]: l["nb_echantillons"] for l in res["sous_totaux"]["type"]} == dict(attendu)
    assert all(l["mois"] == "2025-10" for l in res["lignes"])
    assert res["totaux"]["nb_echantillons"] == len(lignes)


async def test_jeu_analyses_egal_sql(clients, db, jeu_requetes):
    res = await ex(clients["admin_t"], {"jeu": "analyses", "regroupements": ["analyse"], "mesures": ["nb_analyses", "nb_echantillons"]})
    lignes = await db.fetch("SELECT analyse_effectuee a, num_echantillon n FROM resultats_analyses")
    assert par(res, "analyse", "nb_analyses") == dict(Counter((l["a"] or "").strip() or NR for l in lignes))
    assert res["totaux"]["nb_echantillons"] == len({l["n"] for l in lignes})


async def test_aucune_ligne_perdue_pour_chaque_critere(clients, db, jeu_requetes):
    """Pour chaque critère du catalogue : somme des lignes = total général = count(*) direct."""
    total = await db.fetchval("SELECT count(*) FROM echantillons")
    for cle, dim in DIMENSIONS.items():
        if "echantillons" not in dim.sql:
            continue
        res = await ex(clients["admin_t"], {"jeu": "echantillons", "regroupements": [cle], "mesures": ["nb_echantillons"],
                                            "limite": 50000})
        assert sum(par(res, cle).values()) == res["totaux"]["nb_echantillons"] == total, cle


async def test_detail_d_une_case_egal_au_nombre_affiche(clients, jeu_requetes):
    d = {"jeu": "echantillons", "filtres": {"du": "2025-10-01", "au": "2025-10-31"}, "regroupements": ["section"],
         "mesures": ["nb_echantillons"]}
    res = await ex(clients["admin_t"], d)
    for l in res["lignes"]:
        r = await clients["admin_t"].post("/api/requetes/detail", json={"definition": d, "valeurs": {"section": l["section"]}})
        assert r.status_code == 200 and len(r.json()["lignes"]) == l["nb_echantillons"]


@pytest.mark.parametrize("definition", [
    {"jeu": "inconnu"},
    {"jeu": "echantillons", "regroupements": ["colonne_libre"]},
    {"jeu": "echantillons", "regroupements": ["section", "statut", "mois"]},
    {"jeu": "echantillons", "regroupements": ["section", "section"]},
    {"jeu": "echantillons", "mesures": ["count(*)"]},
    {"jeu": "echantillons", "mesures": ["nb_analyses"], "filtres": {"\"N° Echantillon\"": ["x"]}},
    {"jeu": "echantillons", "filtres": {"statut": ["Inexistant"]}},
    {"jeu": "echantillons", "filtres": {"periode": "hier"}},
    {"jeu": "echantillons", "filtres": {"du": "2025-13-45"}},
    {"jeu": "echantillons", "sql": "SELECT 1"},
    {"jeu": "echantillons", "limite": 10 ** 7},
    {"jeu": "echantillons", "tri": {"cle": "DROP TABLE users"}},
])
async def test_cle_hors_catalogue_400(clients, definition):
    await ex(clients["admin_t"], definition, attendu=400)


async def test_valeur_parametree_pas_d_injection(clients):
    res = await ex(clients["admin_t"], {"jeu": "echantillons", "filtres": {"fabricant": ["x' OR '1'='1"]},
                                        "mesures": ["nb_echantillons"]})
    assert res["totaux"]["nb_echantillons"] == 0


async def test_droits_de_section(clients, db, jeu_requetes):
    await ex(clients["sma1"], {"jeu": "echantillons", "filtres": {"section": ["SCHA"]}}, attendu=403)
    res = await ex(clients["sma1"], {"jeu": "echantillons", "regroupements": ["section"], "mesures": ["nb_echantillons"]})
    assert set(par(res, "section")) == {"SMA"}
    assert res["totaux"]["nb_echantillons"] == await db.fetchval("""SELECT count(*) FROM echantillons WHERE "SMA" = 'Yes'""")
    assert "sql" not in res
    assert "sql" in await ex(clients["admin_t"], {"jeu": "echantillons"})


def test_periodes_relatives():
    assert periode_relative("mois_precedent", date(2027, 1, 15)) == (date(2026, 12, 1), date(2026, 12, 31))
    assert periode_relative("mois_precedent", date(2028, 3, 1)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert periode_relative("mois_en_cours", date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert periode_relative("annee_precedente", date(2026, 6, 1)) == (date(2025, 1, 1), date(2025, 12, 31))


def test_catalogue_complet():
    assert set(JEUX) == {"echantillons", "analyses", "facturation"}
    assert {"section", "statut", "type", "fabricant", "organisme", "mois", "analyse", "conformite"} <= set(DIMENSIONS)
