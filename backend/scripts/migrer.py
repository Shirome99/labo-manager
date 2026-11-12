"""
Migrations de la base, suivies dans la table `schema_migrations` (tâche 26).

Applique, dans l'ordre des numéros, les fichiers `backend/migrations/NNN_*.sql` qui ne
sont pas encore enregistrés dans `schema_migrations`, chacun dans sa propre transaction
(la migration et son enregistrement réussissent ou échouent ensemble).

La connexion reprend `settings.DATABASE_URL` (fichier .env, variable d'environnement ou
valeur par défaut de app/core/config.py) : aucun mot de passe en ligne de commande.

Usage (depuis backend/, venv activé) :
    python scripts/migrer.py                         # applique les migrations en attente sur la base configurée
    python scripts/migrer.py --dry-run               # liste ce qui serait appliqué, n'écrit rien
    python scripts/migrer.py --etat                  # état de chaque migration (appliquée, en attente, modifiée)
    python scripts/migrer.py --base labo_test        # autre base du même serveur
    python scripts/migrer.py --base labo_test --creer   # crée la base si elle n'existe pas, puis migre
    python scripts/migrer.py --marquer tout          # enregistre toutes les migrations comme déjà appliquées, sans les exécuter
    python scripts/migrer.py --marquer 012_paiement_analyses.sql   # idem pour un seul fichier
    python scripts/migrer.py --requete "SELECT count(*) FROM rapports_emis"   # lecture seule

Sécurités :
  - si une migration déjà appliquée a été modifiée depuis (empreinte SHA-256 différente),
    le script le signale et s'arrête sans rien appliquer (code 2) ;
  - sur une base qui contient déjà des données mais pas encore `schema_migrations`
    (base créée avant la tâche 26), le script refuse de rejouer les migrations : il faut
    d'abord enregistrer celles qui y sont déjà passées avec `--marquer`.
"""
import argparse
import asyncio
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

DOSSIER = Path(__file__).resolve().parents[1] / "migrations"
MOTIF = re.compile(r"^\d{3}_[\w.-]+\.sql$")

CREER_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    fichier     VARCHAR(200) PRIMARY KEY,
    empreinte   CHAR(64)     NOT NULL,
    applique_le TIMESTAMPTZ  NOT NULL DEFAULT now(),
    mode        VARCHAR(10)  NOT NULL DEFAULT 'appliquee'
                CHECK (mode IN ('appliquee', 'marquee'))
);
COMMENT ON TABLE schema_migrations IS
    'Migrations SQL appliquées (scripts/migrer.py) : fichier, empreinte SHA-256, date ; mode « marquee » = enregistrée sans exécution';
