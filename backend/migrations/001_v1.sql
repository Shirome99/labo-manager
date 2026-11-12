-- ============================================================
-- LIMS LRARVY — Migration V1
-- S'applique PAR-DESSUS le schéma existant de Labo Manager
-- (tables echantillons, users, traitement_sma/scha/ssa déjà créées)
-- ============================================================

-- 1) Statuts d'échantillon + non-conformités à la réception
ALTER TABLE echantillons
    ADD COLUMN IF NOT EXISTS statut          VARCHAR(30) NOT NULL DEFAULT 'Recu',
    ADD COLUMN IF NOT EXISTS non_conformite  TEXT;

-- 2) Validation à deux niveaux + points d'ancrage V2 sur les 3 fiches
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['traitement_sma','traitement_scha','traitement_ssa'] LOOP
    EXECUTE format('ALTER TABLE %I
        ADD COLUMN IF NOT EXISTS saisi_par          VARCHAR(80),
        ADD COLUMN IF NOT EXISTS valide_par         VARCHAR(80),
        ADD COLUMN IF NOT EXISTS date_validation    TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS equipement_utilise VARCHAR(120),
        ADD COLUMN IF NOT EXISTS lot_reactif        VARCHAR(120)', t);
  END LOOP;
END $$;

-- 3) Journal d'audit (traçabilité ISO 17025)
CREATE TABLE IF NOT EXISTS audit_log (
    id           SERIAL PRIMARY KEY,
    horodatage   TIMESTAMPTZ NOT NULL DEFAULT now(),
    utilisateur  VARCHAR(80),
    action       VARCHAR(40)  NOT NULL,
    table_cible  VARCHAR(60)  NOT NULL,
    cle          VARCHAR(80),
    details      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_cle  ON audit_log (cle);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log (horodatage DESC);

-- 4) Trigger de sécurité : l'audit ne peut être ni modifié ni supprimé
CREATE OR REPLACE FUNCTION audit_immuable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Le journal d''audit est immuable.';
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_immuable ON audit_log;
CREATE TRIGGER trg_audit_immuable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_immuable();

-- 5) Index utiles pour le filtrage par section
CREATE INDEX IF NOT EXISTS idx_ech_sma  ON echantillons ("SMA");
CREATE INDEX IF NOT EXISTS idx_ech_scha ON echantillons ("SCHA");
CREATE INDEX IF NOT EXISTS idx_ech_ssa  ON echantillons ("SSA");
