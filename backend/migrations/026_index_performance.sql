-- ============================================================
-- LIMS LRARVY — Index de performance (tâche 30)
-- Migration ADDITIVE : extension et index seulement, aucune donnée modifiée.
--
-- Choisis d'après les plans d'exécution (EXPLAIN ANALYZE) sur 22 000 échantillons et
-- 80 000 lignes d'audit (scripts/remplir_volume.py) :
--   * liste paginée triée par n° d'ordre : tri complet de la table (sur disque à la page 400)
--     -> index sur "N° d'ordre" ;
--   * recherche partielle (ILIKE '%…%') sur le n°, la nature, le fabricant, l'organisme, le
--     client, et dans le journal d'audit sur le n° et l'utilisateur : parcours complet
--     -> index trigrammes (extension pg_trgm, fournie avec PostgreSQL) ;
--   * journal d'audit filtré par table ou par opération, trié par id décroissant : parcours
--     de toute la clé primaire -> index composés (colonne, id).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Liste des échantillons : tri par défaut (plus récents d'abord)
CREATE INDEX IF NOT EXISTS echantillons_ordre_idx ON echantillons ("N° d'ordre");

-- Recherche partielle (barre de recherche, recherche avancée, sélecteur d'échantillon)
CREATE INDEX IF NOT EXISTS echantillons_num_trgm ON echantillons USING gin ("N° Echantillon" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS echantillons_nature_trgm ON echantillons USING gin ("Nature de l'échantillon" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS echantillons_fabricant_trgm ON echantillons USING gin ("Fabricant ou Propriétaire" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS echantillons_organisme_trgm ON echantillons USING gin ("Organisme préleveur" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS echantillons_client_trgm ON echantillons USING gin ("Nom du Client" gin_trgm_ops);

-- Journal d'audit (écran admin) : filtres + tri par id décroissant
CREATE INDEX IF NOT EXISTS audit_donnees_table_id_idx ON audit_donnees (table_nom, id);
CREATE INDEX IF NOT EXISTS audit_donnees_operation_id_idx ON audit_donnees (operation, id);
CREATE INDEX IF NOT EXISTS audit_donnees_num_trgm ON audit_donnees USING gin (num_echantillon gin_trgm_ops);
CREATE INDEX IF NOT EXISTS audit_donnees_utilisateur_trgm ON audit_donnees USING gin (utilisateur gin_trgm_ops);

ANALYZE echantillons;
ANALYZE audit_donnees;
