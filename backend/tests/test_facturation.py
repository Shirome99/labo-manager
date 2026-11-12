"""Facturation (bloc P) : grille tarifaire, lignes, bulletins, avoirs, encaissements, intégration au circuit."""
import csv
import io
from datetime import date, timedelta

AUJ = date.today()


async def _tarif(clients, nom, prix, date_effet, section="SMA", **kw):
    r = await clients["admin_t"].post("/api/admin/ref/tarifs", json={
        "nom_analyse": nom, "section": section, "prix": prix, "date_effet": str(date_effet), **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _prix(clients, nom, d, section="SMA"):
    r = await clients["util1"].get("/api/facturation/tarifs", params={"date": str(d), "section": section})
    assert r.status_code == 200
    ligne = next(x for x in r.json() if x["nom_analyse"] == nom)
    return None if ligne["prix"] is None else float(ligne["prix"])


async def test_changement_de_prix_n_affecte_pas_une_date_anterieure(clients):
    nom = "Analyse tarif daté"
    tid = await _tarif(clients, nom, 100, date(2026, 1, 1))
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}", json={
        "nom_analyse": nom, "section": "SMA", "prix": 150, "date_effet": str(AUJ)})
    assert r.status_code == 200 and r.json()["nouvelle_periode"] is True
    assert await _prix(clients, nom, AUJ) == 150
    assert await _prix(clients, nom, AUJ - timedelta(days=1)) == 100
    assert await _prix(clients, nom, date(2026, 1, 1)) == 100
    assert await _prix(clients, nom, date(2025, 12, 31)) is None          # avant le 1er prix
    h = (await clients["admin_t"].get(f"/api/admin/ref/tarifs/{tid}/historique")).json()
    assert [(float(p["prix"]), p["date_fin"]) for p in h] == [(150, None), (100, str(AUJ - timedelta(days=1)))]
    # même prix : pas de nouvelle période
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}", json={
        "nom_analyse": nom, "section": "SMA", "prix": 150, "par_prelevement": True})
    assert r.json()["nouvelle_periode"] is False
    assert len((await clients["admin_t"].get(f"/api/admin/ref/tarifs/{tid}/historique")).json()) == 2
    # un tarif avec historique ne se supprime pas
    assert (await clients["admin_t"].delete(f"/api/admin/ref/tarifs/{tid}")).status_code == 409


async def test_dates_d_effet_refusees(clients):
    nom = "Analyse tarif dates"
    tid = await _tarif(clients, nom, 50, AUJ - timedelta(days=10))
    corps = {"nom_analyse": nom, "section": "SMA", "prix": 60}
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}",
                                       json={**corps, "date_effet": str(AUJ + timedelta(days=1))})
    assert r.status_code == 400 and "futur" in r.json()["detail"]
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}",
                                       json={**corps, "date_effet": str(AUJ - timedelta(days=20))})
    assert r.status_code == 400
    # correction le jour même du début de la période : pas de nouvelle période
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}",
                                       json={**corps, "date_effet": str(AUJ - timedelta(days=10))})
    assert r.status_code == 200
    h = (await clients["admin_t"].get(f"/api/admin/ref/tarifs/{tid}/historique")).json()
    assert len(h) == 1 and float(h[0]["prix"]) == 60
    # sans historique : suppression possible
    assert (await clients["admin_t"].delete(f"/api/admin/ref/tarifs/{tid}")).status_code == 204


async def test_analyses_sans_prix_signalees(clients, db):
    await db.execute("INSERT INTO ref_analyses (nom_analyse, section) VALUES ('Analyse sans prix test', 'SCHA')")
    r = await clients["admin_t"].get("/api/admin/ref/tarifs/sans-prix")
    assert r.status_code == 200
    noms = {(a["nom_analyse"], a["section"]) for a in r.json()}
    assert ("Analyse sans prix test", "SCHA") in noms
    assert ("FMAT", "SMA") not in noms                       # prix repris d'Access
    tid = await _tarif(clients, "Analyse sans prix test", 30, AUJ, section="SCHA")
    noms = {(a["nom_analyse"], a["section"])
            for a in (await clients["admin_t"].get("/api/admin/ref/tarifs/sans-prix")).json()}
    assert ("Analyse sans prix test", "SCHA") not in noms
    liste = (await clients["admin_t"].get("/api/admin/ref/tarifs")).json()
    t = next(x for x in liste if x["id"] == tid)
    assert t["analyse_id"] is not None and float(t["prix"]) == 30


async def test_prix_access_a_valider(clients):
    liste = (await clients["admin_t"].get("/api/admin/ref/tarifs")).json()
    fmat = next(x for x in liste if x["nom_analyse"] == "FMAT")
    assert fmat["a_valider"] is True and float(fmat["prix"]) == 40 and fmat["depuis"] == "2000-01-01"


async def test_reglages_facturation(clients):
    r = await clients["sma1"].get("/api/facturation/parametres")
    assert r.status_code == 200
    p = r.json()
    assert float(p["taux_tva"]) == 0 and p["etape_paiement"] == "aucune" and p["seuil_impayes_jours"] == 30
    nouveau = {"taux_tva": 20, "etape_paiement": "remise_rapport", "seuil_impayes_jours": 45}
    assert (await clients["resp1"].put("/api/facturation/parametres", json=nouveau)).status_code == 403
    assert (await clients["admin_t"].put("/api/facturation/parametres",
                                         json={**nouveau, "etape_paiement": "jamais"})).status_code == 422
    r = await clients["admin_t"].put("/api/facturation/parametres", json=nouveau)
    assert r.status_code == 200 and r.json()["etape_paiement"] == "remise_rapport"
    # remise à l'état par défaut pour les autres tests
    r = await clients["admin_t"].put("/api/facturation/parametres",
                                     json={"taux_tva": 0, "etape_paiement": "aucune", "seuil_impayes_jours": 30})
    assert r.status_code == 200


async def test_droits_tarifs(clients):
    for nom in ("resp1", "util1", "sma1"):
        assert (await clients[nom].get("/api/admin/ref/tarifs")).status_code == 403
        assert (await clients[nom].post("/api/admin/ref/tarifs", json={
            "nom_analyse": "X", "section": "SMA", "prix": 1})).status_code == 403
    assert (await clients[None].get("/api/facturation/tarifs")).status_code == 401


# ------------------------------------------------------------------ lignes facturables (tâche 35)
from tests.conftest import creer_echantillon  # noqa: E402

RES = {"rp1": "<10", "date_analyse": "2026-09-16"}


async def _fact(clients, num, qui="util1"):
    r = await clients[qui].get(f"/api/facturation/echantillons/{num}")
    assert r.status_code == 200, r.text
    return r.json()


