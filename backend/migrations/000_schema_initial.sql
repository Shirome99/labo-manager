-- ============================================================
-- LIMS LRARVY — Schéma initial (état antérieur à 001_v1.sql)
--
-- Tables créées par l'ancienne application « Labo Manager », avant toute migration
-- numérotée : échantillons, fiches de traitement, résultats, comptes, référentiels.
-- Extrait de la base `labo` le 2026-10-22 (pg_dump --schema-only, tâche 26), avec les
-- données des référentiels (ref_*), pour pouvoir reconstruire une base de zéro :
--     python scripts/migrer.py --base labo_test
--
-- Les colonnes ajoutées plus tard par les migrations 001 à 025 figurent déjà dans ces
-- tables : leurs `ADD COLUMN IF NOT EXISTS` ne font alors rien. Les triggers d'audit
-- sont posés par 001 (audit_log) et 015 (audit_attacher).
--
-- Sur `labo`, ce fichier est enregistré comme « déjà appliqué » (migrer.py --marquer) :
-- il n'y est jamais rejoué.
-- ============================================================

--
-- PostgreSQL database dump
--

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

--
-- Name: echantillons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.echantillons (
    "N° d'ordre" integer NOT NULL,
    "N° Echantillon" character varying(50) NOT NULL,
    "Date reception" timestamp without time zone,
    "Nature de l'échantillon" character varying(255),
    "Catégorie de l'échantillon" character varying(50),
    "Type d'échantillon" integer DEFAULT 0,
    "S/type d'échantillon" integer DEFAULT 0,
    "Espèce animale" character varying(50),
    "Nbre Prlvmts SMA" integer DEFAULT 0,
    "Nbre Prlvmts SCHA" integer DEFAULT 0,
    "Nbre Prlvmts SSA" integer DEFAULT 0,
    "N° de lot" character varying(50),
    "Fabricant ou Propriétaire" character varying(50),
    "Organisme préleveur" character varying(50),
    "Réf Fiche de prélèvement" character varying(50),
    "SMA" character varying(50) DEFAULT 'Yes'::character varying,
    "SCHA" character varying(50) DEFAULT 'No'::character varying,
    "SSA" character varying(50) DEFAULT 'No'::character varying,
    "Date dépôt BA Bactériologie" timestamp without time zone,
    "Date dépôt BA Chimie" timestamp without time zone,
    "Date dépot BA SA" timestamp without time zone,
    "Date 1 Remise Rapport" timestamp without time zone,
    "Date 2 Remise Rapport" timestamp without time zone,
    "Payement" character varying(50),
    "Date de payement" timestamp without time zone,
    "Sortie MA" timestamp without time zone,
    "Sortie CH" timestamp without time zone,
    "Sortie Dc" timestamp without time zone,
    "Nb Para MA" character varying(50),
    "MONTANT TOTAL MA" character varying(50),
    "Nb Para CH" character varying(50),
    "MONTANT TOTAL CH" character varying(50),
    "Nb Para SA" character varying(50),
    "MONTANT TOTAL SA" character varying(50),
    "TOTAL" character varying(50),
    "N° QUITTANCE" character varying(50),
    "DATE" character varying(50),
    statut character varying(20) DEFAULT 'Reçu'::character varying NOT NULL,
    non_conformite text,
    "Nom du Client" character varying(255),
    "Adresse du Client" character varying(255),
    "Date prelevement" timestamp without time zone,
    "Cadre de la demande" character varying(255),
    "Mode de paiement" character varying(40),
    "Montant payé" numeric(12,2),
    temperature_reception numeric(5,1),
    nc_temperature boolean DEFAULT false NOT NULL,
    nc_contenant boolean DEFAULT false NOT NULL,
    nc_quantite boolean DEFAULT false NOT NULL,
    nc_etiquetage boolean DEFAULT false NOT NULL,
    nc_delai boolean DEFAULT false NOT NULL,
    nc_autre boolean DEFAULT false NOT NULL,
    decision_reception character varying(25),
    motif_decision text,
    CONSTRAINT echantillons_decision_reception_check CHECK (((decision_reception IS NULL) OR ((decision_reception)::text = ANY ((ARRAY['Accepté'::character varying, 'Accepté sous réserve'::character varying, 'Refusé'::character varying])::text[])))),
    CONSTRAINT echantillons_statut_check CHECK (((statut)::text = ANY ((ARRAY['Reçu'::character varying, 'En cours'::character varying, 'À valider'::character varying, 'Validé'::character varying, 'Rapport émis'::character varying])::text[])))
);

--
-- Name: COLUMN echantillons.statut; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.echantillons.statut IS 'Statut formel : Reçu → En cours → À valider → Validé → Rapport émis';

--
-- Name: echantillons_N° d'ordre_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public."echantillons_N° d'ordre_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: echantillons_N° d'ordre_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public."echantillons_N° d'ordre_seq" OWNED BY public.echantillons."N° d'ordre";

--
-- Name: historique_statuts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.historique_statuts (
    id integer NOT NULL,
    num_echantillon character varying(50) NOT NULL,
    statut_avant character varying(20),
    statut_apres character varying(20) NOT NULL,
    modifie_par integer,
    modifie_par_nom character varying(100),
    commentaire text,
    created_at timestamp without time zone DEFAULT now()
);

--
-- Name: TABLE historique_statuts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.historique_statuts IS 'Trace chaque changement de statut : qui, quand, de quoi vers quoi';

--
-- Name: historique_statuts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.historique_statuts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: historique_statuts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.historique_statuts_id_seq OWNED BY public.historique_statuts.id;

--
-- Name: num_sequences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.num_sequences (
    section character varying(10) NOT NULL,
    annee integer NOT NULL,
    dernier_num integer DEFAULT 0 NOT NULL
);

--
-- Name: TABLE num_sequences; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.num_sequences IS 'Compteurs pour la numérotation automatique des échantillons par section et par année';

--
-- Name: ref_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_analyses (
    id integer NOT NULL,
    numero_ordre integer,
    nom_analyse character varying(255) NOT NULL,
    prix character varying(30),
    reference_methode character varying(255),
    delai_execution character varying(60),
    type_analyse character varying(255),
    section character varying(10),
    code_prestation character varying(60)
);

--
-- Name: ref_analyses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_analyses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_analyses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_analyses_id_seq OWNED BY public.ref_analyses.id;

