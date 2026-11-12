-- ============================================================
-- LIMS LRARVY — Index pour le moteur de requêtes (tâche 21)
-- Migration ADDITIVE : crée des index, ne modifie aucune donnée.
--
-- Les requêtes du reporting filtrent et regroupent sur la date de réception,
-- le statut, le fabricant et l'organisme préleveur (la section, la décision
-- et le n° d'échantillon sont déjà indexés).
-- ============================================================

CREATE INDEX IF NOT EXISTS echantillons_date_reception_idx ON echantillons ("Date reception");
CREATE INDEX IF NOT EXISTS echantillons_statut_idx         ON echantillons (statut);
CREATE INDEX IF NOT EXISTS echantillons_fabricant_idx      ON echantillons ("Fabricant ou Propriétaire");
CREATE INDEX IF NOT EXISTS echantillons_organisme_idx      ON echantillons ("Organisme préleveur");
CREATE INDEX IF NOT EXISTS resultats_analyses_date_idx     ON resultats_analyses (date_analyse);