async def test_lignes_depuis_les_resultats(clients):
    await _tarif(clients, "Salmonella", 25, date(2026, 1, 1), par_prelevement=True)
    num = (await creer_echantillon(clients["util1"], "SMA", nbre_prlvmts_sma=3))["num_echantillon"]
    a = clients["sma1"]
    assert (await a.post("/api/traitement/SMA", json={"num_echantillon": num})).status_code == 200
    r = await a.put(f"/api/resultats/SMA/{num}", json=[
        {"analyse_effectuee": "Escherichia coli", **RES}, {"analyse_effectuee": "FMAT", **RES},
        {"analyse_effectuee": "Salmonella", **RES}])
    assert r.status_code == 200, r.text
    f = await _fact(clients, num)
    lignes = {l["analyse"]: l for l in f["lignes"]}
    assert set(lignes) == {"Escherichia coli", "FMAT", "Salmonella"}
    assert all(l["origine"] == "automatique" for l in lignes.values())
    assert (float(lignes["Escherichia coli"]["prix_unitaire"]), float(lignes["Escherichia coli"]["quantite"])) == (80, 1)
    assert float(lignes["FMAT"]["montant"]) == 40
    sal = lignes["Salmonella"]
    assert sal["par_prelevement"] and float(sal["quantite"]) == 3 and float(sal["montant"]) == 75   # 25 × 3 prélèvements
    assert float(f["par_section"]["SMA"]["montant"]) == 195 and float(f["total"]) == 195
    # Ré-enregistrement identique : pas de doublon ; retrait d'une analyse : ligne automatique retirée
    r = await a.put(f"/api/resultats/SMA/{num}", json=[
        {"analyse_effectuee": "Escherichia coli", **RES}, {"analyse_effectuee": "FMAT", **RES}])
    assert r.status_code == 200
    f = await _fact(clients, num)
    assert sorted(l["analyse"] for l in f["lignes"]) == ["Escherichia coli", "FMAT"] and float(f["total"]) == 120


async def test_prix_fige_et_arrondis(clients):
    tid = await _tarif(clients, "Analyse prix figé", 100, date(2026, 1, 1), section="SCHA")
    num = (await creer_echantillon(clients["util1"], "SCHA"))["num_echantillon"]
    u = clients["util1"]
    r = await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"section": "SCHA", "analyse": "analyse prix figé"})
    assert r.status_code == 201, r.text
    ligne_id = r.json()["id"]
    r = await clients["admin_t"].patch(f"/api/admin/ref/tarifs/{tid}", json={
        "nom_analyse": "Analyse prix figé", "section": "SCHA", "prix": 120})
    assert r.status_code == 200
    f = await _fact(clients, num)
    assert [float(l["prix_unitaire"]) for l in f["lignes"]] == [100]          # prix figé à la création
    r = await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"section": "SCHA", "analyse": "Analyse prix figé"})
    assert float(next(l for l in r.json()["lignes"] if l["id"] == r.json()["id"])["prix_unitaire"]) == 120
    # Arrondi au centime (demi supérieur) : 1,5 × 33,33 = 49,995 -> 50,00
    r = await u.patch(f"/api/facturation/lignes/{ligne_id}", json={"quantite": 1.5, "prix_unitaire": 33.33})
    assert r.status_code == 200
    assert next(l for l in r.json()["lignes"] if l["id"] == ligne_id)["montant"] == 50
    assert r.json()["total"] == 170
    # Frais divers : montant obligatoire
    assert (await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"analyse": "Frais d'envoi"})).status_code == 400
    r = await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"analyse": "Frais d'envoi", "prix_unitaire": 15.5})
    assert r.json()["par_section"]["Divers"]["montant"] == 15.5 and r.json()["total"] == 185.5
    # Analyse sans tarif : prix à renseigner, comptée 0
    r = await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"section": "SCHA", "analyse": "Analyse inconnue"})
    assert "Analyse inconnue (SCHA)" in r.json()["sans_prix"] and r.json()["total"] == 185.5


async def test_droits_lignes(clients):
    num = (await creer_echantillon(clients["util1"], "SMA"))["num_echantillon"]
    for nom in ("sma1", "scha1"):
        assert (await clients[nom].get(f"/api/facturation/echantillons/{num}")).status_code == 403
    assert (await clients["resp1"].get(f"/api/facturation/echantillons/{num}")).status_code == 200
    corps = {"section": "SMA", "analyse": "FMAT"}
    for nom in ("resp1", "sma1"):
        assert (await clients[nom].post(f"/api/facturation/echantillons/{num}/lignes", json=corps)).status_code == 403
        assert (await clients[nom].post(f"/api/facturation/echantillons/{num}/synchroniser")).status_code == 403
    r = await clients["admin_t"].post(f"/api/facturation/echantillons/{num}/lignes", json=corps)
    assert r.status_code == 201
    lid = r.json()["id"]
    assert (await clients["resp1"].delete(f"/api/facturation/lignes/{lid}")).status_code == 403
    assert (await clients["util1"].delete(f"/api/facturation/lignes/{lid}")).status_code == 200
    assert (await clients["util1"].get("/api/facturation/echantillons/INCONNU")).status_code == 404


# ------------------------------------------------------------------ bulletins et avoirs (tâche 36)
import asyncio  # noqa: E402
import base64  # noqa: E402
import hashlib  # noqa: E402
import re  # noqa: E402
import zlib  # noqa: E402


def texte_pdf(contenu: bytes) -> str:
    """Texte brut des flux d'un PDF ReportLab (FlateDecode), pour y chercher des mentions ASCII."""
    morceaux = []
    for m in re.finditer(rb"stream\r?\n(.*?)\s*endstream", contenu, re.S):
        brut = m.group(1).strip()
        if brut.endswith(b"~>"):                       # /ASCII85Decode puis /FlateDecode
            brut = base64.a85decode(brut[:-2].removeprefix(b"<~"))
        try:
            morceaux.append(zlib.decompress(brut).decode("latin-1"))
        except zlib.error:
            morceaux.append(brut.decode("latin-1", "ignore"))
    return "\n".join(morceaux)


async def _echantillon_facturable(clients, client="Client Bulletin", montant=80, section="SMA"):
    num = (await creer_echantillon(clients["util1"], section, client_nom=client))["num_echantillon"]
    r = await clients["util1"].post(f"/api/facturation/echantillons/{num}/lignes",
                                    json={"analyse": "Analyse forfaitaire", "prix_unitaire": montant})
    assert r.status_code == 201, r.text
    return num


async def _bulletin(clients, nums):
    r = await clients["util1"].post("/api/facturation/factures", json={"echantillons": nums})
    assert r.status_code == 201, r.text
    return r.json()


