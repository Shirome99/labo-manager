# Ajout au Backlog — tâches 9 à 20

> Instructions pour Claude Code : insère les tâches ci-dessous **à la fin de la section « Backlog » de `CLAUDE.md`**, après la tâche 8, sans modifier les tâches existantes ni le Journal. Ajoute ensuite une entrée au Journal : « Ajout des tâches 9 à 20 (production, quotidien, V2 ISO 17025) ».
>
> L'utilisateur **demande maintenant** le rôle « responsable » et le verrouillage du stepper : retire ces deux points de la liste « Reportés volontairement ».
>
> Les changements de règles métier décrits dans les tâches 10 et 14 sont **autorisés par l'utilisateur** : ils ne déclenchent pas de condition d'arrêt. Toute autre modification de règle métier reste une condition d'arrêt.
>
> Toute nouvelle interface utilise **Ant Design**, de façon cohérente avec les pages existantes.

---

## Bloc A — Indispensable avant la mise en production

- [ ] **9. Rapport d'essai officiel et figé.**
  - **Numéro officiel** attribué à la 1re émission, jamais réutilisé. Regarde d'abord l'en-tête actuel de `services/rapport.py` (« RAPPORT D'ESSAI N° /CH/ ») et le dump Access, pour reprendre la numérotation du labo si elle y figure. Sinon, utilise `NNNN/CODE/AAAA` (CODE = `MA` pour SMA, `CH` pour SCHA, `SA` pour SSA), avec une séquence par section remise à zéro chaque année, et note la décision au Journal.
  - Nouvelle table `rapports_emis` (migration additive) : numéro (unique), n° d'échantillon, section, version, date d'émission, émis par, empreinte SHA-256, PDF stocké en `bytea` (il est ainsi inclus dans les sauvegardes `pg_dump`), statut (`valide` / `annulé`), référence au rapport remplacé, motif.
  - À la 1re émission : génération, enregistrement du PDF et de son empreinte, statut `Rapport émis`. Ensuite, `GET /api/rapports/{section}/{num}` renvoie **le PDF stocké**, octet pour octet, et ne le régénère plus.
  - **Erratum** : un responsable rouvre le dossier avec un motif obligatoire (statut → `En cours`). Le circuit normal reprend : correction, soumission, validation. La nouvelle émission crée la version suivante, avec dans le PDF la mention « Annule et remplace le rapport n° X du JJ/MM/AAAA » et le motif ; l'ancienne version passe à `annulé` et reste consultable.
  - `EchantillonDetail` : historique des rapports (numéro, version, date, émetteur, empreinte, statut), avec téléchargement de chaque version.
  - Fait quand : deux téléchargements successifs donnent un fichier identique (même SHA-256) ; une modification de données après l'émission ne change pas le PDF émis ; un erratum produit une version 2 qui référence la version 1, et la version 1 reste téléchargeable.

- [ ] **10. Rôle « responsable » et verrouillage du circuit.** *(changement de règle autorisé)*
  - Nouveau rôle `responsable` (adapter la contrainte sur `users.role` si elle existe, par migration). Il voit toutes les sections.
  - **Valider, renvoyer, émettre un rapport et lancer un erratum** sont réservés à `responsable` et `admin`. `user` garde la lecture globale et la réception, mais ne valide plus.
  - Le double regard reste obligatoire pour tout le monde, admin compris.
  - Stepper manuel de `EchantillonDetail` : réservé à `admin`, et il ne peut plus mener à `Validé` ni à `Rapport émis` (seuls les circuits dédiés y mènent). Vérification côté serveur dans `changer_statut`.
  - Mettre à jour la section « Règles métier » de `CLAUDE.md`, les notifications (le responsable reçoit les fiches `À valider`) et l'écran des comptes (le rôle doit être proposé).
  - Fait quand : des tests curl avec un compte de chaque rôle confirment la matrice de droits (200 / 403 attendus), et le build passe.

- [ ] **11. Journal d'audit inviolable.**
  - Fonction trigger PostgreSQL générique sur `echantillons`, `traitement_sma/scha/ssa`, `resultats_analyses`, `rapports_emis`, `users` et les tables `ref_*`. Elle écrit dans une nouvelle table `audit_donnees` : table, opération, clé, données **avant** et **après** en `jsonb`, utilisateur, horodatage. Ne jamais copier le hash du mot de passe.
  - L'utilisateur applicatif est transmis à la base par `SET LOCAL lims.utilisateur = …` au début de chaque transaction, et lu par `current_setting('lims.utilisateur', true)` ; à défaut, on enregistre l'utilisateur PostgreSQL.
  - `audit_donnees` est protégée par un trigger qui **refuse tout UPDATE et tout DELETE**.
  - Écran admin « Journal d'audit » : filtres (table, utilisateur, période, n° d'échantillon) et comparaison avant / après.
  - L'`AuditLog` applicatif existant est conservé.
  - Fait quand : une modification faite directement en SQL (hors application) apparaît dans le journal, et un `DELETE FROM audit_donnees` échoue.

