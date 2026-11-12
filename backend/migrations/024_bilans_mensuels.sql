-- ============================================================
-- LIMS LRARVY — Bilan mensuel (tâche 24)
-- Migration ADDITIVE : crée deux tables, ajoute des requêtes partagées et le modèle par défaut.
--
-- bilan_modele     : composition du bilan, paramétrable par l'admin (ordre, titre, bloc).
--                    Un bloc est soit la synthèse (calculée), soit une requête enregistrée,
--                    exécutée sur le mois et la section du bilan.
-- bilans_mensuels  : archive de chaque bilan généré (jamais écrasé : une régénération crée
--                    la version suivante). Le fichier (PDF ou Excel) est dans la colonne `pdf`,
--                    nom que le trigger d'audit masque (comme rapports_emis.pdf) : le journal
--                    garde les métadonnées et l'empreinte, pas le contenu.
-- ============================================================

CREATE TABLE IF NOT EXISTS bilan_modele (
    id          SERIAL PRIMARY KEY,
    ordre       INTEGER NOT NULL,
    type_bloc   VARCHAR(10) NOT NULL CHECK (type_bloc IN ('synthese', 'requete')),
    titre       VARCHAR(150) NOT NULL,
    requete_id  INTEGER REFERENCES requetes_enregistrees(id) ON DELETE RESTRICT,
    actif       BOOLEAN NOT NULL DEFAULT true,
    CHECK ((type_bloc = 'requete') = (requete_id IS NOT NULL))
);
SELECT audit_attacher('bilan_modele');

CREATE TABLE IF NOT EXISTS bilans_mensuels (
    id          SERIAL PRIMARY KEY,
    mois        DATE NOT NULL CHECK (extract(day FROM mois) = 1),
    section     VARCHAR(4) CHECK (section IN ('SMA', 'SCHA', 'SSA')),   -- NULL : toutes les sections
    format      VARCHAR(4) NOT NULL CHECK (format IN ('pdf', 'xlsx')),
    version     INTEGER NOT NULL,
    pdf         BYTEA NOT NULL,                                          -- contenu du fichier (PDF ou Excel)
    taille      INTEGER NOT NULL,
    sha256      CHAR(64) NOT NULL,
    auteur      VARCHAR(100) NOT NULL,
    source      VARCHAR(12) NOT NULL DEFAULT 'application' CHECK (source IN ('application', 'script')),
    genere_le   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS bilans_mensuels_version
    ON bilans_mensuels (mois, coalesce(section, 'TOUT'), format, version);
SELECT audit_attacher('bilans_mensuels');

-- Requêtes partagées complémentaires pour le bilan
INSERT INTO requetes_enregistrees (nom, description, definition, auteur, visibilite) VALUES
('Échantillons par section', 'Échantillons reçus le mois précédent : nombre, analyses et prélèvements, par section.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["section"], "mesures": ["nb_echantillons", "nb_analyses", "nb_prelevements"]}',
 'système', 'partagée'),
('Échantillons par type', 'Échantillons reçus le mois précédent, par type d''échantillon.',
 '{"jeu": "echantillons", "filtres": {"periode": "mois_precedent"}, "regroupements": ["type"], "mesures": ["nb_echantillons"], "tri": {"cle": "nb_echantillons", "ordre": "desc"}}',
 'système', 'partagée')
ON CONFLICT DO NOTHING;

-- Modèle par défaut (créé une seule fois)
INSERT INTO bilan_modele (ordre, type_bloc, titre, requete_id)
SELECT m.ordre, m.type_bloc, m.titre, r.id
FROM (VALUES
    (1,  'synthese', 'Synthèse du mois', NULL),
    (2,  'requete',  'Répartition par section', 'Échantillons par section'),
    (3,  'requete',  'Répartition par type d''échantillon', 'Échantillons par type'),
    (4,  'requete',  'Répartition par fabricant', 'Échantillons par fabricant'),
    (5,  'requete',  'Répartition par organisme préleveur', 'Échantillons par organisme préleveur'),
    (6,  'requete',  'Non-conformités par catégorie', 'Taux de non-conformité par catégorie'),
    (7,  'requete',  'Non-conformités par analyse', 'Non-conformités par analyse'),
    (8,  'requete',  'Délais par section (rapports émis dans le mois)', 'Délais moyens par section'),
    (9,  'requete',  'Retards par section (à la date du bilan)', 'Retards par section'),
    (10, 'requete',  'Facturation du mois', 'Facturation par section')
) AS m(ordre, type_bloc, titre, nom_requete)
LEFT JOIN requetes_enregistrees r ON r.auteur = 'système' AND r.nom = m.nom_requete
WHERE NOT EXISTS (SELECT 1 FROM bilan_modele)
  AND (m.type_bloc = 'synthese' OR r.id IS NOT NULL);
