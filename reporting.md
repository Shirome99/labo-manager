# Ajout au Backlog — Bloc D : Requêtes et reporting mensuel

> **Instructions pour Claude Code**
>
> 1. Insère les tâches ci-dessous dans la section « Backlog » de `CLAUDE.md`, **juste après la dernière tâche cochée et avant les tâches pas encore commencées** : l'utilisateur veut ce bloc en priorité. Numérote-les à la suite de la dernière tâche existante (R1 à R5 deviennent les numéros suivants) et ne modifie pas les autres tâches.
> 2. Ajoute une entrée au Journal : « Ajout du bloc D (requêtes et reporting mensuel), placé en priorité ».
> 3. Si une tâche est en cours à moitié, termine-la d'abord, puis passe à ce bloc.
> 4. Les règles de `CLAUDE.md` s'appliquent : lire avant de modifier, migrations additives, vérifications, Journal, conditions d'arrêt. L'interface utilise **Ant Design**, de façon cohérente avec les pages existantes.

## Objectif

Le labo doit pouvoir **compter et extraire ses données selon les critères de son choix**, par exemple : nombre d'échantillons par type, par section, par fabricant, par organisme préleveur, par mois, taux de non-conformité par catégorie. Le résultat doit pouvoir être sorti en **Excel ou en PDF**, en particulier pour le **bilan mensuel** remis à la direction et à l'ONSSA.

## Principes à respecter

- **Pas de SQL libre saisi par l'utilisateur.** Les critères, les regroupements et les mesures sont choisis dans des listes fermées, définies côté serveur dans un **catalogue**. Chaque entrée du catalogue correspond à une expression SQL écrite dans le code. Toutes les valeurs sont paramétrées.
- **Contrôle d'accès** : un rôle de section ne voit que les données de sa section, y compris dans les requêtes, les exports et le bilan mensuel.
- Les identifiants (type, sous-type…) sont toujours affichés par leur **libellé** (jointure sur les référentiels).
- Les valeurs vides sont regroupées sous « Non renseigné », jamais ignorées sans le dire.
- Les chiffres doivent être **justes et vérifiables** : chaque total d'une requête doit correspondre au nombre obtenu par une requête SQL directe.

---

