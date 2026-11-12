-- ============================================================
-- LIMS LRARVY — Réactifs et milieux de culture (tâche 20, ISO 17025 § 6.6)
-- Migration ADDITIVE : crée deux tables, ne modifie rien d'existant.
--
-- reactifs_lots        : un lot = un produit reçu (code interne unique L<AAAA>-<NNNN>,
--                        n° de lot du fournisseur, péremption, stock courant, seuil d'alerte).
-- reactifs_mouvements  : entrées, sorties et ajustements d'inventaire (historique du stock).
-- La fiche de traitement désigne les lots utilisés par leur code dans `lot_reactif`
-- (plusieurs codes séparés par des virgules) : traçabilité « quel lot pour quel échantillon ».
-- ============================================================

CREATE TABLE IF NOT EXISTS reactifs_lots (
    id                 SERIAL PRIMARY KEY,
    code               VARCHAR(20)  NOT NULL UNIQUE,
    produit            VARCHAR(200) NOT NULL,
    categorie          VARCHAR(30)  NOT NULL DEFAULT 'Réactif'
                       CHECK (categorie IN ('Réactif', 'Milieu de culture', 'Souche de référence', 'Autre')),
    numero_lot         VARCHAR(80)  NOT NULL,
    fournisseur        VARCHAR(150),
    section            VARCHAR(4) CHECK (section IN ('SMA', 'SCHA', 'SSA')),   -- NULL : commun
    date_reception     DATE,
    date_ouverture     DATE,
    date_peremption    DATE NOT NULL,
    quantite_initiale  NUMERIC(12, 3) NOT NULL CHECK (quantite_initiale >= 0),
    quantite           NUMERIC(12, 3) NOT NULL CHECK (quantite >= 0),
    unite              VARCHAR(20)  NOT NULL DEFAULT 'unité',
    seuil_alerte       NUMERIC(12, 3) CHECK (seuil_alerte >= 0),
    emplacement        VARCHAR(150),
    actif              BOOLEAN NOT NULL DEFAULT true,
    observations       TEXT,
    cree_par           VARCHAR(100) NOT NULL,
    cree_le            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS reactifs_lots_produit_lot
    ON reactifs_lots (lower(btrim(produit)), lower(btrim(numero_lot)));
CREATE INDEX IF NOT EXISTS reactifs_lots_peremption ON reactifs_lots (date_peremption);
SELECT audit_attacher('reactifs_lots');

CREATE TABLE IF NOT EXISTS reactifs_mouvements (
    id               SERIAL PRIMARY KEY,
    lot_id           INTEGER NOT NULL REFERENCES reactifs_lots(id) ON DELETE RESTRICT,
    date_mouvement   DATE NOT NULL,
    type_mouvement   VARCHAR(12) NOT NULL CHECK (type_mouvement IN ('Entrée', 'Sortie', 'Ajustement')),
    quantite         NUMERIC(12, 3) NOT NULL CHECK (quantite >= 0),   -- Ajustement : stock constaté
    stock_apres      NUMERIC(12, 3) NOT NULL CHECK (stock_apres >= 0),
    num_echantillon  VARCHAR(50),
    motif            TEXT,
    saisi_par        VARCHAR(100) NOT NULL,
    saisi_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reactifs_mouvements_lot ON reactifs_mouvements (lot_id);
SELECT audit_attacher('reactifs_mouvements');
