-- ============================================================
-- LIMS LRARVY — Suivi du paiement des analyses
-- Migration ADDITIVE : conserve les champs historiques Access
-- et ajoute uniquement les informations manquantes.
-- ============================================================

ALTER TABLE echantillons
    ADD COLUMN IF NOT EXISTS "Mode de paiement" VARCHAR(40),
    ADD COLUMN IF NOT EXISTS "Montant payé" NUMERIC(12,2);

-- Le champ historique "Payement" est conservé et devient le statut :
-- Non concerné / À payer / Partiellement payé / Payé / Exonéré.
-- Le champ historique "TOTAL" reste le montant total à régler pour l'instant.
