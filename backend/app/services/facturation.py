"""
Facturation (bloc P) : grille tarifaire datée, réglages, montants.

Règles :
  * le prix d'une analyse à une date = la période de ref_tarifs_prix qui couvre cette date,
    pour un tarif actif de même nom (sans casse ni espaces de bord) et de même section ;
  * modifier un prix ferme la période en cours (veille de la date d'effet) et en ouvre
    une nouvelle : l'historique n'est jamais écrasé ;
  * montants en Decimal, arrondis au centime (ROUND_HALF_UP), jamais en flottant.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import text

CENTIME = Decimal("0.01")
NBSP = "\u00a0"  # espace insécable

# Étape à laquelle le paiement peut être exigé (réglage facturation.etape_paiement)
ETAPES_PAIEMENT = {
    "aucune": "Aucune (avertissement seulement)",
    "mise_en_analyse": "Avant la mise en analyse",
    "remise_rapport": "Avant la remise du rapport",
}

# Réglages : clé -> (valeur par défaut, type)
PARAMETRES = {
    "facturation.taux_tva": ("0", Decimal),
    "facturation.etape_paiement": ("aucune", str),
    "facturation.seuil_impayes_jours": ("30", int),
}


def arrondi(v) -> Decimal:
    return Decimal(str(v if v is not None else 0)).quantize(CENTIME, rounding=ROUND_HALF_UP)


def format_dh(v) -> str:
    """1250.5 -> « 1 250,50 DH » (espace insécable entre les milliers)."""
    m = arrondi(v)
    signe = "-" if m < 0 else ""
    entier, dec = f"{abs(m):.2f}".split(".")
    groupes = []
    while entier:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    return f"{signe}{NBSP.join(groupes)},{dec}{NBSP}DH"


# ------------------------------------------------------------------
#  Réglages
# ------------------------------------------------------------------
async def lire_parametres(db) -> dict:
    r = await db.execute(text("SELECT cle, valeur FROM parametres WHERE cle LIKE 'facturation.%'"))
    brut = {x.cle: x.valeur for x in r}
    out = {}
    for cle, (defaut, typ) in PARAMETRES.items():
        v = brut.get(cle, defaut)
        try:
            out[cle.split(".", 1)[1]] = typ(v)
        except Exception:  # valeur illisible en base : défaut
            out[cle.split(".", 1)[1]] = typ(defaut)
    return out


async def ecrire_parametre(db, cle: str, valeur, utilisateur: str):
    await db.execute(text(
        "INSERT INTO parametres (cle, valeur, modifie_par, modifie_le) VALUES (:c, :v, :u, now()) "
        "ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur, modifie_par = EXCLUDED.modifie_par, "
        "modifie_le = now()"), {"c": cle, "v": str(valeur), "u": utilisateur})


# ------------------------------------------------------------------
#  Grille tarifaire
# ------------------------------------------------------------------
_SQL_GRILLE = """
    SELECT t.id AS tarif_id, t.nom_analyse, t.section, t.par_prelevement, t.a_valider, t.actif,
           t.analyse_id, p.prix, p.date_debut, p.date_fin
    FROM ref_tarifs t
    LEFT JOIN ref_tarifs_prix p
           ON p.tarif_id = t.id AND p.date_debut <= :d AND (p.date_fin IS NULL OR p.date_fin >= :d)
