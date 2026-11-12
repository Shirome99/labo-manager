"""
État du serveur pour GET /api/health (tâche 32) : base de données, migrations, dernière sauvegarde.

La dernière sauvegarde est lue dans le journal de scripts/sauvegarde.ps1 (`sauvegarde.log` du dossier
SAUVEGARDE_DIR), dont chaque ligne commence par « AAAA-MM-JJ HH:MM:SS  » :
  « Sauvegarde terminée : <fichier> (<taille> Ko) »  → succès ;
  « ERREUR : <message> »                              → échec.
"""
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

LIGNE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.*)$")
SUCCES = re.compile(r"^Sauvegarde terminée : (?P<fichier>.+?) \((?P<taille>[\d.,]+) Ko\)$")
SEUIL_HEURES = 26          # sauvegarde quotidienne : au-delà, elle est signalée « ancienne »


def derniere_sauvegarde(dossier: Path, maintenant: datetime | None = None) -> dict:
    """Dernière sauvegarde réussie (et dernière erreur si elle est plus récente)."""
    maintenant = maintenant or datetime.now()
    journal = Path(dossier) / "sauvegarde.log"
    if not journal.exists():
        return {"statut": "absente", "message": "Aucun journal de sauvegarde (sauvegarde.ps1 jamais lancée ?)."}
    succes = erreur = None
    for brute in journal.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = LIGNE.match(brute.strip())
        if not m:
            continue
        quand = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        s = SUCCES.match(m.group(2))
        if s:
            succes = {"date": quand, "fichier": Path(s.group("fichier").strip()).name,
                      "taille_ko": float(s.group("taille").replace(",", "."))}
        elif m.group(2).startswith("ERREUR"):
            erreur = {"date": quand, "message": m.group(2)}
    if succes is None:
        return {"statut": "erreur" if erreur else "absente", "derniere_erreur": erreur,
                "message": "Aucune sauvegarde réussie dans le journal."}
    age = (maintenant - succes["date"]).total_seconds() / 3600
    statut = "ok" if age <= SEUIL_HEURES else "ancienne"
    if erreur and erreur["date"] > succes["date"]:
        statut = "erreur"
    return {"statut": statut, "derniere": succes["date"], "fichier": succes["fichier"],
            "taille_ko": succes["taille_ko"], "age_heures": round(age, 1),
            "derniere_erreur": erreur if statut == "erreur" else None}


async def etat_base(engine) -> dict:
    async with engine.connect() as c:
        r = await c.execute(text("""
            SELECT current_database() AS base,
                   (SELECT count(*) FROM schema_migrations) AS migrations,
                   (SELECT max(fichier) FROM schema_migrations) AS derniere_migration
        """))
        x = r.mappings().one()
    return {"ok": True, "base": x["base"], "migrations": x["migrations"], "derniere_migration": x["derniere_migration"]}
