-- ============================================================
-- LIMS LRARVY — Grille tarifaire datée (tâche 34, bloc P)
-- Migration ADDITIVE : complète ref_tarifs (migration 018) sans rien modifier d'existant.
--
--  * ref_analyses (vide jusqu'ici) reçoit le catalogue de [Table Analyses] et
--    [Table Méthode SSA] du dump Access (nom, méthode, type, section).
--  * ref_tarifs reste « une analyse = un tarif par section » ; elle gagne le lien
--    vers ref_analyses, l'option « facturée par prélèvement » et le statut « à valider ».
--    Sa colonne prix garde le prix en vigueur (affichage, compatibilité).
--  * ref_tarifs_prix : historique des prix, une période [date_debut, date_fin] par
--    changement. Modifier un prix ferme la période en cours et en ouvre une nouvelle,
--    sans écraser l'ancienne. Le prix appliqué à une date = la période qui la couvre.
--  * parametres : réglages de l'application (taux de TVA, étape de paiement exigée…).
-- ============================================================

-- 1. Catalogue des analyses (Access), sans doublon
INSERT INTO ref_analyses (numero_ordre, nom_analyse, prix, reference_methode, type_analyse, section)
SELECT v.numero_ordre, v.nom, v.prix, v.methode, v.type_analyse, v.section
FROM (VALUES
    (1,  'ABVT', '0', 'AOAC', 'Chimie Alimentaire', 'SCHA'),
    (2,  'Acidité', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (48, 'Aflatoxine M1', '0', 'CCM', 'Chimie Alimentaire', 'SCHA'),
    (3,  'Aflatoxines', '0', 'CCM', 'Chimie Alimentaire', 'SCHA'),
    (4,  'Amidon', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (32, 'Anaéro. Sulfitoréducteurs à 46°C.', '60', 'ISO', 'Microbiologie Alimentaire', 'SMA'),
    (47, 'ASP (ppm)', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (5,  'Calcium', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (6,  'Cellulose brute', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (8,  'Chlorures', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (9,  'Coliformes Fécaux', '40', 'ISO', 'Microbiologie Alimentaire', 'SMA'),
    (10, 'Coliformes Totaux', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (11, 'Contrôle de stabilité', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (12, 'Dioxyde de Soufre', '0', 'AOAC', 'Chimie Alimentaire', 'SCHA'),
    (13, 'DSP', '0', 'UE', 'Chimie Alimentaire', 'SCHA'),
    (36, 'EAT', '0', NULL, NULL, 'SSA'),
    (50, 'ELISA Anticorps Blue Tongue', '0', NULL, 'Sérologie', 'SSA'),
    (44, 'Entérobactéries', '0', 'ISO', 'Microbiologie Alimentaire', 'SMA'),
    (30, 'Escherichia coli', '80', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (37, 'FC Brucellose', '0', NULL, NULL, 'SSA'),
    (38, 'FC Chlamydiose', '0', NULL, NULL, 'SSA'),
    (7,  'FMAT', '40', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (49, 'HAP', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (14, 'Histamine (mg/100g)', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (15, 'Humidité', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (16, 'Lactose', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (17, 'Levures et moisissures', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (18, 'Listeria monocytogenes', '70', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (46, 'Matière séche (%)', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (19, 'Matières grasses', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (20, 'Matières minérales', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (21, 'Matières protéiques', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (45, 'Mercure (ppm)', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (22, 'Nitrates', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (23, 'Nitrites', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (24, 'Ochratoxine', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (25, 'Pesticides', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (26, 'pH', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (27, 'Phosphate total', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (28, 'PSP', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (39, 'Recherche de Salmonella aviaires', '0', NULL, NULL, 'SSA'),
    (41, 'Recherche de Salmonella.', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (35, 'Recherche de V. cholerea', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (29, 'Recherche des antibiotiques', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (43, 'Spores-Anaéro Sulfitoréducteurs', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (31, 'St. aureus coagulase positive', '60', NULL, 'Microbiologie Alimentaire', 'SMA'),
    (33, 'TMA', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (34, 'Toxines botulinique', '0', NULL, 'Chimie Alimentaire', 'SCHA'),
    (42, 'Vibrio cholerea', '0', NULL, 'Microbiologie Alimentaire', 'SMA'),
    -- [Table Méthode SSA] : une méthode, prix 0
    (NULL, 'Recherche de Salmonelles', '0', 'XXX-1-1', 'Bactériologie', 'SSA')
) AS v (numero_ordre, nom, prix, methode, type_analyse, section)
WHERE NOT EXISTS (
    SELECT 1 FROM ref_analyses a
    WHERE lower(btrim(a.nom_analyse)) = lower(btrim(v.nom)) AND a.section = v.section);

-- 2. Compléments de ref_tarifs
ALTER TABLE ref_tarifs
    ADD COLUMN IF NOT EXISTS analyse_id      INTEGER REFERENCES ref_analyses (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS par_prelevement BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS a_valider       BOOLEAN NOT NULL DEFAULT false;

UPDATE ref_tarifs t SET analyse_id = a.id
FROM ref_analyses a
WHERE t.analyse_id IS NULL
  AND lower(btrim(a.nom_analyse)) = lower(btrim(t.nom_analyse)) AND a.section = t.section;

-- Les 6 prix repris d'Access (migration 018) sont à confirmer par le laboratoire
-- (tant que leur prix est encore celui d'Access)
UPDATE ref_tarifs t SET a_valider = true
FROM ref_analyses a
WHERE a.id = t.analyse_id AND a.prix = to_char(t.prix, 'FM999999990')
  AND a.numero_ordre IS NOT NULL;

-- 3. Historique des prix
CREATE TABLE IF NOT EXISTS ref_tarifs_prix (
    id          SERIAL PRIMARY KEY,
    tarif_id    INTEGER       NOT NULL REFERENCES ref_tarifs (id) ON DELETE CASCADE,
    prix        NUMERIC(12,2) NOT NULL CHECK (prix >= 0),
    date_debut  DATE          NOT NULL,
    date_fin    DATE,
    cree_par    VARCHAR(80),
    cree_le     TIMESTAMP     NOT NULL DEFAULT now(),
    CHECK (date_fin IS NULL OR date_fin >= date_debut),
    UNIQUE (tarif_id, date_debut)
);
CREATE INDEX IF NOT EXISTS ref_tarifs_prix_tarif ON ref_tarifs_prix (tarif_id, date_debut);

-- Prix actuels : une première période ouverte depuis le 01/01/2000 (couvre l'historique)
INSERT INTO ref_tarifs_prix (tarif_id, prix, date_debut, cree_par)
SELECT t.id, t.prix, DATE '2000-01-01', 'migration 027'
FROM ref_tarifs t
WHERE NOT EXISTS (SELECT 1 FROM ref_tarifs_prix p WHERE p.tarif_id = t.id);

-- 4. Réglages de l'application
CREATE TABLE IF NOT EXISTS parametres (
    cle         VARCHAR(60) PRIMARY KEY,
    valeur      TEXT,
    modifie_par VARCHAR(80),
    modifie_le  TIMESTAMP NOT NULL DEFAULT now()
);
INSERT INTO parametres (cle, valeur, modifie_par) VALUES
    ('facturation.taux_tva', '0', 'migration 027'),
    ('facturation.etape_paiement', 'aucune', 'migration 027'),
    ('facturation.seuil_impayes_jours', '30', 'migration 027')
ON CONFLICT (cle) DO NOTHING;

-- Journal d'audit inviolable (migration 015)
SELECT audit_attacher('ref_tarifs_prix');
SELECT audit_attacher('parametres');
