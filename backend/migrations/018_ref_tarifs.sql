-- ============================================================
-- LIMS LRARVY — Grille de tarifs des analyses (tâche 16)
-- Migration ADDITIVE : crée une table de référence, ne modifie rien d'existant.
--
-- Reprise des prix du dump Access : la table [PRIX] d'Access est un récapitulatif
-- par échantillon (et elle est vide) ; les prix unitaires se trouvent dans
-- [Table Analyses].[Prix de l'Analyse]. Seules 6 analyses (SMA) y ont un prix
-- non nul : elles sont reprises ci-dessous. Les autres sont à saisir dans
-- Référentiels > Tarifs.
-- Le montant d'un échantillon = somme des prix des analyses effectuées
-- (une ligne de résultats = une analyse facturée).
-- ============================================================

CREATE TABLE IF NOT EXISTS ref_tarifs (
    id        SERIAL PRIMARY KEY,
    nom_analyse VARCHAR(150) NOT NULL,
    section   VARCHAR(4)    NOT NULL CHECK (section IN ('SMA', 'SCHA', 'SSA')),
    prix      NUMERIC(10, 2) NOT NULL CHECK (prix >= 0),
    actif     BOOLEAN       NOT NULL DEFAULT true
);

-- Une analyse n'a qu'un tarif par section (comparaison sans casse ni espaces de bord)
CREATE UNIQUE INDEX IF NOT EXISTS ref_tarifs_analyse_section
    ON ref_tarifs (lower(btrim(nom_analyse)), section);

INSERT INTO ref_tarifs (nom_analyse, section, prix) VALUES
    ('Anaéro. Sulfitoréducteurs à 46°C.', 'SMA', 60),
    ('Coliformes Fécaux',                 'SMA', 40),
    ('Escherichia coli',                  'SMA', 80),
    ('FMAT',                              'SMA', 40),
    ('Listeria monocytogenes',            'SMA', 70),
    ('St. aureus coagulase positive',     'SMA', 60)
ON CONFLICT DO NOTHING;

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('ref_tarifs');