--
-- Name: ref_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_categories (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL,
    domaine character varying(120)
);

--
-- Name: ref_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_categories_id_seq OWNED BY public.ref_categories.id;

--
-- Name: ref_criteres_micro; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_criteres_micro (
    id integer NOT NULL,
    numero_ordre integer,
    critere character varying(255),
    domaine character varying(120),
    type_echantillon character varying(255),
    categorie_produit character varying(255) NOT NULL,
    parametre character varying(255),
    n character varying(30),
    c character varying(30),
    m character varying(60),
    grand_m character varying(60)
);

--
-- Name: ref_criteres_micro_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_criteres_micro_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_criteres_micro_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_criteres_micro_id_seq OWNED BY public.ref_criteres_micro.id;

--
-- Name: ref_criteres_scha; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_criteres_scha (
    id integer NOT NULL,
    numero_ordre integer,
    categorie_ch character varying(255) NOT NULL,
    critere_1 text,
    critere_2 text,
    critere_3 text,
    critere_4 text,
    critere_5 text,
    critere_6 text,
    critere_7 text
);

--
-- Name: ref_criteres_scha_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_criteres_scha_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_criteres_scha_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_criteres_scha_id_seq OWNED BY public.ref_criteres_scha.id;

--
-- Name: ref_fabricants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_fabricants (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL,
    adresse character varying(255),
    ville character varying(120),
    telephone character varying(60),
    fax character varying(60)
);

--
-- Name: ref_fabricants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_fabricants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_fabricants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_fabricants_id_seq OWNED BY public.ref_fabricants.id;

--
-- Name: ref_natures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_natures (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL
);

--
-- Name: ref_natures_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_natures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_natures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_natures_id_seq OWNED BY public.ref_natures.id;

--
-- Name: ref_organismes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_organismes (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL,
    adresse character varying(255),
    ville character varying(120),
    telephone character varying(60),
    email character varying(120)
);

--
-- Name: ref_organismes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ref_organismes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ref_organismes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ref_organismes_id_seq OWNED BY public.ref_organismes.id;

--
-- Name: ref_soustypes_echantillon; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_soustypes_echantillon (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL,
    type_id integer
);

--
-- Name: ref_types_echantillon; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ref_types_echantillon (
    id integer NOT NULL,
    libelle character varying(255) NOT NULL
);

--
-- Name: resultats_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resultats_analyses (
    id integer NOT NULL,
    num_echantillon character varying(50) NOT NULL,
    section character varying(10) NOT NULL,
    analyse_effectuee character varying(255),
    reference_methode character varying(255),
    volume_ensemence character varying(60),
    nombre_analyses integer,
    date_analyse date,
    date_sortie date,
    rp1 character varying(60),
    rp2 character varying(60),
    rp3 character varying(60),
    rp4 character varying(60),
    rp5 character varying(60),
    saisi_par character varying(80),
    cree_le timestamp with time zone DEFAULT now(),
    rp6 character varying(60),
    rp7 character varying(60),
    rp8 character varying(60),
    rp9 character varying(60),
    moyenne character varying(60),
    conclusion text,
    resultat_analyse text,
    criteres_interpretation text,
    nbre_positifs integer,
    nbre_negatif integer,
    nbre_douteux integer,
    responsable_analyse character varying(120),
    nbre_prelevements integer
);

--
-- Name: resultats_analyses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resultats_analyses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: resultats_analyses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resultats_analyses_id_seq OWNED BY public.resultats_analyses.id;

--
-- Name: traitement_scha; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traitement_scha (
    id integer NOT NULL,
    num_echantillon character varying(50) NOT NULL,
    num_ordre integer,
    nbre_prelevements integer DEFAULT 0,
    date_reception_cha date,
    nombre_unites_kg character varying(50),
    analyse_prevue_le date,
    resp_reception character varying(100),
    date_revue_demande date,
    lieu_stockage character varying(100),
    delai_retenu_j integer DEFAULT 0,
    date_mise_en_analyse date,
    date_sortie_resultats date,
    date_re_cha date,
    observations text,
    categorie_echantillon character varying(200),
    declaration_conformite text,
    commentaire_1 text,
    commentaire_2 text,
    conformite character varying(50),
    erratum text,
    site_essai character varying(100) DEFAULT 'LRAR Tanger'::character varying,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    saisi_par character varying(80),
    valide_par character varying(80),
    date_validation timestamp with time zone,
    equipement_utilise character varying(120),
    lot_reactif character varying(120),
    etat_echantillon character varying(255),
    temperature_reception character varying(50)
);

--
-- Name: traitement_scha_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traitement_scha_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: traitement_scha_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traitement_scha_id_seq OWNED BY public.traitement_scha.id;

--
-- Name: traitement_sma; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traitement_sma (
    id integer NOT NULL,
    num_echantillon character varying(50) NOT NULL,
    num_ordre integer,
    nbre_prelevements integer DEFAULT 0,
    date_reception_ma date,
    lieu_stockage character varying(100),
    date_revue_demande date,
    analyse_prevue_le date,
    delai_retenu_j integer DEFAULT 0,
    resp_reception character varying(100),
    date_mise_en_analyse date,
    date_sortie_resultats date,
    date_rapport_essai date,
    observations text,
    conformite character varying(50),
    declaration_conformite integer,
    commentaire_1 text,
    commentaire_2 text,
    erratum text,
    site_essai character varying(100) DEFAULT 'LRAR Tanger'::character varying,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    saisi_par character varying(80),
    valide_par character varying(80),
    date_validation timestamp with time zone,
    equipement_utilise character varying(120),
    lot_reactif character varying(120),
    etat_echantillon character varying(255),
    temperature_reception character varying(50),
    conclusion text
);

--
-- Name: traitement_sma_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traitement_sma_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: traitement_sma_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traitement_sma_id_seq OWNED BY public.traitement_sma.id;