async def test_bulletin_emis_fige(clients):
    a = await _echantillon_facturable(clients, "Coopérative Al Amal", 80)
    b = await _echantillon_facturable(clients, "  coopérative al amal ", 45.5)
    autre = await _echantillon_facturable(clients, "Autre client", 10)
    u = clients["util1"]
    r = await u.post("/api/facturation/factures", json={"echantillons": [a, autre]})
    assert r.status_code == 400 and "même client" in r.json()["detail"]
    f = await _bulletin(clients, [a, b])
    assert f["statut"] == "brouillon" and f["numero"] is None and float(f["total_ttc"]) == 125.5
    assert (await u.post("/api/facturation/factures", json={"echantillons": [a]})).status_code == 409   # déjà en brouillon
    apercu = await u.get(f"/api/facturation/factures/{f['id']}/pdf")
    assert apercu.status_code == 200 and "BROUILLON" in texte_pdf(apercu.content)

    r = await u.post(f"/api/facturation/factures/{f['id']}/emettre")
    assert r.status_code == 200, r.text
    e = r.json()
    assert re.fullmatch(r"BUL-\d{4}-\d{5}", e["numero"]) and e["statut"] == "émis"
    assert float(e["total_ttc"]) == 125.5 and len(e["lignes"]) == 2
    p1 = await u.get(f"/api/facturation/factures/{f['id']}/pdf")
    p2 = await clients["resp1"].get(f"/api/facturation/factures/{f['id']}/pdf")
    assert p1.content == p2.content
    assert hashlib.sha256(p1.content).hexdigest() == p1.headers["x-facture-sha256"] == e["sha256"]
    texte = texte_pdf(p1.content)
    assert e["numero"] in texte and "cent vingt-cinq dirhams et cinquante centimes" in texte

    # Plus rien ne change : bulletin, lignes, échantillon
    assert (await u.patch(f"/api/facturation/factures/{f['id']}", json={"client_nom": "X"})).status_code == 409
    assert (await u.post(f"/api/facturation/factures/{f['id']}/emettre")).status_code == 409
    assert (await u.post(f"/api/facturation/factures/{f['id']}/annuler")).status_code == 409
    ligne = (await _fact(clients, a))["lignes"][0]
    assert ligne["verrouillee"] is True
    assert (await u.patch(f"/api/facturation/lignes/{ligne['id']}", json={"quantite": 2})).status_code == 409
    assert (await u.delete(f"/api/facturation/lignes/{ligne['id']}")).status_code == 409
    assert (await u.delete(f"/api/echantillons/{a}")).status_code == 409
    # Une nouvelle ligne sur l'échantillon ne modifie pas le bulletin émis
    await u.post(f"/api/facturation/echantillons/{a}/lignes", json={"analyse": "Frais tardifs", "prix_unitaire": 5})
    assert (await u.get(f"/api/facturation/factures/{f['id']}/pdf")).content == p1.content
    assert float((await u.get(f"/api/facturation/factures/{f['id']}")).json()["total_ttc"]) == 125.5


async def test_emission_refusee_si_prix_a_renseigner(clients):
    num = (await creer_echantillon(clients["util1"], "SCHA", client_nom="Client prix manquant"))["num_echantillon"]
    await clients["util1"].post(f"/api/facturation/echantillons/{num}/lignes",
                                json={"section": "SCHA", "analyse": "Analyse sans grille"})
    f = await _bulletin(clients, [num])
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/emettre")
    assert r.status_code == 400 and "Prix à renseigner" in r.json()["detail"]
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/annuler")
    assert r.status_code == 200 and r.json()["statut"] == "annulé" and r.json()["numero"] is None


async def test_numerotation_simultanee_sans_trou_ni_doublon(clients):
    ids = []
    for i in range(6):
        num = await _echantillon_facturable(clients, f"Client simultané {i}", 10 + i)
        ids.append((await _bulletin(clients, [num]))["id"])
    reps = await asyncio.gather(*(clients["util1"].post(f"/api/facturation/factures/{i}/emettre") for i in ids))
    assert all(r.status_code == 200 for r in reps), [r.text for r in reps]
    sequences = sorted(int(r.json()["numero"].rsplit("-", 1)[1]) for r in reps)
    assert sequences == list(range(sequences[0], sequences[0] + 6))      # consécutifs, sans doublon


async def test_avoir(clients):
    a = await _echantillon_facturable(clients, "Client avoir", 100)
    u = clients["util1"]
    await u.post(f"/api/facturation/echantillons/{a}/lignes", json={"analyse": "Frais d'envoi", "prix_unitaire": 20})
    f = (await u.post(f"/api/facturation/factures/{(await _bulletin(clients, [a]))['id']}/emettre")).json()
    assert float(f["total_ttc"]) == 120
    d_envoi = next(d for d in f["lignes"] if d["analyse"] == "Frais d'envoi")
    url = f"/api/facturation/factures/{f['id']}/avoir"
    assert (await u.post(url, json={"motif": "Erreur", "details": [d_envoi["id"]]})).status_code == 403
    assert (await clients["sma1"].post(url, json={"motif": "Erreur", "details": [d_envoi["id"]]})).status_code == 403
    assert (await clients["resp1"].post(url, json={"motif": " ", "details": [d_envoi["id"]]})).status_code == 400
    r = await clients["resp1"].post(url, json={"motif": "Frais d'envoi non dus", "details": [d_envoi["id"]]})
    assert r.status_code == 201, r.text
    av = r.json()
    assert re.fullmatch(r"AV-\d{4}-\d{5}", av["numero"]) and float(av["total_ttc"]) == -20
    assert av["origine"]["numero"] == f["numero"]
    pdf = await u.get(f"/api/facturation/factures/{av['id']}/pdf")
    assert f["numero"] in texte_pdf(pdf.content) and hashlib.sha256(pdf.content).hexdigest() == av["sha256"]
    bul = (await u.get(f"/api/facturation/factures/{f['id']}")).json()
    assert float(bul["total_ttc"]) == 120 and float(bul["total_avoirs"]) == -20 and float(bul["net"]) == 100
    # la même ligne ne s'annule pas deux fois ; un montant ne dépasse pas le reste
    assert (await clients["resp1"].post(url, json={"motif": "Bis", "details": [d_envoi["id"]]})).status_code == 409
    assert (await clients["resp1"].post(url, json={"motif": "Trop", "montant": 100.01})).status_code == 400
    r = await clients["admin_t"].post(url, json={"motif": "Geste commercial", "montant": 30})
    assert r.status_code == 201 and float(r.json()["total_ttc"]) == -30
    assert float((await u.get(f"/api/facturation/factures/{f['id']}")).json()["net"]) == 70
    # la ligne annulée redevient modifiable ; l'autre reste verrouillée
    lignes = {l["analyse"]: l for l in (await _fact(clients, a))["lignes"]}
    assert lignes["Frais d'envoi"]["verrouillee"] is False and lignes["Analyse forfaitaire"]["verrouillee"] is True
    envoi = lignes["Frais d'envoi"]["id"]
    assert (await u.delete(f"/api/facturation/lignes/{envoi}")).status_code == 200
    # avoir sur un brouillon : refusé
    b = await _bulletin(clients, [await _echantillon_facturable(clients, "Client brouillon", 5)])
    assert (await clients["resp1"].post(f"/api/facturation/factures/{b['id']}/avoir",
                                        json={"motif": "x", "montant": 1})).status_code == 409