- [ ] **R1. Moteur de requêtes (backend).**
  - Fichier `backend/app/services/requetes.py` avec le **catalogue** :
    - **Jeux de données** : `echantillons` (une ligne par échantillon) et `analyses` (une ligne par résultat d'analyse, joint à son échantillon). Ajoute `facturation` si la tâche de facturation est déjà faite.
    - **Filtres** : période (du / au) sur une date de référence au choix (date de réception par défaut ; date d'émission du rapport si `rapports_emis` existe), section, statut, type, sous-type, catégorie, nature, fabricant, organisme préleveur, espèce animale, et selon ce qui existe en base : décision de réception, analyse effectuée, conformité, en retard (oui / non).
    - **Regroupements** (jusqu'à 2 à la fois, pour un tableau croisé) : section, statut, type, sous-type, catégorie, nature, fabricant, organisme préleveur, espèce animale, analyse, conformité, mois, trimestre, année.
    - **Mesures** : nombre d'échantillons, nombre d'analyses, nombre de prélèvements, nombre et taux de non-conformes, nombre en retard, délai moyen et médian entre réception et émission du rapport (en jours), et montant facturé si la facturation existe.
  - Routes :
    - `GET /api/requetes/catalogue` : renvoie le catalogue (libellés en français) pour construire l'interface ;
    - `POST /api/requetes/executer` : prend `{jeu, filtres, regroupements, mesures, tri, limite}` et renvoie les lignes, les totaux et le SQL utilisé (pour l'admin seulement, à titre de contrôle).
  - Refuser (400) toute clé hors catalogue ; limiter le résultat (5 000 lignes par défaut) ; ajouter par migration les index utiles (date de réception, section, statut, fabricant).
  - Fait quand : un script de test compare, pour au moins 8 combinaisons, les totaux de la route avec des requêtes SQL directes, et tous concordent ; une clé inconnue renvoie 400 ; un rôle de section ne voit que sa section.

- [ ] **R2. Page « Requêtes » (constructeur).**
  - Nouvelle entrée de menu « Reporting », avec une page « Requêtes » :
    - à gauche ou en haut : choix du jeu de données, des filtres (`Select` avec recherche, `RangePicker` pour la période), des regroupements et des mesures ;
    - à droite ou en dessous : résultat en `Table` (tri, totaux en pied de tableau), en tableau croisé quand il y a 2 regroupements, et un graphique en barres simple.
  - Pour le graphique, tu peux ajouter `@ant-design/plots` (nouvelle dépendance autorisée, à noter au Journal) ; si l'installation pose problème, fais des barres simples en CSS.
  - Clic sur une ligne du résultat → liste des échantillons correspondants (réutiliser la page Échantillons avec les filtres dans l'URL quand c'est possible).
  - Boutons **Export Excel** et **Export PDF** du résultat affiché :
    - Excel : une feuille « Résultat » (en-tête stylé, totaux, colonnes ajustées), une feuille « Paramètres » (jeu, filtres, regroupements, mesures, date, utilisateur) et une feuille « Détail » avec les lignes brutes, limitée à 50 000 lignes ;
    - PDF (ReportLab) : en-tête ONSSA / LRAR comme le rapport d'essai, titre, paramètres, tableau, graphique (`reportlab.graphics`), date et auteur en pied de page.
  - Fait quand : on peut construire « nombre d'échantillons par type et par mois pour la SMA en septembre », l'afficher, l'exporter en Excel et en PDF, et les deux fichiers s'ouvrent avec les mêmes chiffres qu'à l'écran.

- [ ] **R3. Requêtes enregistrées.**
  - Table `requetes_enregistrees` (migration) : nom, description, définition en `jsonb`, auteur, visibilité (`personnelle` / `partagée`), dates de création et de modification.
  - Dans la page Requêtes : « Enregistrer », « Ouvrir », « Dupliquer », « Supprimer » (seulement l'auteur ou l'admin). Une requête partagée est visible par tous les utilisateurs qui ont accès aux données concernées.
  - Une requête enregistrée peut garder une **période relative** (« mois précédent », « mois en cours », « année en cours ») au lieu de dates fixes.
  - Crée par migration quelques requêtes partagées utiles : échantillons par section et par mois ; par type et sous-type ; par fabricant ; par organisme préleveur ; taux de non-conformité par catégorie ; délais moyens par section ; retards par section.
  - Fait quand : une requête enregistrée avec « mois précédent » donne le bon mois quand on la rouvre, et les droits de visibilité sont respectés.

- [ ] **R4. Bilan mensuel (PDF et Excel).**
  - Page « Bilan mensuel » : choix du mois (par défaut le mois précédent) et de la section (toutes ou une seule), puis **Générer PDF** et **Générer Excel**.
  - Contenu, dans cet ordre :
    1. synthèse : reçus, rapports émis, en cours, à valider, en retard, taux de non-conformité, délai moyen, avec la comparaison au mois précédent ;
    2. répartition par section, par type, par fabricant, par organisme préleveur ;
    3. non-conformités, par catégorie et par analyse ;
    4. délais et retards par section ;
    5. facturation du mois, si elle existe.
  - Le contenu est **paramétrable par l'admin** : un écran liste les requêtes enregistrées (R3) qui composent le bilan, dans quel ordre et sous quel titre. Un modèle par défaut reprenant la liste ci-dessus est créé par migration.
  - Chaque bilan généré est **archivé** (table `bilans_mensuels` : mois, section, format, fichier en `bytea`, empreinte SHA-256, auteur, date), avec un historique téléchargeable. Régénérer un même mois crée une nouvelle version, sans écraser la précédente.
  - Script `backend/scripts/bilan_mensuel.py --mois AAAA-MM [--section SMA]`, utilisable dans une tâche planifiée Windows le 1er du mois. Documente-le dans `docs/bilan_mensuel.md`.
  - Fait quand : le bilan de septembre 2026 se génère en PDF et en Excel, les chiffres concordent avec les requêtes de R1, le fichier est archivé, et le script produit le même bilan en ligne de commande.

- [ ] **R5. Contrôle final du reporting.**
  - Vérifie les chiffres sur les données importées d'Access (2010) si l'import a été fait, sinon sur les données de test : totaux par section = total général, aucune ligne perdue dans « Non renseigné ».
  - Mets à jour `CLAUDE.md` : section Structure (nouveaux fichiers), règles du catalogue (pas de SQL libre), et procédure pour ajouter un nouveau critère ou une nouvelle mesure au catalogue.
  - Fait quand : le Journal contient le tableau des contrôles effectués et leurs résultats.
