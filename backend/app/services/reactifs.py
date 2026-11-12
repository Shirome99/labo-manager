"""
Réactifs et milieux de culture (tâche 20) : état d'un lot, lots d'une fiche de traitement,
traçabilité « quel lot pour quel échantillon ».

Règles :
- état d'un lot : « inactif », « périmé » (péremption < aujourd'hui), « épuisé » (stock nul),
  « péremption proche » (dans les 30 jours), « seuil bas » (stock ≤ seuil), sinon « ok » ;
- la fiche désigne ses lots par leur code dans `lot_reactif` (codes séparés par des virgules) ;
  un lot nouvellement choisi doit exister, être actif, appartenir à la section (ou être commun)
  et **ne pas être périmé à la date de l'analyse** (mise en analyse, sinon 1re date d'analyse,
  sinon aujourd'hui), sinon 400. Les lots déjà présents sur la fiche ne sont pas re-contrôlés.
"""
from datetime import date, timedelta

from sqlalchemy import text

ALERTE_JOURS = 30
COLONNES = """id, code, produit, categorie, numero_lot, fournisseur, section, date_reception, date_ouverture,
              date_peremption, quantite_initiale, quantite, unite, seuil_alerte, emplacement, actif,
              observations, cree_par, cree_le"""


def etat(lot: dict, jour: date | None = None) -> str:
    jour = jour or date.today()
    if not lot.get("actif", True):
        return "inactif"
    if lot["date_peremption"] < jour:
        return "périmé"
    if lot["quantite"] is not None and float(lot["quantite"]) <= 0:
        return "épuisé"
    if lot["date_peremption"] <= jour + timedelta(days=ALERTE_JOURS):
        return "péremption proche"
    if lot.get("seuil_alerte") is not None and float(lot["quantite"]) <= float(lot["seuil_alerte"]):
        return "seuil bas"
    return "ok"


def avec_etat(x) -> dict:
    d = dict(x)
    for k in ("quantite_initiale", "quantite", "seuil_alerte"):
        if d.get(k) is not None:
            d[k] = float(d[k])
    d["etat"] = etat(d)
    if d.get("cree_le"):
        d["cree_le"] = d["cree_le"].isoformat()
    return d


def codes(texte: str | None) -> list[str]:
    """« L2026-0001, L2026-0002 » → ['L2026-0001', 'L2026-0002'] (sans doublon, ordre conservé)."""
    vus = []
    for c in (texte or "").replace(";", ",").split(","):
        c = c.strip()
        if c and c not in vus:
            vus.append(c)
    return vus


async def lots_par_codes(db, liste: list[str]) -> dict[str, dict]:
    if not liste:
        return {}
    r = await db.execute(text(f"SELECT {COLONNES} FROM reactifs_lots WHERE code = ANY(CAST(:c AS text[]))"),
                         {"c": liste})
    return {x["code"]: avec_etat(x) for x in r.mappings().all()}


async def refus_lots(db, section: str, nouveaux: list[str], jour: date) -> list[str]:
    """Raisons de refus des lots nouvellement choisis sur une fiche (liste vide si tout va bien)."""
    lots = await lots_par_codes(db, nouveaux)
    refus = []
    for c in nouveaux:
        lot = lots.get(c)
        if not lot:
            refus.append(f"« {c} » : lot inconnu")
        elif not lot["actif"]:
            refus.append(f"« {c} » : lot inactif")
        elif lot["section"] not in (None, section):
            refus.append(f"« {c} » : lot de la section {lot['section']}")
        elif lot["date_peremption"] < jour:
            refus.append(f"« {c} » ({lot['produit']}, lot {lot['numero_lot']}) : périmé le "
                         f"{lot['date_peremption']:%d/%m/%Y} (analyse du {jour:%d/%m/%Y})")
    return refus


async def tracabilite(db, num: str, sections: list[str]) -> list[dict]:
    """Lots utilisés par les fiches de traitement d'un échantillon (sections visibles)."""
    out = []
    for s, table in (("SMA", "traitement_sma"), ("SCHA", "traitement_scha"), ("SSA", "traitement_ssa")):
        if s not in sections:
            continue
        r = (await db.execute(text(f"SELECT lot_reactif, date_mise_en_analyse FROM {table} WHERE num_echantillon = :n"),
                              {"n": num})).first()
        if not r or not r[0]:
            continue
        liste = codes(r[0])
        lots = await lots_par_codes(db, liste)
        for c in liste:
            lot = lots.get(c)
            out.append({"section": s, "code": c, "connu": lot is not None, **({
                "produit": lot["produit"], "categorie": lot["categorie"], "numero_lot": lot["numero_lot"],
                "fournisseur": lot["fournisseur"], "date_peremption": lot["date_peremption"].isoformat(),
                "id": lot["id"]} if lot else {})})
    return out


async def utilisations(db, code: str) -> list[dict]:
    """Échantillons dont une fiche cite ce lot (traçabilité inverse)."""
    out = []
    for s, table in (("SMA", "traitement_sma"), ("SCHA", "traitement_scha"), ("SSA", "traitement_ssa")):
        r = await db.execute(text(f"""
            SELECT t.num_echantillon, t.date_mise_en_analyse, e.statut, e."Nature de l'échantillon" AS nature
            FROM {table} t LEFT JOIN echantillons e ON e."N° Echantillon" = t.num_echantillon
            WHERE :c = ANY(string_to_array(replace(replace(coalesce(t.lot_reactif, ''), ' ', ''), ';', ','), ','))
            ORDER BY t.num_echantillon"""), {"c": code})
        out += [{"section": s, **dict(x)} for x in r.mappings().all()]
    return out
