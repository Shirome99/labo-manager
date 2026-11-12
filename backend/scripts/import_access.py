"""
Reprise des donnees Access (dump SQL Server) dans la base `labo`.

Usage (depuis backend/, venv active) :
    python scripts/import_access.py "../BD Réception des échantillons 2010-2.sql" --dry-run
    python scripts/import_access.py "../BD Réception des échantillons 2010-2.sql"

Principes :
  - les numeros d'origine (0001, 0723bis...) sont conserves tels quels ;
  - idempotent : un echantillon deja present en base (meme N°) est ignore,
    ainsi que ses fiches et resultats -> relancable sans doublons ;
  - un rapport d'anomalies CSV est toujours produit (ligne, table, cle, raison) ;
  - --dry-run : tout est analyse, rien n'est ecrit en base.

Tables lues : Inf et trt de l'éch (echantillons), Table TTt Echantillon MA / CHA,
Table Ttt Echantillon SA (traitements), Table Résultats ... MA / CHA / SA (resultats).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pour `import app`


# ------------------------------------------------------------------
#  Lecture du dump : INSERT INTO [table] ([col], ...) VALUES (...)
# ------------------------------------------------------------------
RE_INSERT = re.compile(r"^INSERT INTO \[(?P<table>[^\]]+)\] \((?P<cols>.*?)\) VALUES \((?P<vals>.*)\)\s*$")
RE_COL = re.compile(r"\[([^\]]+)\]")


def _valeurs(s: str) -> list:
    """Decoupe la liste VALUES d'un INSERT T-SQL : N'..', '..', NULL, nombres."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " ,":
            i += 1
            continue
        if c == "N" and i + 1 < n and s[i + 1] == "'":
            i += 1
            c = "'"
        if c == "'":
            i += 1
            buf = []
            while i < n:
                if s[i] == "'":
                    if i + 1 < n and s[i + 1] == "'":  # '' = apostrophe echappee
                        buf.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(s[i])
                i += 1
            out.append("".join(buf))
            continue
        j = i
        while j < n and s[j] != ",":
            j += 1
        tok = s[i:j].strip()
        if tok.upper() == "NULL":
            out.append(None)
        else:
            try:
                out.append(int(tok))
            except ValueError:
                try:
                    out.append(float(tok))
                except ValueError:
                    out.append(tok)
        i = j
    return out


def lire_dump(chemin: Path) -> dict[str, list[tuple[int, dict]]]:
    """{table: [(n° de ligne dans le dump, {colonne: valeur})]}"""
    tables: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    with open(chemin, encoding="utf-8-sig") as fh:
        for num_ligne, ligne in enumerate(fh, 1):
            if not ligne.startswith("INSERT INTO"):
                continue
            m = RE_INSERT.match(ligne.rstrip("\r\n"))
            if not m:
                continue
            cols = RE_COL.findall(m.group("cols"))
            vals = _valeurs(m.group("vals"))
            if len(cols) != len(vals):
                tables["__illisible__"].append((num_ligne, {"table": m.group("table")}))
                continue
            tables[m.group("table")].append((num_ligne, dict(zip(cols, vals))))
    return tables


# ------------------------------------------------------------------
#  Normalisation
# ------------------------------------------------------------------
T_ECH = "Inf et trt de l'éch"
DATE_MIN = date(1990, 1, 1)
STATUT_IMPORT = "Rapport émis"   # dossiers historiques : consideres comme clos
SAISI_PAR = "import_access"


class Rapport:
    """Anomalies : une ligne par probleme (ligne du dump, table, cle, raison, action)."""

    def __init__(self):
        self.lignes: list[dict] = []

    def add(self, ligne, table, cle, raison, action):
        self.lignes.append({"ligne": ligne, "table": table, "cle": cle or "",
                            "raison": raison, "action": action})

    def ecrire(self, chemin: Path):
        with open(chemin, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["ligne", "table", "cle", "raison", "action"],
                               delimiter=";")
            w.writeheader()
            w.writerows(self.lignes)


