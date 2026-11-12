-- ============================================================
-- LIMS LRARVY — Équipements et étalonnage (tâche 17, ISO 17025 § 6.4)
-- Migration ADDITIVE : crée deux tables, ne modifie rien d'existant.
--
-- Inventaire des équipements (code d'inventaire unique, désignation, n° de série,
-- section — NULL = commun —, emplacement), dernière date d'étalonnage et de
-- vérification avec leur périodicité (mois ; NULL = non soumis), historique des
-- étalonnages, vérifications, maintenances, pannes et réparations.
-- Les fiches de traitement désignent l'équipement par son code
-- (colonne `equipement_utilise`, déjà présente dans traitement_*).
-- ============================================================

CREATE TABLE IF NOT EXISTS equipements (
    id                          SERIAL PRIMARY KEY,
    code                        VARCHAR(50)  NOT NULL UNIQUE,
    designation                 VARCHAR(200) NOT NULL,
    numero_serie                VARCHAR(100),
    section                     VARCHAR(4) CHECK (section IS NULL OR section IN ('SMA', 'SCHA', 'SSA')),
    emplacement                 VARCHAR(150),
    date_dernier_etalonnage     DATE,
    periodicite_etalonnage_mois INTEGER CHECK (periodicite_etalonnage_mois IS NULL OR periodicite_etalonnage_mois > 0),
    date_derniere_verification  DATE,
    periodicite_verification_mois INTEGER CHECK (periodicite_verification_mois IS NULL OR periodicite_verification_mois > 0),
    actif                       BOOLEAN NOT NULL DEFAULT true,
    observations                TEXT
);

CREATE TABLE IF NOT EXISTS equipement_evenements (
    id              SERIAL PRIMARY KEY,
    equipement_id   INTEGER NOT NULL REFERENCES equipements(id) ON DELETE RESTRICT,
    type_evenement  VARCHAR(20) NOT NULL
                    CHECK (type_evenement IN ('Étalonnage', 'Vérification', 'Maintenance', 'Panne', 'Réparation')),
    date_evenement  DATE NOT NULL,
    resultat        VARCHAR(15) CHECK (resultat IS NULL OR resultat IN ('Conforme', 'Non conforme')),
    description     TEXT,
    saisi_par       VARCHAR(100) NOT NULL,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS equipement_evenements_equipement_idx
    ON equipement_evenements (equipement_id, date_evenement DESC);

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('equipements');
SELECT audit_attacher('equipement_evenements');