--
-- Name: traitement_ssa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traitement_ssa (
    id integer NOT NULL,
    num_echantillon character varying(50) NOT NULL,
    num_ordre integer,
    nbre_prelevements integer DEFAULT 0,
    espece_animale character varying(100),
    date_reception_sa date,
    analyse_prevue_le date,
    resp_reception character varying(100),
    date_revue_demande date,
    lieu_stockage character varying(100),
    delai_retenu_j integer DEFAULT 0,
    date_mise_en_analyse date,
    date_sortie_resultats date,
    type_analyses character varying(200),
    date_emission_re date,
    suspicion_clinique text,
    date_remise_re_sa date,
    observations text,
    categorie_echantillon character varying(200),
    critere_interpretation character varying(200),
    interpretation_resultats text,
    commentaire_1 text,
    commentaire_2 text,
    commentaire_3 text,
    positivite character varying(100),
    erratum text,
    site_essai character varying(100) DEFAULT 'LRAR Tanger'::character varying,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    saisi_par character varying(80),
    valide_par character varying(80),
    date_validation timestamp with time zone,
    equipement_utilise character varying(120),
    lot_reactif character varying(120),
    etat_echantillon character varying(255),
    temperature_reception character varying(50)
);

--
-- Name: traitement_ssa_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traitement_ssa_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: traitement_ssa_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traitement_ssa_id_seq OWNED BY public.traitement_ssa.id;

--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    nom text NOT NULL,
    email text NOT NULL,
    mot_de_passe text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    role character varying(20) DEFAULT 'user'::character varying NOT NULL,
    echecs_connexion integer DEFAULT 0 NOT NULL,
    verrouille_jusqu timestamp with time zone
);

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;

--
-- Name: echantillons N° d'ordre; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.echantillons ALTER COLUMN "N° d'ordre" SET DEFAULT nextval('public."echantillons_N° d''ordre_seq"'::regclass);

--
-- Name: historique_statuts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historique_statuts ALTER COLUMN id SET DEFAULT nextval('public.historique_statuts_id_seq'::regclass);

--
-- Name: ref_analyses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_analyses ALTER COLUMN id SET DEFAULT nextval('public.ref_analyses_id_seq'::regclass);

--
-- Name: ref_categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_categories ALTER COLUMN id SET DEFAULT nextval('public.ref_categories_id_seq'::regclass);

--
-- Name: ref_criteres_micro id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_criteres_micro ALTER COLUMN id SET DEFAULT nextval('public.ref_criteres_micro_id_seq'::regclass);

--
-- Name: ref_criteres_scha id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_criteres_scha ALTER COLUMN id SET DEFAULT nextval('public.ref_criteres_scha_id_seq'::regclass);

--
-- Name: ref_fabricants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_fabricants ALTER COLUMN id SET DEFAULT nextval('public.ref_fabricants_id_seq'::regclass);

--
-- Name: ref_natures id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_natures ALTER COLUMN id SET DEFAULT nextval('public.ref_natures_id_seq'::regclass);

--
-- Name: ref_organismes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_organismes ALTER COLUMN id SET DEFAULT nextval('public.ref_organismes_id_seq'::regclass);

--
-- Name: resultats_analyses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resultats_analyses ALTER COLUMN id SET DEFAULT nextval('public.resultats_analyses_id_seq'::regclass);

--
-- Name: traitement_scha id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_scha ALTER COLUMN id SET DEFAULT nextval('public.traitement_scha_id_seq'::regclass);

--
-- Name: traitement_sma id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_sma ALTER COLUMN id SET DEFAULT nextval('public.traitement_sma_id_seq'::regclass);

--
-- Name: traitement_ssa id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_ssa ALTER COLUMN id SET DEFAULT nextval('public.traitement_ssa_id_seq'::regclass);

--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);

--
-- Name: echantillons echantillons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.echantillons
    ADD CONSTRAINT echantillons_pkey PRIMARY KEY ("N° Echantillon");

--
-- Name: historique_statuts historique_statuts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historique_statuts
    ADD CONSTRAINT historique_statuts_pkey PRIMARY KEY (id);

--
-- Name: num_sequences num_sequences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.num_sequences
    ADD CONSTRAINT num_sequences_pkey PRIMARY KEY (section, annee);

--
-- Name: ref_analyses ref_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_analyses
    ADD CONSTRAINT ref_analyses_pkey PRIMARY KEY (id);

--
-- Name: ref_categories ref_categories_libelle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_categories
    ADD CONSTRAINT ref_categories_libelle_key UNIQUE (libelle);

--
-- Name: ref_categories ref_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_categories
    ADD CONSTRAINT ref_categories_pkey PRIMARY KEY (id);

--
-- Name: ref_criteres_micro ref_criteres_micro_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_criteres_micro
    ADD CONSTRAINT ref_criteres_micro_pkey PRIMARY KEY (id);

--
-- Name: ref_criteres_scha ref_criteres_scha_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_criteres_scha
    ADD CONSTRAINT ref_criteres_scha_pkey PRIMARY KEY (id);

--
-- Name: ref_fabricants ref_fabricants_libelle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_fabricants
    ADD CONSTRAINT ref_fabricants_libelle_key UNIQUE (libelle);

--
-- Name: ref_fabricants ref_fabricants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_fabricants
    ADD CONSTRAINT ref_fabricants_pkey PRIMARY KEY (id);

--
-- Name: ref_natures ref_natures_libelle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_natures
    ADD CONSTRAINT ref_natures_libelle_key UNIQUE (libelle);

--
-- Name: ref_natures ref_natures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_natures
    ADD CONSTRAINT ref_natures_pkey PRIMARY KEY (id);

--
-- Name: ref_organismes ref_organismes_libelle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_organismes
    ADD CONSTRAINT ref_organismes_libelle_key UNIQUE (libelle);

--
-- Name: ref_organismes ref_organismes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_organismes
    ADD CONSTRAINT ref_organismes_pkey PRIMARY KEY (id);

--
-- Name: ref_soustypes_echantillon ref_soustypes_echantillon_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_soustypes_echantillon
    ADD CONSTRAINT ref_soustypes_echantillon_pkey PRIMARY KEY (id);

--
-- Name: ref_types_echantillon ref_types_echantillon_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_types_echantillon
    ADD CONSTRAINT ref_types_echantillon_pkey PRIMARY KEY (id);

--
-- Name: resultats_analyses resultats_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resultats_analyses
    ADD CONSTRAINT resultats_analyses_pkey PRIMARY KEY (id);

--
-- Name: traitement_scha traitement_scha_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_scha
    ADD CONSTRAINT traitement_scha_pkey PRIMARY KEY (id);

