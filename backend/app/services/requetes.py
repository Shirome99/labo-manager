"""
Moteur de requêtes du reporting (tâche 21).

Pas de SQL libre : le jeu de données, les filtres, les regroupements et les mesures sont
choisis dans le CATALOGUE fermé défini ici. Chaque entrée correspond à une expression SQL
écrite dans le code ; les valeurs saisies par l'utilisateur sont toujours passées en
paramètres. Toute clé hors catalogue lève `RequeteInvalide` (400).

Construction : une sous-requête `base` (une ligne par échantillon ou par résultat d'analyse,
filtres appliqués) expose les colonnes nommées du catalogue ; la requête externe regroupe
(GROUPING SETS : lignes, sous-totaux et total général exacts, y compris pour les taux,
les médianes et les comptes distincts) et calcule les mesures.

Règles :
  - les identifiants (type, sous-type) sont affichés par leur libellé ; un code sans libellé
    est affiché « Code inconnu (n) », jamais confondu avec une valeur vide ;
  - les valeurs vides sont regroupées sous « Non renseigné » ;
  - un rôle de section ne voit que sa section (y compris les analyses, la conformité,
    les prélèvements et les montants d'un échantillon à plusieurs sections).

Ajouter un critère : une entrée dans DIMENSIONS (expression par jeu, jointures nécessaires) ;
il devient à la fois regroupement et filtre. Ajouter une mesure : une entrée dans MESURES
(agrégat par jeu, écrit sur les colonnes de `base`) et, si besoin, une colonne dans
COLONNES_BASE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

NR = "Non renseigné"
SECTIONS = ("SMA", "SCHA", "SSA")
LIMITE_DEFAUT = 5000
LIMITE_MAX = 50000


class RequeteInvalide(ValueError):
    """Définition de requête hors catalogue ou incohérente (→ 400)."""


class SectionInterdite(PermissionError):
    """Section demandée hors des droits du rôle (→ 403)."""


# ---------------------------------------------------------------------------
# Expressions SQL élémentaires (écrites dans le code, jamais issues d'une saisie)
# ---------------------------------------------------------------------------
NUM = 'e."N° Echantillon"'
RECEPTION = 'e."Date reception"'


def _txt(expr: str) -> str:
    """Valeur texte, vide ou NULL → « Non renseigné »."""
    return f"coalesce(nullif(btrim(({expr})::text), ''), '{NR}')"


def _conf(expr: str) -> str:
    """Texte libre de conformité → 'Conforme' / 'Non conforme' / NULL (non reconnu)."""
    return (f"(CASE WHEN ({expr}) ~* '^\\s*non[ -]*conforme' THEN 'Non conforme' "
            f"WHEN ({expr}) ~* '^\\s*conforme' THEN 'Conforme' END)")


def _conf_ssa(expr: str) -> str:
    """Positivité SSA : positif = non conforme, négatif = conforme."""
    return (f"(CASE WHEN ({expr}) ~* 'posit' THEN 'Non conforme' "
            f"WHEN ({expr}) ~* 'n[ée]gat' THEN 'Conforme' END)")


def _conf_ligne(r: str) -> str:
    """
    Conformité d'une ligne de résultats : conclusion de la ligne (SCHA), sinon comptages SSA
    (positifs > 0 → non conforme ; négatifs seuls → conforme), sinon conformité déclarée
    sur la fiche de traitement de la section.
    """
    fiche = (f"CASE {r}.section "
             f"WHEN 'SMA' THEN (SELECT {_conf('t.conformite')} FROM traitement_sma t "
             f"WHERE t.num_echantillon = {r}.num_echantillon LIMIT 1) "
             f"WHEN 'SCHA' THEN (SELECT {_conf('t.conformite')} FROM traitement_scha t "
             f"WHERE t.num_echantillon = {r}.num_echantillon LIMIT 1) "
             f"WHEN 'SSA' THEN (SELECT {_conf_ssa('t.positivite')} FROM traitement_ssa t "
             f"WHERE t.num_echantillon = {r}.num_echantillon LIMIT 1) END")
    return (f"coalesce({_conf(f'{r}.conclusion')}, "
            f"CASE WHEN {r}.section = 'SSA' AND {r}.nbre_positifs > 0 THEN 'Non conforme' "
            f"WHEN {r}.section = 'SSA' AND coalesce({r}.nbre_negatif, 0) > 0 THEN 'Conforme' END, "
            f"{fiche}, '{NR}')")


def _code_libelle(col: str, alias: str, quoi: str) -> str:
    return (f"CASE WHEN {col} IS NULL THEN '{NR}' "
            f"ELSE coalesce(nullif(btrim({alias}.libelle), ''), '{quoi} inconnu (code ' || {col}::text || ')') END")


# Jointures : clé → SQL. `:sections` = sections visibles / filtrées (paramètre text[]).
JOINTURES = {
    "ty": """LEFT JOIN ref_types_echantillon ty ON ty.id = e."Type d'échantillon\"""",
    "st": """LEFT JOIN ref_soustypes_echantillon st ON st.id = e."S/type d'échantillon\"""",
    "rap": f"""LEFT JOIN LATERAL (
        SELECT min(re.date_emission)::timestamp AS emission FROM rapports_emis re
        WHERE re.num_echantillon = {NUM}) rap ON true""",
    "fact": f"""LEFT JOIN LATERAL (
        SELECT count(*) AS nb_analyses, coalesce(sum(tf.prix), 0) AS montant
        FROM resultats_analyses rf
        LEFT JOIN ref_tarifs tf ON lower(btrim(tf.nom_analyse)) = lower(btrim(rf.analyse_effectuee))
                               AND tf.section = rf.section AND tf.actif
        WHERE rf.num_echantillon = {NUM} AND rf.section = ANY(CAST(:sections AS text[]))) fact ON true""",
    "conf": f"""LEFT JOIN LATERAL (
        SELECT CASE WHEN bool_or(v = 'Non conforme') THEN 'Non conforme'
                    WHEN bool_or(v = 'Conforme') THEN 'Conforme' ELSE '{NR}' END AS conformite
        FROM (
            SELECT {_conf_ligne('rc')} AS v FROM resultats_analyses rc
             WHERE rc.num_echantillon = {NUM} AND rc.section = ANY(CAST(:sections AS text[]))
            UNION ALL SELECT {_conf('t.conformite')} FROM traitement_sma t
             WHERE t.num_echantillon = {NUM} AND 'SMA' = ANY(CAST(:sections AS text[]))
            UNION ALL SELECT {_conf('t.conformite')} FROM traitement_scha t
             WHERE t.num_echantillon = {NUM} AND 'SCHA' = ANY(CAST(:sections AS text[]))
            UNION ALL SELECT {_conf_ssa('t.positivite')} FROM traitement_ssa t
             WHERE t.num_echantillon = {NUM} AND 'SSA' = ANY(CAST(:sections AS text[]))
        ) x) conf ON true""",
    "tarif": """LEFT JOIN ref_tarifs ta ON lower(btrim(ta.nom_analyse)) = lower(btrim(r.analyse_effectuee))
                              AND ta.section = r.section AND ta.actif""",
}
ORDRE_JOINTURES = ["ty", "st", "rap", "fact", "conf", "tarif"]


