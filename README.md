# Labo Manager (Labbora) — LIMS

Application web de gestion de laboratoire d'analyses (réception des échantillons, traitement par
section, validation à deux niveaux, rapport d'essai PDF figé, qualité ISO 17025, reporting,
facturation). Interface en français.

> **Démonstration en ligne : environnement de démonstration, données fictives.**
> Front : `https://<utilisateur>.github.io/<depot>/` — API : `https://labo-manager-api.onrender.com`.
> Le serveur gratuit s'endort après une période d'inactivité : la première connexion peut prendre
> près d'une minute. Aucune donnée réelle de laboratoire n'y figure.

## Stack

- **Backend** : Python 3.13, FastAPI, SQLAlchemy async (asyncpg), Pydantic v2, ReportLab (PDF), openpyxl (Excel).
- **Base** : PostgreSQL (migrations SQL numérotées, `backend/scripts/migrer.py`).
- **Frontend** : React 18, Vite, Ant Design 6, react-router 6.
- **Tests** : pytest + httpx (backend), Playwright (bout en bout).

## Lancer en local

```powershell
# Backend (depuis backend/)
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.exemple .env          # puis renseigner DATABASE_URL et SECRET_KEY
python scripts/migrer.py --creer
python create_admin.py admin
uvicorn app.main:app --reload --port 8000

# Frontend (depuis frontend/)
npm install
npm run dev                      # http://localhost:5173 (proxy /api -> :8000)
```

Tests : `powershell -File backend\scripts\tester.ps1` (backend), `npm run e2e` (interface).

## Démonstration (GitHub Pages + Render + Neon)

- `render.yaml` : API sur Render (`ENVIRONNEMENT=demo`, `DATABASE_URL` = chaîne Neon collée telle quelle,
  `CORS_ORIGINS=https://<utilisateur>.github.io`, `SECRET_KEY` générée).
- `.github/workflows/pages.yml` : front publié sur GitHub Pages à chaque push sur `main`
  (variable de dépôt `VITE_API_URL` = adresse de l'API Render).
- `backend/scripts/init_demo.py` : migrations, comptes de démonstration et données fictives
  (mots de passe fournis par variables d'environnement, jamais dans le dépôt).

Le déploiement du laboratoire, lui, reste sur son serveur local : voir `docs/deploiement.md`.
