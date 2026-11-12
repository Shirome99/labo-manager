# Ajout au Backlog — Bloc P : Facturation et paiement (priorité)

> **Instructions pour Claude Code**
>
> 1. Ce bloc **remplace la tâche « Facturation des analyses »** déjà présente au Backlog : supprime-la et insère à sa place les tâches ci-dessous, **en priorité**, juste après la dernière tâche cochée (si une tâche est en cours, termine-la d'abord). Numérote-les à la suite (P1 à P8 deviennent les numéros suivants).
> 2. Si le bloc F (« ce que la base Access apporte encore ») a été ajouté au Backlog, déplace-le tel quel dans « Reportés volontairement » : l'utilisateur ne le veut pas pour l'instant.
> 3. Ajoute une entrée au Journal : « Ajout du bloc P (facturation et paiement), en priorité ; tâche de facturation précédente remplacée ».
> 4. Les règles de `CLAUDE.md` s'appliquent (lire avant de modifier, migrations additives, vérifications, Journal, conditions d'arrêt). Interface en **Ant Design**.
> 5. **Commence par lire `012_paiement_analyses.sql`** et le code qui l'utilise : ne recrée pas ce qui existe déjà, complète-le. Note au Journal ce qui était déjà en place.
> 6. Les **décisions par défaut** listées plus bas sont validées par l'utilisateur. Elles ne déclenchent pas de condition d'arrêt, mais doivent rester modifiables là où c'est indiqué.

## Ce qu'on sait de la base Access

- `Table Analyses` : prix par analyse (FMAT 40, coliformes fécaux 40, ASR 60, St. aureus 60, Listeria 70, E. coli 80 ; les autres à 0, donc non renseignés).
- `Table Méthode SSA` : prix par méthode SSA.
- `Nat de l'éch et analy effectuées` : jusqu'à 12 analyses et leur prix par nature d'échantillon (table vide).
- `PRIX` : par échantillon, nombre de paramètres et montant par section (MA, CH, SA), total par bulletin, n° et date de quittance (table vide).
- `Table Payement des Analyses effectuées` : une ligne par analyse facturée (échantillon, analyse, prix) (table vide).
- `Inf et trt de l'éch` : paiement, date de paiement, nombre de paramètres et montant par section, total, n° de quittance (colonnes vides à 99,9 %).
- Les tables de résultats ont toutes une colonne « Prix analyse ».

**Conclusion** : le modèle de facturation d'Access est clair (**une ligne par analyse, des totaux par section, un bulletin par échantillon, une quittance**), mais il n'a jamais été utilisé. Il n'y a donc **pas de données de paiement à importer**, seulement les prix de `Table Analyses` et `Table Méthode SSA`.

## Décisions par défaut

- Monnaie : **dirham marocain**, affiché `1 250,00 DH`. Montants stockés en `numeric(12,2)`, jamais en flottant.
- TVA : **taux configurable, 0 % par défaut** (laboratoire public). Si le taux vaut 0, aucune ligne TVA n'apparaît sur les documents.
- Un **bulletin** (facture) par échantillon par défaut ; on peut aussi regrouper plusieurs échantillons du **même client** dans un seul bulletin.
- Quantité facturée par ligne : **1 par défaut**, modifiable. Une option par analyse (« facturée par prélèvement ») multiplie automatiquement par le nombre de prélèvements de la section.
- Le **prix est figé** sur la ligne au moment où elle est créée : un changement de tarif ne modifie jamais un bulletin existant.
- Un bulletin **émis** n'est plus modifiable. Une correction se fait par un **avoir** (bulletin négatif lié au bulletin d'origine), puis un nouveau bulletin si nécessaire.
- **Exonération** possible (contrôle officiel, convention, autre) avec un motif obligatoire, accordée par un responsable ou un admin.
- Le paiement **ne bloque rien par défaut** : un avertissement s'affiche, et le statut de paiement est visible partout. Un réglage admin permet d'exiger le paiement à une étape (`aucune` / `avant la mise en analyse` / `avant la remise du rapport`) ; valeur par défaut `aucune`.
- Droits :
  - tarifs : admin ;
  - bulletins et encaissements : `user` (accueil) et admin ;
  - exonérations, avoirs et annulations d'encaissement : responsable (s'il existe) et admin ;
  - rôles de section : lecture du statut de paiement seulement.

