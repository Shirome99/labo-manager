"""
Requêtes du reporting (tâche 21) : catalogue fermé, exécution, détail et valeurs des filtres.
Aucun SQL libre : voir app/services/requetes.py.
"""
from datetime import datetime

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLE_SECTION, current_user
from app.routers.echantillons import _delais
from app.models import AuditLog
from app.services import exports_requetes as exports
from app.services import requetes as moteur

router = APIRouter(prefix="/api/requetes", tags=["requetes"])


def _requete(definition: dict, user: dict) -> moteur.Requete:
    try:
        return moteur.valider(definition, ROLE_SECTION.get(user["role"]))
    except moteur.SectionInterdite as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except moteur.RequeteInvalide as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def _sql_controle(user: dict, sql: str, params: dict) -> dict:
    """SQL réellement exécuté, renvoyé à l'admin seulement (contrôle des chiffres)."""
    if user["role"] != "admin":
        return {}
    return {"sql": sql, "parametres": {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                       for k, v in params.items()}}


async def executer_definition(db: AsyncSession, definition: dict, user: dict) -> dict:
    """Exécution partagée par l'API, les exports et le bilan mensuel."""
    q = _requete(definition, user)
    sql, params = moteur.construire(q, await _delais(db))
    lignes = (await db.execute(text(sql), params)).mappings().all()
    return {**moteur.mettre_en_forme(q, [dict(x) for x in lignes]), **_sql_controle(user, sql, params)}


async def detail_definition(db: AsyncSession, definition: dict, user: dict,
                            valeurs: dict | None = None, limite: int | None = None) -> dict:
    q = _requete({**definition, "limite": limite or moteur.LIMITE_DEFAUT}, user)
    try:
        sql, params, entetes = moteur.construire_detail(q, await _delais(db), valeurs)
    except moteur.RequeteInvalide as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    params["limite"] = q.limite + 1          # une ligne de plus pour savoir si c'est tronqué
    lignes = [{k: moteur._val(v) for k, v in dict(x).items()}
              for x in (await db.execute(text(sql), params)).mappings().all()]
    return {"colonnes": [{"cle": c, "libelle": l} for c, l in entetes],
            "lignes": lignes[:q.limite], "tronque": len(lignes) > q.limite}


async def detail_page(db: AsyncSession, definition: dict, user: dict, valeurs: dict, page: int, taille: int) -> dict:
    """Une page du détail (pagination serveur, tâche 30), avec le nombre total de lignes."""
    q = _requete({**definition, "limite": taille}, user)
    delais = await _delais(db)
    try:
        sql, params, entetes = moteur.construire_detail(q, delais, valeurs, decalage=(page - 1) * taille)
        sql_n, params_n, _ = moteur.construire_detail(q, delais, valeurs, compter=True)
    except moteur.RequeteInvalide as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    lignes = [{k: moteur._val(v) for k, v in dict(x).items()}
              for x in (await db.execute(text(sql), params)).mappings().all()]
    total = (await db.execute(text(sql_n), params_n)).scalar_one()
    return {"colonnes": [{"cle": c, "libelle": l} for c, l in entetes], "lignes": lignes,
            "total": total, "page": page, "taille": taille}


@router.get("/catalogue")
async def catalogue(user: dict = Depends(current_user)):
    return moteur.catalogue()


@router.post("/executer")
async def executer(definition: dict = Body(...), user: dict = Depends(current_user),
                   db: AsyncSession = Depends(get_db)):
    return await executer_definition(db, definition, user)