# Jeu « facturation » (tâche 40) : journal des mouvements des bulletins émis, une ligne par mouvement.
#   Facturé      : lignes figées du bulletin (HT) et sa TVA ;
#   Avoir        : lignes des avoirs émis (montant positif, rattaché au bulletin d'origine) et leur TVA ;
#   Exonération  : exonération en vigueur d'un bulletin (reste dû au moment de l'exonération) ;
#   Encaissement : encaissements valides (annulés exclus).
# Reste à recouvrer = facturé − avoirs − exonérations − encaissé (au centime, sans arrondi intermédiaire).
# Section d'un mouvement = section du bulletin (celle de ses échantillons, sinon « Plusieurs sections »).
def _section_bulletin(f: str) -> str:
    return f"""(SELECT CASE WHEN count(DISTINCT s.sec) = 1 THEN min(s.sec)
                    WHEN count(DISTINCT s.sec) > 1 THEN 'Plusieurs sections' END
       FROM factures_echantillons fe
       JOIN echantillons e2 ON e2."N° Echantillon" = fe.num_echantillon
       CROSS JOIN LATERAL (SELECT CASE WHEN e2."SMA" = 'Yes' THEN 'SMA' WHEN e2."SCHA" = 'Yes' THEN 'SCHA'
                                       WHEN e2."SSA" = 'Yes' THEN 'SSA' END AS sec) s
       WHERE fe.facture_id = {f}.id)"""


SANS_OBJET = "Sans objet"
_MVT_COLS = ("type_mvt, bulletin, numero, client, section, date_bulletin, date_mvt, analyse, mode, num, ligne, "
             "facture, avoir, exonere, encaisse")
MOUVEMENTS = f"""(
    SELECT 'Facturé' AS type_mvt, f.id AS bulletin, f.numero, f.client_nom AS client, {_section_bulletin('f')} AS section,
           f.date_emission AS date_bulletin, f.date_emission AS date_mvt, d.libelle::text AS analyse,
           '{SANS_OBJET}'::text AS mode, d.num_echantillon::text AS num, 1 AS ligne,
           d.montant AS facture, 0::numeric AS avoir, 0::numeric AS exonere, 0::numeric AS encaisse
      FROM factures f JOIN factures_details d ON d.facture_id = f.id
     WHERE f.type = 'facture' AND f.statut = 'émis'
    UNION ALL
    SELECT 'Facturé', f.id, f.numero, f.client_nom, {_section_bulletin('f')}, f.date_emission, f.date_emission,
           'TVA', '{SANS_OBJET}', NULL, 0, f.montant_tva, 0, 0, 0
      FROM factures f WHERE f.type = 'facture' AND f.statut = 'émis' AND f.montant_tva <> 0
    UNION ALL
    SELECT 'Avoir', o.id, o.numero, o.client_nom, {_section_bulletin('o')}, o.date_emission, a.date_emission,
           d.libelle, '{SANS_OBJET}', d.num_echantillon, 0, 0, -d.montant, 0, 0
      FROM factures a JOIN factures o ON o.id = a.facture_origine_id JOIN factures_details d ON d.facture_id = a.id
     WHERE a.type = 'avoir' AND a.statut = 'émis'
    UNION ALL
    SELECT 'Avoir', o.id, o.numero, o.client_nom, {_section_bulletin('o')}, o.date_emission, a.date_emission,
           'TVA', '{SANS_OBJET}', NULL, 0, 0, -a.montant_tva, 0, 0
      FROM factures a JOIN factures o ON o.id = a.facture_origine_id
     WHERE a.type = 'avoir' AND a.statut = 'émis' AND a.montant_tva <> 0
    UNION ALL
    SELECT 'Exonération', f.id, f.numero, f.client_nom, {_section_bulletin('f')}, f.date_emission,
           x.accorde_le::date, '{SANS_OBJET}', '{SANS_OBJET}', NULL, 0, 0, 0, x.montant, 0
      FROM exonerations x JOIN factures f ON f.id = x.facture_id WHERE x.statut = 'valide'
    UNION ALL
    SELECT 'Encaissement', f.id, f.numero, f.client_nom, {_section_bulletin('f')}, f.date_emission,
           p.date_paiement, '{SANS_OBJET}', p.mode, NULL, 0, 0, 0, 0, p.montant
      FROM paiements p JOIN factures f ON f.id = p.facture_id WHERE p.statut = 'valide'
  ) m"""
