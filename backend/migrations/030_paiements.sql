-- ============================================================
-- LIMS LRARVY — Encaissements, quittances et exonérations (tâche 37, bloc P)
-- Migration ADDITIVE : nouvelles tables, rien d'existant n'est modifié.
--
--  * paiements : un encaissement sur un bulletin émis (paiements partiels acceptés).
--    Jamais supprimé : une erreur se corrige par l'annulation (statut 'annulé' + motif).
--    N° de quittance unique : celui du carnet de la régie s'il est saisi, sinon Q-AAAA-NNNNN
--    (format dans app/services/bulletins.py, FORMATS_NUMERO). Reçu PDF archivé + SHA-256.
--  * exonerations : sur un bulletin émis ou sur un échantillon (contrôle officiel, convention,
--    autre), motif obligatoire, accordée par un responsable ; annulable avec motif.
-- Le statut de paiement calculé de l'échantillon est recopié dans les champs historiques
-- « Payement », « TOTAL », « Montant payé »… (migration 012), qui servent déjà aux listes.
-- ============================================================

CREATE TABLE IF NOT EXISTS paiements (
    id                SERIAL PRIMARY KEY,
    facture_id        INTEGER       NOT NULL REFERENCES factures (id) ON DELETE RESTRICT,
    date_paiement     DATE          NOT NULL,
    montant           NUMERIC(12,2) NOT NULL CHECK (montant > 0),
    mode              VARCHAR(10)   NOT NULL CHECK (mode IN ('espèces', 'chèque', 'virement', 'autre')),
    reference         VARCHAR(120),
    banque            VARCHAR(120),
    numero_quittance  VARCHAR(40)   NOT NULL UNIQUE,
    annee             INTEGER,
    sequence          INTEGER,
    trop_percu        BOOLEAN       NOT NULL DEFAULT false,
    observation       TEXT,
    statut            VARCHAR(8)    NOT NULL DEFAULT 'valide' CHECK (statut IN ('valide', 'annulé')),
    motif_annulation  TEXT,
    encaisse_par      VARCHAR(80),
    cree_le           TIMESTAMP     NOT NULL DEFAULT now(),
    annule_par        VARCHAR(80),
    annule_le         TIMESTAMP,
    pdf               BYTEA,
    sha256            VARCHAR(64),
    UNIQUE (annee, sequence),
    CHECK (statut <> 'annulé' OR motif_annulation IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS paiements_facture ON paiements (facture_id);
CREATE INDEX IF NOT EXISTS paiements_date ON paiements (date_paiement);

CREATE TABLE IF NOT EXISTS exonerations (
    id               SERIAL PRIMARY KEY,
    facture_id       INTEGER       REFERENCES factures (id) ON DELETE RESTRICT,
    num_echantillon  VARCHAR(50)   REFERENCES echantillons ("N° Echantillon") ON DELETE RESTRICT,
    type             VARCHAR(20)   NOT NULL CHECK (type IN ('contrôle officiel', 'convention', 'autre')),
    motif            TEXT          NOT NULL,
    montant          NUMERIC(12,2) NOT NULL DEFAULT 0,
    statut           VARCHAR(8)    NOT NULL DEFAULT 'valide' CHECK (statut IN ('valide', 'annulé')),
    accorde_par      VARCHAR(80),
    accorde_le       TIMESTAMP     NOT NULL DEFAULT now(),
    motif_annulation TEXT,
    annule_par       VARCHAR(80),
    annule_le        TIMESTAMP,
    CHECK ((facture_id IS NULL) <> (num_echantillon IS NULL)),
    CHECK (statut <> 'annulé' OR motif_annulation IS NOT NULL)
);
-- Une seule exonération en vigueur par bulletin et par échantillon
CREATE UNIQUE INDEX IF NOT EXISTS exonerations_facture_valide ON exonerations (facture_id) WHERE statut = 'valide';
CREATE UNIQUE INDEX IF NOT EXISTS exonerations_echantillon_valide ON exonerations (num_echantillon) WHERE statut = 'valide';

-- Journal d'audit inviolable (migration 015) ; la colonne pdf n'est jamais recopiée
SELECT audit_attacher('paiements');
SELECT audit_attacher('exonerations');
