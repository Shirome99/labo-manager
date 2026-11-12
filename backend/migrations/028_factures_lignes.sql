-- ============================================================
-- LIMS LRARVY — Lignes facturables d'un échantillon (tâche 35, bloc P)
-- Migration ADDITIVE : nouvelle table, rien d'existant n'est modifié.
--
-- Une ligne = une analyse (ou des frais divers) à facturer pour un échantillon.
--  * origine 'automatique' : proposée à partir des analyses saisies dans les résultats ;
--    'manuelle' : ajoutée à la main (analyse de la grille ou frais divers).
--  * le prix unitaire est FIGÉ à la création (prix de la grille ce jour-là) : un changement
--    de tarif ne modifie jamais une ligne existante. NULL = prix à renseigner (montant 0).
--  * montant = quantité × prix unitaire, arrondi au centime, stocké.
-- ============================================================

CREATE TABLE IF NOT EXISTS factures_lignes (
    id              SERIAL PRIMARY KEY,
    num_echantillon VARCHAR(50)   NOT NULL REFERENCES echantillons ("N° Echantillon") ON DELETE CASCADE,
    section         VARCHAR(4)    CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    libelle         VARCHAR(150)  NOT NULL,   -- analyse ou frais divers (« analyse » est un mot réservé)
    tarif_id        INTEGER       REFERENCES ref_tarifs (id) ON DELETE SET NULL,
    quantite        NUMERIC(10,2) NOT NULL DEFAULT 1 CHECK (quantite > 0),
    prix_unitaire   NUMERIC(12,2) CHECK (prix_unitaire >= 0),
    montant         NUMERIC(12,2) NOT NULL DEFAULT 0,
    par_prelevement BOOLEAN       NOT NULL DEFAULT false,
    origine         VARCHAR(12)   NOT NULL DEFAULT 'manuelle' CHECK (origine IN ('automatique', 'manuelle')),
    cree_par        VARCHAR(80),
    cree_le         TIMESTAMP     NOT NULL DEFAULT now(),
    modifie_par     VARCHAR(80),
    modifie_le      TIMESTAMP
);
CREATE INDEX IF NOT EXISTS factures_lignes_echantillon ON factures_lignes (num_echantillon);

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('factures_lignes');
