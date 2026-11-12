-- ============================================================
-- LIMS LRARVY — Habilitations du personnel (tâche 19, ISO 17025 § 6.2)
-- Migration ADDITIVE : crée une table, ne modifie rien d'existant.
--
-- Matrice « utilisateur × analyse » : date de qualification et date d'échéance
-- (NULL = sans échéance). Un résultat ne peut être enregistré pour une analyse
-- que par un utilisateur habilité et à jour (contrôle applicatif, 403).
-- La suppression d'un compte supprime ses habilitations (tracées par audit_donnees).
-- ============================================================

CREATE TABLE IF NOT EXISTS habilitations (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nom_analyse         VARCHAR(150) NOT NULL,
    section             VARCHAR(4)   NOT NULL CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    date_qualification  DATE NOT NULL,
    date_echeance       DATE,
    habilite_par        VARCHAR(100) NOT NULL,
    observations        TEXT,
    CHECK (date_echeance IS NULL OR date_echeance >= date_qualification)
);

CREATE UNIQUE INDEX IF NOT EXISTS habilitations_unique
    ON habilitations (user_id, lower(btrim(nom_analyse)), section);

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('habilitations');
