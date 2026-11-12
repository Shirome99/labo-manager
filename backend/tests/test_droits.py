"""
Matrice des droits : pour chaque route sensible et chaque rôle, accès autorisé (pas de 403)
ou refusé (403) ; sans session : 401.

Chaque ligne prépare sa propre ressource. Les rôles refusés sont appelés en premier, pour
qu'un appel autorisé (qui modifie l'état) ne masque pas un refus.
"""
import itertools

import pytest

from tests.conftest import dossier

ROLES = {"admin_t": "admin", "resp1": "responsable", "util1": "user", "sma1": "sma", "scha1": "scha", "ssa1": "ssa"}
TOUS = set(ROLES)
GLOBAUX = {"admin_t", "resp1", "util1"}
RESPONSABLES = {"admin_t", "resp1"}
ADMIN = {"admin_t"}
_compteur = itertools.count(1)


async def _modele(clients):
    return [{k: b[k] for k in ("type_bloc", "titre", "requete_id", "actif") if k in b}
            for b in (await clients["admin_t"].get("/api/bilans/modele")).json()]


async def _user_id(db, nom):
    return await db.fetchval("SELECT id FROM users WHERE nom = $1", nom)


# (identifiant, rôles autorisés, préparation -> (méthode, url, corps))
async def p_admin_users(c, db):       return "GET", "/api/admin/users", None
async def p_creer_compte(c, db):      return "POST", "/api/admin/users", {"username": f"cpt{next(_compteur)}", "password": "Motdepasse2026", "role": "user"}
async def p_audit(c, db):             return "GET", "/api/admin/audit", None
async def p_tarif(c, db):             return "POST", "/api/admin/ref/tarifs", {"nom_analyse": f"Analyse droits {next(_compteur)}", "section": "SMA", "prix": 50}
async def p_reglages_fact(c, db):     return "PUT", "/api/facturation/parametres", {"taux_tva": 0, "etape_paiement": "aucune", "seuil_impayes_jours": 30}
async def _facturable(c):
    num = await dossier(c, "SMA", "recu", client_nom=f"Client droits {next(_compteur)}")
    await c["util1"].post(f"/api/facturation/echantillons/{num}/lignes", json={"analyse": "Forfait", "prix_unitaire": 50})
    return num


async def _bulletin_emis(c):
    f = (await c["util1"].post("/api/facturation/factures", json={"echantillons": [await _facturable(c)]})).json()
    return (await c["util1"].post(f"/api/facturation/factures/{f['id']}/emettre")).json()


async def p_lignes_fact(c, db):       return "POST", f"/api/facturation/echantillons/{await _facturable(c)}/lignes", {"analyse": "Frais", "prix_unitaire": 5}
async def p_bulletin(c, db):          return "POST", "/api/facturation/factures", {"echantillons": [await _facturable(c)]}
async def p_encaisser(c, db):         return "POST", f"/api/facturation/factures/{(await _bulletin_emis(c))['id']}/paiements", {"date_paiement": "2026-10-01", "montant": 1, "mode": "espèces"}
async def p_avoir(c, db):             return "POST", f"/api/facturation/factures/{(await _bulletin_emis(c))['id']}/avoir", {"motif": "droits", "montant": 1}
async def p_exonerer(c, db):          return "POST", f"/api/facturation/factures/{(await _bulletin_emis(c))['id']}/exonerer", {"type": "autre", "motif": "droits"}
async def p_annuler_paiement(c, db):
    f = await _bulletin_emis(c)
    r = await c["util1"].post(f"/api/facturation/factures/{f['id']}/paiements", json={"date_paiement": "2026-10-01", "montant": 1, "mode": "espèces"})
    return "POST", f"/api/facturation/paiements/{r.json()['paiement_id']}/annuler", {"motif": "droits"}
async def p_caisse(c, db):            return "GET", "/api/facturation/caisse", None
async def p_delai(c, db):             return "PATCH", "/api/admin/ref/delais/SMA", {"jours": 15}
async def p_modele_bilan(c, db):      return "PUT", "/api/bilans/modele", await _modele(c)
async def p_stepper(c, db):           return "PATCH", f"/api/echantillons/{await dossier(c, 'SMA', 'saisi')}/statut", {"statut": "À valider"}
async def p_supprimer(c, db):         return "DELETE", f"/api/echantillons/{await dossier(c, 'SMA', 'recu')}", None
async def p_valider(c, db):           return "POST", f"/api/traitement/SMA/{await dossier(c, 'SMA', 'soumis')}/valider", None
async def p_renvoyer(c, db):          return "POST", f"/api/traitement/SMA/{await dossier(c, 'SMA', 'soumis')}/refuser", {"motif": "test"}
async def p_emettre(c, db):           return "GET", f"/api/rapports/SMA/{await dossier(c, 'SMA', 'valide')}", None
async def p_erratum(c, db):           return "POST", f"/api/rapports/SMA/{await dossier(c, 'SMA', 'emis')}/erratum", {"motif": "test"}
async def p_fiche_sma(c, db):         return "GET", f"/api/traitement/SMA/{await dossier(c, 'SMA', 'saisi')}", None
async def p_resultats_sma(c, db):     return "GET", f"/api/resultats/SMA/{await dossier(c, 'SMA', 'saisi')}", None
async def p_etiquette_sma(c, db):     return "GET", f"/api/echantillons/{await dossier(c, 'SMA', 'recu')}/etiquette", None
async def p_facturation_sma(c, db):   return "GET", f"/api/echantillons/{await dossier(c, 'SMA', 'saisi')}/facturation", None
async def p_requete_sma(c, db):       return "POST", "/api/requetes/executer", {"jeu": "echantillons", "filtres": {"section": ["SMA"]}, "regroupements": ["statut"], "mesures": ["nb_echantillons"]}
async def p_bilan_sma(c, db):         return "POST", "/api/bilans/apercu", {"mois": "2026-09", "section": "SMA"}
async def p_bilan_global(c, db):      return "POST", "/api/bilans/apercu", {"mois": "2026-09"}
async def p_habilitation(c, db):      return "POST", "/api/habilitations", {"user_id": await _user_id(db, "sma1"), "nom_analyse": f"Analyse {next(_compteur)}", "section": "SMA", "date_qualification": "2026-01-01"}
async def p_habilitables(c, db):      return "GET", "/api/habilitations/utilisateurs", None
async def p_equipement(c, db):        return "POST", "/api/equipements", {"code": f"EQ-DROITS-{next(_compteur)}", "designation": "Étuve", "section": "SMA"}
async def p_lot_sma(c, db):           return "POST", "/api/reactifs", {"produit": f"Gélose {next(_compteur)}", "categorie": "Milieu de culture", "numero_lot": "L1", "section": "SMA", "date_peremption": "2030-01-01", "quantite_initiale": 5, "unite": "flacon"}

