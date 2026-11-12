# Facturation et paiement — guide

La facturation suit le modèle de la base Access : **une ligne par analyse**, des **totaux par section**, un **bulletin** par échantillon (ou pour plusieurs échantillons d'un même client) et une **quittance** par encaissement. Les montants sont en dirhams (`1 250,00 DH`), arrondis au centime.

Qui fait quoi :

| Action | Accueil (`user`) | Responsable | Admin | Analyste (rôle de section) |
|---|---|---|---|---|
| Voir les montants, les bulletins, le journal de caisse | oui | oui | oui | non (statut de paiement seulement) |
| Lignes facturables, bulletins, encaissements | oui | non | oui | non |
| Avoirs, exonérations, annulation d'un encaissement | non | oui | oui | non |
| Tarifs et réglages | non | non | oui | non |

---

## 1. Accueil

### 1.1 Les lignes à facturer

Ouvrir la fiche de l'échantillon (**Échantillons** puis le n°). Le bloc **Facturation** affiche :

- les **lignes facturables** : une par analyse. Elles sont **proposées automatiquement** quand l'analyste enregistre ses résultats (étiquette `auto`). Le prix est celui de la grille **le jour où la ligne est créée** ; il ne change plus ensuite, même si le tarif change ;
- le **statut de paiement** de l'échantillon, le montant dû, le payé et le reste ;
- les **bulletins et avoirs** de l'échantillon.

Boutons :

- **Analyse** : ajouter une analyse prévue dès la réception (la liste montre le prix du jour). C'est ainsi qu'on obtient un **montant estimé** avant les résultats ; quand l'analyste saisira cette analyse, elle ne sera pas facturée deux fois ;
- **Frais divers** : un libellé et un montant (frais d'envoi…) ;
- **Mettre à jour depuis les analyses** : reprend les analyses saisies dans les résultats ;
- **Modifier** / **Retirer** une ligne : possible tant qu'elle n'est pas sur un bulletin émis (cadenas sinon).

Une analyse sans tarif apparaît « Prix à renseigner » (comptée 0) : saisir son prix sur la ligne, ou demander à l'admin de compléter la grille.

Une analyse « facturée par prélèvement » (réglage du tarif) est multipliée par le nombre de prélèvements de la section ; la quantité reste modifiable.

### 1.2 Créer et émettre un bulletin

1. Dans le bloc Facturation, cliquer **Bulletin** : un **brouillon** s'ouvre (sans numéro), avec les lignes non encore facturées.
2. Pour **regrouper** plusieurs échantillons du **même client**, les ajouter dans « Échantillons (même client) ». Un échantillon d'un autre client est refusé.
3. **Aperçu PDF** : le bulletin porte la mention « BROUILLON ».
4. **Émettre** : le bulletin reçoit son numéro définitif `BUL-AAAA-NNNNN`, son PDF est archivé (avec son empreinte SHA-256) et il **ne peut plus être modifié**. Le bouton **PDF** redonne toujours exactement le même fichier.

L'émission est refusée tant qu'une ligne est « Prix à renseigner ». Un brouillon inutile se supprime par **Abandonner** (aucun numéro n'est consommé).

Le PDF reprend l'en-tête ONSSA / LRAR, le client et son adresse, les échantillons, les lignes groupées par section avec sous-totaux, le total (et la TVA si son taux n'est pas nul) et le montant en lettres : « Arrêté le présent bulletin à la somme de … dirhams ».

### 1.3 Encaisser et éditer une quittance

Ouvrir le bulletin (depuis la fiche de l'échantillon ou **Facturation > Bulletins et caisse**), puis **Encaisser** :

- date, montant (par défaut : le reste dû), mode (`espèces`, `chèque`, `virement`, `autre`) ; pour un chèque ou un virement, son numéro et la banque ;
- **N° de quittance** : celui du carnet de la régie s'il y en a un ; laissé vide, le numéro est attribué automatiquement (`Q-AAAA-NNNNN`).

La **quittance** (reçu PDF, montant en chiffres et en lettres) s'ouvre aussitôt ; elle reste téléchargeable depuis la liste des encaissements.

Les **paiements partiels** sont acceptés : le statut passe à « Partiellement payé » puis « Payé ». Un montant supérieur au reste dû demande une **confirmation** : il est alors enregistré comme **trop-perçu** (signalé).

Statuts de paiement : `Non payé`, `Partiellement payé`, `Payé`, `Exonéré`, `Avoir total` (et `Non concerné` pour un échantillon sans facturation). Ils apparaissent dans la liste des échantillons, le détail, le tableau de bord et la file de travail ; la liste et son export se filtrent par statut (colonnes « Montant », « Payé », « Reste dû »).

### 1.4 Suivi : page « Facturation »

Menu **Facturation > Bulletins et caisse** :

- **Bulletins** : recherche par n° de bulletin ou d'échantillon, client, période, section, statut ;
- **Impayés** : reste dû par client, par ancienneté (0-30, 31-60, 61-90, plus de 90 jours depuis l'émission) ;
- **Journal de caisse** : encaissements d'un jour ou d'une période, totaux par mode de paiement, pour le rapprochement avec la régie. **Export Excel** et **PDF signé** (nom de l'agent et date). Les encaissements annulés sont rappelés à part et **exclus des totaux**.

La cloche signale les **bulletins impayés** depuis plus de 30 jours (seuil réglable).

---

## 2. Responsable

### 2.1 Faire un avoir

Un bulletin émis ne se modifie jamais : une erreur se corrige par un **avoir** (bulletin négatif lié au bulletin d'origine).

Ouvrir le bulletin, **Faire un avoir**, puis :

- soit cocher les **lignes à annuler** (chacune ne peut être annulée qu'une fois) ;
- soit saisir un **montant** (au plus le reste du bulletin) ;
- et un **motif** (obligatoire).

L'avoir est émis aussitôt (`AV-AAAA-NNNNN`, PDF archivé, mention « Annule (partiellement) le bulletin n° … »). Le net à payer du bulletin baisse d'autant. Les lignes annulées redeviennent modifiables sur l'échantillon : les **corriger puis faire un nouveau bulletin**, ou les **retirer**. Un bulletin entièrement couvert par des avoirs passe à « Avoir total ».

### 2.2 Exonérer

- **Exonérer** un bulletin émis (dans son tiroir), ou **Exonérer l'échantillon** (bloc Facturation, tant qu'il n'est sur aucun bulletin) ;
- type : `contrôle officiel`, `convention` ou `autre`, et un **motif** (obligatoire) ;
- le statut passe à « Exonéré » ; plus aucun encaissement n'est possible ; l'opération est tracée dans le journal d'audit ;
- **Annuler l'exonération** (avec un motif) remet le bulletin ou l'échantillon dans son état précédent.

### 2.3 Annuler un encaissement

Un encaissement n'est **jamais supprimé**. En cas d'erreur (chèque rejeté, mauvaise saisie) : **Annuler** sur la ligne de l'encaissement, avec un motif. Il reste visible (barré), son motif est conservé, il sort des totaux et le statut du bulletin revient en arrière.

---

## 3. Administrateur

### 3.1 Tarifs

**Administration > Référentiels > Tarifs des analyses** :

- la grille affiche le prix en vigueur de chaque analyse (une par section), depuis quelle date, et son état (« À valider » pour les prix repris d'Access, « Validé », « Inactif ») ;
- **Modifier** un prix avec une **date d'effet** (aujourd'hui par défaut, jamais dans le futur) : une **nouvelle période** est créée, l'ancienne est conservée (historique dépliable sur chaque ligne). Les lignes et bulletins déjà créés gardent leur prix ;
- **Grille au** : affiche les prix applicables à une date passée ;
- **Par prélèvement** : la quantité facturée vaut le nombre de prélèvements de la section ;
- la liste repliable « analyse(s) du catalogue sans prix en vigueur » montre les analyses à compléter (**Renseigner le prix**). Dans Access, seules 6 analyses SMA avaient un prix : les grilles SCHA et SSA sont à saisir ;
- un tarif qui a un historique ne se supprime pas : le désactiver.

### 3.2 Réglages de facturation

En tête de l'onglet Tarifs :

- **TVA (%)** : 0 par défaut (laboratoire public) ; à 0, aucune ligne TVA n'apparaît sur les documents. Le taux est figé sur chaque bulletin à son émission ;
- **Paiement exigé** : `Aucune` (par défaut : rien n'est bloqué, un avertissement s'affiche sur la fiche d'un échantillon non soldé), `Avant la mise en analyse` (la création de la fiche de traitement est refusée) ou `Avant la remise du rapport` (la 1re émission du rapport est refusée) tant que l'échantillon n'est ni payé, ni exonéré, ni soldé par un avoir ;
- **Impayé après (jours)** : seuil des notifications d'impayés (30 par défaut).

### 3.3 Reporting et bilan mensuel

Dans **Reporting > Requêtes**, le jeu de données **Facturation** est le journal des mouvements des bulletins émis (lignes facturées, avoirs, exonérations, encaissements). Mesures : nombre de bulletins, montant facturé, avoirs, exonéré, encaissé, reste à recouvrer (= facturé − avoirs − exonérations − encaissé). Regroupements : client, section, analyse, mode de paiement, type de mouvement, mois. Date de référence : émission du bulletin, ou date du mouvement (encaissements du mois).

Le **bilan mensuel** comporte une section « Facturation » (bulletins du mois par section, encaissements par mode de paiement, impayés à la date du bilan), modifiable dans sa composition.

### 3.4 Points techniques

- Format des numéros : `FORMATS_NUMERO` dans `backend/app/services/bulletins.py` (seul endroit à modifier) ; séquences annuelles propres à chaque type, attribuées à l'émission, sans trou ni doublon.
- Les PDF émis (bulletins, avoirs, quittances) sont stockés en base avec leur SHA-256 : ils sont inclus dans les sauvegardes `pg_dump`.
- Toute opération est tracée dans `audit_log` et dans le journal d'audit inviolable `audit_donnees`.