async def test_droits_bulletins(clients):
    num = await _echantillon_facturable(clients, "Client droits", 10)
    for nom in ("resp1", "sma1"):
        assert (await clients[nom].post("/api/facturation/factures", json={"echantillons": [num]})).status_code == 403
    f = await _bulletin(clients, [num])
    assert (await clients["sma1"].get(f"/api/facturation/factures/{f['id']}")).status_code == 403
    assert (await clients["sma1"].get("/api/facturation/factures")).status_code == 403
    assert (await clients["resp1"].get(f"/api/facturation/factures/{f['id']}")).status_code == 200
    assert (await clients["resp1"].post(f"/api/facturation/factures/{f['id']}/emettre")).status_code == 403
    assert (await clients["admin_t"].post(f"/api/facturation/factures/{f['id']}/emettre")).status_code == 200
    liste = (await clients["util1"].get("/api/facturation/factures", params={"q": num})).json()
    assert liste["total"] == 1 and liste["lignes"][0]["numero"] is not None


# ------------------------------------------------------------------ encaissements, quittances, exonérations (tâche 37)
async def _bulletin_emis(clients, client, montant, num=None):
    num = num or await _echantillon_facturable(clients, client, montant)
    f = await _bulletin(clients, [num])
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/emettre")
    assert r.status_code == 200, r.text
    return r.json(), num


async def _ech(db, num):
    return await db.fetchrow('SELECT "Payement" AS statut, "TOTAL" AS total, "Montant payé" AS paye, '
                             '"N° QUITTANCE" AS quittance, "Mode de paiement" AS mode FROM echantillons '
                             'WHERE "N° Echantillon" = $1', num)


async def test_paiements_partiels_et_annulation(clients, db):
    f, num = await _bulletin_emis(clients, "Client paiements", 100)
    assert f["statut_paiement"] == "Non payé" and float(f["reste"]) == 100
    assert (await _ech(db, num))["statut"] == "Non payé"
    u = clients["util1"]
    url = f"/api/facturation/factures/{f['id']}/paiements"
    r = await u.post(url, json={"date_paiement": str(AUJ), "montant": 40, "mode": "espèces"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["statut_paiement"] == "Partiellement payé" and float(c["reste"]) == 60
    assert re.fullmatch(r"Q-\d{4}-\d{5}", c["numero_quittance"])
    e = await _ech(db, num)
    assert e["statut"] == "Partiellement payé" and float(e["paye"]) == 40 and e["total"] == "100.00"
    assert e["quittance"] == c["numero_quittance"] and e["mode"] == "espèces"
    # quittance PDF archivée, identique à chaque téléchargement
    q1 = await u.get(f"/api/facturation/paiements/{c['paiement_id']}/quittance")
    q2 = await clients["resp1"].get(f"/api/facturation/paiements/{c['paiement_id']}/quittance")
    assert q1.status_code == 200 and q1.content == q2.content
    assert hashlib.sha256(q1.content).hexdigest() == q1.headers["x-quittance-sha256"]
    texte = texte_pdf(q1.content)
    assert c["numero_quittance"] in texte and "quarante dirhams" in texte and f["numero"] in texte
    # trop-perçu : confirmation exigée
    r = await u.post(url, json={"date_paiement": str(AUJ), "montant": 70, "mode": "chèque", "reference": "123456"})
    assert r.status_code == 409 and "trop-perçu" in r.json()["detail"]
    r = await u.post(url, json={"date_paiement": str(AUJ), "montant": 60, "mode": "chèque", "reference": "123456",
                                "banque": "Banque Populaire", "numero_quittance": "R-0042"})
    assert r.status_code == 201 and r.json()["statut_paiement"] == "Payé" and float(r.json()["reste"]) == 0
    assert r.json()["numero_quittance"] == "R-0042"                     # n° du carnet de la régie
    assert (await _ech(db, num))["statut"] == "Payé"
    # n° de quittance déjà utilisé
    r = await u.post(url, json={"date_paiement": str(AUJ), "montant": 1, "mode": "espèces", "numero_quittance": "R-0042",
                                "confirmer_trop_percu": True})
    assert r.status_code == 409
    # annulation : responsables seulement, motif obligatoire, statut qui revient en arrière
    pid = next(p["id"] for p in (await u.get(f"/api/facturation/factures/{f['id']}")).json()["paiements"]
                       if p["numero_quittance"] == "R-0042")
    assert (await u.post(f"/api/facturation/paiements/{pid}/annuler", json={"motif": "Chèque rejeté"})).status_code == 403
    assert (await clients["resp1"].post(f"/api/facturation/paiements/{pid}/annuler", json={"motif": ""})).status_code == 422
    r = await clients["resp1"].post(f"/api/facturation/paiements/{pid}/annuler", json={"motif": "Chèque rejeté"})
    assert r.status_code == 200 and r.json()["statut_paiement"] == "Partiellement payé" and float(r.json()["reste"]) == 60
    assert (await clients["resp1"].post(f"/api/facturation/paiements/{pid}/annuler", json={"motif": "bis"})).status_code == 409
    assert (await _ech(db, num))["statut"] == "Partiellement payé"
    # l'encaissement annulé reste visible (jamais supprimé)
    ps = (await u.get(f"/api/facturation/factures/{f['id']}")).json()["paiements"]
    assert [p["statut"] for p in ps] == ["valide", "annulé"]
    # chaque opération est dans le journal d'audit inviolable
    ops = await db.fetch("SELECT operation, apres->>'statut' AS statut FROM audit_donnees "
                         "WHERE table_nom = 'paiements' AND cle = $1 ORDER BY id", str(pid))
    assert [(o["operation"], o["statut"]) for o in ops][0] == ("INSERT", "valide")
    assert ("UPDATE", "annulé") in [(o["operation"], o["statut"]) for o in ops]


async def test_trop_percu_confirme(clients):
    f, _ = await _bulletin_emis(clients, "Client trop-perçu", 50)
    r = await clients["admin_t"].post(f"/api/facturation/factures/{f['id']}/paiements", json={
        "date_paiement": str(AUJ), "montant": 60, "mode": "espèces", "confirmer_trop_percu": True})
    assert r.status_code == 201
    c = r.json()
    assert c["statut_paiement"] == "Payé" and float(c["trop_percu"]) == 10 and c["paiements"][0]["trop_percu"] is True
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/paiements", json={
        "date_paiement": str(AUJ + timedelta(days=1)), "montant": 1, "mode": "espèces", "confirmer_trop_percu": True})
    assert r.status_code == 400                                          # date future