def _texte(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _date(v, rapport: Rapport, ligne, table, cle, champ, jour=False):
    """Date Access -> datetime (ou date) ; illisible ou hors plage -> None + anomalie."""
    v = _texte(v)
    if v is None:
        return None
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        d = None
    if d is None or not (DATE_MIN <= d.date() <= date.today()):
        rapport.add(ligne, table, cle, f"date invalide ({champ} = {v})", "importé, date laissée vide")
        return None
    return d.date() if jour else d


def _oui(v) -> tuple[bool | None, bool]:
    """
    Valeur de section Access -> (oui/non, corrigee ?).
    OUI / 0UI / 0ui -> oui ; NON / 0 / vide -> non (valeurs normales d'Access).
    Fautes de frappe evidentes (OUI0, 0OUI, NO N, N, O-) -> corrigees et signalees.
    Autre -> (None, False) : illisible.
    """
    brut = (_texte(v) or "NON").upper().replace("0", "O")
    if brut in ("OUI", "YES"):
        return True, False
    if brut in ("NON", "NO", "O"):
        return False, False
    lettres = re.sub(r"[^A-Z]", "", brut)
    if lettres in ("OOUI", "OUIO"):
        return True, True
    if lettres in ("NON", "NO", "N", "O"):
        return False, True
    return None, False


def _int(v):
    try:
        return None if v in (None, "") else int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
#  Correspondance des colonnes Access -> PostgreSQL
# ------------------------------------------------------------------
# echantillons : memes noms de colonnes que Access
COLS_ECH_TEXTE = [
    "Nature de l'échantillon", "Catégorie de l'échantillon", "Espèce animale", "N° de lot",
    "Fabricant ou Propriétaire", "Organisme préleveur", "Réf Fiche de prélèvement", "Payement",
    "Nb Para MA", "MONTANT TOTAL MA", "Nb Para CH", "MONTANT TOTAL CH", "Nb Para SA",
    "MONTANT TOTAL SA", "TOTAL", "N° QUITTANCE", "DATE",
]
COLS_ECH_INT = ["Type d'échantillon", "S/type d'échantillon",
                "Nbre Prlvmts SMA", "Nbre Prlvmts SCHA", "Nbre Prlvmts SSA"]
COLS_ECH_DATE = [  # (colonne Access, colonne PostgreSQL)
    ("Date reception", "Date reception"),
    ("Date dépôt BA Bactériologie", "Date dépôt BA Bactériologie"),
    ("Date dépôt  BA Chimie", "Date dépôt BA Chimie"),   # double espace dans Access
    ("Date dépot BA SA", "Date dépot BA SA"),
    ("Date 1 Remise Rapport", "Date 1 Remise Rapport"),
    ("Date 2 Remise Rapport", "Date 2 Remise Rapport"),
    ("Date de payement", "Date de payement"),
    ("Sortie MA", "Sortie MA"), ("Sortie CH", "Sortie CH"), ("Sortie Dc", "Sortie Dc"),
]

# Traitements : table Access -> (section, table PG, {col PG: (col Access, type)})
TRAITEMENTS = {
    "Table TTt Echantillon MA": ("SMA", "traitement_sma", {
        "nbre_prelevements": ("Nbre de prlvmts", "int"),
        "date_reception_ma": ("Date de réception MA", "date"),
        "date_revue_demande": ("Date rev demande", "date"),
        "analyse_prevue_le": ("Analyse prévue le", "date"),
        "lieu_stockage": ("Lieu de stockage", "txt"),
        "date_mise_en_analyse": ("Date de mise en analyse", "date"),
        "date_sortie_resultats": ("Date de Sortie des Résultats", "date"),
        "date_rapport_essai": ("Date du Rapport d'essai", "date"),
        "conformite": ("Conformité", "txt"),
        "conclusion": ("Conclusion", "txt"),
        "commentaire_1": ("Commentaire 1", "txt"),
        "commentaire_2": ("Commentaire 2", "txt"),
        # pas de colonne « responsable d'analyse » en base : conservé dans observations
        "observations": ("Resp Analyse", "resp"),
    }),
    "Table TTt Echantillon CHA": ("SCHA", "traitement_scha", {
        "nbre_prelevements": ("Nbre Prlvmts", "int"),
        "date_reception_cha": ("Date Reception CHA", "date"),
        "lieu_stockage": ("Lieu de Stockage", "txt"),
        "date_revue_demande": ("Date Revue Demande", "date"),
        "date_mise_en_analyse": ("Date de mise en analyse", "date"),
        "date_sortie_resultats": ("Date de sorie des résultats", "date"),
        "date_re_cha": ("Date RE ACH", "date"),
        "conformite": ("Conformité ACH", "txt"),
    }),
    "Table Ttt Echantillon SA": ("SSA", "traitement_ssa", {
        "nbre_prelevements": ("Nbre prlvmts", "int"),
        "espece_animale": ("Espèce animale", "txt"),
        "date_reception_sa": ("Date de Reception SA", "date"),
        "date_revue_demande": ("Date Revue Demande", "date"),
        "lieu_stockage": ("Lieu de Stockage", "txt"),
        "type_analyses": ("Type d'Analyses", "txt"),
        "suspicion_clinique": ("Suspicion clinique", "txt"),
        "date_mise_en_analyse": ("Date de mise en analyse", "date"),
        "date_sortie_resultats": ("Date de sortie des résultats", "date"),
        "date_remise_re_sa": ("Date Remise RE", "date"),
        "interpretation_resultats": ("Interprétation des résultats", "txt"),
    }),
}


def _rp(n):
    return {f"rp{i}": (f"RP {i}", "txt") for i in range(1, n + 1)}


# Resultats : table Access -> (table de traitement parente, section, {col PG: (col Access, type)})
RESULTATS = {
    "Table Résultats de l'analyse MA": ("Table TTt Echantillon MA", "SMA", {
        "analyse_effectuee": ("Analyse effectuée", "txt"),
        "reference_methode": ("Référence de la méthode", "methode_ma"),
        "date_analyse": ("Date d'analyse", "date"),
        "date_sortie": ("Date de sortie des résultats", "date"),
        **_rp(5),
    }),
    "Table Résultats Analyses CHA": ("Table TTt Echantillon CHA", "SCHA", {
        "nbre_prelevements": ("Nbre prélèvements", "int"),
        "analyse_effectuee": ("Analyse effectuée SCHA", "txt"),
        "reference_methode": ("Réf  Méthode", "txt"),
        "responsable_analyse": ("Responsable d'analyse", "txt"),
        "date_analyse": ("Date d'analyse", "date"),
        "date_sortie": ("Date de sortie des résultats", "date"),
        **_rp(9),
        "moyenne": ("Moyenne", "txt"),
        "conclusion": ("Conclusion", "txt"),
    }),
    "Table Résultats d'analyses SA": ("Table Ttt Echantillon SA", "SSA", {
        "analyse_effectuee": ("Analyses effectuées", "txt"),
        "reference_methode": ("Référence Méthode", "txt"),
        "nbre_prelevements": ("Nbre Prlvs Analysés", "int"),
        "responsable_analyse": ("Analyste resp", "txt"),
        "date_analyse": ("Date Analyse", "date"),
        "date_sortie": ("Date de sortie des résultats", "date"),
        "resultat_analyse": ("Résultat Analyse", "txt"),
        "criteres_interpretation": ("Critères d'acceptabilité/interprétation", "txt"),
        "nbre_positifs": ("Nbre positifs", "int"),
        "nbre_negatif": ("Nbre négatif", "int"),
        "nbre_douteux": ("Nbre douteux", "int"),
    }),
}


def _convertir(row, mapping, rapport, ligne, table, cle, methodes_ma=None):
    out = {}
    for col_pg, (col_acc, typ) in mapping.items():
        v = row.get(col_acc)
        if typ == "int":
            out[col_pg] = _int(v)
        elif typ == "date":
            out[col_pg] = _date(v, rapport, ligne, table, cle, col_acc, jour=True)
        elif typ == "resp":
            out[col_pg] = f"Resp. analyse : {_texte(v)}" if _texte(v) else None
        elif typ == "methode_ma":  # id -> reference (Table Méthodes MA)
            out[col_pg] = (methodes_ma or {}).get(v) or _texte(v)
        else:
            out[col_pg] = _texte(v)
    return out


# ------------------------------------------------------------------
#  Preparation (aucune ecriture) : construit les lignes a inserer
# ------------------------------------------------------------------
def preparer(tables, existants: set[str], hors_regle: str, rapport: Rapport):
    """
    Retourne (echantillons, traitements, resultats) a inserer.
    `existants`  : N° deja en base -> ignores, avec leurs fiches (idempotence).
    `hors_regle` : 'importer' ou 'ignorer' les echantillons a 0 ou plusieurs sections.
    """
    for ligne, info in tables.get("__illisible__", []):
        rapport.add(ligne, info["table"], "", "ligne illisible (colonnes/valeurs)", "ignoré")

    echantillons: dict[str, dict] = {}
    deja_en_base: set[str] = set()
    for ligne, r in tables.get(T_ECH, []):
        num = _texte(r.get("N° Echantillon"))  # numero d'origine conserve tel quel
        if not num:
            rapport.add(ligne, T_ECH, "", "champ obligatoire manquant (N° Echantillon)", "ignoré")
            continue
        if num in echantillons:
            rapport.add(ligne, T_ECH, num, "doublon dans le dump", "ignoré")
            continue
        if num in existants:
            deja_en_base.add(num)
            rapport.add(ligne, T_ECH, num, "doublon (déjà présent en base)", "ignoré")
            continue

        sections = {}
        for s in ("SMA", "SCHA", "SSA"):
            o, corrigee = _oui(r.get(s))
            if corrigee:
                rapport.add(ligne, T_ECH, num, f"valeur de section corrigée ({s} = {r.get(s)} -> "
                            f"{'OUI' if o else 'NON'})", "importé")
            if o is None:
                rapport.add(ligne, T_ECH, num, f"valeur de section illisible ({s} = {r.get(s)})",
                            "considérée comme NON")
                o = False
            sections[s] = "Yes" if o else "No"
        actives = [s for s, v in sections.items() if v == "Yes"]
        if len(actives) != 1:
            raison = "aucune section" if not actives else f"section multiple ({', '.join(actives)})"
            if hors_regle == "ignorer":
                rapport.add(ligne, T_ECH, num, raison, "ignoré")
                continue
            rapport.add(ligne, T_ECH, num, raison, "importé tel quel (historique)")

        data = {"N° Echantillon": num, "statut": STATUT_IMPORT, **sections}
        for c in COLS_ECH_TEXTE:
            data[c] = _texte(r.get(c))
        for c in COLS_ECH_INT:
            data[c] = _int(r.get(c))
        for c_acc, c_pg in COLS_ECH_DATE:
            data[c_pg] = _date(r.get(c_acc), rapport, ligne, T_ECH, num, c_acc)
        if not data["Nature de l'échantillon"]:
            rapport.add(ligne, T_ECH, num, "champ obligatoire manquant (Nature de l'échantillon)", "importé")
        if not _texte(r.get("Date reception")):
            rapport.add(ligne, T_ECH, num, "champ obligatoire manquant (Date reception)", "importé")
        echantillons[num] = data

    # ---- Traitements : une fiche par echantillon et par section ----
    traitements: dict[str, list[dict]] = {}
    fiche_vers_num: dict[str, dict[int, str]] = {}  # table Access -> {N° fiche: N° echantillon}
    for t_acc, (section, t_pg, mapping) in TRAITEMENTS.items():
        traitements[t_pg] = []
        fiche_vers_num[t_acc] = {}
        vus: set[str] = set()
        for ligne, r in tables.get(t_acc, []):
            num = _texte(r.get("N° Echantillon"))
            if num and r.get("N°") is not None:
                fiche_vers_num[t_acc][r["N°"]] = num
            if not num:
                rapport.add(ligne, t_acc, f"fiche {r.get('N°')}",
                            "champ obligatoire manquant (N° Echantillon)", "ignoré")
                continue
            if num in deja_en_base:
                continue  # echantillon deja en base : sa fiche aussi
            if num not in echantillons:
                rapport.add(ligne, t_acc, num, "échantillon inconnu ou ignoré", "ignoré")
                continue
            if num in vus:
                rapport.add(ligne, t_acc, num, "doublon dans le dump (2e fiche pour cet échantillon)",
                            "ignoré")
                continue
            vus.add(num)
            if echantillons[num][section] != "Yes":
                rapport.add(ligne, t_acc, num, f"fiche {section} sur un échantillon non routé vers {section}",
                            "importé")
            data = _convertir(r, mapping, rapport, ligne, t_acc, num)
            data.update(num_echantillon=num, num_ordre=_int(r.get("N°")), saisi_par=SAISI_PAR)
            traitements[t_pg].append(data)

    # ---- Resultats : rattaches par le N° de la fiche de traitement ----
    methodes_ma = {r.get("N° d'ordre"): _texte(r.get("Référence de la méthode")) or _texte(r.get("Méthode"))
                   for _, r in tables.get("Table Méthodes MA", [])}
    resultats: list[dict] = []
    for t_acc, (t_trt, section, mapping) in RESULTATS.items():
        for ligne, r in tables.get(t_acc, []):
            num = _texte(r.get("N° Echantillon")) or fiche_vers_num[t_trt].get(r.get("N°"))
            if not num:
                rapport.add(ligne, t_acc, f"fiche {r.get('N°')}",
                            "fiche de traitement introuvable (N° manquant ou inconnu)", "ignoré")
                continue
            if num in deja_en_base:
                continue
            if num not in echantillons:
                rapport.add(ligne, t_acc, num, "échantillon inconnu ou ignoré", "ignoré")
                continue
            data = _convertir(r, mapping, rapport, ligne, t_acc, num, methodes_ma)
            data.update(num_echantillon=num, section=section, saisi_par=SAISI_PAR)
            resultats.append(data)

    return echantillons, traitements, resultats


# ------------------------------------------------------------------
#  Base de donnees (SQL brut parametre)
# ------------------------------------------------------------------
async def _inserer(conn, table: str, row: dict):
    """INSERT parametre. Les noms de colonnes viennent des tables de correspondance
    ci-dessus (jamais du dump) ; les valeurs passent toujours en parametres."""
    from sqlalchemy import text
    cols = list(row)
    noms = ", ".join('"' + c.replace('"', '""') + '"' for c in cols)
    params = ", ".join(f":p{i}" for i in range(len(cols)))
    await conn.execute(text(f"INSERT INTO {table} ({noms}) VALUES ({params})"),
                       {f"p{i}": row[c] for i, c in enumerate(cols)})


async def numeros_existants(conn) -> set[str]:
    from sqlalchemy import text
    r = await conn.execute(text('SELECT "N° Echantillon" FROM echantillons'))
    return {x[0] for x in r}


async def ecrire(conn, echantillons, traitements, resultats, source: str):
    from sqlalchemy import text
    for row in echantillons.values():
        await _inserer(conn, "echantillons", row)
    for t_pg, rows in traitements.items():
        for row in rows:
            # garde-fou d'idempotence : pas de 2e fiche pour un meme echantillon
            r = await conn.execute(text(f"SELECT 1 FROM {t_pg} WHERE num_echantillon = :n"),
                                   {"n": row["num_echantillon"]})
            if r.first() is None:
                await _inserer(conn, t_pg, row)
    for row in resultats:
        await _inserer(conn, "resultats_analyses", row)
    nb_fiches = sum(len(v) for v in traitements.values())
    await _inserer(conn, "audit_log", {
        "utilisateur": SAISI_PAR, "action": "IMPORT", "table_cible": "echantillons", "cle": "access",
        "details": f"{source} : {len(echantillons)} échantillons, {nb_fiches} fiches, "
                   f"{len(resultats)} résultats"})


# ------------------------------------------------------------------
#  Programme principal
# ------------------------------------------------------------------
async def main():
    ap = argparse.ArgumentParser(description="Reprise des données Access dans la base labo.")
    ap.add_argument("dump", type=Path, help="dump SQL Server de la base Access (.sql)")
    ap.add_argument("--dry-run", action="store_true", help="analyse seulement, n'écrit rien en base")
    ap.add_argument("--rapport", type=Path, default=None,
                    help="fichier CSV des anomalies (défaut : rapport_import_access_<horodatage>.csv)")
    ap.add_argument("--sections-hors-regle", choices=["importer", "ignorer"], default="importer",
                    help="échantillons à 0 ou plusieurs sections (défaut : importer tels quels)")
    args = ap.parse_args()

    if not args.dump.exists():
        sys.exit(f"Fichier introuvable : {args.dump}")
    rapport_csv = args.rapport or Path(f"rapport_import_access_{datetime.now():%Y%m%d_%H%M%S}.csv")

    from app.core.db import engine

    tables = lire_dump(args.dump)
    rapport = Rapport()
    async with engine.connect() as conn:
        existants = await numeros_existants(conn)
        ech, trt, res = preparer(tables, existants, args.sections_hors_regle, rapport)

        print(f"Dump : {args.dump.name}")
        print(f"  lignes lues          : {len(tables.get(T_ECH, []))} échantillons, "
              + ", ".join(f"{len(tables.get(t, []))} {t}" for t in (*TRAITEMENTS, *RESULTATS)))
        print(f"  à importer           : {len(ech)} échantillons, "
              + ", ".join(f"{len(v)} {k}" for k, v in trt.items()) + f", {len(res)} résultats")
        print(f"  déjà en base (ignorés): {sum(1 for l in rapport.lignes if l['raison'].startswith('doublon (déjà'))}")
        print("  anomalies par raison :")
        par_raison = Counter(re.sub(r" \(.*", "", l["raison"]) + " → " + l["action"] for l in rapport.lignes)
        for raison, n in par_raison.most_common():
            print(f"    {n:5d}  {raison}")

        if args.dry_run:
            print("\nDRY-RUN : aucune écriture en base.")
        else:
            # meme transaction que la lecture des N° existants (ouverte implicitement) :
            # tout ou rien
            try:
                await ecrire(conn, ech, trt, res, args.dump.name)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
            print("\nImport terminé (transaction validée).")
    await engine.dispose()

    rapport.ecrire(rapport_csv)
    print(f"Rapport d'anomalies : {rapport_csv.resolve()} ({len(rapport.lignes)} lignes)")


if __name__ == "__main__":
    asyncio.run(main())
