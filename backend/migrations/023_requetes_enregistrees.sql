-- ============================================================
-- LIMS LRARVY — Requêtes enregistrées (tâche 23)
-- Migration ADDITIVE : crée une table et y insère des requêtes partagées.
--
-- La définition (jsonb) reprend exactement le corps de POST /api/requetes/executer :
-- {jeu, filtres, regroupements, mesures, tri}. Elle est revalidée contre le catalogue
-- à chaque enregistrement et à chaque exécution (aucun SQL n'est stocké).
-- Une période relative (filtres.periode : mois_precedent, mois_en_cours, annee_en_cours,
-- annee_precedente) est recalculée à chaque exécution.
-- ============================================================

CREATE TABLE IF NOT EXISTS requetes_enregistrees (
    id           SERIAL PRIMARY KEY,
    nom          VARCHAR(150) NOT NULL,
    description  TEXT,
    definition   JSONB NOT NULL,
    auteur       VARCHAR(100) NOT NULL,
    visibilite   VARCHAR(12) NOT NULL DEFAULT 'personnelle' CHECK (visibilite IN ('personnelle', 'partagée')),
    cree_le      TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS requetes_enregistrees_nom_unique
    ON requetes_enregistrees (auteur, lower(btrim(nom)));

SELECT audit_attacher('requetes_enregistrees');

-- Requêtes partagées utiles (auteur « système ») ; relancer la migration ne crée pas de doublon
INSERT INTO requetes_enregistrees (nom, description, definition, auteur, visibilite) VALUES
('Échantillons par section et par mois', 'Échantillons reçus dans l''année en cours, par section et par mois de réception.',
 '{"jeu": "echantillons", "filtres": {"periode": "annee_en_cours"}, "regroupements": ["section", "mois"], "mesures": ["nb_echantillons"]}',
 'système', 'partagée'),
('Échantillons par type et sous-type', 'Échantillons reçus le mois précédent, par type et sous-type.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["type", "soustype"], "mesures": ["nb_echantillons"]}',
 'système', 'partagée'),
('Échantillons par fabricant', 'Échantillons reçus le mois précédent, par fabricant ou propriétaire (du plus fréquent au moins fréquent).',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["fabricant"], "mesures": ["nb_echantillons"], "tri": {"cle": "nb_echantillons", "ordre": "desc"}}',
 'système', 'partagée'),
('Échantillons par organisme préleveur', 'Échantillons reçus le mois précédent, par organisme préleveur.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["organisme"], "mesures": ["nb_echantillons"], "tri": {"cle": "nb_echantillons", "ordre": "desc"}}',
 'système', 'partagée'),
('Taux de non-conformité par catégorie', 'Échantillons reçus le mois précédent : conformes, non conformes et taux, par catégorie.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["categorie"], "mesures": ["nb_echantillons", "nb_conformes", "nb_non_conformes", "taux_non_conformite"]}',
 'système', 'partagée'),
('Non-conformités par analyse', 'Analyses du mois précédent (date de réception) : non conformes et taux, par analyse.',
 '{"jeu": "analyses", "filtres": {"periode": "mois_precedent"}, "regroupements": ["analyse"], "mesures": ["nb_analyses", "nb_non_conformes", "taux_non_conformite"]}',
 'système', 'partagée'),
('Délais moyens par section', 'Rapports émis le mois précédent : délai moyen et médian entre la réception et le rapport, par section.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent", "date_ref": "rapport"}, "regroupements": ["section"], "mesures": ["nb_echantillons", "delai_moyen", "delai_median"]}',
 'système', 'partagée'),
('Retards par section', 'Échantillons actuellement en retard (délai de traitement de la section dépassé), par section et par statut.',
 '{"jeu": "echantillons", "filtres": {"retard": ["Oui"]}, "regroupements": ["section", "statut"], "mesures": ["nb_echantillons"]}',
 'système', 'partagée'),
('Facturation par section', 'Échantillons du mois précédent ayant des analyses saisies : montant facturé, payé et reste, par section.',
 '{"jeu": "facturation", "filtres": {"periode": "mois_precedent"}, "regroupements": ["section"], "mesures": ["nb_echantillons", "nb_analyses", "montant", "montant_paye", "reste_a_payer"]}',
 'système', 'partagée')
ON CONFLICT DO NOTHING;
