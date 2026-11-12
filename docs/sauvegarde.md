# Sauvegarde et restauration de la base `labo`

Script : `backend/scripts/sauvegarde.ps1` (Windows PowerShell 5.1 ou plus récent).

- Il fait un `pg_dump` au format *custom* (compressé, restaurable avec `pg_restore`).
- Le fichier produit s'appelle `labo_AAAA-MM-JJ_HHmmss.dump`, dans un dossier configurable.
- Il supprime les sauvegardes de **plus de 30 jours**. Seuls les fichiers `labo_*.dump` de ce dossier sont concernés, rien d'autre.
- Il tient un journal `sauvegarde.log` dans le même dossier. Le code de sortie vaut 0 si tout va bien et 1 en cas d'erreur.

> Conservez aussi une copie **hors du serveur** : disque externe, partage réseau, etc. Une sauvegarde stockée sur le même disque que la base ne protège pas contre une panne de ce disque.

---

## 1. Mise en place (une fois)

### 1.1 Mot de passe PostgreSQL sans le mettre dans le script

Créer le fichier `%APPDATA%\postgresql\pgpass.conf`, sous le compte Windows qui lancera la sauvegarde :

```
localhost:5432:*:postgres:MOT_DE_PASSE
```

En PowerShell :

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\postgresql" | Out-Null
Set-Content -Path "$env:APPDATA\postgresql\pgpass.conf" -Value "localhost:5432:*:postgres:MOT_DE_PASSE" -Encoding ascii
```

Ne donner accès à ce fichier qu'à ce compte : clic droit → Propriétés → Sécurité.

### 1.2 Test manuel

Depuis la racine du projet :

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\sauvegarde.ps1 -Dossier "D:\Sauvegardes\labo"
```

Paramètres disponibles, tous facultatifs :

| Paramètre         | Défaut                                                         | Rôle |
|-------------------|----------------------------------------------------------------|------|
| `-Dossier`        | `$env:LIMS_SAUVEGARDE_DIR`, sinon `D:\Sauvegardes\labo`        | dossier des sauvegardes |
| `-Base`           | `labo`                                                         | base à sauvegarder |
| `-Hote`, `-Port`  | `localhost`, `5432`                                            | serveur PostgreSQL |
| `-Utilisateur`    | `postgres`                                                     | compte PostgreSQL |
| `-RetentionJours` | `30`                                                           | âge maximal des sauvegardes conservées |
| `-PgBin`          | recherche dans le PATH, puis `C:\Program Files\PostgreSQL\*\bin` | dossier contenant `pg_dump.exe` |

### 1.3 Planification quotidienne (Planificateur de tâches)

Exemple : tous les jours à 20 h. À lancer dans une invite **administrateur**, sous le compte qui possède `pgpass.conf` :

```powershell
schtasks /Create /TN "LIMS - sauvegarde labo" /SC DAILY /ST 20:00 /RU "$env:USERNAME" /RP `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"D:\Programmation\Projet test python Node\lims\backend\scripts\sauvegarde.ps1\" -Dossier \"D:\Sauvegardes\labo\""
```

Adapter le chemin du script et du dossier au serveur. Vérifier ensuite dans le Planificateur de tâches que la tâche s'exécute (« Résultat de la dernière exécution » = `0x0`), et consulter `sauvegarde.log`.

---

## 2. Restauration

Outils utilisés : `pg_restore`, `createdb`, `dropdb`, `psql`, dans `C:\Program Files\PostgreSQL\18\bin`. Ajoutez ce dossier au PATH ou préfixez les commandes par ce chemin.

### 2.1 Vérifier une sauvegarde (sans risque)

Lister le contenu :

```powershell
pg_restore --list "D:\Sauvegardes\labo\labo_2026-10-11_200000.dump" | Select-Object -First 10
```

Restaurer dans une **base séparée**, pour contrôler sans toucher à `labo` :

```powershell
createdb -U postgres -h localhost labo_verif_restauration
pg_restore -U postgres -h localhost --no-owner -d labo_verif_restauration "D:\Sauvegardes\labo\labo_2026-10-11_200000.dump"
psql -U postgres -h localhost -d labo_verif_restauration -c "select count(*) from echantillons"
dropdb -U postgres -h localhost labo_verif_restauration   # base de contrôle uniquement
```

Il est conseillé de faire ce contrôle une fois par mois.

### 2.2 Restaurer la base de production `labo`

> ⚠️ **Opération destructive** : les données actuelles de `labo` sont remplacées par celles de la sauvegarde. Tout ce qui a été saisi depuis la sauvegarde est perdu.

1. **Arrêter l'application** : uvicorn. Personne ne doit être connecté.
2. **Sauvegarder l'état actuel**, même s'il est abîmé, au cas où :
   ```powershell
   powershell -ExecutionPolicy Bypass -File backend\scripts\sauvegarde.ps1 -Dossier "D:\Sauvegardes\labo\avant_restauration"
   ```
3. **Recréer la base vide et restaurer** :
   ```powershell
   dropdb   -U postgres -h localhost labo
   createdb -U postgres -h localhost labo
   pg_restore -U postgres -h localhost --no-owner -d labo "D:\Sauvegardes\labo\labo_2026-10-11_200000.dump"
   ```
   `pg_restore` doit se terminer sans erreur (code de sortie 0).
4. **Contrôler** quelques comptages, puis relancer l'application et vérifier qu'on peut se connecter et ouvrir un échantillon :
   ```powershell
   psql -U postgres -h localhost -d labo -c "select statut, count(*) from echantillons group by statut"
   ```
5. **Migrations** : la sauvegarde contient le schéma tel qu'il était au moment du dump. Si des migrations `backend/migrations/0NN_*.sql` ont été ajoutées depuis, les rejouer dans l'ordre. Elles sont additives (`IF NOT EXISTS`) et peuvent être relancées sans risque.

---

## 3. En cas de problème

| Symptôme dans `sauvegarde.log` | Cause probable / solution |
|---|---|
| `password authentication failed` | `pgpass.conf` absent, mal placé (autre compte Windows) ou mot de passe faux |
| `pg_dump.exe introuvable` | passer `-PgBin "C:\Program Files\PostgreSQL\18\bin"` |
| `could not connect to server` | service PostgreSQL arrêté (`services.msc` → postgresql-x64-18) |
| La tâche planifiée ne produit rien | vérifier le compte d'exécution de la tâche et que « Exécuter même si l'utilisateur n'est pas connecté » est coché |
