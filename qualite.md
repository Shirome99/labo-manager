# Ajout au Backlog — Bloc E : Qualité, fiabilité et mise en production

> **Instructions pour Claude Code**
>
> 1. Insère les tâches ci-dessous dans la section « Backlog » de `CLAUDE.md`, **juste après le bloc D (requêtes et reporting) et avant les tâches pas encore commencées**. Numérote-les à la suite (Q1 à Q8 deviennent les numéros suivants) ; ne modifie pas les autres tâches.
> 2. Ajoute une entrée au Journal : « Ajout du bloc E (qualité, fiabilité, mise en production) ».
> 3. Si une tâche est en cours, termine-la d'abord.
> 4. Les règles de `CLAUDE.md` s'appliquent (lire avant de modifier, migrations additives, vérifications, Journal, conditions d'arrêt). Interface en **Ant Design**.
> 5. **Autorisations spécifiques à ce bloc** (elles ne déclenchent pas de condition d'arrêt) :
>    - créer et vider librement la base de test `labo_test` (jamais `labo`) ;
>    - supprimer les fichiers parasites signalés au Journal (`backend/app/__init__ .py` avec un espace, dossier `{models,schemas,routers,core}`), **après avoir vérifié** qu'aucun code ne les importe ;
>    - ajouter des dépendances de développement : `pytest`, `pytest-asyncio`, `httpx`, `@playwright/test` et ses navigateurs.
>    - Restent interdits sans accord : toute action destructive sur `labo`, l'installation d'un logiciel système (service Windows, NSSM, serveur web…), la modification des règles métier.

## Objectif

L'application fait déjà beaucoup. Ce bloc la rend **fiable, testée et prête pour une vraie utilisation** au laboratoire : on doit pouvoir la modifier sans casser l'existant, la reconstruire de zéro, la déployer, et prouver qu'elle produit des résultats corrects (exigence ISO 17025).

---

- [ ] **Q1. Migrations maîtrisées.**
  - Table `schema_migrations` (nom du fichier, date d'application, empreinte du fichier).
  - Script `backend/scripts/migrer.py [--base labo|labo_test] [--dry-run]` qui applique dans l'ordre les fichiers SQL de `backend/migrations/` non encore appliqués, chacun dans une transaction.
  - Copier `011_conformite_access.sql` et `012_paiement_analyses.sql` de la racine vers `backend/migrations/`, et les enregistrer comme **déjà appliquées** sur `labo` sans les rejouer.
  - Si une migration déjà appliquée a été modifiée depuis (empreinte différente), le script le signale et s'arrête.
  - Fait quand : `labo_test` se construit **de zéro** avec `migrer.py --base labo_test`, et un second lancement n'applique rien.

- [ ] **Q2. Tests automatisés du backend.**
  - `backend/tests/` avec `pytest` + `httpx` (client asynchrone sur l'application), sur `labo_test` recréée à chaque session de tests, avec des comptes de test pour chaque rôle et un jeu de données minimal (fixtures).
  - Couvrir au minimum :
    - numérotation `AAAA-SECTION-NNNN` (suite, remise à zéro annuelle, collision) ;
    - une seule section par échantillon ;
    - circuit des statuts : soumettre, valider, renvoyer, double regard ;
    - verrou du rapport avant validation, et rapport figé s'il existe ;
    - droits de chaque rôle sur chaque route sensible (matrice 200 / 403) ;
    - export Excel/CSV (contenu relu) ;
    - moteur de requêtes (totaux comparés à du SQL direct, clé hors catalogue = 400) ;
    - seuils SMA (valeurs `<10`, `Abs`, `10³`…).
  - Commande unique : `backend/scripts/tester.ps1`.
  - Fait quand : tous les tests passent, et le nombre de tests ainsi que la couverture par fichier sont notés au Journal.

- [ ] **Q3. Tests de bout en bout de l'interface.**
  - Playwright (`frontend/e2e/`) sur le front construit et le backend pointé vers `labo_test`.
  - Parcours : connexion ; réception d'un échantillon (cascade type → sous-type, section unique, numéro généré) ; saisie du traitement et des résultats ; soumission ; validation par un autre compte ; émission du rapport ; export ; requête et bilan mensuel.
  - Vérifier aussi qu'un rôle de section ne voit ni les menus ni les données des autres sections.
  - Capturer des **captures d'écran** de chaque étape dans `docs/captures/` (elles serviront au guide utilisateur, Q8).
  - Fait quand : `npx playwright test` passe, et les captures sont générées.

- [ ] **Q4. Nettoyage et robustesse du code.**
  - Supprimer les fichiers parasites listés dans les autorisations (après vérification), le CSS inutilisé et les composants qui ne servent plus.
  - Configuration par fichier `.env` (URL de la base, clé secrète, durées de session, dossiers), avec un `.env.exemple` documenté. **Refuser de démarrer en production** si la clé secrète est celle par défaut.
  - Gestion d'erreurs uniforme : toute erreur serveur renvoie un JSON `{detail}` en français, sans trace technique ; les erreurs inattendues sont journalisées avec un identifiant affiché à l'utilisateur.
  - Journaux applicatifs dans des fichiers avec rotation (`logs/`), un fichier par jour, conservés 90 jours.
  - Fait quand : les tests Q2 et Q3 passent toujours, et une erreur provoquée volontairement donne un message propre à l'écran et une ligne dans le journal.

- [ ] **Q5. Performance avec de vrais volumes.**
  - Script qui remplit `labo_test` avec un volume réaliste (au moins 20 000 échantillons sur 5 ans, avec résultats et fiches).
  - Pagination **côté serveur** pour la liste des échantillons, le journal d'audit et les résultats de requêtes (tableaux Ant Design en mode serveur, avec tri et filtres conservés).
  - Index manquants ajoutés par migration, après lecture des plans d'exécution (`EXPLAIN ANALYZE`) des requêtes lentes.
  - Objectifs : liste paginée, tableau de bord et notifications en moins de 500 ms ; bilan mensuel en moins de 10 s.
  - Fait quand : les temps mesurés avant et après sont notés au Journal, et les objectifs sont atteints.

- [ ] **Q6. Finitions de l'interface.**
  - Sur toutes les pages : état de chargement (`Skeleton` ou `Spin`), état vide explicite (`Empty` avec action utile), état d'erreur avec bouton « Réessayer ».
  - Avertissement avant de quitter un formulaire modifié et non enregistré.
  - Session expirée : retour à la connexion avec le message « Session expirée », puis retour à la page demandée après reconnexion.
  - Page 404 propre.
  - Numéro de version de l'application et environnement (Production / Test) affichés en bas du menu. En test, un bandeau discret « Environnement de test » apparaît.
  - Vérifier que tout reste utilisable en 1366 × 768 (écran courant au labo).
  - Fait quand : chaque point est vérifié par un test Playwright ou par une capture.

- [ ] **Q7. Déploiement sur le serveur du labo.**
  - `docs/deploiement.md` : installation complète sur un poste Windows neuf (PostgreSQL, Python, venv, dépendances, `.env`, `migrer.py`, build du front, création du compte admin), démarrage automatique, accès depuis les autres postes (adresse fixe, pare-feu), mise à jour d'une version, retour arrière.
  - Scripts `demarrer.ps1` et `mettre_a_jour.ps1` (sauvegarde automatique avant mise à jour, migrations, build, redémarrage). Pour le démarrage automatique, utiliser le Planificateur de tâches Windows. Si un service Windows (NSSM…) paraît préférable, le **documenter et proposer** sans l'installer.
  - Route `GET /api/health` enrichie : état de la base, version, dernière sauvegarde réussie (lue dans le journal de `sauvegarde.ps1`).
  - Fait quand : la procédure a été suivie de bout en bout sur `labo_test`, sans étape manquante.

- [ ] **Q8. Documentation et dossier de validation ISO 17025.**
  - `docs/guide_utilisateur.md` : un chapitre par rôle (réceptionniste, analyste, responsable, admin) avec les captures de Q3, rédigé simplement, en français.
  - `docs/validation/` : **dossier de validation** du logiciel. Pour chaque exigence (numérotation, double regard, verrou du rapport, calcul des seuils, exactitude des requêtes et du bilan, droits d'accès, audit), donner le cas de test, le résultat attendu, le résultat obtenu et la référence du test automatique. Générer le tableau automatiquement à partir de l'exécution des tests Q2 et Q3 (script `generer_dossier_validation.py`), en indiquant la date et la version.
  - `CHANGELOG.md` avec les versions et les changements principaux.
  - Mettre à jour `CLAUDE.md` : structure, commandes de test et de migration, conventions ajoutées.
  - Fait quand : le guide et le dossier de validation sont complets, et le dossier se régénère d'une commande.
