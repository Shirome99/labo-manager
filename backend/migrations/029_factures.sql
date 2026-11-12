-- ============================================================
-- LIMS LRARVY — Bulletins (factures) et avoirs (tâche 36, bloc P)
-- Migration ADDITIVE : nouvelles tables + une colonne ajoutée à factures_lignes (028).
--
--  * factures : un bulletin (type 'facture') ou un avoir (type 'avoir', négatif, lié au
--    bulletin d'origine). Statut 'brouillon' (modifiable, sans numéro), 'émis' (numéro,
--    PDF archivé + SHA-256, plus jamais modifié) ou 'annulé' (brouillon abandonné).
--    Numéro attribué à l'émission, séquence annuelle par type, jamais réutilisée :
--    format défini dans app/services/facturation.py (FORMATS_NUMERO).
--  * factures_echantillons : échantillons (d'un même client) couverts par le bulletin.
--  * factures_details : copie figée des lignes au moment de l'émission (le PDF et les
--    totaux ne dépendent plus des lignes vivantes). Pour un avoir : lignes négatives,
--    avec la ligne du bulletin d'origine qu'elles annulent.
--  * factures_lignes.facture_id : bulletin émis qui porte la ligne (ligne verrouillée).
-- ============================================================

CREATE TABLE IF NOT EXISTS factures (
    id                 SERIAL PRIMARY KEY,
    numero             VARCHAR(30) UNIQUE,
    type               VARCHAR(10)   NOT NULL DEFAULT 'facture' CHECK (type IN ('facture', 'avoir')),
    statut             VARCHAR(10)   NOT NULL DEFAULT 'brouillon' CHECK (statut IN ('brouillon', 'émis', 'annulé')),
    annee              INTEGER,
    sequence           INTEGER,
    client_nom         VARCHAR(255),
    client_adresse     TEXT,
    facture_origine_id INTEGER REFERENCES factures (id) ON DELETE RESTRICT,
    motif              TEXT,
    taux_tva           NUMERIC(5,2)  NOT NULL DEFAULT 0,
    total_ht           NUMERIC(12,2) NOT NULL DEFAULT 0,
    montant_tva        NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_ttc          NUMERIC(12,2) NOT NULL DEFAULT 0,
    date_emission      DATE,
    cree_par           VARCHAR(80),
    cree_le            TIMESTAMP     NOT NULL DEFAULT now(),
    emise_par          VARCHAR(80),
    emise_le           TIMESTAMP,
    annulee_par        VARCHAR(80),
    annulee_le         TIMESTAMP,
    pdf                BYTEA,
    sha256             VARCHAR(64),
    UNIQUE (type, annee, sequence),
    CHECK (statut <> 'émis' OR (numero IS NOT NULL AND pdf IS NOT NULL AND sha256 IS NOT NULL)),
    CHECK (type <> 'avoir' OR (facture_origine_id IS NOT NULL AND motif IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS factures_statut ON factures (type, statut);
CREATE INDEX IF NOT EXISTS factures_origine ON factures (facture_origine_id);
CREATE INDEX IF NOT EXISTS factures_client ON factures (lower(client_nom));

CREATE TABLE IF NOT EXISTS factures_echantillons (
    facture_id      INTEGER     NOT NULL REFERENCES factures (id) ON DELETE CASCADE,
    num_echantillon VARCHAR(50) NOT NULL REFERENCES echantillons ("N° Echantillon") ON DELETE RESTRICT,
    PRIMARY KEY (facture_id, num_echantillon)
);
CREATE INDEX IF NOT EXISTS factures_echantillons_num ON factures_echantillons (num_echantillon);

CREATE TABLE IF NOT EXISTS factures_details (
    id                SERIAL PRIMARY KEY,
    facture_id        INTEGER       NOT NULL REFERENCES factures (id) ON DELETE CASCADE,
    ligne_id          INTEGER       REFERENCES factures_lignes (id) ON DELETE SET NULL,
    detail_origine_id INTEGER       REFERENCES factures_details (id) ON DELETE RESTRICT,
    num_echantillon   VARCHAR(50),
    section           VARCHAR(4),
    libelle           VARCHAR(255)  NOT NULL,
    quantite          NUMERIC(10,2) NOT NULL DEFAULT 1,
    prix_unitaire     NUMERIC(12,2),
    montant           NUMERIC(12,2) NOT NULL,
    ordre             INTEGER       NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS factures_details_facture ON factures_details (facture_id);
CREATE INDEX IF NOT EXISTS factures_details_origine ON factures_details (detail_origine_id);

ALTER TABLE factures_lignes
    ADD COLUMN IF NOT EXISTS facture_id INTEGER REFERENCES factures (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS factures_lignes_facture ON factures_lignes (facture_id);

-- Journal d'audit inviolable (migration 015) ; la colonne pdf n'est jamais recopiée
SELECT audit_attacher('factures');
SELECT audit_attacher('factures_echantillons');
SELECT audit_attacher('factures_details');
