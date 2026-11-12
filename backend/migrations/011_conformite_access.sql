-- ============================================================
-- LIMS LRARVY — Conformité à la base Access (SMA / SCHA / SSA)
-- Migration ADDITIVE : ajoute uniquement des colonnes manquantes.
-- Aucune colonne existante n'est modifiée ou supprimée.
-- Sans effet si les colonnes existent déjà (IF NOT EXISTS).
-- ============================================================

-- ── SMA : champ "Conclusion" présent dans Access, absent en base ──
ALTER TABLE traitement_sma
    ADD COLUMN IF NOT EXISTS conclusion TEXT;

-- ── RÉSULTATS : colonnes spécifiques par section ──
-- La table resultats_analyses est commune ; on ajoute les colonnes
-- que chaque section utilise dans Access.

-- SCHA : jusqu'à 9 prélèvements + moyenne + conclusion
ALTER TABLE resultats_analyses
    ADD COLUMN IF NOT EXISTS rp6         VARCHAR(60),
    ADD COLUMN IF NOT EXISTS rp7         VARCHAR(60),
    ADD COLUMN IF NOT EXISTS rp8         VARCHAR(60),
    ADD COLUMN IF NOT EXISTS rp9         VARCHAR(60),
    ADD COLUMN IF NOT EXISTS moyenne     VARCHAR(60),
    ADD COLUMN IF NOT EXISTS conclusion  TEXT;

-- SSA : résultat en clair + interprétation + comptages (pas de RP)
ALTER TABLE resultats_analyses
    ADD COLUMN IF NOT EXISTS resultat_analyse         TEXT,
    ADD COLUMN IF NOT EXISTS criteres_interpretation  TEXT,
    ADD COLUMN IF NOT EXISTS nbre_positifs            INTEGER,
    ADD COLUMN IF NOT EXISTS nbre_negatif             INTEGER,
    ADD COLUMN IF NOT EXISTS nbre_douteux             INTEGER,
    ADD COLUMN IF NOT EXISTS responsable_analyse      VARCHAR(120),
    ADD COLUMN IF NOT EXISTS nbre_prelevements        INTEGER;