"""


class ErreurMigration(Exception):
    pass


def url(base: str | None = None) -> str:
    # Chaîne Neon acceptée telle quelle : paramètres SSL retirés (passés par settings.connect_args)
    u = urlsplit(settings.url_asyncpg)
    return urlunsplit(u._replace(path="/" + base)) if base else settings.url_asyncpg


def nom_base(base: str | None) -> str:
    return base or settings.nom_base


def empreinte(chemin: Path) -> str:
    # Fins de ligne normalisées : une copie CRLF / LF du même fichier garde la même empreinte
    return hashlib.sha256(chemin.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def fichiers() -> list[Path]:
    return sorted((p for p in DOSSIER.iterdir() if MOTIF.match(p.name)), key=lambda p: p.name)


async def table_existe(conn, nom: str) -> bool:
    return await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{nom}")


async def appliquees(conn) -> dict[str, str]:
    if not await table_existe(conn, "schema_migrations"):
        return {}
    return {r["fichier"]: r["empreinte"] for r in await conn.fetch("SELECT fichier, empreinte FROM schema_migrations")}


async def creer_base(base: str) -> None:
    conn = await asyncpg.connect(url("postgres"), **settings.connect_args)
    try:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", base):
            return
        await conn.execute(f'CREATE DATABASE "{base}" ENCODING \'UTF8\' TEMPLATE template0')
        print(f"Base {base} créée.")
    finally:
        await conn.close()


def controler(faites: dict[str, str], disque: list[Path]) -> list[Path]:
    """Vérifie les empreintes des migrations déjà appliquées ; renvoie celles en attente."""
    par_nom = {p.name: p for p in disque}
    modifiees = [n for n, h in faites.items() if n in par_nom and empreinte(par_nom[n]) != h]
    if modifiees:
        raise ErreurMigration(
            "Migration(s) déjà appliquée(s) modifiée(s) depuis : " + ", ".join(sorted(modifiees))
            + ".\nUne migration appliquée ne doit plus changer : remettez le fichier d'origine et "
              "écrivez une nouvelle migration numérotée à la suite.")
    for n in sorted(set(faites) - set(par_nom)):
        print(f"Attention : {n} est enregistrée dans schema_migrations mais absente du dossier migrations/.")
    return [p for p in disque if p.name not in faites]


async def migrer(base: str | None, dry_run: bool) -> int:
    conn = await asyncpg.connect(url(base), **settings.connect_args)
    try:
        faites = await appliquees(conn)
        if not faites and await table_existe(conn, "echantillons"):
            raise ErreurMigration(
                f"La base {nom_base(base)} contient déjà des tables mais aucune migration n'y est enregistrée.\n"
                "Enregistrez d'abord les migrations déjà passées : python scripts/migrer.py "
                + (f"--base {base} " if base else "") + "--marquer tout")
        attente = controler(faites, fichiers())
        if not attente:
            print(f"Base {nom_base(base)} à jour : aucune migration à appliquer ({len(faites)} déjà appliquées).")
            return 0
        if dry_run:
            print(f"Base {nom_base(base)} : {len(attente)} migration(s) à appliquer (dry-run, rien n'est écrit) :")
            for p in attente:
                print("  -", p.name)
            return 0
        await conn.execute(CREER_TABLE)
        for p in attente:
            sql = p.read_text(encoding="utf-8")
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (fichier, empreinte) VALUES ($1, $2)", p.name, empreinte(p))
            except Exception as e:
                raise ErreurMigration(f"Échec de {p.name} (annulée, les précédentes restent appliquées) : {e}") from e
            print(f"Appliquée : {p.name}")
        print(f"Base {nom_base(base)} : {len(attente)} migration(s) appliquée(s).")
        return 0
    finally:
        await conn.close()


async def marquer(base: str | None, cible: str) -> int:
    disque = fichiers()
    choix = disque if cible == "tout" else [p for p in disque if p.name == Path(cible).name]
    if not choix:
        raise ErreurMigration(f"Fichier de migration introuvable dans migrations/ : {cible}")
    conn = await asyncpg.connect(url(base), **settings.connect_args)
    try:
        await conn.execute(CREER_TABLE)
        controler(await appliquees(conn), disque)
        n = 0
        for p in choix:
            n += (await conn.execute(
                "INSERT INTO schema_migrations (fichier, empreinte, mode) VALUES ($1, $2, 'marquee') "
                "ON CONFLICT (fichier) DO NOTHING", p.name, empreinte(p))).endswith(" 1")
        print(f"Base {nom_base(base)} : {n} migration(s) enregistrée(s) comme déjà appliquée(s), sans exécution.")
        return 0
    finally:
        await conn.close()


async def etat(base: str | None) -> int:
    conn = await asyncpg.connect(url(base), **settings.connect_args)
    try:
        lignes = {r["fichier"]: r for r in await conn.fetch("SELECT * FROM schema_migrations")} \
            if await table_existe(conn, "schema_migrations") else {}
    finally:
        await conn.close()
    code = 0
    for p in fichiers():
        r = lignes.get(p.name)
        if r is None:
            txt = "en attente"
        elif r["empreinte"] != empreinte(p):
            txt, code = "MODIFIÉE depuis l'application", 2
        else:
            txt = f"{'appliquée' if r['mode'] == 'appliquee' else 'marquée'} le {r['applique_le']:%d/%m/%Y %H:%M}"
        print(f"  {p.name:<40} {txt}")
    return code


async def requete(sql: str, base: str | None = None) -> int:
    """Exécute une requête en lecture seule et affiche les lignes."""
    conn = await asyncpg.connect(url(base), **settings.connect_args)
    try:
        async with conn.transaction(readonly=True):
            for ligne in await conn.fetch(sql):
                print(dict(ligne))
    finally:
        await conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Migrations de la base LIMS (voir l'aide en tête du fichier).")
    ap.add_argument("--base", help="autre base du même serveur (ex. labo_test)")
    ap.add_argument("--dry-run", action="store_true", help="liste les migrations à appliquer sans rien écrire")
    ap.add_argument("--creer", action="store_true", help="crée la base si elle n'existe pas")
    ap.add_argument("--etat", action="store_true", help="affiche l'état de chaque migration")
    ap.add_argument("--marquer", metavar="FICHIER|tout", help="enregistre sans exécuter")
    ap.add_argument("--requete", metavar="SQL", help="requête en lecture seule")
    a = ap.parse_args(argv)
    try:
        if a.creer:
            asyncio.run(creer_base(nom_base(a.base)))
        if a.requete:
            return asyncio.run(requete(a.requete, a.base))
        if a.etat:
            return asyncio.run(etat(a.base))
        if a.marquer:
            return asyncio.run(marquer(a.base, a.marquer))
        return asyncio.run(migrer(a.base, a.dry_run))
    except ErreurMigration as e:
        print(f"ARRÊT : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