MATRICE = [
    ("liste des comptes", ADMIN, p_admin_users),
    ("création de compte", ADMIN, p_creer_compte),
    ("journal d'audit", ADMIN, p_audit),
    ("tarifs (référentiel)", ADMIN, p_tarif),
    ("réglages de facturation", ADMIN, p_reglages_fact),
    ("facturation : lignes", {"admin_t", "util1"}, p_lignes_fact),
    ("facturation : bulletin", {"admin_t", "util1"}, p_bulletin),
    ("facturation : encaissement", {"admin_t", "util1"}, p_encaisser),
    ("facturation : avoir", RESPONSABLES, p_avoir),
    ("facturation : exonération", RESPONSABLES, p_exonerer),
    ("facturation : annuler un encaissement", RESPONSABLES, p_annuler_paiement),
    ("facturation : journal de caisse", GLOBAUX, p_caisse),
    ("délais de traitement", ADMIN, p_delai),
    ("modèle du bilan mensuel", ADMIN, p_modele_bilan),
    ("stepper manuel de statut", ADMIN, p_stepper),
    ("suppression d'un échantillon", {"admin_t", "util1"}, p_supprimer),
    ("valider une fiche", RESPONSABLES, p_valider),
    ("renvoyer une fiche", RESPONSABLES, p_renvoyer),
    ("émettre un rapport", RESPONSABLES, p_emettre),
    ("erratum", RESPONSABLES, p_erratum),
    ("lire une fiche SMA", GLOBAUX | {"sma1"}, p_fiche_sma),
    ("lire les résultats SMA", GLOBAUX | {"sma1"}, p_resultats_sma),
    ("étiquettes SMA", GLOBAUX | {"sma1"}, p_etiquette_sma),
    ("facturation SMA (montants)", GLOBAUX, p_facturation_sma),
    ("requête filtrée sur la SMA", GLOBAUX | {"sma1"}, p_requete_sma),
    ("bilan mensuel SMA", GLOBAUX | {"sma1"}, p_bilan_sma),
    ("habilitations : saisie", RESPONSABLES, p_habilitation),
    ("habilitations : utilisateurs", RESPONSABLES, p_habilitables),
    ("équipements : création", RESPONSABLES, p_equipement),
    ("réactifs : lot SMA", RESPONSABLES | {"sma1"}, p_lot_sma),
]


@pytest.mark.parametrize("nom,autorises,preparer", MATRICE, ids=[m[0] for m in MATRICE])
async def test_matrice_des_droits(clients, db, nom, autorises, preparer):
    methode, url, corps = await preparer(clients, db)
    obtenu = {}
    for role in sorted(TOUS, key=lambda r: r in autorises):     # refusés d'abord
        r = await clients[role].request(methode, url, json=corps)
        obtenu[role] = r.status_code
    attendu_ko = {r for r in TOUS if r not in autorises}
    refuses = {r for r, s in obtenu.items() if s == 403}
    assert refuses == attendu_ko, f"{nom} : codes {obtenu}"
    assert all(s < 500 for s in obtenu.values()), obtenu
    assert any(200 <= obtenu[r] < 300 for r in autorises), f"{nom} : aucun appel autorisé n'a abouti {obtenu}"
    r = await clients[None].request(methode, url, json=corps)
    assert r.status_code == 401


async def test_role_de_section_ne_voit_que_sa_section(clients):
    for s in ("SMA", "SCHA", "SSA"):
        await dossier(clients, s, "recu")
    for nom, sec in (("sma1", "SMA"), ("scha1", "SCHA"), ("ssa1", "SSA")):
        lignes = (await clients[nom].get("/api/echantillons")).json()
        assert lignes and all(e[sec.lower()] == "Yes" for e in lignes)
        # export : mêmes limites
        r = await clients[nom].get("/api/echantillons/export", params={"format": "csv"})
        assert r.status_code == 200 and len(r.text.strip().splitlines()) - 1 == len(lignes)
        # filtre explicite sur une autre section
        autre = "SSA" if sec != "SSA" else "SMA"
        r = await clients[nom].get("/api/echantillons", params={"section": autre})
        assert r.status_code == 403 or r.json() == []
