"""
Initialise une base de DÉMONSTRATION (Neon, ou base locale vide) : migrations, comptes, données fictives.

- applique toutes les migrations (scripts/migrer.py) ;
- crée le compte admin (nom DEMO_ADMIN, « admin » par défaut ; mot de passe DEMO_ADMIN_MDP, obligatoire) ;
- crée un compte de démonstration par rôle (demo_responsable, demo_accueil, demo_sma, demo_scha,
  demo_ssa ; mot de passe DEMO_MDP, obligatoire) et leurs habilitations ;
- ajoute des fabricants et organismes INVENTÉS, puis une trentaine d'échantillons fictifs répartis sur
  les 3 sections et tous les statuts, en passant par l'API (mêmes règles métier que l'application :
  numérotation, double regard, rapport figé…).

Aucun mot de passe n'est écrit dans le code ni dans un fichier. Relançable : les comptes existants
sont gardés, et les échantillons ne sont créés que si la base n'en contient aucun.

Usage le plus simple (depuis backend/, venv avec requirements-dev.txt, pour httpx) :
    python scripts/init_demo.py
Le script demande alors, sans les afficher, ce qui n'est pas déjà défini : la chaîne de connexion
Neon (DATABASE_URL), le mot de passe du compte admin (DEMO_ADMIN_MDP) et celui des comptes demo_*
(DEMO_MDP). Il affiche la base visée et demande confirmation avant d'écrire.

Sans saisie (variables d'environnement, PowerShell — apostrophes conseillées) :
    $env:DATABASE_URL = '<chaîne Neon>' ; $env:DEMO_ADMIN_MDP = '…' ; $env:DEMO_MDP = '…'
    python scripts/init_demo.py --oui           # --oui : pas de confirmation
    python scripts/init_demo.py --creer         # base locale : la crée si elle n'existe pas
"""
import argparse
import asyncio
import getpass
import os
import re
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

INTERACTIF = sys.stdin.isatty()


def _chaine_collee(texte: str) -> str:
    """Chaîne Neon collée telle quelle : retire guillemets et préfixe `psql`, garde l'URL."""
    texte = texte.strip().strip("'\"")
    m = re.search(r"postgres(?:ql)?(?:\+asyncpg)?://\S+", texte)
    return m.group(0).strip("'\"") if m else texte


# La chaîne de connexion doit être connue AVANT d'importer la configuration de l'application.
if (__name__ == "__main__" and not os.environ.get("DATABASE_URL") and INTERACTIF
        and not {"-h", "--help"} & set(sys.argv)):
    print("DATABASE_URL n'est pas défini dans cette fenêtre.")
    saisie = getpass.getpass("Collez la chaîne de connexion Neon (rien ne s'affiche, c'est normal) puis Entrée.\n"
                             "Entrée seule = base locale de backend/.env : ")
    if saisie.strip():
        os.environ["DATABASE_URL"] = _chaine_collee(saisie)

# L'application est importée en mode démonstration (clé de travail aléatoire si absente : seuls les
# comptes et les données restent en base, aucun jeton émis ici n'est réutilisé)
os.environ.setdefault("ENVIRONNEMENT", "demo")
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
os.environ.setdefault("HABILITATIONS_OBLIGATOIRES", "1")

import asyncpg  # noqa: E402
import bcrypt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402
from app.core.security import MDP_REGLE, ROLE_SECTION, mot_de_passe_conforme  # noqa: E402
from scripts import migrer  # noqa: E402

BASES_INTERDITES = {"labo", "postgres", "template0", "template1"}
COMPTES_DEMO = {"demo_responsable": "responsable", "demo_accueil": "user",
                "demo_sma": "sma", "demo_scha": "scha", "demo_ssa": "ssa"}
ANALYSES = {"SMA": ["Escherichia coli", "Salmonella", "FMAT", "Staphylocoque à coagulase positive"],
            "SCHA": ["Histamine", "ABVT"], "SSA": ["Brucellose"]}
FABRICANTS = [("Laiterie des Collines (fictif)", "Ville A"), ("Conserverie Atlantique Démo", "Ville B"),
              ("Fromagerie du Plateau (fictif)", "Ville C"), ("Abattoir Exemple", "Ville D"),
              ("Miellerie Démonstration", "Ville E"), ("Provenderie Modèle (fictif)", "Ville F")]
ORGANISMES = [("Service vétérinaire fictif Nord", "Ville A"), ("Inspection démo Sud", "Ville B"),
              ("Contrôle officiel (exemple)", "Ville C")]
NATURES = {"SMA": ["Fromage frais", "Lait cru", "Viande hachée", "Crème glacée"],
           "SCHA": ["Thon en conserve", "Sardines", "Miel"],
           "SSA": ["Sérum bovin", "Sérum ovin", "Prélèvement apicole"]}
# Répartition par statut, par section (Reçu, En cours, À valider, Validé, Rapport émis) : 30 échantillons
ETAPES = ["recu", "saisi", "soumis", "valide", "emis"]
PAR_SECTION = {"SMA": [3, 2, 2, 2, 3], "SCHA": [2, 2, 2, 2, 2], "SSA": [2, 2, 1, 1, 2]}


