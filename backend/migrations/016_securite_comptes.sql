-- ============================================================
-- LIMS LRARVY — Sécurité des comptes (tâche 12)
-- Migration ADDITIVE : deux colonnes ajoutées à `users`, rien n'est modifié.
--
-- Verrouillage du compte pendant 15 min après 5 échecs de connexion
-- consécutifs : compteur d'échecs + date de fin de verrouillage.
-- (Les écritures sur `users` sont déjà tracées par audit_donnees.)
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS echecs_connexion INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verrouille_jusqu TIMESTAMPTZ;