---

- [ ] **P1. Grille tarifaire.**
  - Table `ref_tarifs` : analyse (lien vers `ref_analyses`), section, prix unitaire, « facturée par prélèvement » (oui / non), date de début et date de fin de validité (historique des prix), statut « à valider ».
  - Initialiser avec les prix non nuls de `Table Analyses` et `Table Méthode SSA` ; les analyses à 0 apparaissent « prix à renseigner ».
  - Écran admin dans `Referentiels` (onglet « Tarifs ») : modifier un prix crée une nouvelle période de validité, sans écraser l'ancienne. Ajouter un réglage du taux de TVA et de l'étape de paiement exigée.
  - Fait quand : un changement de prix daté d'aujourd'hui n'affecte pas un calcul fait pour une date antérieure, et les analyses sans prix sont clairement signalées.

- [ ] **P2. Lignes facturables de l'échantillon.**
  - Table `factures_lignes` : échantillon, section, analyse, quantité, prix unitaire figé, montant, origine (`automatique` / `manuelle`).
  - Les lignes sont proposées automatiquement à partir des analyses saisies dans les résultats (et des analyses demandées si elles existent), et modifiables tant que le bulletin n'est pas émis. On peut ajouter une ligne manuelle (frais divers) avec libellé et montant.
  - Dans `EchantillonDetail` : un bloc « Facturation » avec les lignes, les totaux par section, le total général, et le statut de paiement.
  - À la réception : affichage d'un **montant estimé** dès que les analyses sont connues.
  - Fait quand : un échantillon avec 3 analyses produit 3 lignes au bon prix, les totaux sont justes, et la quantité « par prélèvement » s'applique.

