-- ============================================================
-- LIMS LRARVY — Contrôles qualité internes (tâche 18, ISO 17025 § 7.7)
-- Migration ADDITIVE : crée deux tables, ne modifie rien d'existant.
--
-- Une « série » = un contrôle suivi dans le temps pour une méthode
-- (témoin positif / négatif, blanc, duplicata, matériau de référence).
--   - quantitatif : valeurs numériques -> carte de contrôle (moyenne, ±2σ, ±3σ).
--     Moyenne et écart-type de référence : fixés sur la série, sinon calculés
--     sur ses mesures. Alerte : valeur hors ±3σ, ou 7 points consécutifs du
--     même côté de la moyenne.
--   - qualitatif : résultat attendu / obtenu ; alerte si non conforme.
-- ============================================================

CREATE TABLE IF NOT EXISTS cq_series (
    id               SERIAL PRIMARY KEY,
    libelle          VARCHAR(150) NOT NULL,
    section          VARCHAR(4)   NOT NULL CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    methode          VARCHAR(150) NOT NULL,
    type_controle    VARCHAR(25)  NOT NULL
                     CHECK (type_controle IN ('Témoin positif', 'Témoin négatif', 'Blanc', 'Duplicata',
                                              'Matériau de référence')),
    nature           VARCHAR(12)  NOT NULL DEFAULT 'quantitatif' CHECK (nature IN ('quantitatif', 'qualitatif')),
    unite            VARCHAR(30),
    moyenne_ref      NUMERIC(14, 4),
    ecart_type_ref   NUMERIC(14, 4) CHECK (ecart_type_ref IS NULL OR ecart_type_ref > 0),
    resultat_attendu VARCHAR(50),
    actif            BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (section, methode, libelle)
);

CREATE TABLE IF NOT EXISTS cq_mesures (
    id           SERIAL PRIMARY KEY,
    serie_id     INTEGER NOT NULL REFERENCES cq_series(id) ON DELETE RESTRICT,
    date_mesure  DATE NOT NULL,
    valeur       NUMERIC(14, 4),
    resultat     VARCHAR(50),
    commentaire  TEXT,
    saisi_par    VARCHAR(100) NOT NULL,
    cree_le      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valeur IS NOT NULL OR resultat IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS cq_mesures_serie_idx ON cq_mesures (serie_id, date_mesure, id);

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('cq_series');
SELECT audit_attacher('cq_mesures');