"""


async def prix_a_date(db, nom_analyse: str, section: str, d: date | None = None) -> dict | None:
    """Tarif actif applicable à la date d (aujourd'hui par défaut), ou None (« prix à renseigner »)."""
    r = await db.execute(text(_SQL_GRILLE + """
        WHERE t.actif AND t.section = :s AND lower(btrim(t.nom_analyse)) = lower(btrim(:a))
          AND p.prix IS NOT NULL
    """), {"d": d or date.today(), "s": section, "a": nom_analyse or ""})
    x = r.mappings().first()
    return dict(x) if x else None


async def grille_a_date(db, d: date | None = None, section: str | None = None) -> list[dict]:
    r = await db.execute(text(_SQL_GRILLE + """
        WHERE (CAST(:s AS TEXT) IS NULL OR t.section = :s)
        ORDER BY t.section, lower(t.nom_analyse)
    """), {"d": d or date.today(), "s": section})
    return [dict(x) for x in r.mappings().all()]


async def historique_prix(db, tarif_id: int) -> list[dict]:
    r = await db.execute(text(
        "SELECT id, prix, date_debut, date_fin, cree_par, cree_le FROM ref_tarifs_prix "
        "WHERE tarif_id = :t ORDER BY date_debut DESC"), {"t": tarif_id})
    return [dict(x) for x in r.mappings().all()]


async def fixer_prix(db, tarif_id: int, prix, date_effet: date, utilisateur: str) -> bool:
    """
    Applique un prix à partir de date_effet. Renvoie True si l'historique a changé.
      - même prix que la période en vigueur : rien ;
      - date d'effet = début de la période en vigueur : correction de cette période ;
      - sinon : la période en vigueur est fermée la veille, une nouvelle est ouverte.
    Une date d'effet dans le futur ou antérieure au début de la période en vigueur est refusée.
    """
    prix = arrondi(prix)
    if date_effet > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date d'effet ne peut pas être dans le futur.")
    r = await db.execute(text(
        "SELECT id, prix, date_debut FROM ref_tarifs_prix WHERE tarif_id = :t AND date_fin IS NULL "
        "ORDER BY date_debut DESC LIMIT 1 FOR UPDATE"), {"t": tarif_id})
    en_cours = r.mappings().first()
    if en_cours is None:
        await db.execute(text(
            "INSERT INTO ref_tarifs_prix (tarif_id, prix, date_debut, cree_par) VALUES (:t, :p, :d, :u)"),
            {"t": tarif_id, "p": prix, "d": date_effet, "u": utilisateur})
    elif arrondi(en_cours["prix"]) == prix:
        return False
    elif date_effet < en_cours["date_debut"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"La date d'effet doit être postérieure ou égale au {en_cours['date_debut']:%d/%m/%Y} "
            "(début du prix en vigueur).")
    elif date_effet == en_cours["date_debut"]:
        await db.execute(text("UPDATE ref_tarifs_prix SET prix = :p, cree_par = :u, cree_le = now() WHERE id = :id"),
                         {"p": prix, "u": utilisateur, "id": en_cours["id"]})
    else:
        await db.execute(text("UPDATE ref_tarifs_prix SET date_fin = :f WHERE id = :id"),
                         {"f": date_effet - timedelta(days=1), "id": en_cours["id"]})
        await db.execute(text(
            "INSERT INTO ref_tarifs_prix (tarif_id, prix, date_debut, cree_par) VALUES (:t, :p, :d, :u)"),
            {"t": tarif_id, "p": prix, "d": date_effet, "u": utilisateur})
    # ref_tarifs.prix garde le prix en vigueur (affichage, compatibilité)
    await db.execute(text("UPDATE ref_tarifs SET prix = :p WHERE id = :t"), {"p": prix, "t": tarif_id})
    return True


async def analyses_sans_prix(db, d: date | None = None) -> list[dict]:
    """Analyses du catalogue (ref_analyses) sans tarif actif ayant un prix à la date d."""
    r = await db.execute(text("""
        SELECT a.id AS analyse_id, a.nom_analyse, a.section, a.type_analyse, a.reference_methode
        FROM ref_analyses a
        WHERE a.section IN ('SMA', 'SCHA', 'SSA')
          AND NOT EXISTS (
              SELECT 1 FROM ref_tarifs t
              JOIN ref_tarifs_prix p ON p.tarif_id = t.id AND p.date_debut <= :d
                                    AND (p.date_fin IS NULL OR p.date_fin >= :d)
              WHERE t.actif AND t.section = a.section
                AND lower(btrim(t.nom_analyse)) = lower(btrim(a.nom_analyse)))
        ORDER BY a.section, lower(a.nom_analyse)
    """), {"d": d or date.today()})
    return [dict(x) for x in r.mappings().all()]


# ------------------------------------------------------------------
#  Lignes facturables d'un échantillon (tâche 35)
# ------------------------------------------------------------------
COLONNE_PRELEVEMENTS = {"SMA": "Nbre Prlvmts SMA", "SCHA": "Nbre Prlvmts SCHA", "SSA": "Nbre Prlvmts SSA"}

_SQL_LIGNES = """
    SELECT id, num_echantillon, section, libelle AS analyse, tarif_id, quantite, prix_unitaire, montant,
           par_prelevement, origine, cree_par, cree_le, modifie_par, modifie_le
    FROM factures_lignes
"""


def _cle(section, analyse) -> tuple:
    return (section, (analyse or "").strip().lower())


def montant_ligne(quantite, prix_unitaire) -> Decimal:
    """Quantité × prix unitaire, arrondi au centime ; prix à renseigner (None) -> 0."""
    if prix_unitaire is None:
        return arrondi(0)
    return arrondi(Decimal(str(quantite)) * Decimal(str(prix_unitaire)))


async def nb_prelevements(db, num: str, section: str | None) -> int:
    if section not in COLONNE_PRELEVEMENTS:
        return 1
    r = await db.execute(text(f'SELECT "{COLONNE_PRELEVEMENTS[section]}" FROM echantillons '
                              'WHERE "N° Echantillon" = :n'), {"n": num})
    return max(int(r.scalar() or 1), 1)


async def lignes_echantillon(db, num: str) -> list[dict]:
    r = await db.execute(text(_SQL_LIGNES + " WHERE num_echantillon = :n ORDER BY section NULLS LAST, id"),
                         {"n": num})
    return [dict(x) for x in r.mappings().all()]


async def ligne(db, ligne_id: int) -> dict | None:
    r = await db.execute(text(_SQL_LIGNES + " WHERE id = :id"), {"id": ligne_id})
    x = r.mappings().first()
    return dict(x) if x else None


def totaux(lignes: list[dict]) -> dict:
    """Totaux par section (« Divers » pour une ligne sans section) et total général, au centime."""
    par_section: dict[str, dict] = {}
    for l in lignes:
        p = par_section.setdefault(l["section"] or "Divers", {"nb": 0, "montant": Decimal("0.00")})
        p["nb"] += 1
        p["montant"] = arrondi(p["montant"] + Decimal(str(l["montant"])))
    total = arrondi(sum((p["montant"] for p in par_section.values()), Decimal("0")))
    return {"par_section": par_section, "total": total,
            "sans_prix": [l["analyse"] + (f" ({l['section']})" if l["section"] else "")
                          for l in lignes if l["prix_unitaire"] is None]}


async def creer_ligne(db, num: str, section: str | None, analyse: str, utilisateur: str,
                      origine: str = "manuelle", quantite=None, prix_unitaire=None) -> int:
    """
    Crée une ligne au prix de la grille du jour (figé), sauf prix unitaire donné.
    Tarif « par prélèvement » : quantité = nombre de prélèvements de la section (sauf quantité donnée).
    """
    tarif = await prix_a_date(db, analyse, section) if section else None
    pu = prix_unitaire if prix_unitaire is not None else (tarif["prix"] if tarif else None)
    pp = bool(tarif and tarif["par_prelevement"])
    q = quantite if quantite is not None else (await nb_prelevements(db, num, section) if pp else 1)
    r = await db.execute(text("""
        INSERT INTO factures_lignes (num_echantillon, section, libelle, tarif_id, quantite, prix_unitaire,
                                     montant, par_prelevement, origine, cree_par)
        VALUES (:n, :s, :a, :t, :q, :pu, :m, :pp, :o, :u) RETURNING id
    """), {"n": num, "s": section, "a": analyse.strip(), "t": tarif["tarif_id"] if tarif else None,
           "q": q, "pu": None if pu is None else arrondi(pu), "m": montant_ligne(q, pu), "pp": pp,
           "o": origine, "u": utilisateur})
    return r.scalar_one()


async def modifier_ligne(db, ligne_id: int, utilisateur: str, quantite=None, prix_unitaire=None,
                         analyse: str | None = None, prix_fourni: bool = False):
    l = await ligne(db, ligne_id)
    q = quantite if quantite is not None else l["quantite"]
    pu = (None if prix_unitaire is None else arrondi(prix_unitaire)) if prix_fourni else l["prix_unitaire"]
    await db.execute(text("""
        UPDATE factures_lignes SET quantite = :q, prix_unitaire = :pu, montant = :m, libelle = :a,
               modifie_par = :u, modifie_le = now()
        WHERE id = :id
    """), {"q": q, "pu": pu, "m": montant_ligne(q, pu), "a": (analyse or l["analyse"]).strip(),
           "u": utilisateur, "id": ligne_id})


async def lignes_verrouillees(db, num: str) -> set[int]:
    """Lignes qui ne peuvent plus être modifiées : portées par un bulletin émis."""
    r = await db.execute(text("""
        SELECT l.id FROM factures_lignes l JOIN factures f ON f.id = l.facture_id
        WHERE l.num_echantillon = :n AND f.statut = 'émis'
    """), {"n": num})
    return {x[0] for x in r}


async def synchroniser(db, num: str, utilisateur: str) -> dict:
    """
    Aligne les lignes automatiques sur les analyses saisies dans les résultats :
      - une analyse (section + nom) sans ligne reçoit une ligne automatique au prix du jour ;
        quantité = nombre de lignes de résultats de cette analyse, ou de prélèvements si le tarif
        est « par prélèvement » ;
      - une ligne automatique dont l'analyse a disparu des résultats est retirée (sauf verrouillée) ;
      - les lignes existantes (y compris manuelles, ajoutées dès la réception) ne sont pas touchées.
    """
    r = await db.execute(text("""
        SELECT section, min(btrim(analyse_effectuee)) AS analyse, count(*) AS n
        FROM resultats_analyses
        WHERE num_echantillon = :n AND coalesce(btrim(analyse_effectuee), '') <> ''
        GROUP BY section, lower(btrim(analyse_effectuee))
        ORDER BY section, min(id)
    """), {"n": num})
    analyses = {_cle(x.section, x.analyse): (x.section, x.analyse, x.n) for x in r}
    existantes = await lignes_echantillon(db, num)
    cles_existantes = {_cle(l["section"], l["analyse"]) for l in existantes}
    verrou = await lignes_verrouillees(db, num)
    ajoutees, retirees = [], []
    for cle, (section, analyse, n) in analyses.items():
        if cle not in cles_existantes:
            tarif = await prix_a_date(db, analyse, section)
            quantite = None if tarif and tarif["par_prelevement"] else n
            await creer_ligne(db, num, section, analyse, utilisateur, "automatique", quantite=quantite)
            ajoutees.append(f"{analyse} ({section})")
    for l in existantes:
        if (l["origine"] == "automatique" and l["id"] not in verrou
                and _cle(l["section"], l["analyse"]) not in analyses):
            await db.execute(text("DELETE FROM factures_lignes WHERE id = :id"), {"id": l["id"]})
            retirees.append(f"{l['analyse']} ({l['section']})")
    return {"ajoutees": ajoutees, "retirees": retirees}


# ------------------------------------------------------------------
#  Montant en lettres (bulletins, quittances)
# ------------------------------------------------------------------
_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
           "onze", "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n: int) -> str:
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    if d in (7, 9):                         # soixante-dix…, quatre-vingt-dix…
        base = "soixante" if d == 7 else "quatre-vingt"
        if d == 7 and u == 1:
            return "soixante et onze"
        return f"{base}-{_UNITES[10 + u]}"
    if d == 8:
        return "quatre-vingts" if u == 0 else f"quatre-vingt-{_UNITES[u]}"
    if u == 0:
        return _DIZAINES[d]
    if u == 1:
        return f"{_DIZAINES[d]} et un"
    return f"{_DIZAINES[d]}-{_UNITES[u]}"


def _moins_de_mille(n: int) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_cent(r)
    tete = "cent" if c == 1 else f"{_UNITES[c]} cent" + ("s" if r == 0 else "")
    return tete if r == 0 else f"{tete} {_moins_de_cent(r)}"


def nombre_en_lettres(n: int) -> str:
    """Entier positif en toutes lettres (orthographe traditionnelle) : 1250 -> « mille deux cent cinquante »."""
    if n == 0:
        return "zéro"
    parties = []
    for valeur, sing, plur in ((10 ** 9, "milliard", "milliards"), (10 ** 6, "million", "millions")):
        q, n = divmod(n, valeur)
        if q:
            parties.append(f"{nombre_en_lettres(q)} {sing if q == 1 else plur}")
    q, n = divmod(n, 1000)
    if q:
        # « mille » est invariable ; « quatre-vingts » et « cents » perdent leur s devant mille
        tete = _moins_de_mille(q)
        if tete.endswith("vingts") or tete.endswith("cents"):
            tete = tete[:-1]
        parties.append("mille" if q == 1 else f"{tete} mille")
    if n:
        parties.append(_moins_de_mille(n))
    return " ".join(parties)


def montant_en_lettres(v) -> str:
    """1250.50 -> « mille deux cent cinquante dirhams et cinquante centimes »."""
    m = abs(arrondi(v))
    dirhams = int(m)
    centimes = int((m - dirhams) * 100)
    de = " de" if dirhams >= 10 ** 6 and dirhams % 10 ** 6 == 0 else ""     # « un million de dirhams »
    texte = f"{nombre_en_lettres(dirhams)}{de} dirham{'s' if dirhams > 1 else ''}"
    if centimes:
        texte += f" et {nombre_en_lettres(centimes)} centime{'s' if centimes > 1 else ''}"
    return texte
