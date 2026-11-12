"""
Habilitations du personnel (tâche 19) : un utilisateur est habilité pour une analyse
d'une section à une date J si une habilitation (nom d'analyse comparé sans casse ni espaces
de bord) a date_qualification ≤ J et (pas d'échéance ou échéance ≥ J).
Alerte 30 jours avant l'échéance.
"""
from datetime import date, timedelta

from sqlalchemy import text

ALERTE_JOURS = 30


def etat(h: dict, jour: date | None = None) -> str:
    """'à venir' (qualification future), 'à jour', 'proche' (échéance < 30 j), 'échue'."""
    jour = jour or date.today()
    if h["date_qualification"] > jour:
        return "à venir"
    e = h.get("date_echeance")
    if e is None:
        return "à jour"
    if e < jour:
        return "échue"
    return "proche" if e <= jour + timedelta(days=ALERTE_JOURS) else "à jour"


async def analyses_non_habilitees(db, user_id: int, section: str, analyses: list[str],
                                  jour: date | None = None) -> list[str]:
    """Analyses (parmi `analyses`) pour lesquelles l'utilisateur n'est pas habilité et à jour."""
    jour = jour or date.today()
    r = await db.execute(text("""
        SELECT lower(btrim(nom_analyse)) FROM habilitations
        WHERE user_id = :u AND section = :s AND date_qualification <= :j
          AND (date_echeance IS NULL OR date_echeance >= :j)
    """), {"u": user_id, "s": section, "j": jour})
    ok = {x[0] for x in r}
    manquantes = []
    for a in analyses:
        if a.strip().lower() not in ok and a not in manquantes:
            manquantes.append(a)
    return manquantes
