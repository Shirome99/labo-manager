-- ============================================================
-- LIMS LRARVY — Journal d'audit inviolable (tâche 11)
-- Migration ADDITIVE : crée une table, des fonctions et des triggers.
-- Aucune donnée existante n'est modifiée.
--
-- Toute écriture (INSERT / UPDATE / DELETE) sur les tables suivies est
-- enregistrée par la base elle-même dans `audit_donnees`, y compris
-- hors application (psql, pgAdmin...) : table, opération, clé, n° d'échantillon,
-- données AVANT / APRÈS en jsonb, utilisateur, horodatage.
-- L'utilisateur applicatif est transmis par set_config('lims.utilisateur', …, true)
-- au début de chaque transaction ; à défaut, c'est l'utilisateur PostgreSQL.
-- `audit_donnees` refuse tout UPDATE, DELETE et TRUNCATE.
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_donnees (
    id               BIGSERIAL PRIMARY KEY,
    table_nom        VARCHAR(63)  NOT NULL,
    operation        VARCHAR(6)   NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    cle              TEXT,
    num_echantillon  VARCHAR(50),
    avant            JSONB,
    apres            JSONB,
    utilisateur      VARCHAR(100) NOT NULL,
    source           VARCHAR(12)  NOT NULL CHECK (source IN ('application', 'base')),
    horodatage       TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS audit_donnees_table_idx       ON audit_donnees (table_nom, horodatage DESC);
CREATE INDEX IF NOT EXISTS audit_donnees_echantillon_idx ON audit_donnees (num_echantillon);
CREATE INDEX IF NOT EXISTS audit_donnees_utilisateur_idx ON audit_donnees (utilisateur);
CREATE INDEX IF NOT EXISTS audit_donnees_date_idx        ON audit_donnees (horodatage DESC);

-- ------------------------------------------------------------
-- Trigger générique d'audit. TG_ARGV[0] = colonne de clé primaire.
-- Colonnes jamais copiées : hash du mot de passe, PDF binaire.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION audit_donnees_trigger() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_avant  jsonb;
    v_apres  jsonb;
    v_ligne  jsonb;
    v_user   text := nullif(current_setting('lims.utilisateur', true), '');
    v_masque text[] := ARRAY['mot_de_passe', 'password', 'hashed_password', 'pdf'];
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        v_avant := to_jsonb(OLD) - v_masque;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        v_apres := to_jsonb(NEW) - v_masque;
    END IF;
    -- UPDATE sans changement réel : rien à tracer
    IF TG_OP = 'UPDATE' AND v_avant IS NOT DISTINCT FROM v_apres THEN
        RETURN NULL;
    END IF;
    v_ligne := coalesce(v_apres, v_avant);

    INSERT INTO audit_donnees (table_nom, operation, cle, num_echantillon, avant, apres, utilisateur, source)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        v_ligne ->> TG_ARGV[0],
        coalesce(v_ligne ->> 'num_echantillon', v_ligne ->> 'N° Echantillon'),
        v_avant,
        v_apres,
        coalesce(v_user, 'pg:' || session_user),
        CASE WHEN v_user IS NULL THEN 'base' ELSE 'application' END
    );
    RETURN NULL;   -- trigger AFTER : la valeur de retour est ignorée
END;
$$;

-- ------------------------------------------------------------
-- Protection : le journal ne se modifie ni ne s'efface.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION audit_donnees_protection() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_donnees est en ajout seul : % interdit', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE OR REPLACE TRIGGER audit_donnees_pas_de_modif
    BEFORE UPDATE OR DELETE ON audit_donnees
    FOR EACH ROW EXECUTE FUNCTION audit_donnees_protection();

CREATE OR REPLACE TRIGGER audit_donnees_pas_de_truncate
    BEFORE TRUNCATE ON audit_donnees
    FOR EACH STATEMENT EXECUTE FUNCTION audit_donnees_protection();

-- ------------------------------------------------------------
-- Attache le trigger d'audit à une table (clé primaire détectée).
-- À appeler pour chaque nouvelle table métier : SELECT audit_attacher('ma_table');
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION audit_attacher(p_table regclass) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_pk text;
BEGIN
    SELECT a.attname INTO v_pk
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
    WHERE i.indrelid = p_table AND i.indisprimary;
    IF v_pk IS NULL THEN
        RAISE EXCEPTION 'Table % sans clé primaire : audit impossible', p_table;
    END IF;
    EXECUTE format(
        'CREATE OR REPLACE TRIGGER audit_donnees_trg AFTER INSERT OR UPDATE OR DELETE ON %s '
        'FOR EACH ROW EXECUTE FUNCTION audit_donnees_trigger(%L)', p_table, v_pk);
END;
$$;

-- Tables suivies : échantillons, traitements, résultats, rapports émis, comptes, référentiels
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['echantillons', 'traitement_sma', 'traitement_scha', 'traitement_ssa',
                             'resultats_analyses', 'rapports_emis', 'users'] LOOP
        PERFORM audit_attacher(t::regclass);
    END LOOP;
    FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'ref\_%' LOOP
        PERFORM audit_attacher(t::regclass);
    END LOOP;
END;
$$;