async def test_exonerations(clients, db):
    f, num = await _bulletin_emis(clients, "Client exonéré", 75)
    url = f"/api/facturation/factures/{f['id']}/exonerer"
    corps = {"type": "contrôle officiel", "motif": "Plan de surveillance ONSSA"}
    assert (await clients["util1"].post(url, json=corps)).status_code == 403
    assert (await clients["resp1"].post(url, json={**corps, "type": "faveur"})).status_code == 422
    r = await clients["resp1"].post(url, json=corps)
    assert r.status_code == 200 and r.json()["statut_paiement"] == "Exonéré" and float(r.json()["reste"]) == 0
    assert float(r.json()["exoneration"]["montant"]) == 75
    assert (await _ech(db, num))["statut"] == "Exonéré"
    assert (await clients["resp1"].post(url, json=corps)).status_code == 409
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/paiements",
                                    json={"date_paiement": str(AUJ), "montant": 10, "mode": "espèces"})
    assert r.status_code == 400
    trace = await db.fetchval("SELECT count(*) FROM audit_donnees WHERE table_nom = 'exonerations' AND num_echantillon IS NULL "
                              "AND apres->>'facture_id' = $1", str(f["id"]))
    assert trace == 1
    # annulation de l'exonération : le bulletin redevient dû
    eid = (await clients["util1"].get(f"/api/facturation/factures/{f['id']}")).json()["exoneration"]["id"]
    r = await clients["admin_t"].post(f"/api/facturation/exonerations/{eid}/annuler", json={"motif": "Erreur de saisie"})
    assert r.status_code == 200 and r.json()["statut_paiement"] == "Non payé"
    assert (await _ech(db, num))["statut"] == "Non payé"

    # Exonération d'un échantillon sans bulletin : plus rien à facturer
    num2 = await _echantillon_facturable(clients, "Convention", 30)
    r = await clients["resp1"].post(f"/api/facturation/echantillons/{num2}/exonerer",
                                    json={"type": "convention", "motif": "Convention 2026 n° 12"})
    assert r.status_code == 200 and r.json()["paiement"]["statut"] == "Exonéré"
    assert (await _ech(db, num2))["statut"] == "Exonéré"
    r = await clients["util1"].post("/api/facturation/factures", json={"echantillons": [num2]})
    assert r.status_code == 400 and "exonéré" in r.json()["detail"]
    assert (await clients["util1"].delete(f"/api/echantillons/{num2}")).status_code == 409
    # échantillon déjà sur un bulletin émis non soldé : exonérer le bulletin
    r = await clients["resp1"].post(f"/api/facturation/echantillons/{num}/exonerer", json=corps)
    assert r.status_code == 409


async def test_avoir_total(clients, db):
    f, num = await _bulletin_emis(clients, "Client avoir total", 90)
    r = await clients["resp1"].post(f"/api/facturation/factures/{f['id']}/avoir",
                                    json={"motif": "Analyse non réalisée", "details": [f["lignes"][0]["id"]]})
    assert r.status_code == 201
    bul = (await clients["util1"].get(f"/api/facturation/factures/{f['id']}")).json()
    assert bul["statut_paiement"] == "Avoir total" and float(bul["reste"]) == 0
    # la ligne annulée redevient « à facturer » : on la retire, l'échantillon est soldé par l'avoir
    ligne = next(l for l in (await _fact(clients, num))["lignes"] if not l["verrouillee"])
    await clients["util1"].delete(f"/api/facturation/lignes/{ligne['id']}")
    assert (await _ech(db, num))["statut"] == "Avoir total"


async def test_statut_echantillon_regroupe(clients, db):
    a = await _echantillon_facturable(clients, "Client regroupé", 60)
    b = await _echantillon_facturable(clients, "Client regroupé", 40)
    f = await _bulletin(clients, [a, b])
    f = (await clients["util1"].post(f"/api/facturation/factures/{f['id']}/emettre")).json()
    await clients["util1"].post(f"/api/facturation/factures/{f['id']}/paiements",
                                json={"date_paiement": str(AUJ), "montant": 50, "mode": "virement"})
    ea, eb = await _ech(db, a), await _ech(db, b)
    assert ea["statut"] == eb["statut"] == "Partiellement payé"
    assert (float(ea["paye"]), float(eb["paye"])) == (30, 20)            # au prorata (60 % / 40 %)
    assert (ea["total"], eb["total"]) == ("60.00", "40.00")


# ------------------------------------------------------------------ intégration au circuit (tâche 38)
from tests.conftest import dossier  # noqa: E402

PARAMS_DEFAUT = {"taux_tva": 0, "etape_paiement": "aucune", "seuil_impayes_jours": 30}


async def _etape(clients, etape):
    r = await clients["admin_t"].put("/api/facturation/parametres", json={**PARAMS_DEFAUT, "etape_paiement": etape})
    assert r.status_code == 200


async def _payer(clients, num):
    f = await _bulletin(clients, [num])
    f = (await clients["util1"].post(f"/api/facturation/factures/{f['id']}/emettre")).json()
    r = await clients["util1"].post(f"/api/facturation/factures/{f['id']}/paiements",
                                    json={"date_paiement": str(AUJ), "montant": float(f["net"]), "mode": "espèces"})
    assert r.status_code == 201, r.text
    return f


async def test_etape_aucune_ne_bloque_rien(clients, db):
    num = await dossier(clients, "SMA", "valide")                # ligne E. coli 80 DH non payée
    assert (await _ech(db, num))["statut"] == "Non payé"
    assert (await clients["resp1"].get(f"/api/rapports/SMA/{num}")).status_code == 200


async def test_paiement_exige_avant_la_remise_du_rapport(clients, db):
    num = await dossier(clients, "SMA", "valide")
    num2 = await dossier(clients, "SMA", "valide")
    await _etape(clients, "remise_rapport")
    try:
        r = await clients["resp1"].get(f"/api/rapports/SMA/{num}")
        assert r.status_code == 409 and "Paiement exigé avant la remise du rapport" in r.json()["detail"]
        assert "Non payé" in r.json()["detail"]
        await _payer(clients, num)
        assert (await _ech(db, num))["statut"] == "Payé"
        assert (await clients["resp1"].get(f"/api/rapports/SMA/{num}")).status_code == 200
        # exonération : acceptée aussi
        assert (await clients["resp1"].get(f"/api/rapports/SMA/{num2}")).status_code == 409
        r = await clients["resp1"].post(f"/api/facturation/echantillons/{num2}/exonerer",
                                        json={"type": "contrôle officiel", "motif": "Plan de contrôle"})
        assert r.status_code == 200
        assert (await clients["resp1"].get(f"/api/rapports/SMA/{num2}")).status_code == 200
        # la mise en analyse n'est pas concernée par ce réglage
        assert (await dossier(clients, "SCHA", "saisi"))
    finally:
        await _etape(clients, "aucune")