def _defaut_mdp(mdp: str) -> str:
    """Ce qui manque à un mot de passe, sans jamais l'afficher."""
    manque = []
    if len(mdp) < 10:
        manque.append(f"{len(mdp)} caractère(s) seulement")
    if not any(c.isalpha() for c in mdp):
        manque.append("aucune lettre")
    if not any(c.isdigit() for c in mdp):
        manque.append("aucun chiffre")
    return ", ".join(manque) or "non conforme"


def mot_de_passe(var: str, compte: str) -> str:
    """Mot de passe de la variable `var`, sinon demandé au clavier (masqué, avec confirmation)."""
    mdp = os.environ.get(var)
    if mdp:
        if mot_de_passe_conforme(mdp):
            return mdp
        raise SystemExit(f"La variable {var} est définie mais refusée ({_defaut_mdp(mdp)}). {MDP_REGLE}\n"
                         f"Corrigez-la, ou supprimez-la pour que le mot de passe soit demandé : "
                         f"Remove-Item Env:{var}")
    if not INTERACTIF:
        raise SystemExit(f"Variable {var} absente (mot de passe {compte}). {MDP_REGLE}")
    while True:
        mdp = getpass.getpass(f"Mot de passe {compte} (au moins 10 caractères, lettres et chiffres) : ")
        if not mot_de_passe_conforme(mdp):
            print(f"  Refusé : {_defaut_mdp(mdp)}. Recommencez.")
            continue
        if getpass.getpass("  Confirmez : ") != mdp:
            print("  Les deux saisies sont différentes. Recommencez.")
            continue
        return mdp


async def comptes(conn, admin: str, mdp_admin: str, mdp_demo: str) -> None:
    await conn.execute("SELECT set_config('lims.utilisateur', 'init_demo', false)")
    for nom, role, mdp in [(admin, "admin", mdp_admin)] + [(n, r, mdp_demo) for n, r in COMPTES_DEMO.items()]:
        uid = await conn.fetchval("SELECT id FROM users WHERE nom = $1", nom)
        if uid:
            print(f"  compte {nom} : existe déjà (inchangé)")
            continue
        h = bcrypt.hashpw(mdp.encode(), bcrypt.gensalt()).decode()
        uid = await conn.fetchval(
            "INSERT INTO users (nom, email, mot_de_passe, role, created_at) VALUES ($1, $2, $3, $4, now()) RETURNING id",
            nom, f"{nom}@demo.invalid", h, role)
        sections = ANALYSES if role in ("admin", "responsable") else (
            {ROLE_SECTION[role]: ANALYSES[ROLE_SECTION[role]]} if role in ROLE_SECTION else {})
        for s, analyses in sections.items():
            for a in analyses:
                await conn.execute(
                    "INSERT INTO habilitations (user_id, nom_analyse, section, date_qualification, habilite_par) "
                    "VALUES ($1, $2, $3, $4, 'init_demo') ON CONFLICT DO NOTHING", uid, a, s, date(2024, 1, 1))
        print(f"  compte {nom} ({role}) créé")


async def referentiels(conn) -> None:
    for lib, ville in FABRICANTS:
        if not await conn.fetchval("SELECT 1 FROM ref_fabricants WHERE libelle = $1", lib):
            await conn.execute("INSERT INTO ref_fabricants (libelle, ville) VALUES ($1, $2)", lib, ville)
    for lib, ville in ORGANISMES:
        if not await conn.fetchval("SELECT 1 FROM ref_organismes WHERE libelle = $1", lib):
            await conn.execute("INSERT INTO ref_organismes (libelle, ville) VALUES ($1, $2)", lib, ville)


