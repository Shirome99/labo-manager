"""État du serveur (tâche 32) : /api/health, lecture du journal de sauvegarde.ps1."""
from datetime import datetime

from app.core.config import VERSION
from app.services.sante import derniere_sauvegarde

MAINTENANT = datetime(2026, 10, 26, 12, 0, 0)


def _journal(tmp_path, lignes):
    (tmp_path / "sauvegarde.log").write_text("\ufeff" + "\n".join(lignes) + "\n", encoding="utf-8")
    return tmp_path


def test_sauvegarde_absente(tmp_path):
    assert derniere_sauvegarde(tmp_path, MAINTENANT)["statut"] == "absente"


def test_derniere_sauvegarde_reussie(tmp_path):
    d = _journal(tmp_path, [
        "2026-10-24 02:00:00  Début de la sauvegarde de « labo » vers D:\\S\\labo_2026-10-24_020000.dump",
        "2026-10-24 02:00:05  Sauvegarde terminée : D:\\S\\labo_2026-10-24_020000.dump (64,2 Ko)",
        "2026-10-26 02:00:00  Début de la sauvegarde de « labo » vers D:\\S\\labo_2026-10-26_020000.dump",
        "2026-10-26 02:00:04  Sauvegarde terminée : D:\\S\\labo_2026-10-26_020000.dump (65.5 Ko)",
        "2026-10-26 02:00:04  Supprimée (plus de 30 jours) : labo_2026-09-25_020000.dump",
    ])
    s = derniere_sauvegarde(d, MAINTENANT)
    assert s["statut"] == "ok" and s["fichier"] == "labo_2026-10-26_020000.dump"
    assert s["taille_ko"] == 65.5 and s["age_heures"] == 10.0 and s["derniere"] == datetime(2026, 10, 26, 2, 0, 4)


def test_sauvegarde_ancienne_ou_en_erreur(tmp_path):
    d = _journal(tmp_path, ["2026-10-20 02:00:05  Sauvegarde terminée : D:\\S\\labo_x.dump (64 Ko)"])
    assert derniere_sauvegarde(d, MAINTENANT)["statut"] == "ancienne"
    d = _journal(tmp_path, ["2026-10-25 02:00:05  Sauvegarde terminée : D:\\S\\labo_x.dump (64 Ko)",
                            "2026-10-26 02:00:01  ERREUR : pg_dump a échoué (code 1)."])
    s = derniere_sauvegarde(d, MAINTENANT)
    assert s["statut"] == "erreur" and "pg_dump" in s["derniere_erreur"]["message"]
    d = _journal(tmp_path, ["2026-10-26 02:00:01  ERREUR : pg_dump a échoué (code 1)."])
    assert derniere_sauvegarde(d, MAINTENANT)["statut"] == "erreur"


async def test_health(clients, db):
    r = await clients[None].get("/api/health")
    assert r.status_code == 200
    h = r.json()
    assert h["status"] == "ok" and h["version"] == VERSION and h["environnement"] == "test"
    nb = await db.fetchval("SELECT count(*) FROM schema_migrations")
    assert h["base"] == {"ok": True, "base": "labo_test", "migrations": nb,
                         "derniere_migration": await db.fetchval("SELECT max(fichier) FROM schema_migrations")}
    assert h["sauvegarde"]["statut"] in ("ok", "ancienne", "erreur", "absente")