async def test_paiement_exige_avant_la_mise_en_analyse(clients):
    num = (await creer_echantillon(clients["util1"], "SMA", client_nom="Client mise en analyse"))["num_echantillon"]
    await _etape(clients, "mise_en_analyse")
    try:
        r = await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num})
        assert r.status_code == 409 and "avant la mise en analyse" in r.json()["detail"]
        await clients["util1"].post(f"/api/facturation/echantillons/{num}/lignes",
                                    json={"section": "SMA", "analyse": "FMAT"})        # analyse prévue (40 DH)
        assert (await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num})).status_code == 409
        await _payer(clients, num)
        assert (await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num})).status_code == 200
        # les mises à jour de la fiche ne sont pas re-contrôlées
        assert (await clients["sma1"].post("/api/traitement/SMA", json={"num_echantillon": num,
                                                                        "observations": "RAS"})).status_code == 200
    finally:
        await _etape(clients, "aucune")


async def test_filtre_et_export_paiement(clients):
    num = await _echantillon_facturable(clients, "Client filtre paiement", 70)
    num_paye = await _echantillon_facturable(clients, "Client filtre payé", 30)
    await _payer(clients, num_paye)
    u = clients["util1"]
    non_payes = {e["num_echantillon"] for e in (await u.get("/api/echantillons", params={"paiement": "Non payé"})).json()}
    payes = {e["num_echantillon"] for e in (await u.get("/api/echantillons", params={"paiement": "Payé"})).json()}
    assert num in non_payes and num not in payes and num_paye in payes
    r = await u.get("/api/echantillons/export", params={"format": "csv", "paiement": "Payé"})
    lignes = {l["N° Échantillon"]: l for l in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";")}
    assert num_paye in lignes and num not in lignes
    l = lignes[num_paye]
    assert l["Statut de paiement"] == "Payé" and float(l["Montant"]) == 30 and float(l["Payé"]) == 30 and float(l["Reste dû"]) == 0
    assert (await u.get("/api/echantillons", params={"paiement": "Inconnu"})).status_code == 422


async def test_modification_de_l_echantillon_garde_le_statut_calcule(clients, db):
    num = await _echantillon_facturable(clients, "Client modification", 25)
    e = (await clients["util1"].get(f"/api/echantillons/{num}")).json()
    r = await clients["util1"].put(f"/api/echantillons/{num}", json={**e, "payement": "Payé", "montant_paye": "25",
                                                                     "nature": "Nature corrigée"})
    assert r.status_code == 200
    assert (await _ech(db, num))["statut"] == "Non payé"                # recalculé, pas saisi


async def test_notifications_impayes_et_statut_dans_les_listes(clients, db):
    f, num = await _bulletin_emis(clients, "Client retardataire", 45)
    await db.execute("UPDATE factures SET date_emission = current_date - 40 WHERE id = $1", f["id"])
    n = (await clients["util1"].get("/api/notifications")).json()
    impayes = [i for i in n["items"] if i["type"] == "impaye"]
    assert n["impayes"] >= 1 and any(i["num"] == f["numero"] for i in impayes)
    assert any("émis il y a 40 jours" in i["detail"] for i in impayes)
    assert (await clients["admin_t"].get("/api/notifications")).json()["impayes"] >= 1
    for nom in ("resp1", "sma1"):
        assert (await clients[nom].get("/api/notifications")).json()["impayes"] == 0
    # un bulletin récent n'est pas signalé
    f2, _ = await _bulletin_emis(clients, "Client récent", 45)
    assert all(i["num"] != f2["numero"] for i in (await clients["util1"].get("/api/notifications")).json()["items"])
    # statut de paiement dans le tableau de bord et la file de travail
    tb = (await clients["util1"].get("/api/echantillons/dashboard")).json()
    assert all("payement" in e for e in tb["recents"])
    travail = (await clients["sma1"].get("/api/travail")).json()
    assert all("payement" in e for e in travail["items"])


# ------------------------------------------------------------------ page Facturation : bulletins, impayés, caisse (tâche 39)
from openpyxl import load_workbook  # noqa: E402

JOUR_CAISSE = date(2026, 3, 16)          # journée réservée à ce test (aucun autre encaissement à cette date)


async def test_journal_de_caisse(clients, db):
    u = clients["util1"]
    montants = [("espèces", 120.5), ("chèque", 80), ("virement", 45.25), ("espèces", 10)]
    ids = []
    for i, (mode, m) in enumerate(montants):
        f, _ = await _bulletin_emis(clients, f"Client caisse {i}", m)
        r = await u.post(f"/api/facturation/factures/{f['id']}/paiements", json={
            "date_paiement": str(JOUR_CAISSE), "montant": m, "mode": mode, "reference": "CH-1" if mode == "chèque" else None})
        ids.append(r.json()["paiement_id"])
    await clients["resp1"].post(f"/api/facturation/paiements/{ids[-1]}/annuler", json={"motif": "Erreur de caisse"})
    j = (await u.get("/api/facturation/caisse", params={"du": str(JOUR_CAISSE)})).json()
    attendu = await db.fetchval("SELECT sum(montant) FROM paiements WHERE date_paiement = $1 AND statut = 'valide'",
                                JOUR_CAISSE)
    assert float(j["total"]) == float(attendu) == 245.75 and j["nb"] == 3
    assert float(j["par_mode"]["espèces"]["montant"]) == 120.5 and j["par_mode"]["chèque"]["nb"] == 1
    assert float(j["par_mode"]["virement"]["montant"]) == 45.25
    assert sum(float(v["montant"]) for v in j["par_mode"].values()) == 245.75
    assert [p["id"] for p in j["annules"]] == [ids[-1]]                 # annulé : listé à part, exclu
    # période plus large : mêmes totaux (aucun autre encaissement ce mois-là)
    j2 = (await u.get("/api/facturation/caisse", params={"du": "2026-03-01", "au": "2026-03-31"})).json()
    assert float(j2["total"]) == 245.75
    assert (await u.get("/api/facturation/caisse", params={"du": "2026-03-31", "au": "2026-03-01"})).status_code == 400
    # exports : Excel relu, PDF signé (agent)
    r = await u.get("/api/facturation/caisse/export", params={"du": str(JOUR_CAISSE), "format": "xlsx"})
    ws = load_workbook(io.BytesIO(r.content)).active
    valeurs = [[c.value for c in ligne] for ligne in ws.iter_rows()]
    total = next(l for l in valeurs if l[0] == "Total" and l[6] == "3 encaissement(s)")
    assert total[7] == 245.75
    assert any(isinstance(l[0], str) and l[0].startswith("Établi par util1") for l in valeurs)
    r = await u.get("/api/facturation/caisse/export", params={"du": str(JOUR_CAISSE), "format": "pdf"})
    texte = texte_pdf(r.content)
    assert r.status_code == 200 and "JOURNAL DE CAISSE" in texte and "util1" in texte


