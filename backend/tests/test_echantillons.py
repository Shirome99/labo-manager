"""Réception : numérotation AAAA-SECTION-NNNN, section unique, décision de réception."""
import re
from datetime import date

import pytest

from app.routers import echantillons as module_echantillons
from tests.conftest import corps_echantillon, creer_echantillon

ANNEE = date.today().year


def _seq(num: str) -> int:
    return int(num.rsplit("-", 1)[1])


# ---------------------------------------------------------------- numérotation

async def test_format_et_suite(clients):
    """Numéro AAAA-SECTION-NNNN, suite +1 dans la section."""
    a = (await creer_echantillon(clients["util1"], "SCHA"))["num_echantillon"]
    b = (await creer_echantillon(clients["util1"], "SCHA"))["num_echantillon"]
    assert re.fullmatch(rf"{ANNEE}-SCHA-\d{{4}}", a)
    assert _seq(b) == _seq(a) + 1


async def test_compteur_propre_a_chaque_section(clients, db):
    """Chaque section a son compteur : SSA ne suit pas SMA."""
    n_ssa = await db.fetchval("""SELECT count(*) FROM echantillons WHERE "N° Echantillon" LIKE $1""", f"{ANNEE}-SSA-%")
    for _ in range(3):
        await creer_echantillon(clients["util1"], "SMA")
    ssa = (await creer_echantillon(clients["util1"], "SSA"))["num_echantillon"]
    assert ssa == f"{ANNEE}-SSA-{n_ssa + 1:04d}"


async def test_max_plus_un_apres_suppression(clients):
    """Calcul par max + 1 : la suppression d'un numéro intermédiaire ne crée pas de doublon."""
    a = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    b = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    assert (await clients["admin_t"].delete(f"/api/echantillons/{a}")).status_code == 204
    c = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    assert _seq(c) == _seq(b) + 1


async def test_remise_a_zero_annuelle(clients, monkeypatch):
    """Le compteur repart à 0001 au changement d'année ; les numéros de l'année précédente sont ignorés."""
    class Date2031(date):
        @classmethod
        def today(cls):
            return date(2031, 1, 2)
    await creer_echantillon(clients["util1"], "SMA", num_echantillon="2030-SMA-0457")
    monkeypatch.setattr(module_echantillons, "date", Date2031)
    a = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    b = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    assert (a, b) == ("2031-SMA-0001", "2031-SMA-0002")


async def test_collision_relance_un_nouveau_numero(clients, monkeypatch):
    """Si le numéro calculé vient d'être pris (réception simultanée), un autre est généré."""
    pris = (await creer_echantillon(clients["util1"], "SSA"))["num_echantillon"]
    original = module_echantillons._next_num
    appels = []

    async def next_num_concurrent(db, section=None):
        appels.append(section)
        if len(appels) == 1:
            return pris          # 1er essai : numéro déjà enregistré par un autre poste
        return await original(db, section)

    monkeypatch.setattr(module_echantillons, "_next_num", next_num_concurrent)
    nouveau = (await creer_echantillon(clients["util1"], "SSA"))["num_echantillon"]
    assert len(appels) == 2 and nouveau != pris and _seq(nouveau) == _seq(pris) + 1


async def test_receptions_simultanees_numeros_distincts(clients):
    import asyncio
    rs = await asyncio.gather(*[clients["util1"].post("/api/echantillons", json=corps_echantillon("SCHA")) for _ in range(4)])
    nums = [r.json()["num_echantillon"] for r in rs if r.status_code == 201]
    assert len(nums) == 4 and len(set(nums)) == 4


async def test_numero_manuel_en_double_refuse(clients):
    num = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    r = await clients["util1"].post("/api/echantillons", json=corps_echantillon("SMA", num_echantillon=num))
    assert r.status_code == 409


# ---------------------------------------------------------------- une seule section

@pytest.mark.parametrize("sections,attendu", [
    ({"sma": "No", "scha": "No", "ssa": "No"}, 400),
    ({"sma": "Yes", "scha": "Yes", "ssa": "No"}, 400),
    ({"sma": "Yes", "scha": "Yes", "ssa": "Yes"}, 400),
    ({"sma": "No", "scha": "No", "ssa": "Yes"}, 201),
])
async def test_section_unique_a_la_creation(clients, sections, attendu):
    r = await clients["util1"].post("/api/echantillons", json={**corps_echantillon("SMA"), **sections})
    assert r.status_code == attendu, r.text


async def test_section_unique_a_la_modification(clients):
    e = await creer_echantillon(clients["util1"], "SMA")
    corps = {**corps_echantillon("SMA"), "scha": "Yes"}
    r = await clients["util1"].put(f"/api/echantillons/{e['num_echantillon']}", json=corps)
    assert r.status_code == 400


# ---------------------------------------------------------------- décision de réception

async def test_decision_par_defaut_et_motif_obligatoire(clients):
    e = await creer_echantillon(clients["util1"], "SMA")
    assert e["decision_reception"] == "Accepté" and e["statut"] == "Reçu"
    for decision in ("Refusé", "Accepté sous réserve"):
        r = await clients["util1"].post("/api/echantillons", json=corps_echantillon("SMA", decision_reception=decision))
        assert r.status_code == 400
    r = await clients["util1"].post("/api/echantillons",
                                    json=corps_echantillon("SMA", decision_reception="Refusé", motif_decision="Flacon cassé"))
    assert r.status_code == 201


async def test_refuse_sans_fiche_de_traitement(clients):
    e = await creer_echantillon(clients["util1"], "SMA", decision_reception="Refusé", motif_decision="Hors délai")
    r = await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": e["num_echantillon"]})
    assert r.status_code == 409
