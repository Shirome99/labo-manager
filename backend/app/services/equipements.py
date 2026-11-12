"""
Équipements (tâche 17) : échéances d'étalonnage / vérification, validité d'un
équipement à une date, et fiches de traitement « contestables ».

Règles :
- échéance = dernière date + périodicité (mois) ; « proche » si dans les 30 jours ;
- un équipement est hors étalonnage à une date D s'il est soumis à étalonnage
  (périodicité renseignée) et qu'aucun étalonnage conforme ne couvre D
  (étalonnage du ≤ D et D < étalonnage + périodicité) ;
- il est aussi non utilisable à D s'il est en panne à cette date (dernier
  événement Panne / Réparation antérieur à D = Panne) ;
- une fiche est « contestable » si son équipement est non utilisable à la date
  de l'analyse (date de mise en analyse, sinon 1re date d'analyse saisie, sinon aujourd'hui).
"""
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import text

ALERTE_JOURS = 30


def ajouter_mois(d: date, mois: int) -> date:
    m = d.month - 1 + mois
    annee, mois_ = d.year + m // 12, m % 12 + 1
    return date(annee, mois_, min(d.day, monthrange(annee, mois_)[1]))


def _echeance(derniere: date | None, periodicite: int | None) -> date | None:
    if not periodicite:
        return None
    return ajouter_mois(derniere, periodicite) if derniere else date.min


def etat_echeances(eq: dict, aujourd_hui: date | None = None) -> dict:
    """Prochaines échéances et statut global : 'à jour', 'proche', 'échu', 'non soumis', 'inactif'."""
    aujourd_hui = aujourd_hui or date.today()
    e_eta = _echeance(eq.get("date_dernier_etalonnage"), eq.get("periodicite_etalonnage_mois"))
    e_ver = _echeance(eq.get("date_derniere_verification"), eq.get("periodicite_verification_mois"))
    echeances = [e for e in (e_eta, e_ver) if e is not None]
    if not eq.get("actif", True):
        statut = "inactif"
    elif not echeances:
        statut = "non soumis"
    elif min(echeances) < aujourd_hui:
        statut = "échu"
    elif min(echeances) <= aujourd_hui + timedelta(days=ALERTE_JOURS):
        statut = "proche"
    else:
        statut = "à jour"
    fmt = lambda e: None if e is None or e == date.min else e.isoformat()  # noqa: E731
    return {"prochain_etalonnage": fmt(e_eta), "prochaine_verification": fmt(e_ver),
            "jamais_etalonne": e_eta == date.min, "jamais_verifie": e_ver == date.min,
            "statut_echeance": statut}


async def validite_a_la_date(db, eq: dict, d: date) -> str | None:
    """None si l'équipement est utilisable à la date d ; sinon la raison."""
    r = await db.execute(text("""
        SELECT type_evenement, date_evenement, resultat FROM equipement_evenements
        WHERE equipement_id = :id AND date_evenement <= :d
        ORDER BY date_evenement DESC, id DESC
    """), {"id": eq["id"], "d": d})
    evenements = r.mappings().all()
    # Panne en cours à la date d
    for ev in evenements:
        if ev["type_evenement"] in ("Panne", "Réparation"):
            if ev["type_evenement"] == "Panne":
                return f"en panne depuis le {ev['date_evenement']:%d/%m/%Y}"
            break
    periodicite = eq.get("periodicite_etalonnage_mois")
    if not periodicite:
        return None
    dates = [ev["date_evenement"] for ev in evenements
             if ev["type_evenement"] == "Étalonnage" and ev["resultat"] != "Non conforme"]
    if eq.get("date_dernier_etalonnage") and eq["date_dernier_etalonnage"] <= d:
        dates.append(eq["date_dernier_etalonnage"])
    if not dates:
        return f"aucun étalonnage valide au {d:%d/%m/%Y}"
    dernier = max(dates)
    fin = ajouter_mois(dernier, periodicite)
    if d >= fin:
        return f"étalonnage échu le {fin:%d/%m/%Y} (analyse du {d:%d/%m/%Y})"
    return None


async def equipement_par_code(db, code: str | None) -> dict | None:
    if not code or not str(code).strip():
        return None
    r = await db.execute(text("SELECT * FROM equipements WHERE code = :c"), {"c": str(code).strip()})
    x = r.mappings().first()
    return dict(x) if x else None


async def date_analyse(db, section: str, trt) -> date:
    """Date de l'analyse : mise en analyse, sinon 1re date d'analyse des résultats, sinon aujourd'hui."""
    d = getattr(trt, "date_mise_en_analyse", None)
    if d:
        return d
    r = await db.execute(text("""
        SELECT min(date_analyse) FROM resultats_analyses
        WHERE num_echantillon = :n AND section = :s AND date_analyse IS NOT NULL
    """), {"n": trt.num_echantillon, "s": section})
    return r.scalar() or date.today()


async def contestation_fiche(db, section: str, trt) -> dict | None:
    """{code, designation, date, raison} si l'équipement de la fiche est non utilisable à la date de l'analyse."""
    if trt is None:
        return None
    eq = await equipement_par_code(db, getattr(trt, "equipement_utilise", None))
    if not eq:
        return None
    d = await date_analyse(db, section, trt)
    raison = await validite_a_la_date(db, eq, d)
    if not raison:
        return None
    return {"code": eq["code"], "designation": eq["designation"], "date": d.isoformat(), "raison": raison}
