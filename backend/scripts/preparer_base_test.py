"""
Prépare la base de test (tâches 27 et 28) : la supprime, la reconstruit de zéro par les
migrations, puis crée un compte de test par rôle et leurs habilitations.

Utilisé par les tests du backend (tests/conftest.py) et par les tests de bout en bout de
l'interface (frontend/e2e, Playwright). Refuse de toucher à la base de l'application.

Usage (depuis backend/) :
    python scripts/preparer_base_test.py              # base labo_test
    python scripts/preparer_base_test.py --base autre_base_de_test
"""
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import asyncpg
import bcrypt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import migrer  # noqa: E402

MOT_DE_PASSE = "Testlims2026"
COMPTES = {           # nom -> rôle
    "admin_t": "admin",
    "resp1": "responsable",
    "resp2": "responsable",
    "util1": "user",
    "sma1": "sma",
    "scha1": "scha",
    "ssa1": "ssa",
}
# Analyses pour lesquelles les analystes (et responsables) sont habilités
HABILITATIONS = {
    "SMA": ["Escherichia coli", "Staphylocoque à coagulase positive", "Salmonella", "FMAT"],
    "SCHA": ["Histamine", "ABVT"],
    "SSA": ["Brucellose"],
}
SECTIONS_HABILITEES = {"sma1": ["SMA"], "scha1": ["SCHA"], "ssa1": ["SSA"], "resp1": ["SMA", "SCHA", "SSA"],
                       "resp2": ["SMA", "SCHA", "SSA"], "admin_t": ["SMA", "SCHA", "SSA"]}


def verifier_nom(base: str) -> None:
    """Garde-fou : la base supprimée doit être une base de test (nom contenant « test »)."""
    if "test" not in base.lower() or base in ("labo", "postgres", "template0", "template1"):
        raise SystemExit(f"Base de test refusée : {base} (son nom doit contenir « test » ; jamais la base de l'application).")


async def preparer(base: str = "labo_test") -> None:
    verifier_nom(base)
    conn = await asyncpg.connect(migrer.url("postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)')
    finally:
        await conn.close()
    await migrer.creer_base(base)
    if await migrer.migrer(base, dry_run=False) != 0:
        raise SystemExit("Échec des migrations de la base de test.")

    conn = await asyncpg.connect(migrer.url(base))
    try:
        h = bcrypt.hashpw(MOT_DE_PASSE.encode(), bcrypt.gensalt(rounds=4)).decode()
        ids = {}
        for nom, role in COMPTES.items():
            ids[nom] = await conn.fetchval(
                "INSERT INTO users (nom, email, mot_de_passe, role, created_at) VALUES ($1, $2, $3, $4, now()) RETURNING id",
                nom, f"{nom}@test.local", h, role)
        for nom, secs in SECTIONS_HABILITEES.items():
            for s in secs:
                for a in HABILITATIONS[s]:
                    await conn.execute(
                        "INSERT INTO habilitations (user_id, nom_analyse, section, date_qualification, habilite_par) "
                        "VALUES ($1, $2, $3, $4, 'tests')", ids[nom], a, s, date(2020, 1, 1))
    finally:
        await conn.close()
    print(f"Base de test {base} prête : {len(COMPTES)} comptes (mot de passe {MOT_DE_PASSE}).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--base", default="labo_test")
    asyncio.run(preparer(ap.parse_args().base))