- [ ] **P3. Bulletin (facture) en PDF.**
  - Tables `factures` (numéro, client, date, statut `brouillon` / `émis` / `annulé`, type `facture` / `avoir`, facture d'origine pour un avoir, totaux HT, TVA et TTC, émise par) et `factures_echantillons` (lien vers un ou plusieurs échantillons du même client).
  - **Numéro** attribué à l'émission, jamais réutilisé, séquence annuelle : `BUL-AAAA-NNNNN` pour les factures, `AV-AAAA-NNNNN` pour les avoirs. Le format est modifiable dans un seul endroit du code ; note-le au Journal.
  - PDF (ReportLab) avec l'en-tête ONSSA / LRAR du rapport d'essai : client (nom, adresse depuis le référentiel), échantillons concernés, lignes groupées par section avec sous-totaux, total, **montant en lettres** (« Arrêté le présent bulletin à la somme de … dirhams »), mentions de paiement. Le PDF émis est **archivé** en base avec son empreinte SHA-256 (même principe que le rapport d'essai figé).
  - Avoir : choisir un bulletin émis, sélectionner les lignes ou le montant à annuler, avec un motif obligatoire.
  - Fait quand : un bulletin émis ne peut plus être modifié, son PDF retéléchargé est identique (même empreinte), et un avoir réduit bien le montant dû.

- [ ] **P4. Encaissements et quittances.**
  - Table `paiements` : bulletin, date, montant, mode (`espèces` / `chèque` / `virement` / `autre`), référence (n° de chèque ou de virement, banque), **n° de quittance**, encaissé par, observation, statut (`valide` / `annulé` avec motif).
  - Paiements **partiels** acceptés. Statut calculé du bulletin et de l'échantillon : `Non payé`, `Partiellement payé`, `Payé`, `Exonéré`, `Avoir total`. Le montant encaissé ne peut pas dépasser le reste dû, sauf confirmation explicite (trop-perçu signalé).
  - Annuler un encaissement : jamais de suppression, seulement le statut `annulé` avec un motif (réservé au responsable ou à l'admin).
  - Reçu de paiement PDF (quittance) avec n°, montant en chiffres et en lettres, mode, bulletin concerné.
  - Exonération : bouton sur le bulletin ou l'échantillon, avec motif obligatoire ; le statut passe à `Exonéré`, et l'exonération est tracée dans l'audit.
  - Fait quand : 2 paiements partiels donnent `Partiellement payé` puis `Payé`, une annulation fait revenir le statut en arrière, et chaque opération apparaît dans l'audit.

- [ ] **P5. Intégration au circuit de l'échantillon.**
  - `Tag` de statut de paiement dans la liste des échantillons, le détail, le tableau de bord et la file de travail.
  - Filtre « Statut de paiement » dans la liste et dans l'export Excel/CSV, avec les colonnes « Montant », « Payé », « Reste dû ».
  - Réglage de l'étape exigée (P1) : si une étape est configurée et que l'échantillon n'est ni payé ni exonéré, l'action correspondante est refusée côté serveur avec un message clair. Par défaut (`aucune`), seul un avertissement s'affiche.
  - Notifications : bulletins impayés depuis plus de 30 jours (seuil configurable), pour l'accueil et l'admin.
  - Fait quand : avec le réglage `aucune`, rien n'est bloqué mais l'avertissement s'affiche ; avec `avant la remise du rapport`, l'émission du rapport d'un échantillon impayé est refusée, puis acceptée après paiement ou exonération.

- [ ] **P6. Page « Paiements » et suivi de caisse.**
  - Nouvelle entrée de menu « Facturation » avec :
    - **Bulletins** : liste avec filtres (période, client, section, statut), recherche par n° ;
    - **Impayés** : reste dû par client, avec l'ancienneté (0–30, 31–60, 61–90, plus de 90 jours) ;
    - **Journal de caisse** : encaissements d'un jour ou d'une période, totaux par mode de paiement, pour le rapprochement avec la régie ; export Excel et PDF signé (nom de l'agent, date).
  - Fait quand : les totaux du journal de caisse correspondent à la somme des paiements valides de la période, encaissements annulés exclus.

- [ ] **P7. Reporting de la facturation.**
  - Ajouter au catalogue des requêtes (s'il existe) le jeu de données `facturation` et les mesures : montant facturé, montant encaissé, reste à recouvrer, montant exonéré, montant des avoirs, nombre de bulletins. Regroupements utiles : client, section, analyse, mode de paiement, mois.
  - Ajouter une section « Facturation » au bilan mensuel (s'il existe) : facturé, encaissé, impayés, exonérations, répartition par section et par mode de paiement.
  - Si le reporting n'existe pas encore, ajoute seulement un export Excel mensuel de la facturation dans la page Paiements, et note au Journal ce qui reste à brancher.
  - Fait quand : pour un mois de test, facturé − avoirs − exonérations − encaissé = reste dû, au centime près.

- [ ] **P8. Tests et documentation.**
  - Tests automatiques (si `backend/tests/` existe, sinon un script de vérification) :
    - prix figé après un changement de tarif ;
    - totaux et arrondis au centime ;
    - numérotation sans trou ni doublon, y compris en cas d'émissions simultanées ;
    - bulletin émis non modifiable ;
    - avoir, paiements partiels, annulation, exonération ;
    - réglage de l'étape exigée ;
    - droits de chaque rôle (200 / 403).
  - `docs/facturation.md` : guide pour l'accueil (créer un bulletin, encaisser, éditer une quittance, faire un avoir) et pour l'admin (tarifs, réglages).
  - Mettre à jour `CLAUDE.md` : règles de facturation (prix figé, bulletin émis non modifiable, avoir, pas de suppression d'encaissement) dans la section « Règles métier ».
  - Fait quand : tous les tests passent et la documentation est écrite.