TYPES_MOUVEMENT = ["Facturé", "Avoir", "Exonération", "Encaissement"]

# En retard : pas « Rapport émis », pas refusé, reçu avant maintenant − délai de la section
# (même définition que la liste et le tableau de bord). Paramètres :lim_SMA, :lim_SCHA, :lim_SSA.
RETARD = (f"coalesce(coalesce(e.statut, '') <> 'Rapport émis' "
          f"AND coalesce(e.decision_reception, '') <> 'Refusé' AND ("
          + " OR ".join(f"(e.\"{s}\" = 'Yes' AND {RECEPTION} < :lim_{s})" for s in SECTIONS)
          + "), false)")
EMISSION = 'coalesce(rap.emission, e."Date 1 Remise Rapport")'
DELAI = (f"CASE WHEN {EMISSION} >= {RECEPTION} "
         f"THEN extract(epoch FROM ({EMISSION} - {RECEPTION})) / 86400.0 END")


def _section_echantillon() -> str:
    n = " + ".join(f"(e.\"{s}\" = 'Yes')::int" for s in SECTIONS)
    une = " ".join(f"WHEN e.\"{s}\" = 'Yes' THEN '{s}'" for s in SECTIONS)
    return f"CASE ({n}) WHEN 0 THEN '{NR}' WHEN 1 THEN CASE {une} END ELSE 'Plusieurs sections' END"


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
@dataclass
class Jeu:
    cle: str
    libelle: str
    description: str
    dates: list[str]                     # dates de référence possibles (la 1re par défaut)


JEUX = {
    "echantillons": Jeu("echantillons", "Échantillons", "Une ligne par échantillon.", ["reception", "rapport"]),
    "analyses": Jeu("analyses", "Analyses", "Une ligne par résultat d'analyse, jointe à son échantillon.",
                    ["reception", "rapport", "analyse"]),
    "facturation": Jeu("facturation", "Facturation",
                       "Journal des bulletins émis : une ligne par mouvement (lignes facturées, avoirs, "
                       "exonérations, encaissements). Reste à recouvrer = facturé − avoirs − exonérations − encaissé.",
                       ["emission_bulletin", "mouvement"]),
}

DATES_REF = {
    "reception": ("Date de réception", RECEPTION, set()),
    "rapport": ("Date d'émission du rapport (1re version)", EMISSION, {"rap"}),
    "analyse": ("Date d'analyse", "r.date_analyse::timestamp", set()),
    "emission_bulletin": ("Date d'émission du bulletin", "m.date_bulletin::timestamp", set()),
    "mouvement": ("Date du mouvement (bulletin, avoir, exonération, encaissement)", "m.date_mvt::timestamp", set()),
}

PERIODES_RELATIVES = {
    "mois_en_cours": "Mois en cours",
    "mois_precedent": "Mois précédent",
    "annee_en_cours": "Année en cours",
    "annee_precedente": "Année précédente",
}


@dataclass
class Dimension:
    cle: str
    libelle: str
    sql: dict[str, str]                  # jeu → expression (texte)
    jointures: dict[str, set] = field(default_factory=dict)
    filtrable: bool = True
    valeurs: list[str] | None = None     # valeurs fixes (sinon : liste distincte en base)


_ECH = ("echantillons",)
_TOUS = ("echantillons", "analyses", "facturation")


def _pour_tous(expr: str, jointures: set | None = None, jeux=("echantillons", "analyses")):
    return {j: expr for j in jeux}, {j: set(jointures or ()) for j in jeux}


def _dim(cle, libelle, expr, jointures=None, jeux=("echantillons", "analyses"), **kw):
    sql, jt = _pour_tous(expr, jointures, jeux)
    return Dimension(cle, libelle, sql, jt, **kw)


