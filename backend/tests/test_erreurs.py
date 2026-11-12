"""Gestion uniforme des erreurs, journaux applicatifs et configuration (tâche 29)."""
import pytest

from app.core.config import SECRET_KEY_DEFAUT, Settings, settings


def _journal() -> str:
    return (settings.LOG_DIR / "lims.log").read_text(encoding="utf-8")


async def test_erreur_inattendue_message_propre_et_journal(clients):
    r = await clients["util1"].get("/api/test/erreur")
    assert r.status_code == 500
    corps = r.json()
    ref = corps["reference"]
    assert ref in corps["detail"] and "Erreur interne du serveur" in corps["detail"]
    assert "Traceback" not in r.text and "RuntimeError" not in r.text
    contenu = _journal()
    assert f"[ref {ref}] GET /api/test/erreur (utilisateur util1)" in contenu
    assert "RuntimeError: Erreur provoquée volontairement" in contenu       # trace complète dans le journal


async def test_donnees_invalides_en_francais(clients):
    r = await clients["util1"].post("/api/echantillons", json={"sma": "Yes", "date_reception": "pas une date",
                                                               "nbre_prlvmts_sma": "trois"})
    assert r.status_code == 422
    d = r.json()
    assert d["detail"].startswith("Données invalides")
    assert {e["champ"] for e in d["erreurs"]} == {"date_reception", "nbre_prlvmts_sma"}
    assert "Input should" not in r.text


async def test_erreur_metier_json(clients):
    r = await clients["util1"].get("/api/echantillons/INEXISTANT-0000")
    assert r.status_code == 404 and r.json() == {"detail": 'Echantillon "INEXISTANT-0000" introuvable.'}


async def test_journal_des_requetes(clients):
    await clients["sma1"].get("/api/notifications")
    assert any("lims.acces GET /api/notifications 200" in l and l.rstrip().endswith("sma1")
               for l in _journal().splitlines())


def test_production_refuse_la_cle_par_defaut():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(ENVIRONNEMENT="production", SECRET_KEY=SECRET_KEY_DEFAUT, _env_file=None).verifier_production()
    with pytest.raises(RuntimeError):
        Settings(ENVIRONNEMENT="production", SECRET_KEY="trop-courte", _env_file=None).verifier_production()
    Settings(ENVIRONNEMENT="production", SECRET_KEY="x" * 48, _env_file=None).verifier_production()
    Settings(ENVIRONNEMENT="developpement", SECRET_KEY=SECRET_KEY_DEFAUT, _env_file=None).verifier_production()


def test_fichier_env_lu(tmp_path, monkeypatch):
    for v in ("ENVIRONNEMENT", "SESSION_INACTIVITE_MIN", "HABILITATIONS_OBLIGATOIRES"):
        monkeypatch.delenv(v, raising=False)
    env = tmp_path / ".env"
    env.write_text("ENVIRONNEMENT=test\nSESSION_INACTIVITE_MIN=12\nHABILITATIONS_OBLIGATOIRES=0\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert (s.ENVIRONNEMENT, s.SESSION_INACTIVITE_MIN, s.HABILITATIONS_OBLIGATOIRES) == ("test", 12, False)