--
-- Name: traitement_sma traitement_sma_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_sma
    ADD CONSTRAINT traitement_sma_pkey PRIMARY KEY (id);

--
-- Name: traitement_ssa traitement_ssa_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_ssa
    ADD CONSTRAINT traitement_ssa_pkey PRIMARY KEY (id);

--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);

--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

--
-- Name: echantillons_date_reception_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX echantillons_date_reception_idx ON public.echantillons USING btree ("Date reception");

--
-- Name: echantillons_decision_reception_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX echantillons_decision_reception_idx ON public.echantillons USING btree (decision_reception);

--
-- Name: echantillons_fabricant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX echantillons_fabricant_idx ON public.echantillons USING btree ("Fabricant ou Propriétaire");

--
-- Name: echantillons_organisme_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX echantillons_organisme_idx ON public.echantillons USING btree ("Organisme préleveur");

--
-- Name: echantillons_statut_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX echantillons_statut_idx ON public.echantillons USING btree (statut);

--
-- Name: idx_analyses_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analyses_section ON public.ref_analyses USING btree (section);

--
-- Name: idx_crit_categorie; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_crit_categorie ON public.ref_criteres_micro USING btree (categorie_produit);

--
-- Name: idx_crit_scha_cat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_crit_scha_cat ON public.ref_criteres_scha USING btree (categorie_ch);

--
-- Name: idx_ech_scha; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ech_scha ON public.echantillons USING btree ("SCHA");

--
-- Name: idx_ech_sma; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ech_sma ON public.echantillons USING btree ("SMA");

--
-- Name: idx_ech_ssa; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ech_ssa ON public.echantillons USING btree ("SSA");

--
-- Name: idx_historique_statuts_ech; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_historique_statuts_ech ON public.historique_statuts USING btree (num_echantillon);

--
-- Name: idx_res_ech; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_res_ech ON public.resultats_analyses USING btree (num_echantillon);

--
-- Name: idx_res_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_res_section ON public.resultats_analyses USING btree (section);

--
-- Name: idx_soustype_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_soustype_type ON public.ref_soustypes_echantillon USING btree (type_id);

--
-- Name: idx_traitement_scha_ech; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_traitement_scha_ech ON public.traitement_scha USING btree (num_echantillon);

--
-- Name: idx_traitement_sma_ech; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_traitement_sma_ech ON public.traitement_sma USING btree (num_echantillon);

--
-- Name: idx_traitement_ssa_ech; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_traitement_ssa_ech ON public.traitement_ssa USING btree (num_echantillon);

--
-- Name: resultats_analyses_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resultats_analyses_date_idx ON public.resultats_analyses USING btree (date_analyse);

--
-- Name: ref_soustypes_echantillon fk_soustype_type; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ref_soustypes_echantillon
    ADD CONSTRAINT fk_soustype_type FOREIGN KEY (type_id) REFERENCES public.ref_types_echantillon(id) ON DELETE RESTRICT;

--
-- Name: historique_statuts historique_statuts_num_echantillon_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historique_statuts
    ADD CONSTRAINT historique_statuts_num_echantillon_fkey FOREIGN KEY (num_echantillon) REFERENCES public.echantillons("N° Echantillon") ON DELETE CASCADE;

--
-- Name: resultats_analyses resultats_analyses_num_echantillon_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resultats_analyses
    ADD CONSTRAINT resultats_analyses_num_echantillon_fkey FOREIGN KEY (num_echantillon) REFERENCES public.echantillons("N° Echantillon") ON DELETE CASCADE;

--
-- Name: traitement_scha traitement_scha_num_echantillon_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_scha
    ADD CONSTRAINT traitement_scha_num_echantillon_fkey FOREIGN KEY (num_echantillon) REFERENCES public.echantillons("N° Echantillon") ON DELETE CASCADE;

--
-- Name: traitement_sma traitement_sma_num_echantillon_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_sma
    ADD CONSTRAINT traitement_sma_num_echantillon_fkey FOREIGN KEY (num_echantillon) REFERENCES public.echantillons("N° Echantillon") ON DELETE CASCADE;

--
-- Name: traitement_ssa traitement_ssa_num_echantillon_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traitement_ssa
    ADD CONSTRAINT traitement_ssa_num_echantillon_fkey FOREIGN KEY (num_echantillon) REFERENCES public.echantillons("N° Echantillon") ON DELETE CASCADE;

--
-- PostgreSQL database dump complete
--