def _dims() -> dict[str, Dimension]:
    d = [
        Dimension("section", "Section",
                  {"echantillons": _section_echantillon(), "facturation": _txt("m.section"),
                   "analyses": _txt("r.section")},
                  valeurs=list(SECTIONS)),
        Dimension("client", "Client",
                  {"echantillons": _txt('e."Nom du Client"'), "analyses": _txt('e."Nom du Client"'),
                   "facturation": _txt("m.client")}),
        _dim("statut", "Statut", _txt("e.statut"),
             valeurs=["Reçu", "En cours", "À valider", "Validé", "Rapport émis"]),
        _dim("type", "Type d'échantillon", _code_libelle('e."Type d\'échantillon"', "ty", "Type"), {"ty"}),
        _dim("soustype", "Sous-type d'échantillon", _code_libelle('e."S/type d\'échantillon"', "st", "Sous-type"), {"st"}),
        _dim("categorie", "Catégorie", _txt('e."Catégorie de l\'échantillon"')),
        _dim("nature", "Nature", _txt('e."Nature de l\'échantillon"')),
        _dim("fabricant", "Fabricant / propriétaire", _txt('e."Fabricant ou Propriétaire"')),
        _dim("organisme", "Organisme préleveur", _txt('e."Organisme préleveur"')),
        _dim("espece", "Espèce animale", _txt('e."Espèce animale"')),
        # Décision non renseignée (échantillons antérieurs à la tâche 14) = acceptée
        _dim("decision", "Décision de réception", "coalesce(nullif(btrim(e.decision_reception), ''), 'Accepté')",
             valeurs=["Accepté", "Accepté sous réserve", "Refusé"]),
        Dimension("analyse", "Analyse", {"analyses": _txt("r.analyse_effectuee"), "facturation": _txt("m.analyse")}),
        Dimension("conformite", "Conformité",
                  {"echantillons": "conf.conformite", "analyses": _conf_ligne("r")},
                  {"echantillons": {"conf"}, "analyses": set()},
                  valeurs=["Conforme", "Non conforme", NR]),
        _dim("retard", "En retard", f"CASE WHEN {RETARD} THEN 'Oui' ELSE 'Non' END", valeurs=["Oui", "Non"]),
        _dim("paiement", "Statut de paiement", "coalesce(nullif(btrim(e.\"Payement\"), ''), 'Non concerné')",
             valeurs=["Non concerné", "Non payé", "À payer", "Partiellement payé", "Payé", "Exonéré", "Avoir total"]),
        Dimension("mode_paiement", "Mode de paiement",
                  {"echantillons": _txt('e."Mode de paiement"'), "analyses": _txt('e."Mode de paiement"'),
                   "facturation": _txt("m.mode")}),
        Dimension("type_mouvement", "Type de mouvement", {"facturation": "m.type_mvt"}, valeurs=TYPES_MOUVEMENT),
        # Périodes : calculées sur la date de référence choisie ({DREF} remplacé à la construction)
        _dim("mois", "Mois", f"coalesce(to_char({{DREF}}, 'YYYY-MM'), '{NR}')", jeux=_TOUS),
        _dim("trimestre", "Trimestre", f"coalesce(to_char({{DREF}}, 'YYYY-\"T\"Q'), '{NR}')", jeux=_TOUS),
        _dim("annee", "Année", f"coalesce(to_char({{DREF}}, 'YYYY'), '{NR}')", jeux=_TOUS),
    ]
    return {x.cle: x for x in d}


DIMENSIONS = _dims()


@dataclass
class Mesure:
    cle: str
    libelle: str
    format: str                          # entier | decimal | pourcent | jours | montant
    sql: dict[str, str]                  # jeu → agrégat sur les colonnes de base
    colonnes: set
    description: str = ""


_TAUX = ("round(100.0 * count(*) FILTER (WHERE conformite = 'Non conforme') / "
         "nullif(count(*) FILTER (WHERE conformite IN ('Conforme', 'Non conforme')), 0), 1)")

MESURES = {m.cle: m for m in [
    Mesure("nb_echantillons", "Nombre d'échantillons", "entier",
           {"echantillons": "count(*)", "facturation": "count(DISTINCT num)", "analyses": "count(DISTINCT num)"},
           {"num"}, "Journal de facturation : échantillons des lignes facturées."),
    Mesure("nb_analyses", "Nombre d'analyses", "entier",
           {"echantillons": "coalesce(sum(nb_analyses), 0)::bigint", "facturation": "coalesce(sum(nb_analyses), 0)::bigint",
            "analyses": "count(*)"}, {"nb_analyses"},
           "Lignes de résultats saisies (journal de facturation : lignes facturées)."),
    Mesure("nb_prelevements", "Nombre de prélèvements", "entier",
           {"echantillons": "coalesce(sum(prelevements), 0)"},
           {"prelevements"}, "Nbre Prlvmts des sections visibles."),
    Mesure("nb_conformes", "Conformes", "entier",
           {j: "count(*) FILTER (WHERE conformite = 'Conforme')" for j in ("echantillons", "analyses")}, {"conformite"}),
    Mesure("nb_non_conformes", "Non conformes", "entier",
           {j: "count(*) FILTER (WHERE conformite = 'Non conforme')" for j in ("echantillons", "analyses")}, {"conformite"}),
    Mesure("taux_non_conformite", "Taux de non-conformité (%)", "pourcent", {j: _TAUX for j in ("echantillons", "analyses")}, {"conformite"},
           "Non conformes / (conformes + non conformes) ; les non renseignés sont exclus du calcul."),
    Mesure("nb_retard", "En retard", "entier",
           {"echantillons": "count(*) FILTER (WHERE retard)",
            "analyses": "count(DISTINCT num) FILTER (WHERE retard)"}, {"retard", "num"},
           "Échantillons en retard (délai de traitement de la section dépassé)."),
    Mesure("delai_moyen", "Délai moyen réception → rapport (j)", "jours",
           {j: "round(avg(delai)::numeric, 1)" for j in _ECH}, {"delai"},
           "Jours entre la réception et la 1re émission du rapport ; dossiers sans rapport exclus."),
    Mesure("delai_median", "Délai médian réception → rapport (j)", "jours",
           {j: "round((percentile_cont(0.5) WITHIN GROUP (ORDER BY delai))::numeric, 1)" for j in _ECH}, {"delai"}),
    Mesure("montant", "Montant facturé (DH)", "montant",
           {j: "coalesce(sum(montant), 0)" for j in JEUX}, {"montant"},
           "Journal de facturation : bulletins émis (HT + TVA). Échantillons et analyses : estimation par la "
           "grille de tarifs en vigueur (analyses sans tarif comptées à 0)."),
    Mesure("montant_avoirs", "Montant des avoirs (DH)", "montant",
           {"facturation": "coalesce(sum(avoir), 0)"}, {"avoir"}, "Avoirs émis, rattachés à leur bulletin d'origine."),
    Mesure("montant_exonere", "Montant exonéré (DH)", "montant",
           {"facturation": "coalesce(sum(exonere), 0)"}, {"exonere"},
           "Exonérations en vigueur de bulletins émis (reste dû au moment de l'exonération)."),
    Mesure("montant_paye", "Montant encaissé (DH)", "montant",
           {"facturation": "coalesce(sum(paye), 0)"}, {"paye"}, "Encaissements valides (annulés exclus)."),
    Mesure("reste_a_payer", "Reste à recouvrer (DH)", "montant",
           {"facturation": "coalesce(sum(montant), 0) - coalesce(sum(avoir), 0) - coalesce(sum(exonere), 0) "
                           "- coalesce(sum(paye), 0)"}, {"montant", "avoir", "exonere", "paye"},
           "Facturé − avoirs − exonérations − encaissé (négatif en cas de trop-perçu)."),
    Mesure("nb_bulletins", "Nombre de bulletins", "entier",
           {"facturation": "count(DISTINCT bulletin)"}, {"bulletin"}, "Bulletins émis concernés par les mouvements."),
]}

