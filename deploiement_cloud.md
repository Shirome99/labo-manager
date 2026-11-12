# Tâche : mettre le projet sur GitHub et le déployer (GitHub Pages + Render + Neon)

> **Instructions pour Claude Code**
>
> Lis d'abord `CLAUDE.md` : ses règles s'appliquent (lire avant de modifier, vérifications, Journal). Ajoute cette tâche en tête du Backlog sous le nom « Déploiement cloud (démo) », traite-la avant les autres, et note chaque étape au Journal.
>
> **Pour cette tâche, l'utilisateur autorise** : `git init`, les commits, la création du dépôt GitHub et le `push` vers ce dépôt. Toutes les autres conditions d'arrêt de `CLAUDE.md` restent valables.
>
> **Arrêts obligatoires** pour cette tâche :
> 1. **Avant le premier `push`** : montrer la liste complète des fichiers suivis (`git ls-files`), le résultat de la recherche de secrets (étape 2), et demander confirmation, en précisant si le dépôt sera public ou privé.
> 2. Quand une action doit être faite par l'utilisateur sur un site (création de compte, de projet, réglage), s'arrêter avec des instructions précises, numérotées, puis attendre les informations demandées.

## Architecture cible

- **Frontend** (React + Vite) : build statique publié sur **GitHub Pages**, à l'adresse `https://<utilisateur>.github.io/<depot>/`.
- **Backend** (FastAPI) : service web sur **Render** (offre gratuite), par exemple `https://labo-manager-api.onrender.com`.
- **Base** : PostgreSQL sur **Neon** (offre gratuite).
- Il s'agit d'un **environnement de démonstration**. La production du laboratoire reste sur le serveur local : le cadrage impose que les données d'analyses officielles ne quittent pas le bâtiment.

## Règles de sécurité et de confidentialité (non négociables)

- **Aucune donnée réelle du laboratoire** sur GitHub, Render ou Neon : ni le dump Access (`*.sql` de 2010), ni le rapport d'anomalies d'import, ni les sauvegardes `*.dump`, ni les journaux, ni des exports Excel/CSV, ni des PDF générés. La base Neon ne contient que des **données de démonstration fictives**.
- **Aucun secret dans le dépôt** : pas de `.env`, pas de mot de passe en dur, pas de `pgpass`, pas de clé secrète par défaut utilisable en ligne. Les secrets vont dans les variables d'environnement de Render et dans les secrets / variables GitHub.
- GitHub Pages sur un **dépôt privé** demande un compte GitHub payant. Avec un compte gratuit, le dépôt sera **public** : tout ce qui est suivi par git sera visible de tous, d'où l'arrêt obligatoire avant le push.

---

## Étape 1 — Préparer le dépôt local