-- Fonction historique de numérotation (non utilisée par l'application, conservée)
CREATE OR REPLACE FUNCTION public.gen_num_echantillon(p_section character varying)
 RETURNS character varying
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_annee     INTEGER;
    v_num       INTEGER;
    v_resultat  VARCHAR;
BEGIN
    v_annee := EXTRACT(YEAR FROM NOW())::INTEGER;

    -- Insérer le compteur s'il n'existe pas encore pour cette année
    INSERT INTO num_sequences (section, annee, dernier_num)
    VALUES (p_section, v_annee, 0)
    ON CONFLICT DO NOTHING;

    -- Incrémenter de manière atomique (verrou sur la ligne)
    UPDATE num_sequences
    SET dernier_num = dernier_num + 1
    WHERE section = p_section AND annee = v_annee
    RETURNING dernier_num INTO v_num;

    -- Format : YYYY-SEC-NNNN
    v_resultat := v_annee || '-' || p_section || '-' || LPAD(v_num::TEXT, 4, '0');

    RETURN v_resultat;
END;
$function$;

COMMENT ON FUNCTION public.gen_num_echantillon(p_section character varying) IS 'Génère un numéro unique au format YYYY-SEC-NNNN (ex: 2026-SMA-0042)';

-- ============================================================
-- Données des référentiels
-- ============================================================

--
-- PostgreSQL database dump
--

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

--
-- Data for Name: ref_analyses; Type: TABLE DATA; Schema: public; Owner: -
--

--
-- Data for Name: ref_categories; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (1, 'Autres produits en poudre à base de lait', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (2, 'Beurre au lait cru ou lait ayant subi un traitement thermique plus faible que la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (3, 'Beurre et crème', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (4, 'Beurre fabriqués à partir de lait cru ou de lait traité à une température inférieure à celle de la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (5, 'Carcasse de volailles entière ou pièces de découpe', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (6, 'Carcasses ou demi-carcasses', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (7, 'Charcuteries de poisson (produits cuits) : terrines, rillettes.', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (8, 'Crustacés congelés et surgelés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (9, 'Crustacés congelés ou surgelés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (10, 'Crustacés crus décortiqués ou queues', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (11, 'Crustacés crus entiers', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (12, 'Crustacés cuits entiers', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (13, 'Crustacés et mollusques cuits décortiqués', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (14, 'Crème fabriqués à partir de lait cru ou de lait traité à une température inférieure à celle de la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (15, 'Crème pâtissière et pâtisserie non cuite', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (16, 'Crèmes glacées', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (17, 'Cuisse de grenouilles crues, escargot décoquillés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (18, 'Foie gras cru, abats', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (19, 'Foie gras cru, abats crus', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (20, 'Fromage fabriqué à partir de lait cru', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (21, 'Fromage fabriqué à partir de lait traité à une température inférieure à celle de la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (22, 'Fromages', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (23, 'Fromages affinés à base de lait ou lactosérum avec traitement thermique plus que la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (24, 'Fromages affinés à base de lait ou lactosérum pasteurisés.', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (25, 'Fromages au lait cru', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (26, 'Fromages à base de lait ayant subi un traitement thermique moins fort que la pasteurisation', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (27, 'Fromages à base de lait ou de lactosérum ayant subi un traitement thermique', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (28, 'Fromages à pâte molle non affinés (fromages frais) à base de lait ou lactosérum pasteurisés ou traitement thermique plus fort', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (29, 'Fruits et légumes prédécoupés (prêts à être consommés)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (30, 'Graines germées (prêtes à être consommées)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (31, 'Graisses animales d’origine non laitière', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (32, 'Gélatine, collagène', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (33, 'Hors d’œuvre à base de poisson', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (34, 'Jus de fruits et de légumes non pasteurisé (prêt à être consommé)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (35, 'Lactosérum en poudre', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (36, 'Lait cru', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (37, 'Lait en poudre', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (38, 'Lait pasteurisé et autres produits laitiers liquides pasteurisés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (39, 'Mollusque bivalves vivants et échinodermes, tuniciers et gastéropodes vivants', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (40, 'Mollusques crus à l’état frais ou congelé (sauf coquillages vivants)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (41, 'Mollusques et crustacés cuits entiers', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (42, 'Ovoproduit', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (43, 'Pièces de découpe de volailles fumées, salées', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (44, 'Pièces de viande réfrigérées ou congelées', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (45, 'Plats cuisinés à base de poisson cuit', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (46, 'Plats cuisinés à base de poisson cuit conditionnés sous vide ou atmosphère.', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (47, 'Poissons congelés et surgelés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (48, 'Poissons fumés (semi conserves)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (49, 'Poissons marinés (semi conserves)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (50, 'Poissons salés (semi conserves)', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (51, 'Poissons séchés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (52, 'Poissons tranchés, panés ou non, filets de poissons frais, réfrigérés, congelés ou surgelés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (53, 'Poissons, crustacés et mollusques congelés et surgelés', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (54, 'Produits alimentaires prêts à être consommés contenant des œufs crus, excepté les produits dont le procédé de fabrication ou la composition permettent de supprimer le risque salmonelle', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (55, 'Produits alimentaires prêts à être consommés destinés aux nourrissons et produits alimentaires prêts à être consommés destinés à des fins médicales spéciales', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (56, 'Produits alimentaires prêts à être consommés ne permettant pas la croissance de Listeria monocytogenes*, autres que ceux destinés aux nourrissons ou à des fins médicales spéciales', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (57, 'Produits alimentaires prêts à être consommés permettant la croissance de Listeria monocytogenes, autres que ceux destinés aux nourrissons ou à des fins médicales spéciales', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (58, 'Produits de charcuterie crus soumis à dessiccation et produits de salaison crus', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (59, 'Préparations de suite en poudre de suite', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (60, 'Préparations de viande autres que volailles à consommer cuites', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (61, 'Préparations en poudre pour nourrissons et aliments diététiques en poudre destinés à des fins médicales spéciales pour nourrissons de moins de six mois', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (62, 'Surimi', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (63, 'Viande hachée autres espèces que les volailles', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (64, 'Viandes hachées et préparations de viande de volailles à consommer cuites', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (65, 'Viandes séparées mécaniquement', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (66, 'Viandes séparées mécaniquement, autre que volailles', 'ANIMAL');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (67, 'Mollusques bivalves', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (68, 'Céphalopodes', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (71, 'Boyaux animaux', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (72, 'Peaux salées', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (73, 'Aliments de bétail', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (74, 'Conserve de poissons', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (75, 'Crustacés - 80 à 120 U/Kg', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (76, 'Crustacés - < 80 U/Kg', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (77, 'Crustacés - > 120 U/Kg', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (78, 'Crustacés cuits', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (79, 'Crustacés - Autres crustacés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (80, 'Eau potable', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (81, 'Escargot', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (83, 'Huile d''olive', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (84, 'Intoxication', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (85, 'Lait et dérivés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (86, 'Oeufs de poissons', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (87, 'Poissons cuits', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (88, 'Poissons frais ou congelés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (89, 'Poissons marinés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (90, 'Poissons maturés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (91, 'Poissons salés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (92, 'Saumure', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (93, 'Viande et dérivés', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (94, 'Farines de poissons', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (95, 'Prélévements pour Toxicologie', 'CHIMIE');
INSERT INTO public.ref_categories (id, libelle, domaine) VALUES (96, 'Autres Mollusques', 'CHIMIE');

--
-- Data for Name: ref_criteres_micro; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_criteres_micro (id, numero_ordre, critere, domaine, type_echantillon, categorie_produit, parametre, n, c, m, grand_m) VALUES (1, 93, 'Critères de sécurité (Arr.293-19 du15/02/19)', 'ANIMAL', '6°- Critères de sécurité relatifs aux laits et produits dérivés de lait', 'Fromage frais au lait pasteurisé (marché)', 'Entérotoxines Staphylococciques', 'n =5', 'c=0', 'absence/25 g', 'absence/25 g');
INSERT INTO public.ref_criteres_micro (id, numero_ordre, critere, domaine, type_echantillon, categorie_produit, parametre, n, c, m, grand_m) VALUES (2, 94, 'Critères de sécurité (Arr.293-19 du15/02/19)', 'ANIMAL', '6°- Critères de sécurité relatifs aux laits et produits dérivés de lait', 'Fromage frais au lait pasteurisé (marché)', 'Salmonella', 'n =5', 'c=0', 'absence/25g', 'absence/25g');
INSERT INTO public.ref_criteres_micro (id, numero_ordre, critere, domaine, type_echantillon, categorie_produit, parametre, n, c, m, grand_m) VALUES (3, 95, 'Critères de sécurité (Arr.293-19 du15/02/19)', 'ANIMAL', '6°- Critères de sécurité relatifs aux laits et produits dérivés de lait', 'Fromage frais au lait pasteurisé (marché)', 'Listeria monocytogenes', 'n =5', 'c=0', 'm=10(2) ufc/g', 'M=10(2) ufc/g');
INSERT INTO public.ref_criteres_micro (id, numero_ordre, critere, domaine, type_echantillon, categorie_produit, parametre, n, c, m, grand_m) VALUES (4, 96, 'Critères d''hygiène (Arr.293-19 du15/02/19)', 'ANIMAL', '6*- Critères d’hygiène relatifs aux laits et produits dérivés de lait', 'Fromage frais au lait pasteurisé (marché)', 'Staphylocoque à coagulase positive', 'n =5', 'c=2', 'm=10 ufc/g', 'M=10(2) ufc/g');
INSERT INTO public.ref_criteres_micro (id, numero_ordre, critere, domaine, type_echantillon, categorie_produit, parametre, n, c, m, grand_m) VALUES (5, 97, 'Critères d''hygiène (Arr.293-19 du15/02/19)', 'ANIMAL', '6*- Critères d’hygiène relatifs aux laits et produits dérivés de lait', 'Fromage frais au lait pasteurisé (marché)', 'E.coli', 'n =5', 'c=2', 'm=10(2) ufc/g', 'M=10(3) ufc/g');

--
-- Data for Name: ref_criteres_scha; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (1, 8, 'Mollusques bivalves frais', '<= 20 ppm (HPLC)', 'Survie 3 souris/24 h', '<=400US/100g', 'Hg:0,5-Pb:1,5-Cd:1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (2, 9, 'Céphalopodes', '-', '-', '<=150 mg/Kg', 'Hg:0,5-Pb:1,0-Cd:1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (3, 14, 'Lait en poudre', NULL, NULL, NULL, 'M1:<=0,05 µg/Kg', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (4, 15, 'Crèmes glacées', NULL, NULL, NULL, 'M1:Absence -CCM', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (5, 16, 'Boyaux animaux', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (6, 17, 'Peaux tannées', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (7, 24, 'Aliments de bétail', '-', '-', '-', 'Absence (CCM)', NULL, '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (8, 31, 'Conserve de poissons', NULL, '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (9, 37, 'Crustacés - 80 à 120 U/Kg', '-', '-', '<200mg/Kg', 'Hg:0,5-Pb:0,5-Cd:0,5mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (10, 38, 'Crustacés - < 80 U/Kg', '-', '-', '<150mg/Kg', 'Hg:0,5-Pb:0,5-Cd:0,5mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (11, 39, 'Crustacés - > 120 U/Kg', '-', '-', '<300mg/Kg', 'Hg:0,5-Pb:0,5-Cd:0,5mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (12, 40, 'Crustacés cuits', '-', '-', '<50mg/kg', 'Hg:0,5-Pb:0,5-Cd:0,5mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (13, 44, 'Crustacés - Autres crustacés', '-', '-', '<150mg/Kg', 'Hg:0,5-Pb:0,3-Cd:0,05mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (14, 49, 'Eau potable', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (15, 50, 'Escargot', NULL, NULL, NULL, NULL, 'Absence (CCM)', NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (16, 51, 'Fromages', NULL, NULL, NULL, 'M1:Absence -CCM', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (17, 58, 'Huile d''olive', NULL, NULL, NULL, '-', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (18, 59, 'Intoxication', NULL, NULL, NULL, '-', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (19, 61, 'Lait et dérivés', NULL, NULL, NULL, 'M1:Absence -CCM', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (20, 69, 'M', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (21, 70, 'Oeufs de poissons', NULL, NULL, NULL, 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (22, 71, 'Poissons cuits', '-2 sur 9:Entre 100et200ppm-Aucun>200ppm-Moy<100ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (23, 91, 'Poissons frais ou congelés', '-2 sur 9:Entre 100et200ppm-Aucun>200ppm-Moy<100ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (24, 104, 'Poissons marinés', '-2 sur 9:Entre 100et200ppm-Aucun>200ppm-Moy<100ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (25, 105, 'Poissons maturés', '-2 sur 9:Entre 200et400ppm-Aucun>400ppm-Moy<200ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '>=15%');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (26, 126, 'Poissons salés', '-2 sur 9:Entre 100et200ppm-Aucun>200ppm-Moy<100ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '>=10%');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (27, 127, 'Saumure', '-', '-', '-', '-', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (28, 128, 'Viande et dérivés', '-', '-', '-', '-', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (29, 129, 'Farines de poissons', '-2 sur 9:Entre 100et200ppm-Aucun>200ppm-Moy<100ppm', '-', '-', 'Hg:0,5à1,0-Pb:0,3à1,5-Cd:0,05à1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (30, 130, 'Prélévements pour Toxicologie', NULL, NULL, NULL, '-', NULL, NULL, NULL);
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (31, 131, 'Mollusques bivalves en conserve', '<= 20 ppm (HPLC)', 'Survie 3 souris/24 h', 'Absence de PSP', 'Hg:0,5-Pb:1,5-Cd:1,0mg/Kg', '-', '-', '-');
INSERT INTO public.ref_criteres_scha (id, numero_ordre, categorie_ch, critere_1, critere_2, critere_3, critere_4, critere_5, critere_6, critere_7) VALUES (32, 132, 'Autres Mollusques', '-', '-', '<=150 mg/Kg', 'Hg:0,5-Pb:0,3-Cd:0,05mg/Kg', '-', '-', '-');

--
-- Data for Name: ref_fabricants; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (1, 'Akhattab Abdelali - Casa', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (2, 'Amendis', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (3, 'ANOC', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (4, 'Boyauderie Atlas', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (5, 'Boyauderie Ghazal', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (6, 'C2M', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (7, 'Colaib', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (8, 'Colainord', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (9, 'Conservas Y Salasones', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (10, 'Crangomar', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (11, 'Cumarex', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (12, 'Damjiguend', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (13, 'Détroit Sea Food', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (14, 'Dinay', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (15, 'El Menu Conserve', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (16, 'F & C', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (17, 'F.B.M.', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (18, 'FTN Avicole', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (19, 'Gamarsa', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (20, 'Gastronemia Napoletana', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (21, 'Gil Gomes', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (22, 'Glanord', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (23, 'Global Fisherie', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (24, 'INMAR', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (25, 'Klaas Puul', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (26, 'La Monegasque', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (27, 'Larafil', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (28, 'Marcorea', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (29, 'Maroc Sea Food', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (30, 'Maromar', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (31, 'Mohdavnor', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (32, 'Nador Pêche', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (33, 'Pamapêche', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (34, 'Pecatlan', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (35, 'Pesca de punto Almina Tétouan', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (36, 'PICOBA', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (37, 'Pimentonera', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (38, 'SIEPF', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (39, 'SOGAVI', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (40, 'Solait', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (41, 'Somafaco', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (42, 'Somavian', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (43, 'Sopetan', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (44, 'Sté Fromagerie BEL Maroc', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (45, 'T K Fish', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_fabricants (id, libelle, adresse, ville, telephone, fax) VALUES (46, 'TALAB', NULL, NULL, NULL, NULL);

--
-- Data for Name: ref_natures; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_natures (id, libelle) VALUES (1, 'Abeilles');
INSERT INTO public.ref_natures (id, libelle) VALUES (2, 'Abeilles + couvain');
INSERT INTO public.ref_natures (id, libelle) VALUES (3, 'Anchois marinés');
INSERT INTO public.ref_natures (id, libelle) VALUES (4, 'Anchois salés');
INSERT INTO public.ref_natures (id, libelle) VALUES (5, 'Beurre pasteurisé');
INSERT INTO public.ref_natures (id, libelle) VALUES (6, 'boisson');
INSERT INTO public.ref_natures (id, libelle) VALUES (7, 'boissons non gazeuse non alcoolisé');
INSERT INTO public.ref_natures (id, libelle) VALUES (8, 'Bonites congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (9, 'Boyaux salés d''ovins');
INSERT INTO public.ref_natures (id, libelle) VALUES (10, 'Boyaux salés de porc');
INSERT INTO public.ref_natures (id, libelle) VALUES (11, 'Calamars congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (12, 'Casserons congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (13, 'Coque rouge au naturel');
INSERT INTO public.ref_natures (id, libelle) VALUES (14, 'CREME UHT PB');
INSERT INTO public.ref_natures (id, libelle) VALUES (15, 'Crevettes congelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (16, 'Crevettes cuites décortiquées');
INSERT INTO public.ref_natures (id, libelle) VALUES (17, 'Crevettes grises cuites décortiquées');
INSERT INTO public.ref_natures (id, libelle) VALUES (18, 'Crevettes grises cuites décortiquées en saumure');
INSERT INTO public.ref_natures (id, libelle) VALUES (19, 'Crevettes Pandalus Borealis cuites décortiquées');
INSERT INTO public.ref_natures (id, libelle) VALUES (20, 'Crevettes Pandalus Borealis cuites décortiquées en saumure');
INSERT INTO public.ref_natures (id, libelle) VALUES (21, 'Crevettes Pandalus Borealis précuites décortiquées');
INSERT INTO public.ref_natures (id, libelle) VALUES (22, 'Crevettes précuites décortiquées');
INSERT INTO public.ref_natures (id, libelle) VALUES (23, 'Crevettes roses congelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (24, 'Crevettes rouges géantes congelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (25, 'Crème glacée');
INSERT INTO public.ref_natures (id, libelle) VALUES (26, 'Dindonneaux d''un jour');
INSERT INTO public.ref_natures (id, libelle) VALUES (27, 'Eau de puit');
INSERT INTO public.ref_natures (id, libelle) VALUES (28, 'Eau de réseau de la ville');
INSERT INTO public.ref_natures (id, libelle) VALUES (29, 'Escargots de terre vivants');
INSERT INTO public.ref_natures (id, libelle) VALUES (30, 'Filets d''Anchois marinés');
INSERT INTO public.ref_natures (id, libelle) VALUES (31, 'Filets d''Anchois salés');
INSERT INTO public.ref_natures (id, libelle) VALUES (32, 'Filets de maquereaux');
INSERT INTO public.ref_natures (id, libelle) VALUES (33, 'Filets de poulets');
INSERT INTO public.ref_natures (id, libelle) VALUES (34, 'Filtets d''Anchois');
INSERT INTO public.ref_natures (id, libelle) VALUES (35, 'Fraises congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (36, 'Fraises frais');
INSERT INTO public.ref_natures (id, libelle) VALUES (37, 'Fraises surgelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (38, 'Fromage affiné');
INSERT INTO public.ref_natures (id, libelle) VALUES (39, 'Fromage Emmental 1/2 LONGE');
INSERT INTO public.ref_natures (id, libelle) VALUES (40, 'Fromage fondu');
INSERT INTO public.ref_natures (id, libelle) VALUES (41, 'Fromage frais fondu');
INSERT INTO public.ref_natures (id, libelle) VALUES (42, 'Lait cru');
INSERT INTO public.ref_natures (id, libelle) VALUES (43, 'Lait en poudre');
INSERT INTO public.ref_natures (id, libelle) VALUES (44, 'Lait pasteurisé');
INSERT INTO public.ref_natures (id, libelle) VALUES (45, 'Lait UHT');
INSERT INTO public.ref_natures (id, libelle) VALUES (46, 'Langoustines congelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (47, 'Lben');
INSERT INTO public.ref_natures (id, libelle) VALUES (48, 'Maqurereaux congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (49, 'Microbeurrier PB 10G DOUX');
INSERT INTO public.ref_natures (id, libelle) VALUES (50, 'Morceaux d''anchois marinés');
INSERT INTO public.ref_natures (id, libelle) VALUES (51, 'Morceaux d''anchois salés');
INSERT INTO public.ref_natures (id, libelle) VALUES (52, 'Moules');
INSERT INTO public.ref_natures (id, libelle) VALUES (53, 'Moustiques');
INSERT INTO public.ref_natures (id, libelle) VALUES (54, 'Mûres surgelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (55, 'Palourdes');
INSERT INTO public.ref_natures (id, libelle) VALUES (56, 'PETIT MOULE NAT 16.67 G');
INSERT INTO public.ref_natures (id, libelle) VALUES (57, 'Pilons de poulets');
INSERT INTO public.ref_natures (id, libelle) VALUES (58, 'Plants de framboisier');
INSERT INTO public.ref_natures (id, libelle) VALUES (59, 'Plants de myrtillier');
INSERT INTO public.ref_natures (id, libelle) VALUES (60, 'Plants de mûres');
INSERT INTO public.ref_natures (id, libelle) VALUES (61, 'Poissons congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (62, 'Poissons frais');
INSERT INTO public.ref_natures (id, libelle) VALUES (63, 'Poulet entier');
INSERT INTO public.ref_natures (id, libelle) VALUES (64, 'Poulpes congelés');
INSERT INTO public.ref_natures (id, libelle) VALUES (65, 'Poussins');
INSERT INTO public.ref_natures (id, libelle) VALUES (66, 'Poussins d''un jour');
INSERT INTO public.ref_natures (id, libelle) VALUES (67, 'Puntilla congelé');
INSERT INTO public.ref_natures (id, libelle) VALUES (68, 'Sangs sur anticoagulants');
INSERT INTO public.ref_natures (id, libelle) VALUES (69, 'Sangs sur tubes secs');
INSERT INTO public.ref_natures (id, libelle) VALUES (70, 'Sardines salées');
INSERT INTO public.ref_natures (id, libelle) VALUES (71, 'Seiches congelées');
INSERT INTO public.ref_natures (id, libelle) VALUES (72, 'Tissu cérebral');
INSERT INTO public.ref_natures (id, libelle) VALUES (73, 'Tête entier');
INSERT INTO public.ref_natures (id, libelle) VALUES (74, 'V.S.M. de dinde congelée');
INSERT INTO public.ref_natures (id, libelle) VALUES (75, 'Vernis');
INSERT INTO public.ref_natures (id, libelle) VALUES (76, 'Viande hachée de poulet congelé');
INSERT INTO public.ref_natures (id, libelle) VALUES (77, 'VSM de poulet');
INSERT INTO public.ref_natures (id, libelle) VALUES (78, 'Yaourt');
INSERT INTO public.ref_natures (id, libelle) VALUES (79, 'Œufs de consommation');
INSERT INTO public.ref_natures (id, libelle) VALUES (80, 'Œufs à couver de dinde');

--
-- Data for Name: ref_organismes; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (1, 'BCH Tanger-ville', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (2, 'I.V. Larache', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (3, 'Propriétaire', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (4, 'S. V. ORMVAG', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (5, 'S.R.F Tanger', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (6, 'S.V. Chefchaouène', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (7, 'S.V. Kénitra', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (8, 'S.V. M.B.Ksiri S.L.G.', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (9, 'S.V. ORMVAL', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (10, 'S.V. Tanger', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (11, 'S.V. Tétouan', NULL, NULL, NULL, NULL);
INSERT INTO public.ref_organismes (id, libelle, adresse, ville, telephone, email) VALUES (12, 'S.V.F. Tanger', NULL, NULL, NULL, NULL);

--
-- Data for Name: ref_types_echantillon; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (1, 'Laits et Produits laitiers');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (2, 'Produits de la Pêche');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (3, 'Viandes et Produits Carnés');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (4, 'Eaux');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (5, 'Aliments de Bétail');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (6, 'Ovoproduits');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (7, 'Plats Cuisinés');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (8, 'Autres Prdts Alimentaires');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (9, 'Lait de mammite');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (10, 'Avorton(s)');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (11, 'Ecouvillon(s)');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (12, 'Sang sur Ac');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (13, 'Gastéropode');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (14, 'Filets de maquereaux');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (15, 'Fragments d''organes');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (16, 'Animaux vivants');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (17, 'Prélévements postmortem');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (18, 'Elevage avicole');
INSERT INTO public.ref_types_echantillon (id, libelle) VALUES (19, 'test');

--
-- Data for Name: ref_soustypes_echantillon; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (32, 'Chifonnettes', NULL);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (1, 'Conserves', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (2, 'Semi-Conserves', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (3, 'Poissons frais', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (4, 'Poissons fumés', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (5, 'Poissons Congelés et Surgelés', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (6, 'Crustacés', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (7, 'Mollusques', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (8, 'Viande de volailles', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (9, 'Viande bovine', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (10, 'Viande Ovine', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (11, 'Produits de la Charcuterie', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (12, 'VSM', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (13, 'Eaux d''Aviculture', 4);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (14, 'Eaux (Industries)', 4);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (15, 'Aliments de bétail', 5);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (16, 'Ovoproduits', 6);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (17, 'Plats Cuisinés', 7);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (18, 'Laits crus', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (19, 'Lait Pasteurisé', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (20, 'Lait fermenté aromatisé', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (21, 'Lben', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (22, 'Beurre', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (23, 'Fromage', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (24, 'Crémes glacées', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (25, 'Autres produits laitiers', 1);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (26, 'Autres produits de la pêche', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (27, 'Autres produits carnés', 3);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (28, 'Autres Eaux', 4);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (29, 'Gastéropode', 2);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (30, 'Poussins de 1 j', 18);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (31, 'Œufs à couver', 18);
INSERT INTO public.ref_soustypes_echantillon (id, libelle, type_id) VALUES (33, 'Escargots de terre', 8);

--
-- Name: ref_analyses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_analyses_id_seq', 1, false);

--
-- Name: ref_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_categories_id_seq', 96, true);

--
-- Name: ref_criteres_micro_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_criteres_micro_id_seq', 5, true);

--
-- Name: ref_criteres_scha_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_criteres_scha_id_seq', 32, true);

--
-- Name: ref_fabricants_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_fabricants_id_seq', 47, true);

--
-- Name: ref_natures_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_natures_id_seq', 80, true);

--
-- Name: ref_organismes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ref_organismes_id_seq', 12, true);

--
-- PostgreSQL database dump complete
--
