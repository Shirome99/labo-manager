"""
File de travail (« Mon travail »), selon le rôle :

- analyste (sma / scha / ssa) : échantillons à traiter dans sa section, par priorité :
  1. fiches renvoyées par un responsable, 2. en retard, 3. « Reçu », 4. « En cours » non soumis.
  Les échantillons refusés à la réception sont exclus.
- responsable / admin : fiches « À valider » (toutes sections), puis rapports à émettre
  (« Validé » sans rapport valide, ou nouvelle version après erratum).
- user : échantillons en retard (suivi, lecture seule).

Chaque élément porte un lien direct vers la page de travail (Traitement ?num=…).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION, ROLES_RESPONSABLES
from app.models import Echantillon
from app.routers.echantillons import SECTION_COL, _cond_retard, _delais
from app.routers.notifications import fiches_renvoyees

router = APIRouter(prefix="/api/travail", tags=["travail"])

LIBELLES = {
    "renvoyee": "Fiche renvoyée",
    "retard": "En retard",
    "recu": "Reçu, à traiter",
    "en_cours": "En cours, non soumis",
    "a_valider": "À valider",
    "a_emettre": "Rapport à émettre",
}


def _section(e: Echantillon) -> str | None:
    return next((s for s, a in (("SMA", e.sma), ("SCHA", e.scha), ("SSA", e.ssa)) if a == "Yes"), None)


def _element(e: Echantillon, motif: str, priorite: int, detail: str | None = None, page: str = "traitement") -> dict:
    sec = _section(e)
    return {
        "num": e.num_echantillon, "section": sec, "nature": e.nature, "statut": e.statut, "payement": e.payement,
        "date_reception": e.date_reception.isoformat() if e.date_reception else None,
        "motif": motif, "libelle": LIBELLES[motif], "priorite": priorite, "detail": detail,
        "lien": (f"/{page}/{sec}?num={e.num_echantillon}" if sec and page != "detail"
                 else f"/echantillons/detail/{e.num_echantillon}"),
    }


def _non_refuse():
    return or_(Echantillon.decision_reception.is_(None), Echantillon.decision_reception != "Refusé")


async def _echantillons(db, *conditions):
    r = await db.execute(select(Echantillon).where(*conditions)
                         .order_by(Echantillon.date_reception.asc().nulls_last(), Echantillon.ordre))
    return r.scalars().all()


@router.get("")
async def mon_travail(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    role = user["role"]
    section = ROLE_SECTION.get(role)
    items: list[dict] = []
    vus: set[str] = set()

    def ajouter(e, motif, priorite, detail=None, page="traitement"):
        if e.num_echantillon not in vus:
            vus.add(e.num_echantillon)
            items.append(_element(e, motif, priorite, detail, page))

    if section:
        vue = "analyste"
        col = SECTION_COL[section]
        # 1. Fiches renvoyées
        renvois = {x["cle"]: x for x in await fiches_renvoyees(db, section)}
        if renvois:
            for e in await _echantillons(db, Echantillon.num_echantillon.in_(list(renvois)), _non_refuse()):
                x = renvois[e.num_echantillon]
                ajouter(e, "renvoyee", 1, f"par {x['utilisateur']} : {x['details'] or 'sans motif'}")
        # 2. En retard (hors « À valider » : déjà soumis)
        delais = await _delais(db)
        for e in await _echantillons(db, _cond_retard(delais, [section]),
                                     Echantillon.statut.in_(["Reçu", "En cours"]), _non_refuse()):
            ajouter(e, "retard", 2, f"délai de {delais[section]} jours dépassé")
        # 3. Reçus, 4. En cours non soumis
        for e in await _echantillons(db, col == "Yes", or_(Echantillon.statut.is_(None), Echantillon.statut == "Reçu"),
                                     _non_refuse()):
            ajouter(e, "recu", 3)
        for e in await _echantillons(db, col == "Yes", Echantillon.statut == "En cours", _non_refuse()):
            ajouter(e, "en_cours", 4)

    elif role in ROLES_RESPONSABLES:
        vue = "responsable"
        for e in await _echantillons(db, Echantillon.statut == "À valider"):
            ajouter(e, "a_valider", 1)
        # Rapports à émettre : « Validé » sans rapport valide, ou rapport valide en erratum
        r = await db.execute(text("""
            SELECT num_echantillon, section FROM rapports_emis
            WHERE statut = 'valide' AND erratum_motif IS NULL
        """))
        emis = {(x.num_echantillon, x.section) for x in r}
        for e in await _echantillons(db, Echantillon.statut == "Validé"):
            if (e.num_echantillon, _section(e)) not in emis:
                ajouter(e, "a_emettre", 2, page="detail")

    else:
        vue = "suivi"
        delais = await _delais(db)
        for e in await _echantillons(db, _cond_retard(delais)):
            ajouter(e, "retard", 1, f"statut {e.statut}", page="detail")

    items.sort(key=lambda x: x["priorite"])   # tri stable : l'ordre interne (date) est conservé
    compteurs = {}
    for x in items:
        compteurs[x["motif"]] = compteurs.get(x["motif"], 0) + 1
    return {"vue": vue, "section": section, "total": len(items), "compteurs": compteurs, "items": items}