async def test_impayes_par_anciennete(clients, db):
    f45, _ = await _bulletin_emis(clients, "Client ancien", 60)
    f100, _ = await _bulletin_emis(clients, "Client ancien", 40)
    f5, _ = await _bulletin_emis(clients, "Client ancien", 25)
    await db.execute("UPDATE factures SET date_emission = current_date - 45 WHERE id = $1", f45["id"])
    await db.execute("UPDATE factures SET date_emission = current_date - 100 WHERE id = $1", f100["id"])
    await clients["util1"].post(f"/api/facturation/factures/{f5['id']}/paiements",
                                json={"date_paiement": str(AUJ), "montant": 5, "mode": "espèces"})
    r = (await clients["resp1"].get("/api/facturation/impayes")).json()
    c = next(x for x in r["clients"] if x["client"] == "Client ancien")
    assert c["nb"] == 3 and float(c["0-30"]) == 20 and float(c["31-60"]) == 60 and float(c["plus de 90"]) == 40
    assert float(c["61-90"]) == 0 and float(c["total"]) == 120
    # total général = somme des restes des bulletins émis non soldés (liste des bulletins)
    liste = (await clients["util1"].get("/api/facturation/factures", params={"type": "facture", "statut": "émis",
                                                                            "taille": 500})).json()
    assert float(r["totaux"]["total"]) == round(sum(float(b["reste"]) for b in liste["lignes"]), 2)
    assert float(liste["reste_total"]) == float(r["totaux"]["total"])


async def test_liste_des_bulletins_filtres(clients):
    num = await _echantillon_facturable(clients, "Client filtres liste", 33, section="SSA")
    f, _ = await _bulletin_emis(clients, "Client filtres liste", 33, num=num)
    u = clients["util1"]
    r = (await u.get("/api/facturation/factures", params={"section": "SSA", "paiement": "Non payé"})).json()
    assert f["id"] in [b["id"] for b in r["lignes"]]
    assert all(b["statut_paiement"] == "Non payé" for b in r["lignes"])
    r = (await u.get("/api/facturation/factures", params={"section": "SCHA", "q": num})).json()
    assert r["total"] == 0
    r = (await u.get("/api/facturation/factures", params={"q": f["numero"]})).json()
    assert r["total"] == 1 and r["lignes"][0]["statut_paiement"] == "Non payé" and float(r["lignes"][0]["reste"]) == 33
    assert (await u.get("/api/facturation/factures", params={"paiement": "Inconnu"})).status_code == 422
    for route in ("/api/facturation/factures", "/api/facturation/impayes", "/api/facturation/caisse"):
        assert (await clients["sma1"].get(route)).status_code == 403


# ------------------------------------------------------------------ reporting de la facturation (tâche 40)
from decimal import Decimal  # noqa: E402

MOIS_TEST = ("2026-02-01", "2026-02-28")       # mois réservé à ce test (bulletins antidatés)
MESURES_FACT = ["nb_bulletins", "montant", "montant_avoirs", "montant_exonere", "montant_paye", "reste_a_payer"]


async def _requete(clients, qui="resp1", **definition):
    r = await clients[qui].post("/api/requetes/executer", json={"jeu": "facturation", **definition})
    assert r.status_code == 200, r.text
    return r.json()


