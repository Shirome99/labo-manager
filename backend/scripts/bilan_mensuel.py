"""
Génère le bilan mensuel en ligne de commande (tâche planifiée du 1er du mois) : même calcul et
même archivage que l'écran « Bilan mensuel » (table bilans_mensuels, nouvelle version à chaque
génération, source « script »). Voir docs/bilan_mensuel.md.

Usage (depuis backend/) :
    python scripts/bilan_mensuel.py                         # mois précédent, toutes sections, PDF + Excel
    python scripts/bilan_mensuel.py --mois 2026-09 --section SMA --format pdf
    python scripts/bilan_mensuel.py --mois 2026-09 --sortie D:\\Bilans   # copie aussi les fichiers
    python scripts/bilan_mensuel.py --base labo_test ...      # autre base du même serveur (essais)

Code de sortie : 0 si tout est généré, 1 sinon.
"""
import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
UTILISATEUR = "script:bilan_mensuel"


def _arguments():
    p = argparse.ArgumentParser(description="Bilan mensuel du LIMS (PDF et/ou Excel, archivé en base).")
    p.add_argument("--mois", help="mois AAAA-MM (défaut : mois précédent)")
    p.add_argument("--section", choices=["SMA", "SCHA", "SSA"], help="une section (défaut : toutes)")
    p.add_argument("--format", choices=["pdf", "xlsx", "les-deux"], default="les-deux")
    p.add_argument("--sortie", help="dossier où copier les fichiers générés (facultatif)")
    p.add_argument("--base", help="autre base du même serveur PostgreSQL (essais)")
    return p.parse_args()


async def main() -> int:
    args = _arguments()
    if args.base:   # avant l'import de l'application, qui crée la connexion
        from app.core.config import settings
        os.environ["DATABASE_URL"] = settings.DATABASE_URL.rsplit("/", 1)[0] + "/" + args.base
        settings.DATABASE_URL = os.environ["DATABASE_URL"]
    from app.core.db import SessionLocal, engine, transmettre_utilisateur
    from app.models import AuditLog
    from app.services import bilan as service

    try:
        mois = service.lire_mois(args.mois) if args.mois else service.mois_precedent(date.today())
    except ValueError:
        print(f"Mois invalide : {args.mois} (attendu AAAA-MM).", file=sys.stderr)
        return 1
    formats = ["pdf", "xlsx"] if args.format == "les-deux" else [args.format]
    user = {"id": 0, "username": UTILISATEUR, "role": "admin"}
    code = 0
    try:
        for fmt in formats:
            async with SessionLocal() as db:
                transmettre_utilisateur(db, UTILISATEUR)
                try:
                    r = await service.generer(db, mois, args.section, fmt, user, source="script")
                    db.add(AuditLog(utilisateur=UTILISATEUR, action="BILAN_MENSUEL", table_cible="bilans_mensuels",
                                    cle=str(r["id"]), details=f"{mois:%Y-%m} {args.section or 'toutes'} {fmt} v{r['version']} (script)"))
                    await db.commit()
                except Exception as e:  # noqa: BLE001 — message clair pour le journal de la tâche planifiée
                    await db.rollback()
                    print(f"ÉCHEC {fmt} : {e}", file=sys.stderr)
                    code = 1
                    continue
            ligne = f"{r['nom_fichier']} : bilan n° {r['id']}, version {r['version']}, SHA-256 {r['sha256']}"
            if args.sortie:
                dossier = Path(args.sortie)
                dossier.mkdir(parents=True, exist_ok=True)
                (dossier / r["nom_fichier"]).write_bytes(r["contenu"])
                ligne += f", copié dans {dossier / r['nom_fichier']}"
            print(ligne)
    finally:
        await engine.dispose()
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