@router.post("/detail")
async def detail(corps: dict = Body(...), user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """
    Lignes brutes de la requête ; `valeurs` = {regroupement: valeur} d'une case du résultat.
    Avec `page` (et `taille`, 50 par défaut, 500 au plus) : pagination serveur, avec le total.
    """
    valeurs = corps.get("valeurs") or {}
    if not isinstance(valeurs, dict) or not all(isinstance(v, str) for v in valeurs.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Valeurs de regroupement invalides.")
    if corps.get("page") is not None:
        try:
            page, taille = int(corps["page"]), int(corps.get("taille") or 50)
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pagination invalide.")
        if page < 1 or not 1 <= taille <= 500:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pagination invalide (page ≥ 1, taille de 1 à 500).")
        return await detail_page(db, corps.get("definition") or {}, user, valeurs, page, taille)
    limite = corps.get("limite") or moteur.LIMITE_DEFAUT
    return await detail_definition(db, corps.get("definition") or {}, user, valeurs, limite)


@router.post("/valeurs")
async def valeurs(corps: dict = Body(...), dimension: str = Query(...),
                  user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Valeurs distinctes d'un critère (avec leur effectif), selon les droits et le jeu choisi."""
    q = _requete({"jeu": corps.get("jeu") or "echantillons",
                  "filtres": {k: v for k, v in (corps.get("filtres") or {}).items() if k == "section"}}, user)
    try:
        sql, params = moteur.construire_valeurs(q, dimension, await _delais(db))
    except moteur.RequeteInvalide as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return [{"valeur": x.valeur, "n": x.n} for x in await db.execute(text(sql), params)]


@router.post("/export")
async def exporter(corps: dict = Body(...), format: str = Query(..., pattern="^(xlsx|pdf)$"),
                   user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Export du résultat affiché : Excel (Résultat, Tableau croisé, Paramètres, Détail) ou PDF."""
    definition = corps.get("definition") or {}
    titre = (str(corps.get("titre") or "").strip() or "Requête")[:150]
    resultat = await executer_definition(db, definition, user)
    params = exports.parametres(definition, resultat, user["username"])
    horodatage = datetime.now().strftime("%Y%m%d_%H%M")
    if format == "xlsx":
        detail = await detail_definition(db, definition, user, limite=moteur.LIMITE_MAX)
        contenu = exports.excel_requete(resultat, detail, params)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        contenu = exports.pdf_requete(resultat, params, titre, user["username"])
        media = "application/pdf"
    db.add(AuditLog(utilisateur=user["username"], action="EXPORT_REQUETE", table_cible="requetes",
                    cle=format, details=titre))
    await db.commit()
    return Response(contenu, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="requete_{horodatage}.{format}"'})


# ---------------------------------------------------------------------------
# Requêtes enregistrées (tâche 23)
# ---------------------------------------------------------------------------
class RequeteEnregistreeIn(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    description: str | None = Field(None, max_length=2000)
    definition: dict
    visibilite: str = Field("personnelle", pattern="^(personnelle|partagée)$")


def _visible(r: dict, user: dict) -> bool:
    """Personnelle : son auteur. Partagée : tous ceux qui ont accès aux données concernées
    (un rôle de section ne voit pas une requête filtrée sur une autre section)."""
    if r["auteur"] == user["username"]:
        return True
    if r["visibilite"] != "partagée":
        return False
    rs = ROLE_SECTION.get(user["role"])
    sections = ((r["definition"] or {}).get("filtres") or {}).get("section") or []
    return not rs or not sections or sections == [rs]


def _peut_modifier(r: dict, user: dict) -> bool:
    return r["auteur"] == user["username"] or user["role"] == "admin"


def _ligne(r) -> dict:
    d = dict(r)
    if isinstance(d.get("definition"), str):
        d["definition"] = json.loads(d["definition"])
    for k in ("cree_le", "modifie_le"):
        d[k] = d[k].isoformat() if d.get(k) else None
    return d


async def requete_enregistree(db: AsyncSession, rid: int, user: dict) -> dict:
    r = (await db.execute(text("SELECT * FROM requetes_enregistrees WHERE id = :id"), {"id": rid})).mappings().first()
    if r is None or not _visible(_ligne(r), user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requête introuvable.")
    d = _ligne(r)
    return {**d, "peut_modifier": _peut_modifier(d, user)}


def _controler(p: RequeteEnregistreeIn, user: dict) -> str:
    _requete(p.definition, user)               # même contrôle qu'à l'exécution (400 / 403)
    return json.dumps(p.definition, ensure_ascii=False)


@router.get("/enregistrees")
async def enregistrees(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("SELECT * FROM requetes_enregistrees ORDER BY visibilite DESC, lower(nom)"))
    out = []
    for x in r.mappings().all():
        d = _ligne(x)
        if _visible(d, user):
            out.append({**d, "peut_modifier": _peut_modifier(d, user)})
    return out


@router.get("/enregistrees/{rid}")
async def lire_enregistree(rid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await requete_enregistree(db, rid, user)


async def _nom_libre(db, nom: str, auteur: str, sauf: int | None = None):
    r = await db.execute(text("""SELECT 1 FROM requetes_enregistrees WHERE auteur = :a
        AND lower(btrim(nom)) = lower(btrim(:n)) AND (CAST(:id AS INTEGER) IS NULL OR id <> :id)"""),
        {"a": auteur, "n": nom, "id": sauf})
    if r.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Vous avez déjà une requête de ce nom.")


@router.post("/enregistrees", status_code=status.HTTP_201_CREATED)
async def creer_enregistree(p: RequeteEnregistreeIn, user: dict = Depends(current_user),
                            db: AsyncSession = Depends(get_db)):
    definition = _controler(p, user)
    await _nom_libre(db, p.nom, user["username"])
    rid = (await db.execute(text("""
        INSERT INTO requetes_enregistrees (nom, description, definition, auteur, visibilite)
        VALUES (:n, :d, CAST(:def AS jsonb), :a, :v) RETURNING id"""),
        {"n": p.nom.strip(), "d": (p.description or "").strip() or None, "def": definition,
         "a": user["username"], "v": p.visibilite})).scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="REQUETE_ENREGISTREE", table_cible="requetes_enregistrees",
                    cle=str(rid), details=p.nom.strip()))
    await db.commit()
    return await requete_enregistree(db, rid, user)


@router.patch("/enregistrees/{rid}")
async def modifier_enregistree(rid: int, p: RequeteEnregistreeIn, user: dict = Depends(current_user),
                               db: AsyncSession = Depends(get_db)):
    r = await requete_enregistree(db, rid, user)
    if not r["peut_modifier"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul l'auteur ou l'administrateur peut modifier cette requête.")
    definition = _controler(p, user)
    await _nom_libre(db, p.nom, r["auteur"], rid)
    await db.execute(text("""UPDATE requetes_enregistrees SET nom = :n, description = :d, definition = CAST(:def AS jsonb),
        visibilite = :v, modifie_le = now() WHERE id = :id"""),
        {"n": p.nom.strip(), "d": (p.description or "").strip() or None, "def": definition, "v": p.visibilite, "id": rid})
    db.add(AuditLog(utilisateur=user["username"], action="REQUETE_ENREGISTREE", table_cible="requetes_enregistrees",
                    cle=str(rid), details="modifiée"))
    await db.commit()
    return await requete_enregistree(db, rid, user)


@router.delete("/enregistrees/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_enregistree(rid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    r = await requete_enregistree(db, rid, user)
    if not r["peut_modifier"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul l'auteur ou l'administrateur peut supprimer cette requête.")
    if (await db.execute(text("SELECT 1 FROM bilan_modele WHERE requete_id = :id"), {"id": rid})).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette requête compose le bilan mensuel : retirez-la d'abord du modèle.")
    await db.execute(text("DELETE FROM requetes_enregistrees WHERE id = :id"), {"id": rid})
    db.add(AuditLog(utilisateur=user["username"], action="REQUETE_SUPPRIMEE", table_cible="requetes_enregistrees",
                    cle=str(rid), details=r["nom"]))
    await db.commit()
