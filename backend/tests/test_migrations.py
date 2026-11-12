"""Migrations (tâche 26) : base construite de zéro, second passage vide, empreintes contrôlées."""
import pytest

from scripts import migrer
from tests.conftest import BASE_TEST


async def test_base_de_test_construite_par_les_migrations(db):
    enregistrees = {r["fichier"] for r in await db.fetch("SELECT fichier FROM schema_migrations")}
    assert enregistrees == {p.name for p in migrer.fichiers()}
    assert await db.fetchval("SELECT count(*) FROM ref_categories") > 0     # référentiels de 000


async def test_second_passage_n_applique_rien(capsys):
    assert await migrer.migrer(BASE_TEST, dry_run=False) == 0
    assert "aucune migration à appliquer" in capsys.readouterr().out


def test_migration_modifiee_detectee(tmp_path):
    f = tmp_path / "001_essai.sql"
    f.write_text("SELECT 1;\n", encoding="utf-8")
    faites = {"001_essai.sql": migrer.empreinte(f)}
    assert migrer.controler(faites, [f]) == []
    f.write_text("SELECT 2;\n", encoding="utf-8")
    with pytest.raises(migrer.ErreurMigration, match="001_essai.sql"):
        migrer.controler(faites, [f])


def test_empreinte_independante_des_fins_de_ligne(tmp_path):
    a, b = tmp_path / "a.sql", tmp_path / "b.sql"
    a.write_bytes(b"SELECT 1;\nSELECT 2;\n")
    b.write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    assert migrer.empreinte(a) == migrer.empreinte(b)


async def test_ordre_numerique():
    noms = [p.name for p in migrer.fichiers()]
    assert noms == sorted(noms) and noms[0] == "000_schema_initial.sql"