- [ ] **12. Sécurité des comptes.**
  - Expiration de session après inactivité (durée configurable, 30 min par défaut), en plus de la durée maximale.
  - Verrouillage du compte pendant 15 min après 5 échecs de connexion consécutifs (compteur en base), avec trace dans l'audit.
  - Règles de mot de passe : au moins 10 caractères, avec lettres et chiffres. Chaque utilisateur peut changer son propre mot de passe ; l'admin peut le réinitialiser.
  - Protection CSRF : sur les requêtes qui modifient des données, refuser une en-tête `Origin` / `Referer` étrangère, en plus de `SameSite`.
  - `docs/https.md` : procédure pour servir l'application en HTTPS sur le réseau local (documentation seulement, aucune installation système).
  - Fait quand : chaque règle est vérifiée par curl ou par un script de test, et documentée dans `CLAUDE.md`.

## Bloc B — Gain au quotidien

- [ ] **13. Étiquettes code-barres et scan.**
  - `GET /api/echantillons/{num}/etiquette` : PDF d'étiquettes (format configurable, 50 × 25 mm par défaut) avec un code-barres Code 128 du n° d'échantillon, la section, la nature et la date de réception. Générer avec `reportlab.graphics.barcode`, sans nouvelle dépendance. Une étiquette par prélèvement (selon `Nbre Prlvmts` de la section).
  - Bouton « Imprimer les étiquettes » après l'enregistrement d'une réception et dans `EchantillonDetail`.
  - Champ de recherche global dans la topbar, compatible douchette (qui se comporte comme un clavier et envoie Entrée) : un n° exact ouvre directement la fiche détail, sinon on arrive sur la liste filtrée.
  - Fait quand : le PDF s'ouvre, le code-barres est lisible (vérifie en le décodant si un outil est disponible) et le scan simulé (n° + Entrée) ouvre la bonne fiche.

- [ ] **14. Non-conformités à la réception structurées.** *(changement de règle autorisé)*
  - Migration additive : température à réception, cases de non-conformité (température, contenant, quantité insuffisante, étiquetage, délai d'acheminement, autre), **décision** (`Accepté` / `Accepté sous réserve` / `Refusé`) et motif. Le champ texte `non_conformite` actuel est conservé comme observation.
  - Un échantillon `Refusé` ne peut pas recevoir de fiche de traitement (409 côté serveur). Il s'affiche avec un `Tag` « Refusé » dans les listes et le détail. On n'ajoute pas de nouveau statut.
  - Le bloc II du rapport (« Données relevées par le laboratoire ») reprend la température, l'état et la réserve éventuelle.
  - Filtre « Décision de réception » dans la liste et dans l'export.
  - Fait quand : on peut enregistrer chaque cas, la création d'une fiche sur un échantillon refusé est bloquée, et le rapport affiche la réserve.

- [ ] **15. File de travail.**
  - Page « Mon travail ». Pour un analyste (rôle de section) : ses échantillons à traiter, classés par priorité (renvoyés, puis en retard, puis `Reçu`, puis `En cours` non soumis). Pour un responsable : fiches `À valider` et rapports à émettre.
  - Dans `Traitement` et `Resultats` : boutons « Précédent / Suivant » pour enchaîner les fiches de la file sans revenir à la liste.
  - Fait quand : la page existe pour chaque rôle, et l'enchaînement fonctionne.

- [ ] **16. Facturation des analyses.**
  - Vérifie d'abord ce que couvre la migration `012_paiement_analyses.sql`. Reprends la grille de prix depuis la table `PRIX` du dump Access dans une table `ref_tarifs` (analyse, section, prix), administrable dans `Referentiels`.
  - Calcul du montant par échantillon à partir des analyses effectuées ; saisie du n° de quittance, de la date et du statut de paiement ; filtre et colonnes de paiement dans la liste et l'export.
  - Fait quand : le montant se calcule sur un échantillon de test, et l'export contient les colonnes de paiement.

## Bloc C — V2 : exigences ISO 17025

- [ ] **17. Équipements et étalonnage.**
  Inventaire (désignation, n° de série, section, emplacement), dates d'étalonnage et de vérification avec périodicité, historique des maintenances et des pannes. Alerte dans les notifications 30 jours avant l'échéance. Choix de l'équipement utilisé dans la fiche de traitement (champ `equipement_utilise` déjà prévu) ; si l'équipement est hors étalonnage à la date de l'analyse, la fiche est signalée « contestable » au responsable.
  Fait quand : un équipement échu déclenche l'alerte et le signalement.

- [ ] **18. Contrôles qualité internes.**
  Saisie des contrôles (témoins positifs / négatifs, blancs, duplicatas) par méthode et par date. Cartes de contrôle (moyenne, ±2σ, ±3σ) affichées en graphique. Alerte quand une valeur sort de ±3σ, ou quand 7 points consécutifs se trouvent du même côté de la moyenne.
  Fait quand : une série de test produit la carte et l'alerte attendue.

- [ ] **19. Habilitations du personnel.**
  Matrice « utilisateur × analyse » avec date de qualification et d'échéance. Seul un analyste habilité et à jour peut enregistrer un résultat pour cette analyse (contrôle côté serveur). Alerte 30 jours avant l'échéance.
  Fait quand : un analyste non habilité reçoit un 403 à l'enregistrement.

- [ ] **20. Réactifs et milieux de culture.**
  Stocks par lot (produit, n° de lot, fournisseur, péremption, quantité). Alertes de péremption et de seuil bas. Choix du lot utilisé dans la fiche de traitement (champ `lot_reactif` déjà prévu), pour la traçabilité « quel lot pour quel échantillon ». Un lot périmé ne peut pas être choisi.
  Fait quand : un lot périmé est refusé et la traçabilité s'affiche dans le détail de l'échantillon.