# Colonnes de la sous-requête `base` utilisées par les mesures : jeu → (expression, jointures)
COLONNES_BASE = {
    "num": {"echantillons": (NUM, set()), "facturation": ("m.num", set()), "analyses": ("r.num_echantillon", set())},
    "nb_analyses": {"echantillons": ("fact.nb_analyses", {"fact"}), "facturation": ("m.ligne", set())},
    "montant": {"echantillons": ("fact.montant", {"fact"}), "facturation": ("m.facture", set()),
                "analyses": ("ta.prix", {"tarif"})},
    "avoir": {"facturation": ("m.avoir", set())},
    "exonere": {"facturation": ("m.exonere", set())},
    "paye": {"facturation": ("m.encaisse", set())},
    "bulletin": {"facturation": ("m.bulletin", set())},
    "conformite": {"echantillons": ("conf.conformite", {"conf"}),
                   "analyses": (_conf_ligne("r"), set())},
    "retard": {j: (RETARD, set()) for j in ("echantillons", "analyses")},
    "delai": {j: (DELAI, {"rap"}) for j in _ECH},
    "prelevements": {j: ("{PRL}", set()) for j in _ECH},
}

# Colonnes de la liste détaillée (export « Détail », clic sur une ligne)
DETAIL = {
    "echantillons": ["num", "reception", "section", "statut", "type", "soustype", "nature", "fabricant",
                     "organisme", "decision", "conformite", "retard", "delai"],
    "facturation": ["bulletin_num", "date_mvt", "type_mouvement", "client", "section", "analyse", "mode_paiement",
                    "num", "montant_mvt"],
    "analyses": ["num", "reception", "section", "analyse", "date_analyse", "conformite", "nature", "fabricant",
                 "montant"],
}
LIBELLES_DETAIL = {"num": "N° échantillon", "reception": "Date de réception", "delai": "Délai (j)",
                   "nb_analyses": "Analyses", "montant": "Montant (DH)", "paye": "Payé (DH)",
                   "bulletin_num": "Bulletin", "date_mvt": "Date du mouvement", "montant_mvt": "Montant (DH)",
                   "date_analyse": "Date d'analyse"}
COLONNES_DETAIL_SUPP = {
    "reception": {j: (RECEPTION, set()) for j in ("echantillons", "analyses")},
    "bulletin_num": {"facturation": ("m.numero", set())},
    "date_mvt": {"facturation": ("m.date_mvt", set())},
    "montant_mvt": {"facturation": ("m.facture + m.avoir + m.exonere + m.encaisse", set())},
    "date_analyse": {"analyses": ("r.date_analyse", set())},
}


