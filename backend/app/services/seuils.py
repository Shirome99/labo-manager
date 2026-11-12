"""
Comparaison des resultats SMA (RP1-RP5) aux criteres microbiologiques m / M
de la categorie de l'echantillon (table ref_criteres_micro).

Les criteres et les resultats sont saisis en texte libre ; on interprete :
  criteres : "m=10(2) ufc/g", "M=10(3) ufc/g", "m=10 ufc/g", "absence/25 g", "1,5x10^3"
  resultats: "150", "<10", ">300", "1.5x10(3)", "2.10^3", "10²", "Abs", "Absence",
             "Présence", "Positif", "Indénombrable"...
Ce qui n'est pas interpretable est signale comme tel, sans erreur.

Classement d'une valeur (plan a 3 classes n / c / m / M) :
  ok        : valeur <= m
  marginal  : m < valeur <= M   (au plus c prelevements autorises)
  depasse   : valeur > M  (ou > m si M absent / egal a m ; presence si critere d'absence)
  illisible : valeur non interpretable
"""
from __future__ import annotations

import math
import re
import unicodedata

EXPOSANTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
MOTS_ABSENCE = ("abs", "absence", "absent", "nd", "non detecte", "neg", "negatif", "negative")
MOTS_PRESENCE = ("pres", "presence", "present", "pos", "positif", "positive", "detecte")
MOTS_INDENOMBRABLE = ("ind", "indenombrable", "innombrable", "tnpc")


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _nombre(s: str) -> float | None:
    """Extrait un nombre ecrit a la francaise, avec puissance de 10 eventuelle."""
    # 10² -> 10^2 (exposants Unicode)
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda x: "^" + x.group(0).translate(EXPOSANTS), s)
    s = s.replace(" ", "").replace(",", ".")
    # a x 10^b  /  a.10^b  /  a*10(b)  /  a×10b
    m = re.search(r"(\d+(?:\.\d+)?)[x×*.]10(?:\^|\(|e)?(-?\d+)\)?", s)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    # 10^b  /  10(b)  /  10b avec exposant
    m = re.search(r"(?<![\d.])10(?:\^|\()(-?\d+)\)?", s)
    if m:
        return 10.0 ** int(m.group(1))
    m = re.search(r"\d+(?:\.\d+)?(?:e-?\d+)?", s)
    return float(m.group(0)) if m else None


def lire_seuil(texte: str | None) -> dict | None:
    """'m=10(2) ufc/g' -> {'type': 'num', 'val': 100.0} ; 'absence/25 g' -> {'type': 'absence'}."""
    if not texte or not str(texte).strip():
        return None
    s = _sans_accents(str(texte)).lower().strip()
    if "absence" in s or s.startswith("abs"):
        return {"type": "absence"}
    s = re.sub(r"^\s*[mM]\s*=\s*", "", s)
    s = re.sub(r"(ufc|ucf|cfu|npp)\s*/.*$", "", s)  # unite
    v = _nombre(s)
    return {"type": "num", "val": v} if v is not None else None


def lire_valeur(texte: str | None) -> dict | None:
    """Resultat saisi -> {'type': 'num', 'val', 'op'} | {'type': 'absence'} | {'type': 'presence'}."""
    if texte is None or not str(texte).strip():
        return None
    s = _sans_accents(str(texte)).lower().strip().rstrip(".")
    mot = re.sub(r"[^a-z ]", "", s).strip()
    if mot in MOTS_ABSENCE or s.startswith("abs"):
        return {"type": "absence"}
    if mot in MOTS_INDENOMBRABLE:
        return {"type": "num", "val": math.inf, "op": None}
    if mot in MOTS_PRESENCE or s.startswith("pres"):
        return {"type": "presence"}
    op = None
    if s.startswith(("<", "inf")):
        op = "<"
    elif s.startswith((">", "sup")):
        op = ">"
    v = _nombre(s)
    if v is None:
        return None
    return {"type": "num", "val": v, "op": op}


