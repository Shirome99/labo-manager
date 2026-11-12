-- ============================================================
-- LIMS LRARVY — Rapports d'essai officiels et figés (tâche 9)
-- Migration ADDITIVE : crée une table, ne modifie rien d'existant.
--
-- Chaque émission d'un rapport crée une ligne : numéro officiel
-- NNNN/CODE/AAAA (séquence par section, remise à zéro chaque année,
-- jamais réutilisée), PDF figé en bytea (inclus dans pg_dump) et
-- son empreinte SHA-256. Un erratum crée la version suivante, qui
-- référence la version remplacée ; celle-ci passe à « annulé ».
-- ============================================================

CREATE TABLE IF NOT EXISTS rapports_emis (
    id               SERIAL PRIMARY KEY,
    numero           VARCHAR(30)  NOT NULL UNIQUE,
    num_echantillon  VARCHAR(50)  NOT NULL,
    section          VARCHAR(4)   NOT NULL CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    version          INTEGER      NOT NULL DEFAULT 1 CHECK (version >= 1),
    annee            INTEGER      NOT NULL,
    sequence         INTEGER      NOT NULL CHECK (sequence >= 1),
    date_emission    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    emis_par         VARCHAR(100) NOT NULL,
    sha256           CHAR(64)     NOT NULL,
    pdf              BYTEA        NOT NULL,
    statut           VARCHAR(10)  NOT NULL DEFAULT 'valide' CHECK (statut IN ('valide', 'annulé')),
    remplace_id      INTEGER      REFERENCES rapports_emis(id) ON DELETE RESTRICT,
    motif            TEXT,
    -- Erratum demandé sur cette version (dossier rouvert, nouvelle version à venir)
    erratum_motif    TEXT,
    erratum_par      VARCHAR(100),
    erratum_le       TIMESTAMPTZ,
    UNIQUE (section, annee, sequence),
    UNIQUE (num_echantillon, section, version)
);

CREATE INDEX IF NOT EXISTS rapports_emis_echantillon_idx
    ON rapports_emis (num_echantillon, section);

-- Au plus un rapport valide par échantillon et par section
CREATE UNIQUE INDEX IF NOT EXISTS rapports_emis_un_valide
    ON rapports_emis (num_echantillon, section) WHERE statut = 'valide';
