# Bilan mensuel

Le bilan mensuel est le rapport d'activité remis à la direction et à l'ONSSA. Il se génère depuis l'écran **Reporting > Bilan mensuel**, ou en ligne de commande (tâche planifiée du 1er du mois). Les deux voies font exactement le même calcul.

## Contenu

Le contenu est défini par le **modèle du bilan** (table `bilan_modele`), que l'administrateur modifie dans la carte « Composition du bilan » de l'écran : ordre des blocs, titres, blocs actifs ou non.

Modèle par défaut (migration `024_bilans_mensuels.sql`) :

1. Synthèse du mois : reçus, rapports émis, encore en cours, à valider, en retard, taux de non-conformité, délai moyen, avec la comparaison au mois précédent ;
2. à 5. Répartition par section, par type d'échantillon, par fabricant, par organisme préleveur ;
6. et 7. Non-conformités par catégorie et par analyse ;
8. et 9. Délais par section (rapports émis dans le mois) et retards par section ;
10. Facturation du mois.

Hors synthèse, chaque bloc est une **requête enregistrée partagée** (écran Requêtes). Pour le bilan, sa période est remplacée par le mois choisi et sa section par celle du bilan. Une requête sans période (les retards, par exemple) décrit la situation **à la date de génération**, et le bilan le signale.

Pour ajouter un bloc :

1. construire la requête dans **Reporting > Requêtes** ;
2. l'enregistrer en visibilité **Partagée**, avec une période relative (« Mois précédent », par exemple) ;
3. dans « Composition du bilan », cliquer sur « Ajouter un bloc », choisir la requête, donner un titre et enregistrer.

Une requête qui fait partie du modèle ne peut pas être supprimée : il faut d'abord la retirer du modèle.

Définitions : voir `backend/app/services/requetes.py` (en-tête et catalogue). Les chiffres du bilan sont ceux des requêtes de l'écran Requêtes, pour le même mois.

## Archivage

Chaque génération est archivée dans la table `bilans_mensuels` : mois, section, format, version, fichier, empreinte SHA-256, auteur, date, et source (`application` ou `script`). Régénérer le même mois crée une **nouvelle version**, sans toucher aux précédentes. L'historique et le téléchargement de chaque version sont dans l'écran. Les fichiers sont dans la base : ils sont donc inclus dans les sauvegardes `pg_dump`.

Droits : tout utilisateur connecté peut générer un bilan. Un rôle de section (`sma`, `scha`, `ssa`) ne le fait que pour sa section, et ne voit que les bilans de sa section. Le modèle n'est modifiable que par l'administrateur.

## Ligne de commande

Depuis `backend/` (venv activé). La connexion est celle de l'application (`DATABASE_URL`).

```powershell
python scripts/bilan_mensuel.py                                  # mois précédent, toutes sections, PDF + Excel
python scripts/bilan_mensuel.py --mois 2026-09                   # un mois donné
python scripts/bilan_mensuel.py --mois 2026-09 --section SMA --format pdf
python scripts/bilan_mensuel.py --sortie "D:\Bilans"             # copie aussi les fichiers dans un dossier
```

Options : `--mois AAAA-MM` (défaut : le mois précédent), `--section SMA|SCHA|SSA` (défaut : toutes), `--format pdf|xlsx|les-deux` (défaut : les deux), `--sortie <dossier>` (facultatif), `--base <nom>` (autre base du même serveur, pour des essais).

Le script affiche, pour chaque fichier, le numéro du bilan archivé, sa version et son empreinte. Il renvoie le code de sortie 0 si tout est généré, 1 sinon. L'auteur enregistré est `script:bilan_mensuel`.

## Tâche planifiée (le 1er du mois)

Avec PowerShell, en adaptant les chemins (dossier du projet, Python du venv, dossier de copie) :

```powershell
schtasks /Create /TN "LIMS - bilan mensuel" /SC MONTHLY /D 1 /ST 06:00 /RU "$env:USERNAME" /RP `
  /TR "cmd /c cd /d \"D:\Programmation\Projet test python Node\lims\backend\" && venv\Scripts\python.exe scripts\bilan_mensuel.py --sortie \"D:\Bilans\" >> \"D:\Bilans\bilan_mensuel.log\" 2>&1"
```

Le 1er du mois à 6 h, la tâche génère le bilan du mois précédent (PDF et Excel, toutes sections), l'archive en base et en dépose une copie dans `D:\Bilans`. Pour un bilan par section, ajouter une tâche par section avec `--section`.

Vérification : dans le Planificateur de tâches, « Résultat de la dernière exécution » doit valoir `0x0`. Le journal `bilan_mensuel.log` contient une ligne par fichier, et le bilan apparaît dans l'historique de l'écran, avec l'étiquette « Tâche planifiée ».

## Points d'attention

- Le bilan d'un mois peut changer si les données de ce mois changent ensuite (saisie tardive, correction) : c'est pour cela que chaque version est archivée avec son empreinte.
- Le délai réception - rapport ne porte que sur les dossiers dont le rapport a été émis par l'application. Les données reprises d'Access n'ont pas de date de rapport.
- Le taux de non-conformité exclut les échantillons dont la conformité n'est pas renseignée.