def classer(valeur: dict | None, m: dict | None, grand_m: dict | None) -> str:
    if valeur is None or m is None:
        return "illisible"
    # Critere d'absence (Salmonella, Listeria... "absence/25 g")
    if m["type"] == "absence":
        if valeur["type"] == "absence":
            return "ok"
        if valeur["type"] == "presence":
            return "depasse"
        if valeur["op"] == "<" or valeur["val"] == 0:
            return "ok"
        return "depasse"
    # Critere chiffre
    if valeur["type"] == "absence":
        return "ok"
    if valeur["type"] == "presence":
        return "illisible"  # presence sans denombrement face a un seuil chiffre
    v = valeur["val"]
    if valeur["op"] == "<":
        v = math.nextafter(v, -math.inf)   # "<10" : strictement inferieur a 10
    elif valeur["op"] == ">":
        v = math.nextafter(v, math.inf)
    if v <= m["val"]:
        return "ok"
    if grand_m and grand_m["type"] == "num" and grand_m["val"] > m["val"]:
        return "marginal" if v <= grand_m["val"] else "depasse"
    return "depasse"


# ------------------------------------------------------------------
#  Rapprochement analyse <-> critere
# ------------------------------------------------------------------
ALIAS = {
    "ecoli": "escherichia coli",
    "e coli": "escherichia coli",
    "staph": "staphylocoque",
    "sasp": "staphylocoque coagulase positive",
    "fmat": "flore mesophile aerobie totale",
    "salmonelles": "salmonella",
    "listeria": "listeria monocytogenes",
}
MOTS_VIDES = {"de", "des", "du", "la", "le", "les", "a", "au", "aux", "et", "en", "recherche",
              "denombrement", "spp", "ufc", "g", "ml"}


def _jetons(s: str | None) -> set[str]:
    s = _sans_accents(s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = ALIAS.get(s, ALIAS.get(s.replace(" ", ""), s))
    out = set()
    for mot in s.split():
        if mot in MOTS_VIDES or len(mot) < 2:
            continue
        out.add(mot[:-1] if len(mot) > 4 and mot.endswith("s") else mot)  # pluriel
    return out


def trouver_critere(analyse: str | None, criteres: list[dict]) -> dict | None:
    """Critere dont le parametre ressemble le plus a l'analyse (recouvrement de mots)."""
    ja = _jetons(analyse)
    if not ja:
        return None
    meilleur, score_max = None, 0.0
    for c in criteres:
        jc = _jetons(c.get("parametre"))
        if not jc:
            continue
        commun = len(ja & jc)
        score = commun / min(len(ja), len(jc))
        if commun and score > score_max:
            meilleur, score_max = c, score
    return meilleur if score_max >= 0.5 else None


def _entier(s) -> int | None:
    m = re.search(r"\d+", str(s or ""))
    return int(m.group(0)) if m else None


def evaluer_lignes(lignes: list[dict], criteres: list[dict], nb_rp: int = 5) -> dict:
    """
    Evalue chaque ligne de resultats SMA.
    criteres : [{'id', 'parametre', 'n', 'c', 'm', 'M'}]
    Retourne {'lignes': [...], 'conclusion': 'Non conforme' | 'Conforme' | 'À vérifier' | None}
    """
    sortie = []
    for i, l in enumerate(lignes):
        crit = trouver_critere(l.get("analyse_effectuee"), criteres)
        rps, verdict = {}, None
        if crit:
            m, gm = lire_seuil(crit.get("m")), lire_seuil(crit.get("M"))
            for k in range(1, nb_rp + 1):
                brut = l.get(f"rp{k}")
                if brut is not None and str(brut).strip():
                    rps[f"rp{k}"] = classer(lire_valeur(brut), m, gm)
            if rps:
                c = _entier(crit.get("c")) or 0
                nb_marg = sum(v == "marginal" for v in rps.values())
                if "depasse" in rps.values() or nb_marg > c:
                    verdict = "Non conforme"
                elif "illisible" in rps.values():
                    verdict = "À vérifier"
                else:
                    verdict = "Conforme"
        sortie.append({
            "index": i,
            "critere": ({k: crit.get(k) for k in ("id", "parametre", "n", "c", "m", "M")}
                        if crit else None),
            "rps": rps,
            "verdict": verdict,
        })
    verdicts = [l["verdict"] for l in sortie if l["verdict"]]
    if "Non conforme" in verdicts:
        conclusion = "Non conforme"
    elif "À vérifier" in verdicts:
        conclusion = "À vérifier"
    elif verdicts:
        conclusion = "Conforme"
    else:
        conclusion = None
    return {"lignes": sortie, "conclusion": conclusion}
