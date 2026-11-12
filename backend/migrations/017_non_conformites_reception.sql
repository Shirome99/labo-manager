-- ============================================================
-- LIMS LRARVY — Non-conformités à la réception structurées (tâche 14)
-- Migration ADDITIVE : colonnes ajoutées à `echantillons`, rien n'est modifié.
-- Le champ texte `non_conformite` existant est conservé (observation).
--
-- Décision de réception : 'Accepté' / 'Accepté sous réserve' / 'Refusé'.
-- Un échantillon 'Refusé' ne peut pas recevoir de fiche de traitement (contrôle applicatif).
-- NULL = non renseigné (échantillons antérieurs) : traité comme accepté.
-- ============================================================

ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS temperature_reception NUMERIC(5, 1);
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_temperature   BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_contenant     BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_quantite      BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_etiquetage    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_delai         BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS nc_autre         BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS decision_reception VARCHAR(25);
ALTER TABLE echantillons ADD COLUMN IF NOT EXISTS motif_decision   TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'echantillons_decision_reception_check') THEN
        ALTER TABLE echantillons ADD CONSTRAINT echantillons_decision_reception_check
            CHECK (decision_reception IS NULL
                   OR decision_reception IN ('Accepté', 'Accepté sous réserve', 'Refusé'));
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS echantillons_decision_reception_idx ON echantillons (decision_reception);