def catalogue() -> dict:
    """Catalogue sérialisable (libellés en français) pour construire l'interface."""
    return {
        "jeux": [{"cle": j.cle, "libelle": j.libelle, "description": j.description,
                  "dates": [{"cle": d, "libelle": DATES_REF[d][0]} for d in j.dates]} for j in JEUX.values()],
        "dimensions": [{"cle": d.cle, "libelle": d.libelle, "jeux": list(d.sql), "filtrable": d.filtrable,
                        "valeurs": d.valeurs} for d in DIMENSIONS.values()],
        "mesures": [{"cle": m.cle, "libelle": m.libelle, "format": m.format, "jeux": list(m.sql),
                     "description": m.description} for m in MESURES.values()],
        "periodes": [{"cle": k, "libelle": v} for k, v in PERIODES_RELATIVES.items()],
        "max_regroupements": 2,
        "limite_defaut": LIMITE_DEFAUT,
        "non_renseigne": NR,
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def periode_relative(cle: str, jour: date | None = None) -> tuple[date, date]:
    """Bornes incluses (du, au) d'une période relative."""
    jour = jour or date.today()
    debut_mois = jour.replace(day=1)
    if cle == "mois_en_cours":
        fin = (debut_mois + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return debut_mois, fin
    if cle == "mois_precedent":
        fin = debut_mois - timedelta(days=1)
        return fin.replace(day=1), fin
    if cle == "annee_en_cours":
        return date(jour.year, 1, 1), date(jour.year, 12, 31)
    if cle == "annee_precedente":
        return date(jour.year - 1, 1, 1), date(jour.year - 1, 12, 31)
    raise RequeteInvalide(f"Période relative inconnue : {cle}.")


def _date(v, nom: str) -> date | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise RequeteInvalide(f"Date invalide pour « {nom} » (format AAAA-MM-JJ).")


@dataclass
class Requete:
    jeu: str
    filtres: dict
    regroupements: list[str]
    mesures: list[str]
    tri: dict | None
    limite: int
    date_ref: str
    du: date | None
    au: date | None
    sections: list[str]                  # sections visibles après droits et filtre
    restreint: bool                      # True : limiter aux sections ci-dessus


def valider(definition: dict, role_section: str | None, jour: date | None = None) -> Requete:
    """Contrôle la définition contre le catalogue (RequeteInvalide → 400, SectionInterdite → 403)."""
    if not isinstance(definition, dict):
        raise RequeteInvalide("Définition de requête invalide.")
    inconnues = set(definition) - {"jeu", "filtres", "regroupements", "mesures", "tri", "limite"}
    if inconnues:
        raise RequeteInvalide(f"Clé(s) inconnue(s) : {', '.join(sorted(inconnues))}.")
    jeu = definition.get("jeu") or "echantillons"
    if jeu not in JEUX:
        raise RequeteInvalide(f"Jeu de données inconnu : {jeu}.")

    regs = definition.get("regroupements") or []
    if not isinstance(regs, list) or len(regs) > 2 or len(set(regs)) != len(regs):
        raise RequeteInvalide("Deux regroupements au plus, sans doublon.")
    for g in regs:
        if g not in DIMENSIONS or jeu not in DIMENSIONS[g].sql:
            raise RequeteInvalide(f"Regroupement inconnu pour ce jeu de données : {g}.")

    mesures = definition.get("mesures") or ["nb_echantillons"]
    if not isinstance(mesures, list) or not mesures:
        raise RequeteInvalide("Choisissez au moins une mesure.")
    for m in mesures:
        if m not in MESURES or jeu not in MESURES[m].sql:
            raise RequeteInvalide(f"Mesure inconnue pour ce jeu de données : {m}.")

    filtres = definition.get("filtres") or {}
    if not isinstance(filtres, dict):
        raise RequeteInvalide("Filtres invalides.")
    speciaux = {"du", "au", "periode", "date_ref"}
    for k, v in filtres.items():
        if k in speciaux:
            continue
        if k not in DIMENSIONS or jeu not in DIMENSIONS[k].sql or not DIMENSIONS[k].filtrable:
            raise RequeteInvalide(f"Filtre inconnu pour ce jeu de données : {k}.")
        if v in (None, [], ""):
            continue
        if not isinstance(v, list) or len(v) > 500 or not all(isinstance(x, str) and len(x) <= 300 for x in v):
            raise RequeteInvalide(f"Valeurs invalides pour le filtre « {DIMENSIONS[k].libelle} ».")
        fixes = DIMENSIONS[k].valeurs
        if fixes and k != "section" and any(x not in fixes for x in v):
            raise RequeteInvalide(f"Valeur inconnue pour le filtre « {DIMENSIONS[k].libelle} ».")

    date_ref = filtres.get("date_ref") or JEUX[jeu].dates[0]
    if date_ref not in JEUX[jeu].dates:
        raise RequeteInvalide(f"Date de référence inconnue pour ce jeu de données : {date_ref}.")
    if filtres.get("periode"):
        du, au = periode_relative(filtres["periode"], jour)
    else:
        du, au = _date(filtres.get("du"), "du"), _date(filtres.get("au"), "au")
    if du and au and au < du:
        raise RequeteInvalide("La date de fin précède la date de début.")

    # Sections : droits du rôle, puis filtre éventuel
    demandees = [s for s in (filtres.get("section") or [])]
    if any(s not in SECTIONS for s in demandees):
        raise RequeteInvalide("Section inconnue dans le filtre.")
    if role_section:
        if jeu == "facturation":
            raise SectionInterdite("La facturation est réservée à l'accueil, aux responsables et à l'admin.")
        if demandees and any(s != role_section for s in demandees):
            raise SectionInterdite("Section non autorisée pour votre rôle.")
        sections, restreint = [role_section], True
    elif demandees:
        sections, restreint = sorted(set(demandees), key=SECTIONS.index), True
    else:
        sections, restreint = list(SECTIONS), False

    tri = definition.get("tri")
    if tri:
        if not isinstance(tri, dict) or tri.get("cle") not in set(regs) | set(mesures) \
                or tri.get("ordre", "asc") not in ("asc", "desc"):
            raise RequeteInvalide("Tri invalide (un regroupement ou une mesure de la requête).")
    try:
        limite = int(definition.get("limite") or LIMITE_DEFAUT)
    except (TypeError, ValueError):
        raise RequeteInvalide("Limite invalide.")
    if not 1 <= limite <= LIMITE_MAX:
        raise RequeteInvalide(f"La limite doit être comprise entre 1 et {LIMITE_MAX}.")

    return Requete(jeu, filtres, regs, mesures, tri, limite, date_ref, du, au, sections, restreint)


def _sql_base(q: Requete, colonnes: dict[str, str], jointures: set, params: dict,
              valeurs: dict[str, str] | None = None) -> str:
    """Sous-requête `base` : colonnes demandées, jointures nécessaires, filtres."""
    dref_expr, dref_j = DATES_REF[q.date_ref][1], DATES_REF[q.date_ref][2]
    jointures = set(jointures)
    where = []

    if q.jeu == "analyses":
        frm = f'resultats_analyses r LEFT JOIN echantillons e ON {NUM} = r.num_echantillon'
        if q.restreint:
            where.append("r.section = ANY(CAST(:sections AS text[]))")
    elif q.jeu == "facturation":
        frm = MOUVEMENTS
        if q.restreint:
            where.append("m.section = ANY(CAST(:sections AS text[]))")
    else:
        frm = "echantillons e"
        if q.restreint:
            where.append("(" + " OR ".join(f"e.\"{s}\" = 'Yes'" for s in q.sections) + ")")

    params["sections"] = list(q.sections)

    if q.du or q.au:
        jointures |= dref_j
        if q.du:
            where.append(f"{dref_expr} >= :du")
            params["du"] = datetime.combine(q.du, datetime.min.time())
        if q.au:
            where.append(f"{dref_expr} < :au")
            params["au"] = datetime.combine(q.au + timedelta(days=1), datetime.min.time())

    def expr_dim(cle: str) -> str:
        d = DIMENSIONS[cle]
        jointures.update(d.jointures.get(q.jeu, set()))
        if cle in ("mois", "trimestre", "annee"):
            jointures.update(dref_j)
        return d.sql[q.jeu].replace("{DREF}", dref_expr)

    for i, (k, v) in enumerate(sorted(q.filtres.items())):
        if k in ("du", "au", "periode", "date_ref", "section") or v in (None, [], ""):
            continue
        params[f"f{i}"] = list(v)
        where.append(f"{expr_dim(k)} = ANY(CAST(:f{i} AS text[]))")
    for i, (k, v) in enumerate(sorted((valeurs or {}).items())):
        params[f"v{i}"] = v
        where.append(f"{expr_dim(k)} = :v{i}")

    prl = " + ".join(f"coalesce(e.\"Nbre Prlvmts {s}\", 0)" for s in q.sections)
    cols = []
    for alias, expr in colonnes.items():
        if expr.startswith("@dim:"):
            expr = expr_dim(expr[5:])
        cols.append(f"{expr.replace('{PRL}', prl)} AS {alias}")

    joins = "\n    ".join(JOINTURES[j] for j in ORDRE_JOINTURES if j in jointures)
    sql = f"SELECT {', '.join(cols)}\n  FROM {frm}\n    {joins}"
    if where:
        sql += "\n  WHERE " + "\n    AND ".join(where)
    return sql


def _params_retard(params: dict, sql: str, delais: dict[str, int], maintenant: datetime) -> None:
    for s in SECTIONS:
        if f":lim_{s}" in sql:
            params[f"lim_{s}"] = maintenant - timedelta(days=delais.get(s, 15))


def construire(q: Requete, delais: dict[str, int], maintenant: datetime | None = None) -> tuple[str, dict]:
    """SQL agrégé (GROUPING SETS) et paramètres."""
    maintenant = maintenant or datetime.now()
    params: dict = {}
    colonnes: dict[str, str] = {}
    jointures: set = set()
    for i, g in enumerate(q.regroupements, 1):
        colonnes[f"g{i}"] = f"@dim:{g}"
    for m in q.mesures:
        for c in MESURES[m].colonnes:
            if q.jeu not in COLONNES_BASE[c]:      # colonne inutile pour ce jeu (ex. count(*))
                continue
            expr, jt = COLONNES_BASE[c][q.jeu]
            colonnes[c] = expr
            jointures |= jt
    base = _sql_base(q, colonnes, jointures, params)
    aggs = ", ".join(f"{MESURES[m].sql[q.jeu]} AS {m}" for m in q.mesures)
    gs = [f"g{i}" for i in range(1, len(q.regroupements) + 1)]
    if not gs:
        sql = f"WITH base AS (\n  {base}\n)\nSELECT {aggs}\n  FROM base"
    else:
        ensembles = ["(g1, g2)", "(g1)", "(g2)", "()"] if len(gs) == 2 else ["(g1)", "()"]
        flags = ", ".join(f"GROUPING({g}) AS _t{g[1]}" for g in gs)
        sql = (f"WITH base AS (\n  {base}\n)\nSELECT {', '.join(gs)}, {flags}, {aggs}\n  FROM base\n"
               f" GROUP BY GROUPING SETS ({', '.join(ensembles)})")
    _params_retard(params, sql, delais, maintenant)
    return sql, params


def construire_detail(q: Requete, delais: dict[str, int], valeurs: dict[str, str] | None = None,
                      maintenant: datetime | None = None, decalage: int = 0,
                      compter: bool = False) -> tuple[str, dict, list[tuple[str, str]]]:
    """
    Lignes brutes (une par échantillon ou par analyse), filtrées, éventuellement sur une case du résultat.
    `decalage` : pagination serveur (OFFSET) ; `compter` : SQL du nombre total de lignes.
    """
    maintenant = maintenant or datetime.now()
    for k in valeurs or {}:
        if k not in DIMENSIONS or q.jeu not in DIMENSIONS[k].sql:
            raise RequeteInvalide(f"Regroupement inconnu : {k}.")
    params: dict = {}
    colonnes: dict[str, str] = {}
    jointures: set = set()
    entetes = []
    for c in DETAIL[q.jeu]:
        if c in DIMENSIONS:
            colonnes[c] = f"@dim:{c}"
            entetes.append((c, DIMENSIONS[c].libelle))
            continue
        expr, jt = (COLONNES_BASE.get(c) or COLONNES_DETAIL_SUPP[c])[q.jeu]
        if c == "delai":
            expr = f"round(({expr})::numeric, 1)"
        colonnes[c] = expr
        jointures |= jt
        entetes.append((c, LIBELLES_DETAIL.get(c, c)))
    base = _sql_base(q, colonnes, jointures, params, valeurs)
    if compter:
        sql = f"SELECT count(*) FROM (\n{base}\n) AS detail"
    else:
        sql = f"{base}\n ORDER BY 2 DESC NULLS LAST, 1\n LIMIT :limite OFFSET :decalage"
        params["limite"] = q.limite
        params["decalage"] = decalage
    _params_retard(params, sql, delais, maintenant)
    return sql, params, entetes


def construire_valeurs(q: Requete, dimension: str, delais: dict[str, int],
                       maintenant: datetime | None = None) -> tuple[str, dict]:
    """Valeurs distinctes d'une dimension (listes de choix des filtres), avec leur effectif."""
    if dimension not in DIMENSIONS or q.jeu not in DIMENSIONS[dimension].sql:
        raise RequeteInvalide(f"Regroupement inconnu : {dimension}.")
    params: dict = {}
    base = _sql_base(q, {"valeur": f"@dim:{dimension}"}, set(), params)
    sql = f"WITH base AS (\n  {base}\n)\nSELECT valeur, count(*) AS n FROM base GROUP BY valeur ORDER BY valeur LIMIT 2000"
    _params_retard(params, sql, delais, maintenant or datetime.now())
    return sql, params


# ---------------------------------------------------------------------------
# Mise en forme du résultat
# ---------------------------------------------------------------------------
def _val(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _cle_tri(v, dim: str | None = None):
    """Ordre du catalogue pour les critères à valeurs fixes (statut, décision…), sinon tri naturel ;
    « Non renseigné » et valeurs nulles en dernier."""
    if v is None or v == NR:
        return (2, 0, "")
    fixes = DIMENSIONS[dim].valeurs if dim in DIMENSIONS else None
    if fixes and v in fixes:
        return (0, fixes.index(v), "")
    if isinstance(v, (int, float)):
        return (0, v, "")
    return (1, 0, str(v).lower())


def mettre_en_forme(q: Requete, lignes: list[dict]) -> dict:
    n = len(q.regroupements)
    detail, sous1, sous2, total = [], [], [], {}
    for row in lignes:
        r = {k: _val(v) for k, v in row.items()}
        t1, t2 = r.pop("_t1", 0), r.pop("_t2", 0)
        if n == 0 or (t1 and (n == 1 or t2)):
            total = r
        elif n == 2 and t2:
            sous1.append(r)           # sous-total par 1er regroupement
        elif n == 2 and t1:
            sous2.append(r)           # sous-total par 2e regroupement
        else:
            detail.append(r)
    # g1 / g2 → clé du regroupement ; les regroupements « totalisés » n'apparaissent pas
    for liste, gardes in ((detail, (1, 2)), (sous1, (1,)), (sous2, (2,)), ([total], ())):
        for r in liste:
            for i, g in enumerate(q.regroupements, 1):
                v = r.pop(f"g{i}", None)
                if i in gardes:
                    r[g] = v

    if q.tri:
        cle, desc = q.tri["cle"], q.tri.get("ordre") == "desc"
        detail.sort(key=lambda r: _cle_tri(r.get(cle), cle), reverse=desc)
    else:
        detail.sort(key=lambda r: tuple(_cle_tri(r.get(g), g) for g in q.regroupements))
    for liste, g in ((sous1, q.regroupements[:1]), (sous2, q.regroupements[1:2])):
        liste.sort(key=lambda r: tuple(_cle_tri(r.get(x), x) for x in g))

    tronque = len(detail) > q.limite
    return {
        "jeu": q.jeu,
        "regroupements": [{"cle": g, "libelle": DIMENSIONS[g].libelle} for g in q.regroupements],
        "mesures": [{"cle": m, "libelle": MESURES[m].libelle, "format": MESURES[m].format} for m in q.mesures],
        "periode": {"du": q.du.isoformat() if q.du else None, "au": q.au.isoformat() if q.au else None,
                    "date_ref": q.date_ref, "libelle_date": DATES_REF[q.date_ref][0]},
        "sections": q.sections if q.restreint else [],
        "lignes": detail[:q.limite],
        "nb_lignes": len(detail),
        "tronque": tronque,
        "sous_totaux": {q.regroupements[0]: sous1, **({q.regroupements[1]: sous2} if n == 2 else {})} if n else {},
        "totaux": total,
    }