async def test_reporting_facturation_mois(clients, db):
    u, resp = clients["util1"], clients["resp1"]
    bulletins = []
    # 1. SMA, TVA 20 % : 33,33 + 12,50 = 45,83 HT -> TVA 9,166 arrondie à 9,17 -> 55,00 TTC ; payé 20 (partiel)
    await _etape(clients, "aucune")
    await clients["admin_t"].put("/api/facturation/parametres", json={**PARAMS_DEFAUT, "taux_tva": 20})
    try:
        num = await _echantillon_facturable(clients, "Client reporting A", 33.33)
        await u.post(f"/api/facturation/echantillons/{num}/lignes", json={"analyse": "Frais", "prix_unitaire": 12.5})
        f1, _ = await _bulletin_emis(clients, "Client reporting A", 0, num=num)
    finally:
        await clients["admin_t"].put("/api/facturation/parametres", json=PARAMS_DEFAUT)
    assert float(f1["total_ttc"]) == 55 and float(f1["montant_tva"]) == 9.17
    await u.post(f"/api/facturation/factures/{f1['id']}/paiements",
                 json={"date_paiement": str(AUJ), "montant": 20, "mode": "espèces"})
    bulletins.append(f1)
    # 2. SCHA : 100 ; avoir de la ligne (−100) puis rien d'autre -> avoir total
    num = await _echantillon_facturable(clients, "Client reporting B", 100, section="SCHA")
    f2, _ = await _bulletin_emis(clients, "Client reporting B", 0, num=num)
    await resp.post(f"/api/facturation/factures/{f2['id']}/avoir", json={"motif": "Annulé", "details": [f2["lignes"][0]["id"]]})
    bulletins.append(f2)
    # 3. SSA : 75 ; exonéré
    num = await _echantillon_facturable(clients, "Client reporting C", 75, section="SSA")
    f3, _ = await _bulletin_emis(clients, "Client reporting C", 0, num=num)
    await resp.post(f"/api/facturation/factures/{f3['id']}/exonerer", json={"type": "convention", "motif": "Convention"})
    bulletins.append(f3)
    # 4. SMA : 80 ; avoir de 10 ; payé 70 par chèque (soldé)
    f4, _ = await _bulletin_emis(clients, "Client reporting D", 80)
    await resp.post(f"/api/facturation/factures/{f4['id']}/avoir", json={"motif": "Remise", "montant": 10})
    await u.post(f"/api/facturation/factures/{f4['id']}/paiements",
                 json={"date_paiement": str(AUJ), "montant": 70, "mode": "chèque", "reference": "77"})
    bulletins.append(f4)
    ids = [b["id"] for b in bulletins]
    await db.execute("UPDATE factures SET date_emission = DATE '2026-02-10' WHERE id = ANY($1::int[])", ids)

    filtres = {"du": MOIS_TEST[0], "au": MOIS_TEST[1], "date_ref": "emission_bulletin"}
    res = await _requete(clients, filtres=filtres, mesures=MESURES_FACT)
    t = {k: Decimal(str(v)) for k, v in res["totaux"].items()}
    assert t["nb_bulletins"] == 4
    assert t["montant"] == Decimal("55.00") + 100 + 75 + 80                        # facturé TTC
    assert t["montant_avoirs"] == Decimal("110") and t["montant_exonere"] == Decimal("75")
    assert t["montant_paye"] == Decimal("90")
    # facturé − avoirs − exonérations − encaissé = reste dû, au centime près
    assert t["reste_a_payer"] == t["montant"] - t["montant_avoirs"] - t["montant_exonere"] - t["montant_paye"]
    reste_bulletins = sum([Decimal(str((await u.get(f"/api/facturation/factures/{i}")).json()["reste"])) for i in ids])
    assert t["reste_a_payer"] == reste_bulletins == Decimal("35.00")
    # mêmes montants en SQL direct
    assert Decimal(str(await db.fetchval("SELECT sum(total_ttc) FROM factures WHERE id = ANY($1::int[])", ids))) == t["montant"]
    assert Decimal(str(await db.fetchval("SELECT sum(montant) FROM paiements WHERE facture_id = ANY($1::int[]) "
                                         "AND statut = 'valide'", ids))) == t["montant_paye"]

    # par section : la somme des lignes = le total
    par_section = await _requete(clients, filtres=filtres, regroupements=["section"], mesures=MESURES_FACT)
    lignes = {l["section"]: l for l in par_section["lignes"]}
    assert set(lignes) == {"SMA", "SCHA", "SSA"}
    for m in MESURES_FACT[1:]:
        assert sum(Decimal(str(l[m])) for l in lignes.values()) == t[m]
    assert Decimal(str(lignes["SCHA"]["reste_a_payer"])) == 0 and Decimal(str(lignes["SSA"]["montant_exonere"])) == 75
    # par analyse et TVA, par client
    par_analyse = await _requete(clients, filtres=filtres, regroupements=["analyse"], mesures=["montant"])
    analyses = {l["analyse"]: Decimal(str(l["montant"])) for l in par_analyse["lignes"]}
    assert analyses["TVA"] == Decimal("9.17") and sum(analyses.values()) == t["montant"]
    par_client = await _requete(clients, filtres=filtres, regroupements=["client"], mesures=["reste_a_payer"])
    assert {l["client"] for l in par_client["lignes"]} == {f"Client reporting {x}" for x in "ABCD"}
    # encaissements par mode, sur la date du mouvement (aujourd'hui)
    modes = await _requete(clients, filtres={"du": str(AUJ), "au": str(AUJ), "date_ref": "mouvement",
                                             "type_mouvement": ["Encaissement"]},
                           regroupements=["mode_paiement"], mesures=["montant_paye"])
    jour = {l["mode_paiement"]: Decimal(str(l["montant_paye"])) for l in modes["lignes"]}
    caisse = (await u.get("/api/facturation/caisse")).json()
    assert sum(jour.values()) == Decimal(str(caisse["total"]))                   # = journal de caisse du jour
    for mode, v in caisse["par_mode"].items():
        assert jour.get(mode, Decimal("0")) == Decimal(str(v["montant"]))
    # détail : une ligne par mouvement
    r = await clients["resp1"].post("/api/requetes/detail", json={"definition": {
        "jeu": "facturation", "filtres": filtres, "mesures": ["montant"]}, "page": 1, "taille": 200})
    assert r.status_code == 200, r.text
    types = sorted({l["type_mouvement"] for l in r.json()["lignes"]})
    assert types == ["Avoir", "Encaissement", "Exonération", "Facturé"]


async def test_reporting_facturation_droits_et_bilan(clients):
    for nom in ("sma1", "scha1"):
        r = await clients[nom].post("/api/requetes/executer", json={"jeu": "facturation", "mesures": ["montant"]})
        assert r.status_code == 403
    assert (await _requete(clients, "util1", mesures=["montant"]))["totaux"]["montant"] is not None
    # bilan de février 2026 : section « Facturation » = requête de la tâche 40
    b = (await clients["resp1"].post("/api/bilans/apercu", json={"mois": "2026-02"})).json()
    blocs = {x["titre"]: x for x in b["blocs"]}
    bloc = blocs["Facturation : bulletins du mois par section"]
    attendu = await _requete(clients, filtres={"du": MOIS_TEST[0], "au": MOIS_TEST[1], "date_ref": "emission_bulletin"},
                             regroupements=["section"], mesures=MESURES_FACT)
    assert bloc["resultat"]["totaux"] == attendu["totaux"]
    assert "Facturation : encaissements du mois par mode de paiement" in blocs
    assert blocs["Facturation : impayés (à la date du bilan)"]["note"].startswith("Situation")
    # bilan d'un analyste : les blocs de facturation ne sont pas calculés
    b = (await clients["sma1"].post("/api/bilans/apercu", json={"mois": "2026-02", "section": "SMA"})).json()
    bloc = next(x for x in b["blocs"] if x["titre"] == "Facturation : bulletins du mois par section")
    assert bloc["type"] == "erreur" and "réservée" in bloc["note"]


# ------------------------------------------------------------------ fonctions pures : montants (tâche 41)
import pytest  # noqa: E402

from app.services.facturation import arrondi, format_dh, montant_en_lettres, montant_ligne  # noqa: E402


@pytest.mark.parametrize("valeur,attendu", [
    (0, "zéro dirham"), (1, "un dirham"), (21, "vingt et un dirhams"), (71, "soixante et onze dirhams"),
    (80, "quatre-vingts dirhams"), (81, "quatre-vingt-un dirhams"), (99, "quatre-vingt-dix-neuf dirhams"),
    (200, "deux cents dirhams"), (201, "deux cent un dirhams"), (1000, "mille dirhams"),
    (80000, "quatre-vingt mille dirhams"), (200000, "deux cent mille dirhams"),
    (1000000, "un million de dirhams"), (2000080, "deux millions quatre-vingts dirhams"),
    (1250.5, "mille deux cent cinquante dirhams et cinquante centimes"),
    (371.01, "trois cent soixante et onze dirhams et un centime"),
])
def test_montant_en_lettres(valeur, attendu):
    assert montant_en_lettres(valeur) == attendu


def test_arrondis_au_centime():
    assert str(montant_ligne(1.5, 33.33)) == "50.00"            # 49,995 -> 50,00 (demi supérieur)
    assert str(montant_ligne(3, "0.10")) == "0.30"              # pas d'erreur de flottant
    assert montant_ligne(2, None) == 0                          # prix à renseigner
    assert str(arrondi("9.166")) == "9.17" and str(arrondi("-0.005")) == "-0.01"
    assert format_dh(1250.5) == "1 250,50 DH" and format_dh(-20) == "-20,00 DH"
