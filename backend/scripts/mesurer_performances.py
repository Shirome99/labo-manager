"""
Mesure les temps de réponse des écrans principaux (tâche 30), sur un serveur lancé.

Pour chaque appel : médiane et maximum de N essais (après un appel de chauffe), comparés à
l'objectif (500 ms pour les listes, le tableau de bord et les notifications ; 10 s pour le
bilan mensuel). Code de sortie 1 si un objectif n'est pas atteint.

Usage (depuis backend/, serveur de test lancé sur une base remplie) :
    python scripts/serveur_test.py --sans-preparation --port 8020     # dans une autre fenêtre
    python scripts/mesurer_performances.py [--url http://127.0.0.1:8020] [--essais 5]
"""
import argparse
import statistics
import sys
import time
from datetime import date

import httpx

MOT_DE_PASSE = "Testlims2026"


def mois_precedent() -> str:
    d = date.today().replace(day=1)
    return f"{d.year - (d.month == 1)}-{(d.month - 2) % 12 + 1:02d}"


def scenarios():
    m = mois_precedent()
    req = {"jeu": "echantillons", "filtres": {"periode": "annee_en_cours"}, "regroupements": ["type", "mois"],
           "mesures": ["nb_echantillons", "taux_non_conformite", "delai_moyen"]}
    return [
        # (libellé, compte, méthode, url, corps, objectif en ms)
        ("Liste des échantillons (1re page)", "util1", "GET", "/api/echantillons?page=1&taille=50", None, 500),
        ("Liste SMA filtrée (fabricant)", "util1", "GET", "/api/echantillons?page=1&taille=50&section=SMA&fabricant=a", None, 500),
        ("Liste triée par réception", "util1", "GET", "/api/echantillons?page=40&taille=50&tri=date_reception&ordre=asc", None, 500),
        ("Recherche texte « beurre »", "util1", "GET", "/api/echantillons?page=1&taille=50&q=beurre", None, 500),
        ("Sélecteur d'échantillon (recherche)", "sma1", "GET", "/api/echantillons?page=1&taille=50&section=SMA&q=2024-SMA-01", None, 500),
        ("Liste d'un analyste (SMA)", "sma1", "GET", "/api/echantillons?page=1&taille=50", None, 500),
        ("Compteurs du menu", "util1", "GET", "/api/echantillons/stats", None, 500),
        ("Tableau de bord (responsable)", "resp1", "GET", "/api/echantillons/dashboard", None, 500),
        ("Tableau de bord (analyste SMA)", "sma1", "GET", "/api/echantillons/dashboard", None, 500),
        ("Notifications (responsable)", "resp1", "GET", "/api/notifications", None, 500),
        ("Notifications (analyste SMA)", "sma1", "GET", "/api/notifications", None, 500),
        ("Mon travail (responsable)", "resp1", "GET", "/api/travail", None, 500),
        ("Journal d'audit (1re page)", "admin_t", "GET", "/api/admin/audit?limite=50", None, 500),
        ("Journal d'audit filtré (table, n°)", "admin_t", "GET", "/api/admin/audit?limite=50&table=traitement_sma&num=SMA-01", None, 500),
        ("Requête type × mois (année)", "resp1", "POST", "/api/requetes/executer", req, 2000),
        ("Détail d'une requête (1re page)", "resp1", "POST", "/api/requetes/detail", {"definition": req, "page": 1, "taille": 50}, 500),
        ("Bilan mensuel : aperçu", "resp1", "POST", "/api/bilans/apercu", {"mois": m}, 10000),
        ("Bilan mensuel : PDF archivé", "resp1", "POST", "/api/bilans/generer", {"mois": m, "format": "pdf"}, 10000),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Temps de réponse des écrans principaux.")
    ap.add_argument("--url", default="http://127.0.0.1:8020")
    ap.add_argument("--essais", type=int, default=5)
    a = ap.parse_args()
    clients = {}
    echecs = 0
    print(f"{'Appel':<38} {'statut':>6} {'médiane':>9} {'max':>9} {'objectif':>9}")
    for lib, compte, methode, url, corps, objectif in scenarios():
        if compte not in clients:
            c = httpx.Client(base_url=a.url, timeout=120)
            r = c.post("/api/auth/login", json={"username": compte, "password": MOT_DE_PASSE})
            r.raise_for_status()
            clients[compte] = c
        c = clients[compte]
        c.request(methode, url, json=corps)               # chauffe
        durees, statut = [], None
        for _ in range(a.essais if objectif < 5000 else max(2, a.essais // 2)):
            t = time.perf_counter()
            r = c.request(methode, url, json=corps)
            durees.append((time.perf_counter() - t) * 1000)
            statut = r.status_code
        med = statistics.median(durees)
        ok = statut == 200 and med <= objectif
        echecs += not ok
        print(f"{lib:<38} {statut:>6} {med:>7.0f} ms {max(durees):>6.0f} ms {objectif:>6} ms  {'OK' if ok else 'NON ATTEINT'}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