- `git init` à la racine du projet (branche `main`).
- `.gitignore` complet :
  - Python : `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `.pytest_cache/`
  - Node : `node_modules/`, `frontend/dist/`
  - secrets : `.env`, `.env.*` sauf `.env.exemple`, `pgpass.conf`
  - données : `*.sql` **sauf** `backend/migrations/*.sql`, `*.dump`, `*.csv`, `*.xlsx`, `*.pdf`, `logs/`, `rapport_import_access*`, `docs/captures/` si elles montrent des données réelles
  - divers : `.DS_Store`, `Thumbs.db`, `*.log`
- Si les migrations `011` et `012` sont encore à la racine, vérifier qu'elles ont bien été copiées dans `backend/migrations/` (sinon le `.gitignore` les exclurait).
- `README.md` : présentation courte, stack, lancement en local, lien vers la démo, et la mention « environnement de démonstration, données fictives ».

## Étape 2 — Rechercher les secrets et les données sensibles

- Chercher dans tous les fichiers qui seront suivis : mots de passe, `SECRET_KEY`, chaînes de connexion `postgresql://`, `PGPASSWORD`, adresses e-mail, numéros de téléphone, noms de clients ou de fabricants réels (comparer avec les référentiels du dump Access), chemins Windows personnels.
- Tout secret trouvé dans le code est remplacé par une lecture de variable d'environnement. Une valeur par défaut n'est autorisée qu'en local, et l'application doit **refuser de démarrer** hors local si la clé secrète est celle par défaut.
- Les migrations qui insèrent des **référentiels réels** (fabricants, organismes, adresses) : les signaler à l'utilisateur au moment de l'arrêt avant push, et proposer une migration de démonstration à la place pour la base Neon.
- Mettre le résultat de cette recherche dans le message de l'arrêt n° 1.

## Étape 3 — Adapter le backend pour Render et Neon

- **Configuration** par variables d'environnement : `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS` (liste séparée par des virgules), `ENVIRONNEMENT` (`local` / `demo` / `production`), et durées de session si elles existent.
- **Connexion à Neon avec asyncpg** (pièges connus) :
  - les chaînes Neon contiennent `?sslmode=require&channel_binding=require` : **asyncpg n'accepte pas ces paramètres dans l'URL**. Les retirer de l'URL et passer `connect_args={"ssl": "require"}` à `create_async_engine` ;
  - convertir `postgresql://` en `postgresql+asyncpg://` dans le code, pour que l'utilisateur colle la chaîne Neon telle quelle ;
  - utiliser la connexion **directe** de Neon (hôte sans `-pooler`). Si l'utilisateur fournit l'hôte `-pooler`, ajouter `statement_cache_size=0` dans `connect_args` ;
  - régler `pool_pre_ping=True` : Neon met la base en veille et les connexions peuvent être coupées.
- **CORS** : `CORSMiddleware` avec `allow_origins` = `CORS_ORIGINS`, `allow_credentials=True`, méthodes et en-têtes nécessaires. Attention : l'origine GitHub Pages est `https://<utilisateur>.github.io`, **sans** le chemin `/<depot>/`. Si une vérification d'origine CSRF existe, elle doit accepter les mêmes origines.
- **Authentification entre deux domaines** : le front (github.io) et l'API (onrender.com) sont sur des sites différents. Le cookie de session devient un cookie tiers, que Brave et Safari bloquent par défaut, ce qui ferait échouer la connexion. Donc :
  - ajouter une **authentification par jeton** : `POST /api/auth/login` renvoie aussi un jeton signé à durée limitée (signé avec `itsdangerous`, déjà présent via Starlette, ou avec PyJWT), et `current_user` accepte `Authorization: Bearer <jeton>` ;
  - **garder** la session par cookie pour le fonctionnement local actuel ;
  - les règles d'expiration et de verrouillage de compte existantes s'appliquent aussi au jeton ;
  - le changement de rôle ou la désactivation d'un compte doit être pris en compte au plus tard à l'expiration du jeton (durée courte, 30 à 60 min, avec renouvellement).
- **Route catch-all SPA** dans `main.py` : ne l'enregistrer que si `frontend/dist` existe, pour que l'API démarre sur Render sans build du front.
- `GET /api/health` (s'il n'existe pas) : renvoie l'état de la base et la version ; sert au contrôle de santé de Render.
- Vérifier que rien ne dépend de Windows : chemins `C:\…`, polices chargées depuis `C:\Windows\Fonts` dans `services/rapport.py` (embarquer alors une police libre comme DejaVu dans le dépôt), paquets Windows dans `requirements.txt` (`pywin32`…). Épingler les versions dans `requirements.txt`.
- Fichier **`render.yaml`** (blueprint) :
  - service web Python, `rootDir: backend` ;
  - `buildCommand: pip install -r requirements.txt` ;
  - `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT` ;
  - `healthCheckPath: /api/health` ;
  - variables `PYTHON_VERSION` (la version utilisée en local), `DATABASE_URL`, `SECRET_KEY` (`generateValue: true`), `CORS_ORIGINS`, `ENVIRONNEMENT=demo` (`sync: false` pour celles que l'utilisateur saisit).
- Script `backend/scripts/init_demo.py` : applique toutes les migrations sur la base indiquée (via `migrer.py` s'il existe, sinon les fichiers de `backend/migrations/` dans l'ordre), crée un compte admin dont le mot de passe vient d'une variable d'environnement (jamais en dur), crée un compte de démonstration par rôle, et insère un **jeu de données fictif** : une trentaine d'échantillons répartis sur les 3 sections et tous les statuts, avec fabricants et organismes inventés.

## Étape 4 — Adapter le frontend pour GitHub Pages

- `vite.config.js` : `base: process.env.VITE_BASE ?? "/"`. Le workflow donnera `/<depot>/`.
- `BrowserRouter` avec `basename={import.meta.env.BASE_URL}`.
- **Routes profondes** : après le build, copier `dist/index.html` en `dist/404.html`, pour qu'un rechargement sur `/<depot>/echantillons` fonctionne sur GitHub Pages.
- `src/api/client.js` :
  - `BASE = (import.meta.env.VITE_API_URL ?? "") + "/api"` (vide en local : le proxy Vite continue de fonctionner) ;
  - envoyer `Authorization: Bearer <jeton>` quand un jeton existe (stocké en `sessionStorage`, effacé à la déconnexion et sur toute réponse 401) ;
  - **liens directs** : les PDF (rapport d'essai, bulletins, quittances, étiquettes, bilans) et les exports Excel/CSV s'ouvrent aujourd'hui par une URL (`urlRapport`, `urlExportEchantillons`…). Une URL ne transporte pas l'en-tête `Authorization`, ils échoueraient en ligne. Les remplacer par une fonction qui fait un `fetch` avec le jeton, récupère un `Blob`, puis l'ouvre dans un onglet (PDF) ou le télécharge avec le nom de fichier de l'en-tête `Content-Disposition`. Mettre à jour tous les appelants, et vérifier qu'il ne reste aucun `href` ni `window.open` vers `/api`.
- **Réveil du serveur** : l'API gratuite de Render s'endort après une période d'inactivité, et le premier appel peut prendre près d'une minute. Pendant la première requête, si elle dépasse 3 secondes, afficher « Démarrage du serveur, merci de patienter… ».
- Bandeau discret « Démonstration — données fictives » quand `VITE_ENVIRONNEMENT=demo`.

## Étape 5 — Publication automatique sur GitHub Pages

- Workflow `.github/workflows/pages.yml`, déclenché sur `push` vers `main` (fichiers `frontend/**`) et à la main :
  - installation Node (version du projet), `npm ci` dans `frontend/` ;
  - build avec `VITE_BASE=/<depot>/`, `VITE_API_URL=${{ vars.VITE_API_URL }}`, `VITE_ENVIRONNEMENT=demo` ;
  - copie de `index.html` vers `404.html` ;
  - `actions/upload-pages-artifact`, puis `actions/deploy-pages`, avec les permissions `pages: write` et `id-token: write`.
- Prendre la dernière version majeure de chaque action GitHub officielle.

## Étape 6 — Vérifier en local avant de publier

- Lancer le backend en mode `demo` sur une base locale vide, exécuter `init_demo.py`, builder le front avec `VITE_API_URL=http://localhost:8000` et `VITE_BASE=/<depot>/`, servir `dist/` sur un autre port (origine différente), puis vérifier :
  - connexion, navigation, rechargement sur une page profonde ;
  - un PDF et un export Excel qui s'ouvrent ;
  - CORS correct, avec un 401 propre après expiration du jeton.
- `npm run build` et les tests existants passent toujours, et le fonctionnement local habituel (proxy Vite + cookie) n'a pas changé.
- **Arrêt n° 1** (avant le premier push).

## Étape 7 — Mise en ligne (avec l'utilisateur)

Créer le dépôt et pousser. Si l'outil `gh` est connecté, l'utiliser ; sinon, demander à l'utilisateur de créer un dépôt vide et de donner son URL. Ensuite, s'arrêter et donner à l'utilisateur ces étapes, numérotées :

1. **Neon** : créer un projet (région européenne la plus proche), copier la chaîne de connexion **directe** (hôte sans `-pooler`).
2. Exécuter en local `python backend/scripts/init_demo.py` avec `DATABASE_URL` = la chaîne Neon et le mot de passe admin choisi (Claude Code peut le lancer si l'utilisateur fournit la chaîne dans une variable d'environnement, sans l'écrire dans un fichier suivi).
3. **Render** : *New → Blueprint*, choisir le dépôt (`render.yaml` est détecté), saisir `DATABASE_URL` (chaîne Neon) et `CORS_ORIGINS=https://<utilisateur>.github.io`, puis déployer et noter l'URL `https://….onrender.com`.
4. **GitHub** : *Settings → Secrets and variables → Actions → Variables* : créer `VITE_API_URL` = l'URL Render. Puis *Settings → Pages → Source : GitHub Actions*. Relancer le workflow.
5. Ouvrir `https://<utilisateur>.github.io/<depot>/`, se connecter avec un compte de démonstration.

Après le retour de l'utilisateur : tester l'API en ligne (`/api/health`, connexion par jeton, une liste, un PDF) et corriger si besoin.

## Fait quand

- Le site GitHub Pages charge, permet la connexion et la navigation, un rechargement sur une page profonde fonctionne, et un rapport PDF ainsi qu'un export Excel se téléchargent.
- Ça fonctionne dans Chrome **et dans Brave** (cookies tiers bloqués).
- Aucun secret ni donnée réelle dans le dépôt (recherche refaite après le push).
- Le fonctionnement local habituel est inchangé.
- `CLAUDE.md` est mis à jour :
  - section « Déploiement cloud » : URLs, variables d'environnement, commande `init_demo.py`, mise à jour par push sur `main` ;
  - conventions : `BASE` d'API, jeton, téléchargements par `Blob`, `base` Vite ;
  - entrée au Journal.
