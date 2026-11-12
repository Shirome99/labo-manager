"""
Configuration de l'application (tâche 29).

Les valeurs viennent, par ordre de priorité : des variables d'environnement, puis du
fichier `backend/.env` (voir `backend/.env.exemple`, modèle commenté), puis des valeurs
par défaut ci-dessous. Aucun secret n'est écrit dans ce fichier : l'URL de la base (avec
son mot de passe) et la clé secrète se règlent dans `.env`.
"""
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[2]
SECRET_KEY_DEFAUT = "change-me-en-production"
# Version de l'application (affichée en bas du menu, /api/version, CHANGELOG.md)
VERSION = "2.0.0"
# Environnements « locaux » : la clé secrète par défaut y est tolérée (jamais en démo ni en production)
ENVIRONNEMENTS_LOCAUX = ("developpement", "local", "test")
# Paramètres d'URL de libpq (chaînes Neon) que asyncpg n'accepte pas dans l'URL
PARAMS_SSL = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def preparer_url(url: str) -> tuple[str, dict]:
    """
    URL de la base telle que collée (chaîne Neon `postgresql://…?sslmode=require&channel_binding=require`
    comprise) → (URL `postgresql+asyncpg://` sans les paramètres SSL, options de connexion asyncpg).
    - sslmode / channel_binding retirés de l'URL (asyncpg les refuse) ; SSL demandé par `ssl="require"` ;
    - hôte « -pooler » de Neon (PgBouncer en mode transaction) : `statement_cache_size=0`.
    """
    p = urlsplit(url.strip())
    schema = "postgresql+asyncpg" if p.scheme in ("postgres", "postgresql", "postgresql+asyncpg") else p.scheme
    params = parse_qsl(p.query, keep_blank_values=True)
    options: dict = {}
    sslmode = dict(params).get("sslmode")
    if sslmode and sslmode not in ("disable", "allow", "prefer"):
        options["ssl"] = "require"
    if "-pooler" in (p.hostname or ""):
        options["statement_cache_size"] = 0
    garde = urlencode([(k, v) for k, v in params if k not in PARAMS_SSL])
    return urlunsplit((schema, p.netloc, p.path, garde, "")), options


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND / ".env", env_file_encoding="utf-8", extra="ignore")

    # « production » et « demo » : refus de démarrer avec la clé secrète par défaut ;
    # « test » : bandeau « Environnement de test » ; « demo » : démonstration en ligne (données fictives) ;
    # « local » = « developpement »
    ENVIRONNEMENT: Literal["production", "demo", "test", "developpement", "local"] = "production"

    # postgresql+asyncpg://utilisateur:motdepasse@hote:5432/base
    # (une chaîne Neon « postgresql://…?sslmode=require » se colle telle quelle : voir preparer_url)
    DATABASE_URL: str = "postgresql+asyncpg://postgres@localhost:5432/labo"
    SECRET_KEY: str = SECRET_KEY_DEFAUT          # signature des cookies de session
    SESSION_MAX_AGE: int = 60 * 60 * 8           # durée maximale d'une session (secondes)
    SITE_ESSAI: str = "LRAR Tanger"

    # --- Sécurité des comptes (tâche 12) ---
    # Expiration de la session après N minutes sans activité (en plus de SESSION_MAX_AGE)
    SESSION_INACTIVITE_MIN: int = 30
    # Verrouillage du compte après N échecs de connexion consécutifs, pendant M minutes
    VERROU_ECHECS: int = 5
    VERROU_MINUTES: int = 15
    # Origines autorisées pour les requêtes qui modifient des données (protection CSRF),
    # en plus de l'hôte lui-même. Par défaut : le serveur Vite de développement.
    ORIGINES_AUTORISEES: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Cookie de session « Secure » : à activer quand l'application est servie en HTTPS
    SESSION_HTTPS: bool = False
    # Démonstration en ligne (front sur un autre site) : origines autorisées par CORS, séparées par
    # des virgules, sans chemin (ex. https://utilisateur.github.io). Vide = pas de CORS (serveur local).
    CORS_ORIGINS: str = ""
    # Jeton d'authentification (Authorization: Bearer) : durée de validité en minutes, renouvelé
    # pendant l'activité ; à défaut, SESSION_INACTIVITE_MIN. Durée totale bornée par SESSION_MAX_AGE.
    JETON_DUREE_MIN: int | None = None

    # Habilitations (tâche 19) : un résultat ne peut être enregistré que par un utilisateur
    # habilité et à jour pour l'analyse. HABILITATIONS_OBLIGATOIRES=0 suspend le contrôle
    # (le temps de saisir la matrice d'habilitations lors de la mise en service).
    HABILITATIONS_OBLIGATOIRES: bool = True
    # Étiquettes d'échantillon : format par défaut (mm), modifiable par requête
    ETIQUETTE_LARGEUR_MM: float = 50
    ETIQUETTE_HAUTEUR_MM: float = 25

    # --- Dossiers (tâche 29) ---
    # Journaux applicatifs : un fichier par jour, conservés LOG_RETENTION_JOURS jours
    LOG_DIR: Path = BACKEND / "logs"
    LOG_RETENTION_JOURS: int = 90
    # Dossier des sauvegardes de sauvegarde.ps1 (lu par /api/health : dernière sauvegarde)
    SAUVEGARDE_DIR: Path = Path(r"D:\Sauvegardes\labo")

    @property
    def nom_base(self) -> str:
        return urlsplit(self.DATABASE_URL).path.lstrip("/")

    @property
    def url_sqlalchemy(self) -> str:
        return preparer_url(self.DATABASE_URL)[0]

    @property
    def url_asyncpg(self) -> str:
        """URL pour asyncpg.connect (scripts) : `postgresql://`, sans les paramètres SSL."""
        return self.url_sqlalchemy.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def connect_args(self) -> dict:
        return preparer_url(self.DATABASE_URL)[1]

    @property
    def origines_cors(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def duree_jeton_min(self) -> int:
        return self.JETON_DUREE_MIN or self.SESSION_INACTIVITE_MIN

    def verifier_production(self) -> None:
        """Hors local (production, démo), refuse de démarrer avec la clé secrète par défaut (ou trop courte)."""
        if self.ENVIRONNEMENT not in ENVIRONNEMENTS_LOCAUX and (
                self.SECRET_KEY == SECRET_KEY_DEFAUT or len(self.SECRET_KEY) < 32):
            raise RuntimeError(
                "Démarrage refusé : SECRET_KEY est la clé par défaut (ou fait moins de 32 caractères). "
                "Définissez une clé secrète dans backend/.env (voir .env.exemple), par exemple avec : "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


settings = Settings()