async def echantillons(admin: str, mdp_admin: str, mdp_demo: str) -> int:
    import httpx
    from app.main import app

    async def client(nom, mdp):
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo")
        r = await c.post("/api/auth/login", json={"username": nom, "password": mdp})
        r.raise_for_status()
        return c

    accueil = await client("demo_accueil", mdp_demo)
    resp = await client("demo_responsable", mdp_demo)
    analystes = {s: await client(f"demo_{s.lower()}", mdp_demo) for s in ANALYSES}

    def ok(r, attendu=(200, 201)):
        if r.status_code not in attendu:
            raise SystemExit(f"Échec {r.request.method} {r.request.url.path} : {r.status_code} {r.text}")
        return r

    n, aujourd_hui = 0, date.today()
    for section, quantites in PAR_SECTION.items():
        i = 0
        for etape, combien in zip(ETAPES, quantites):
            for _ in range(combien):
                i += 1
                recu = datetime.combine(aujourd_hui - timedelta(days=70 - 5 * i - len(section)), datetime.min.time()) \
                    + timedelta(hours=9)
                analyse_le = (recu + timedelta(days=1)).date().isoformat()
                corps = {s.lower(): ("Yes" if s == section else "No") for s in ANALYSES}
                corps.update({
                    "date_reception": recu.strftime("%Y-%m-%dT%H:%M"),
                    "nature": NATURES[section][i % len(NATURES[section])],
                    "fabricant": FABRICANTS[(i + len(section)) % len(FABRICANTS)][0],
                    "organisme_preleveur": ORGANISMES[i % len(ORGANISMES)][0],
                    "nom_client": FABRICANTS[(i + len(section)) % len(FABRICANTS)][0],
                    f"nbre_prlvmts_{section.lower()}": 1 + i % 3,
                })
                if section == "SMA" and etape == "recu" and i == 1:
                    corps.update({"decision_reception": "Refusé", "motif_decision": "Contenant endommagé (exemple)",
                                  "nc_contenant": True})
                num = ok(await accueil.post("/api/echantillons", json=corps)).json()["num_echantillon"]
                n += 1
                if etape != "recu":
                    a = analystes[section]
                    analyse = ANALYSES[section][i % len(ANALYSES[section])]
                    fiche = {"num_echantillon": num, "date_mise_en_analyse": analyse_le}
                    ligne = {"analyse_effectuee": analyse, "date_analyse": analyse_le}
                    if section == "SMA":
                        fiche["conformite"] = "Conforme"
                        ligne.update({"rp1": "<10", "rp2": "<10", "rp3": str(10 + i), "rp4": "<10", "rp5": "<10"})
                    elif section == "SCHA":
                        fiche["conformite"] = "Conforme"
                        ligne.update({"rp1": str(8 + i), "moyenne": str(8 + i), "conclusion": "Conforme"})
                    else:
                        ligne.update({"resultat_analyse": "Négatif", "nbre_positifs": 0, "nbre_negatif": 3 + i})
                    ok(await a.post(f"/api/traitement/{section}", json=fiche))
                    ok(await a.put(f"/api/resultats/{section}/{num}", json=[ligne]))
                if etape in ("soumis", "valide", "emis"):
                    ok(await analystes[section].post(f"/api/traitement/{section}/{num}/soumettre"))
                if etape in ("valide", "emis"):
                    ok(await resp.post(f"/api/traitement/{section}/{num}/valider"))
                if etape == "emis":
                    ok(await resp.get(f"/api/rapports/{section}/{num}"))
                print(f"  {num} : {etape}")
    for c in [accueil, resp, *analystes.values()]:
        await c.aclose()
    return n


async def principal(creer: bool, oui: bool = False) -> int:
    base = settings.nom_base
    if base in BASES_INTERDITES:
        raise SystemExit(f"Base refusée : {base} (jamais la base du laboratoire ; utilisez une base de démonstration).\n"
                         "Définissez DATABASE_URL avec la chaîne Neon, ou lancez le script sans et collez-la.")
    hote = urlsplit(migrer.url()).hostname or "?"
    source = "DATABASE_URL" if os.environ.get("DATABASE_URL") else "backend/.env"
    print(f"Base visée : {base} sur {hote} (connexion lue dans {source}).")
    if INTERACTIF and not oui:
        if input("Continuer ? (o/N) ").strip().lower() not in ("o", "oui", "y", "yes"):
            raise SystemExit("Annulé : rien n'a été écrit.")

    admin = os.environ.get("DEMO_ADMIN", "admin")
    mdp_admin = mot_de_passe("DEMO_ADMIN_MDP", f"du compte {admin}")
    mdp_demo = mot_de_passe("DEMO_MDP", "des comptes demo_*")

    print(f"Base de démonstration : {base}")
    if creer:
        await migrer.creer_base(base)
    if await migrer.migrer(None, dry_run=False) != 0:
        raise SystemExit("Échec des migrations.")

    conn = await asyncpg.connect(migrer.url(), **settings.connect_args)
    try:
        await comptes(conn, admin, mdp_admin, mdp_demo)
        await referentiels(conn)
        deja = await conn.fetchval("SELECT count(*) FROM echantillons")
    finally:
        await conn.close()

    if deja:
        print(f"La base contient déjà {deja} échantillon(s) : aucune donnée fictive ajoutée.")
        return 0
    n = await echantillons(admin, mdp_admin, mdp_demo)
    print(f"Démonstration prête : {n} échantillons fictifs, comptes {admin}, {', '.join(COMPTES_DEMO)}.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--creer", action="store_true", help="crée la base si elle n'existe pas (base locale)")
    ap.add_argument("--oui", action="store_true", help="ne pas demander confirmation avant d'écrire")
    a = ap.parse_args()
    try:
        sys.exit(asyncio.run(principal(a.creer, a.oui)))
    except (OSError, asyncpg.PostgresError) as e:
        hote = urlsplit(migrer.url()).hostname or "?"
        if isinstance(e, asyncpg.InvalidPasswordError):
            cause = "mot de passe refusé : recopiez la chaîne depuis Neon (bouton Connect)"
        elif isinstance(e, asyncpg.InvalidCatalogNameError):
            cause = "base introuvable : vérifiez le nom de la base à la fin de la chaîne"
        elif isinstance(e, OSError):
            cause = "serveur injoignable : vérifiez l'hôte de la chaîne et votre connexion internet"
        else:
            cause = f"{type(e).__name__} : {e}"
        raise SystemExit(f"Connexion impossible à {hote} ({cause}). Rien n'a été écrit ou l'opération a été annulée.")
