"""
Notifications de la topbar : ce qui concerne l'utilisateur connecte.

  - admin / responsable : fiches « À valider » (toutes sections) + retards
  - user : retards (toutes sections)
  - sma / scha / ssa : fiches renvoyees par un responsable dans sa section + retards de sa section
  - user / admin : bulletins impayes depuis plus de N jours (reglage facturation.seuil_impayes_jours)

Une fiche est « renvoyee » si l'echantillon est « En cours » et que le dernier
evenement du circuit de validation (SOUMETTRE / REFUSER / VALIDATE) dans audit_log
est un REFUSER (le motif est dans details). Aucune table supplementaire.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION, ROLES_FACTURATION, ROLES_RESPONSABLES
from app.models import Echantillon
from app.routers.echantillons import SECTION_COL, _cond_retard, _delais
from app.routers.equipements import alertes as alertes_equipements
from app.routers.cq import series_avec_analyse
from app.routers.habilitations import habilitations as liste_habilitations
from app.routers.reactifs import lots_en_alerte
from app.services.equipements import contestation_fiche
from app.services.facturation import format_dh, lire_parametres as lire_parametres_facturation
from app.services.paiements import bulletins_impayes
from app.models import TRAITEMENT_MODELS

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

LIMITE = 15  # elements detailles par categorie (le compteur reste exact)
TABLE_TRT = {"SMA": "traitement_sma", "SCHA": "traitement_scha", "SSA": "traitement_ssa"}


def _section(e: Echantillon) -> str | None:
    return next((s for s, a in (("SMA", e.sma), ("SCHA", e.scha), ("SSA", e.ssa)) if a == "Yes"), None)


def _date(e: Echantillon) -> str | None:
    return e.date_reception.date().isoformat() if e.date_reception else None


async def fiches_renvoyees(db: AsyncSession, section: str) -> list:
    """
    Fiches « renvoyées » d'une section : échantillon « En cours » dont le dernier événement
    du circuit (SOUMETTRE / REFUSER / VALIDATE) est un REFUSER. Plus récentes d'abord.
    """
    r = await db.execute(text(f"""
        SELECT DISTINCT ON (a.cle) a.cle, a.action, a.details, a.utilisateur, a.horodatage
        FROM audit_log a
        JOIN echantillons e ON e."N° Echantillon" = a.cle
        WHERE a.table_cible = :table
          AND a.action IN ('SOUMETTRE', 'REFUSER', 'VALIDATE')
          AND e.statut = 'En cours'
          AND e."{section}" = 'Yes'
        ORDER BY a.cle, a.horodatage DESC, a.id DESC
    """), {"table": TABLE_TRT[section]})
    renvois = [x for x in r.mappings().all() if x["action"] == "REFUSER"]
    renvois.sort(key=lambda x: x["horodatage"], reverse=True)
    return renvois


@router.get("")
async def notifications(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    role_section = ROLE_SECTION.get(user["role"])
    sections = [role_section] if role_section else list(SECTION_COL)
    items: list[dict] = []
    compteurs = {"aValider": 0, "renvoyees": 0, "retards": 0, "contestables": 0, "etalonnages": 0, "cq": 0, "habilitations": 0, "reactifs": 0, "impayes": 0}

    # ---- Fiches a valider (responsables : admin, responsable) ----
    if user["role"] in ROLES_RESPONSABLES:
        r = await db.execute(select(Echantillon).where(Echantillon.statut == "À valider")
                             .order_by(Echantillon.date_reception.asc().nulls_last()))
        rows = r.scalars().all()
        compteurs["aValider"] = len(rows)
        for e in rows[:LIMITE]:
            sec = _section(e)
            items.append({"type": "a_valider", "num": e.num_echantillon, "section": sec,
                          "texte": "Fiche à valider", "detail": e.nature,
                          "lien": f"/traitement/{sec}?num={e.num_echantillon}" if sec
                          else f"/echantillons/detail/{e.num_echantillon}"})

    # ---- Fiches renvoyees (analyste de la section) ----
    if role_section:
        renvois = await fiches_renvoyees(db, role_section)
        compteurs["renvoyees"] = len(renvois)
        for x in renvois[:LIMITE]:
            items.append({"type": "renvoyee", "num": x["cle"], "section": role_section,
                          "texte": f"Fiche renvoyée par {x['utilisateur']}",
                          "detail": x["details"] or "Sans motif",
                          "lien": f"/traitement/{role_section}?num={x['cle']}"})

    # ---- Retards (perimetre de l'utilisateur) ----
    delais = await _delais(db)
    r = await db.execute(select(Echantillon).where(_cond_retard(delais, sections))
                         .order_by(Echantillon.date_reception.asc()))
    rows = r.scalars().all()
    compteurs["retards"] = len(rows)
    for e in rows[:LIMITE]:
        items.append({"type": "retard", "num": e.num_echantillon, "section": _section(e),
                      "texte": f"En retard — reçu le {_date(e)}", "detail": e.statut,
                      "lien": f"/echantillons/detail/{e.num_echantillon}"})

    # ---- Fiches contestables (responsables) : équipement non utilisable à la date de l'analyse ----
    if user["role"] in ROLES_RESPONSABLES:
        for sec, Model in TRAITEMENT_MODELS.items():
            r = await db.execute(
                select(Model, Echantillon)
                .join(Echantillon, Echantillon.num_echantillon == Model.num_echantillon)
                .where(Model.equipement_utilise.isnot(None), Model.equipement_utilise != "",
                       Echantillon.statut.in_(["En cours", "À valider", "Validé"])))
            for trt, e in r.all():
                c = await contestation_fiche(db, sec, trt)
                if c:
                    compteurs["contestables"] += 1
                    items.append({"type": "contestable", "num": e.num_echantillon, "section": sec,
                                  "texte": f"Fiche contestable — {c['code']}", "detail": c["raison"],
                                  "lien": f"/traitement/{sec}?num={e.num_echantillon}"})

    # ---- Échéances d'étalonnage / vérification (dans les 30 jours ou échues) ----
    if user["role"] != "user":
        eqs = await alertes_equipements(user, db)
        compteurs["etalonnages"] = len(eqs)
        for q in eqs[:LIMITE]:
            echeance = min(x for x in (q["prochain_etalonnage"], q["prochaine_verification"]) if x) \
                if (q["prochain_etalonnage"] or q["prochaine_verification"]) else None
            items.append({"type": "etalonnage", "num": q["code"], "section": q["section"],
                          "texte": f"{q['designation']} — {'échu' if q['statut_echeance'] == 'échu' else 'échéance proche'}",
                          "detail": ("jamais étalonné / vérifié" if not echeance
                                     else f"échéance le {echeance[8:10]}/{echeance[5:7]}/{echeance[:4]}"),
                          "lien": "/equipements"})

    # ---- Réactifs et milieux : lots périmés, péremption < 30 j, stock sous le seuil (tâche 20) ----
    if user["role"] != "user":
        lots = await lots_en_alerte(db, user)
        compteurs["reactifs"] = len(lots)
        for x in lots[:LIMITE]:
            detail = {"périmé": f"périmé le {x['date_peremption']:%d/%m/%Y}",
                      "péremption proche": f"péremption le {x['date_peremption']:%d/%m/%Y}",
                      "seuil bas": f"stock {x['quantite']:g} {x['unite']} (seuil {x['seuil_alerte']:g})"}[x["etat"]]
            items.append({"type": "reactif", "num": x["code"], "section": x["section"],
                          "texte": f"{x['produit']} (lot {x['numero_lot']})", "detail": detail,
                          "lien": f"/reactifs?lot={x['id']}"})

    # ---- Contrôles qualité internes : séries dont la dernière mesure est en alerte ----
    if user["role"] != "user":
        for q in await series_avec_analyse(db, user):
            if q["alerte_active"]:
                compteurs["cq"] += 1
                items.append({"type": "cq", "num": f"CQ-{q['id']}", "section": q["section"],
                              "texte": f"{q['methode']} — {q['libelle']}",
                              "detail": ", ".join(q["derniere_alerte"]["regles"]),
                              "lien": f"/controles-qualite?serie={q['id']}"})

    # ---- Habilitations arrivant à échéance dans les 30 jours (responsables : toutes ; autres : les leurs) ----
    if user["role"] != "user":
        for h in await liste_habilitations(db, user):
            if h["etat"] == "proche":
                compteurs["habilitations"] += 1
                items.append({"type": "habilitation", "num": f"H-{h['id']}", "section": h["section"],
                              "texte": f"{h['utilisateur']} — {h['nom_analyse']}",
                              "detail": f"habilitation à renouveler avant le {h['date_echeance']:%d/%m/%Y}",
                              "lien": "/habilitations"})

    # ---- Bulletins impayés depuis plus de N jours (accueil et admin ; N = facturation.seuil_impayes_jours) ----
    if user["role"] in ROLES_FACTURATION:
        seuil = (await lire_parametres_facturation(db))["seuil_impayes_jours"]
        impayes = await bulletins_impayes(db, seuil + 1)
        compteurs["impayes"] = len(impayes)
        for b in impayes[:LIMITE]:
            items.append({"type": "impaye", "num": b["numero"], "section": None,
                          "texte": f"{b['numero']} — {b['client_nom'] or 'client non renseigné'}",
                          "detail": f"reste dû {format_dh(b['reste'])}, émis il y a {b['jours']} jours",
                          "lien": f"/facturation?bulletin={b['id']}"})

    return {"total": sum(compteurs.values()), **compteurs, "items": items}
