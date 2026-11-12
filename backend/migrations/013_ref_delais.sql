-- ============================================================
-- LIMS LRARVY — Délais de traitement par section (tableau de bord)
-- Migration ADDITIVE : crée une table de référence, ne modifie rien.
-- Un échantillon non « Rapport émis » reçu depuis plus de `jours`
-- jours est signalé en retard pour sa section.
-- ============================================================

CREATE TABLE IF NOT EXISTS ref_delais (
    section  VARCHAR(4) PRIMARY KEY CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    jours    INTEGER NOT NULL DEFAULT 15 CHECK (jours > 0)
);

INSERT INTO ref_delais (section, jours) VALUES
    ('SMA', 15), ('SCHA', 15), ('SSA', 15)
ON CONFLICT (section) DO NOTHING;
