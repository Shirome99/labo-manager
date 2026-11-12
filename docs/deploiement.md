# Déploiement sur le serveur du laboratoire

Procédure complète pour installer le LIMS sur un poste Windows neuf (Windows 10 / 11 ou Windows Server), le démarrer automatiquement, le rendre accessible aux autres postes, le mettre à jour et revenir en arrière.

Dans ce document :

- le dossier de l'application est `D:\LIMS\app` (copie du projet : `backend\`, `frontend\`, `docs\`) ;
- les sauvegardes vont dans `D:\Sauvegardes\labo`, les copies de versions dans `D:\LIMS\versions` ;
- les commandes se tapent dans **PowerShell**. « PowerShell administrateur » = clic droit sur PowerShell, « Exécuter en tant qu'administrateur ».

Les scripts utilisés : `backend\scripts\demarrer.ps1`, `mettre_a_jour.ps1`, `sauvegarde.ps1`, `migrer.py`, et `backend\create_admin.py`.

---

## 1. Prérequis

| Élément | Version | Remarque |
|---|---|---|
| PostgreSQL | 16 à 18 | installeur « EDB » de postgresql.org, avec les outils en ligne de commande |
| Python | 3.12 ou 3.13 | python.org ; cocher « Add python.exe to PATH » |
| Node.js | 22 ou 24 LTS | nodejs.org (seulement pour construire l'interface) |
| Navigateur des postes | Edge ou Chrome récents | |

Poste serveur : 8 Go de mémoire, 20 Go libres sur `D:`, adresse IP fixe sur le réseau du labo (voir § 9).

## 2. PostgreSQL

1. Installer PostgreSQL (port 5432 par défaut). Noter le mot de passe du compte `postgres`.
2. Créer un compte dédié à l'application (recommandé, plutôt que `postgres`) : ouvrir **SQL Shell (psql)** et taper :

   ```sql
   CREATE ROLE lims LOGIN PASSWORD 'un-mot-de-passe-long';
   ALTER ROLE lims CREATEDB;
   ```

   (`CREATEDB` permet à `migrer.py --creer` de créer la base ; il peut être retiré ensuite : `ALTER ROLE lims NOCREATEDB;`.)
3. PostgreSQL ne doit **pas** être ouvert au réseau : laisser `listen_addresses = 'localhost'` dans `postgresql.conf` (valeur par défaut). Seule l'application, sur le même poste, s'y connecte.

## 3. Copier l'application

Copier le dossier du projet dans `D:\LIMS\app` (clé USB, partage réseau…). Ne pas copier `backend\.venv`, `frontend\node_modules` ni `backend\.env` d'un autre poste.

## 4. Environnement Python

```powershell
cd D:\LIMS\app\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 5. Configuration (`backend\.env`)

```powershell
cd D:\LIMS\app\backend
copy .env.exemple .env
notepad .env
```

Remplir au minimum (chaque ligne est commentée dans `.env.exemple`) :

- `DATABASE_URL=postgresql+asyncpg://lims:un-mot-de-passe-long@localhost:5432/labo`
- `SECRET_KEY=` une clé aléatoire d'au moins 32 caractères, générée par :
  `.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `ENVIRONNEMENT=production` (l'application refuse alors de démarrer avec la clé par défaut)
- `LOG_DIR=D:\LIMS\logs`, `SAUVEGARDE_DIR=D:\Sauvegardes\labo`
- `SESSION_HTTPS=1` seulement si l'application est servie en HTTPS (§ 10).

Le fichier `.env` contient des secrets : il ne quitte jamais le serveur et n'est pas sauvegardé avec le code.

## 6. Base de données

```powershell
cd D:\LIMS\app\backend
.venv\Scripts\python scripts\migrer.py --creer      # crée la base « labo » et applique toutes les migrations
.venv\Scripts\python scripts\migrer.py --etat       # chaque migration doit être « appliquée »
```

Les migrations créent le schéma, les référentiels, le catalogue des analyses et la grille de tarifs repris d'Access.
Reprise des données Access : voir `backend\scripts\import_access.py` (d'abord `--dry-run`).

## 7. Compte administrateur

```powershell
cd D:\LIMS\app\backend
.venv\Scripts\python create_admin.py admin
```

Le mot de passe est demandé deux fois, sans écho (au moins 10 caractères, avec lettres et chiffres). Les autres comptes se créent ensuite dans l'application (**Administration > Comptes**).

## 8. Interface, premier démarrage, démarrage automatique

### 8.1 Construire l'interface

```powershell
cd D:\LIMS\app\frontend
npm install
npm run build          # produit frontend\dist, servi par le serveur Python
```

### 8.2 Premier démarrage (manuel)

```powershell
powershell -ExecutionPolicy Bypass -File D:\LIMS\app\backend\scripts\demarrer.ps1
```

Sur le serveur, ouvrir `http://localhost:8000` : l'écran de connexion s'affiche ; se connecter avec le compte admin. En bas du menu : « Labo Manager 2.0.0 · Production ».
Contrôle technique : `http://localhost:8000/api/health` renvoie `"status": "ok"`, la version, la base et ses migrations, et l'état de la dernière sauvegarde.
Arrêter le serveur : Ctrl+C dans la fenêtre.

### 8.3 Démarrage automatique (Planificateur de tâches)

Dans un **PowerShell administrateur** :

```powershell
powershell -ExecutionPolicy Bypass -File D:\LIMS\app\backend\scripts\demarrer.ps1 -InstallerTache
Start-ScheduledTask -TaskName "LIMS - serveur"
```

La tâche « LIMS - serveur » lance `demarrer.ps1` au démarrage de Windows (compte SYSTEM, sans session ouverte), et le relance jusqu'à 5 fois en cas d'arrêt. Vérifier dans le Planificateur de tâches (`taskschd.msc`) que l'état est « En cours d'exécution », puis redémarrer le poste et rouvrir `http://localhost:8000`.

Arrêter / relancer : `Stop-ScheduledTask -TaskName "LIMS - serveur"` / `Start-ScheduledTask -TaskName "LIMS - serveur"`.

> **Alternative proposée (non installée) : service Windows avec NSSM.** NSSM (nssm.cc) transforme une commande en vrai service Windows (redémarrage automatique, journaux de sortie). Commande indicative, à faire valider par l'informatique du labo avant installation :
> `nssm install LIMS "D:\LIMS\app\backend\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"` puis `nssm set LIMS AppDirectory D:\LIMS\app\backend`.
> Le Planificateur de tâches suffit dans la plupart des cas ; NSSM est utile si l'on veut gérer le LIMS comme les autres services (`services.msc`).

### 8.4 Sauvegardes et bilan mensuel

- Sauvegarde quotidienne : fichier `pgpass.conf` et tâche planifiée, voir `docs/sauvegarde.md`. L'état de la dernière sauvegarde apparaît dans `/api/health` (`ok`, `ancienne` au-delà de 26 h, `erreur`, `absente`).
- Bilan mensuel automatique (le 1er du mois) : voir `docs/bilan_mensuel.md`.

## 9. Accès depuis les autres postes

1. **Adresse fixe** du serveur : réservation DHCP sur la box / le routeur (recommandé) ou adresse IP statique (Paramètres > Réseau > Modifier les options de l'adaptateur > IPv4). Exemple : `192.168.1.10`.
2. **Nom** (facultatif) : ajouter dans `C:\Windows\System32\drivers\etc\hosts` de chaque poste la ligne `192.168.1.10  lims.lrarvy.local`, ou un enregistrement DNS si le labo a un serveur DNS.
3. **Pare-feu** du serveur, dans un PowerShell administrateur (réseaux privé et domaine seulement) :

   ```powershell
   New-NetFirewallRule -DisplayName "LIMS (TCP 8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 `
       -Action Allow -Profile Domain,Private
   ```

   Le profil réseau du serveur doit être « Privé » (Paramètres > Réseau > propriétés de la connexion).
4. Depuis un autre poste : `http://192.168.1.10:8000` (ou `http://lims.lrarvy.local:8000`). Créer un raccourci sur le bureau des postes.

## 10. HTTPS (recommandé)

Voir `docs/https.md` (autorité interne, certificat du serveur). Démarrage en HTTPS :

```powershell
powershell -ExecutionPolicy Bypass -File D:\LIMS\app\backend\scripts\demarrer.ps1 -Port 8443 `
    -CertFile D:\LIMS\tls\serveur.crt -KeyFile D:\LIMS\tls\serveur.key
```

(et `-InstallerTache` avec les mêmes paramètres pour la tâche planifiée, `SESSION_HTTPS=1` dans `.env`, règle de pare-feu sur le port 8443).

## 11. Vérifications après l'installation

- [ ] `/api/health` : `"status": "ok"`, base `labo`, toutes les migrations, sauvegarde `ok` le lendemain de la 1re sauvegarde planifiée ;
- [ ] connexion depuis un autre poste ;
- [ ] création d'un compte de chaque rôle, puis réception d'un échantillon de test, étiquettes, fiche, résultats, validation, rapport ;
- [ ] redémarrage du serveur : l'application revient seule ;
- [ ] Référentiels > Tarifs : valider les prix repris d'Access et compléter la grille ; régler l'étape de paiement exigée ;
- [ ] supprimer l'échantillon de test (Échantillons, bouton Supprimer) s'il n'a ni rapport ni bulletin.

## 12. Mise à jour d'une version

1. Copier la nouvelle version dans un dossier à part, par exemple `D:\LIMS\nouvelle-version` (sans `.env`, `.venv`, `node_modules`).
2. Prévenir les utilisateurs (le serveur est arrêté quelques minutes).
3. Dans un **PowerShell administrateur** :

   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\LIMS\app\backend\scripts\mettre_a_jour.ps1 -Source D:\LIMS\nouvelle-version
   ```

Le script enchaîne, et s'arrête à la première erreur : sauvegarde de la base ; copie de la version en place dans `D:\LIMS\versions\<date_heure>` ; copie des nouveaux fichiers ; arrêt du serveur ; dépendances Python ; migrations ; construction de l'interface ; redémarrage ; vérification par `/api/health`. Le déroulé est écrit dans `backend\logs\mise_a_jour.log`. Paramètres utiles : `-Port`, `-DossierSauvegarde`, `-DossierVersions`, `-Base`.

4. Sur un poste : Ctrl+F5, contrôler la version en bas du menu.

## 13. Retour arrière

Les migrations sont **additives** (elles ajoutent sans rien retirer) : une version précédente du code fonctionne en général sur la base mise à jour. Le retour arrière du **code** suffit donc le plus souvent ; la base ne se restaure que si ses données posent problème.

### 13.1 Revenir à la version précédente du code

Dans un PowerShell administrateur (remplacer `<date_heure>` par le dossier créé par la mise à jour, indiqué dans `mise_a_jour.log`) :

```powershell
Stop-ScheduledTask -TaskName "LIMS - serveur"
robocopy D:\LIMS\versions\<date_heure> D:\LIMS\app /E /XD .venv node_modules logs
cd D:\LIMS\app\backend
.venv\Scripts\python -m pip install -r requirements.txt
Start-ScheduledTask -TaskName "LIMS - serveur"
```

La copie contient aussi l'interface construite (`frontend\dist`) : pas besoin de reconstruire. Contrôler `/api/health` et la version en bas du menu.

### 13.2 Restaurer la base (si nécessaire)

**Opération destructive** : la base est remplacée par la sauvegarde ; tout ce qui a été saisi depuis est perdu. Suivre la procédure « 2.2 Restaurer la base de production `labo` » de `docs/sauvegarde.md`, avec la sauvegarde faite par la mise à jour (son nom est dans `mise_a_jour.log`) : arrêter le serveur, restaurer avec `pg_restore` dans une base vide, vérifier, puis redémarrer.

## 14. Dépannage

| Symptôme | Cause probable | Que faire |
|---|---|---|
| `demarrer.ps1` : « Le port 8000 est déjà utilisé » | le serveur tourne déjà (tâche planifiée) | `Stop-ScheduledTask -TaskName "LIMS - serveur"` ou garder l'instance en cours |
| Refus de démarrer : « SECRET_KEY » | clé par défaut ou trop courte en production | générer une clé (§ 5) |
| `/api/health` en 503 | PostgreSQL arrêté ou `DATABASE_URL` faux | `services.msc` > postgresql ; vérifier `.env` |
| `migrer.py` s'arrête (code 2) | une migration déjà appliquée a été modifiée | ne pas modifier une migration appliquée ; restaurer le fichier d'origine (copie de version) |
| Les autres postes n'accèdent pas | pare-feu, profil réseau « Public », adresse | § 9 |
| Écran blanc après une mise à jour | cache du navigateur | Ctrl+F5 |

Journaux : `D:\LIMS\logs\lims.log` (un fichier par jour), `backend\logs\mise_a_jour.log`, `D:\Sauvegardes\labo\sauvegarde.log`.
