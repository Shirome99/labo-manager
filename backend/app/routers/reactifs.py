"""
Réactifs et milieux de culture (tâche 20) : lots, stock, alertes, traçabilité.

Lecture : tout utilisateur connecté (un rôle de section voit sa section et les lots communs).
Création / modification d'un lot, mouvements de stock : responsables, et analystes pour les
lots de leur section. Suppression : admin, seulement sans mouvement ni utilisation (sinon
désactiver). Le stock ne change que par les mouvements (entrée, sortie, ajustement d'inventaire).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import ROLE_SECTION, ROLES_RESPONSABLES, current_user
from app.models import AuditLog
from app.services import reactifs as service

router = APIRouter(prefix="/api/reactifs", tags=["reactifs"])
CATEGORIE = "^(Réactif|Milieu de culture|Souche de référence|Autre)$"


class LotIn(BaseModel):
    produit: str = Field(min_length=1, max_length=200)
    categorie: str = Field("Réactif", pattern=CATEGORIE)
    numero_lot: str = Field(min_length=1, max_length=80)
    fournisseur: str | None = Field(None, max_length=150)
    section: str | None = Field(None, pattern="^(SMA|SCHA|SSA)$")
    date_reception: date | None = None
    date_ouverture: date | None = None
    date_peremption: date
    unite: str = Field("unité", min_length=1, max_length=20)
    seuil_alerte: float | None = Field(None, ge=0)
    emplacement: str | None = Field(None, max_length=150)
    actif: bool = True
    observations: str | None = None


class LotCreation(LotIn):
    quantite_initiale: float = Field(ge=0)


class MouvementIn(BaseModel):
    type_mouvement: str = Field(pattern="^(Entrée|Sortie|Ajustement)$")
    date_mouvement: date
    quantite: float = Field(ge=0)
    num_echantillon: str | None = Field(None, max_length=50)
    motif: str | None = None

    @model_validator(mode="after")
    def _date(self):
        if self.date_mouvement > date.today():
            raise ValueError("La date du mouvement ne peut pas être dans le futur.")
        if self.type_mouvement != "Ajustement" and self.quantite <= 0:
            raise ValueError("La quantité doit être positive.")
        return self


def _vide(v):
    return (str(v).strip() or None) if v is not None else None


def _peut_ecrire(user: dict, section: str | None) -> None:
    if user["role"] in ROLES_RESPONSABLES:
        return
    rs = ROLE_SECTION.get(user["role"])
    if rs and section == rs:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        "Réservé aux responsables et aux analystes de la section du lot.")


async def _lot(db, lid: int, user: dict) -> dict:
    r = (await db.execute(text(f"SELECT {service.COLONNES} FROM reactifs_lots WHERE id = :id"), {"id": lid})).mappings().first()
    rs = ROLE_SECTION.get(user["role"])
    if r is None or (rs and r["section"] not in (None, rs)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lot introuvable.")
    return service.avec_etat(r)


async def _doublon(db, p: LotIn, sauf: int | None = None):
    r = await db.execute(text("""SELECT code FROM reactifs_lots WHERE lower(btrim(produit)) = lower(btrim(:p))
        AND lower(btrim(numero_lot)) = lower(btrim(:l)) AND (CAST(:id AS INTEGER) IS NULL OR id <> :id)"""),
        {"p": p.produit, "l": p.numero_lot, "id": sauf})
    x = r.first()
    if x:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ce lot de ce produit est déjà enregistré ({x[0]}).")


def _dates(p: LotIn):
    if p.date_ouverture and p.date_reception and p.date_ouverture < p.date_reception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date d'ouverture précède la date de réception.")


@router.get("")
async def liste(section: str | None = Query(None, pattern="^(SMA|SCHA|SSA)$"), actifs: bool = False,
                user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rs = ROLE_SECTION.get(user["role"])
    r = await db.execute(text(f"""
        SELECT {service.COLONNES} FROM reactifs_lots
        WHERE (CAST(:rs AS VARCHAR) IS NULL OR section IS NULL OR section = :rs)
          AND (CAST(:s AS VARCHAR) IS NULL OR section IS NULL OR section = :s)
          AND (NOT :actifs OR actif)
        ORDER BY date_peremption, produit"""), {"rs": rs, "s": section, "actifs": actifs})
    return [service.avec_etat(x) for x in r.mappings().all()]


@router.get("/alertes")
async def alertes(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Lots actifs non épuisés : périmés, péremption dans les 30 jours ou stock sous le seuil."""
    return await lots_en_alerte(db, user)


async def lots_en_alerte(db, user: dict) -> list[dict]:
    lots = await liste(None, True, user, db)
    return [x for x in lots if x["etat"] in ("périmé", "péremption proche", "seuil bas") and x["quantite"] > 0]


@router.get("/echantillon/{num}")
async def tracabilite(num: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Lots utilisés pour un échantillon (fiches de traitement des sections visibles)."""
    r = (await db.execute(text('SELECT "SMA", "SCHA", "SSA" FROM echantillons WHERE "N° Echantillon" = :n'),
                          {"n": num})).first()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    sections = [s for s, v in zip(("SMA", "SCHA", "SSA"), r) if v == "Yes"]
    rs = ROLE_SECTION.get(user["role"])
    if rs:
        if rs not in sections:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cet echantillon n'appartient pas a votre section.")
        sections = [rs]
    return await service.tracabilite(db, num, sections)


@router.post("", status_code=status.HTTP_201_CREATED)
async def creer(p: LotCreation, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    _peut_ecrire(user, p.section)
    _dates(p)
    await _doublon(db, p)
    annee = date.today().year
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('reactifs_lots'))"))
    n = (await db.execute(text("""SELECT coalesce(max(substring(code FROM '-(\\d+)$')::int), 0) + 1
        FROM reactifs_lots WHERE code LIKE :pref"""), {"pref": f"L{annee}-%"})).scalar_one()
    code = f"L{annee}-{n:04d}"
    lid = (await db.execute(text("""
        INSERT INTO reactifs_lots (code, produit, categorie, numero_lot, fournisseur, section, date_reception,
            date_ouverture, date_peremption, quantite_initiale, quantite, unite, seuil_alerte, emplacement, actif,
            observations, cree_par)
        VALUES (:code, :produit, :categorie, :numero_lot, :fournisseur, :section, :date_reception, :date_ouverture,
            :date_peremption, :q, :q, :unite, :seuil_alerte, :emplacement, :actif, :observations, :par)
        RETURNING id"""), {
        **p.model_dump(exclude={"quantite_initiale"}), "code": code, "q": p.quantite_initiale,
        "produit": p.produit.strip(), "numero_lot": p.numero_lot.strip(), "fournisseur": _vide(p.fournisseur),
        "emplacement": _vide(p.emplacement), "observations": _vide(p.observations), "par": user["username"]})).scalar_one()
    db.add(AuditLog(utilisateur=user["username"], action="REACTIF_LOT", table_cible="reactifs_lots", cle=code,
                    details=f"{p.produit.strip()} lot {p.numero_lot.strip()}"))
    await db.commit()
    return await _lot(db, lid, user)


@router.patch("/{lid}")
async def modifier(lid: int, p: LotIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    lot = await _lot(db, lid, user)
    _peut_ecrire(user, lot["section"])
    _peut_ecrire(user, p.section)
    _dates(p)
    await _doublon(db, p, lid)
    await db.execute(text("""
        UPDATE reactifs_lots SET produit = :produit, categorie = :categorie, numero_lot = :numero_lot,
            fournisseur = :fournisseur, section = :section, date_reception = :date_reception,
            date_ouverture = :date_ouverture, date_peremption = :date_peremption, unite = :unite,
            seuil_alerte = :seuil_alerte, emplacement = :emplacement, actif = :actif, observations = :observations
        WHERE id = :id"""), {**p.model_dump(), "produit": p.produit.strip(), "numero_lot": p.numero_lot.strip(),
                             "fournisseur": _vide(p.fournisseur), "emplacement": _vide(p.emplacement),
                             "observations": _vide(p.observations), "id": lid})
    db.add(AuditLog(utilisateur=user["username"], action="REACTIF_LOT", table_cible="reactifs_lots", cle=lot["code"],
                    details="modifié"))
    await db.commit()
    return await _lot(db, lid, user)


@router.delete("/{lid}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer(lid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé à l'administrateur")
    lot = await _lot(db, lid, user)
    mvt = (await db.execute(text("SELECT 1 FROM reactifs_mouvements WHERE lot_id = :id LIMIT 1"), {"id": lid})).first()
    if mvt or await service.utilisations(db, lot["code"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Lot déjà mouvementé ou utilisé : désactivez-le plutôt.")
    await db.execute(text("DELETE FROM reactifs_lots WHERE id = :id"), {"id": lid})
    db.add(AuditLog(utilisateur=user["username"], action="REACTIF_LOT", table_cible="reactifs_lots", cle=lot["code"],
                    details="supprimé"))
    await db.commit()


@router.get("/{lid}/mouvements")
async def mouvements(lid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _lot(db, lid, user)
    r = await db.execute(text("""SELECT id, date_mouvement, type_mouvement, quantite, stock_apres, num_echantillon,
        motif, saisi_par FROM reactifs_mouvements WHERE lot_id = :id ORDER BY date_mouvement DESC, id DESC"""), {"id": lid})
    return [{**dict(x), "quantite": float(x.quantite), "stock_apres": float(x.stock_apres)} for x in r.mappings().all()]


@router.post("/{lid}/mouvements", status_code=status.HTTP_201_CREATED)
async def ajouter_mouvement(lid: int, p: MouvementIn, user: dict = Depends(current_user),
                            db: AsyncSession = Depends(get_db)):
    lot = await _lot(db, lid, user)
    _peut_ecrire(user, lot["section"])
    # Verrou de la ligne : deux sorties simultanées ne peuvent pas rendre le stock négatif
    stock = float((await db.execute(text("SELECT quantite FROM reactifs_lots WHERE id = :id FOR UPDATE"),
                                    {"id": lid})).scalar_one())
    if p.type_mouvement == "Entrée":
        apres = stock + p.quantite
    elif p.type_mouvement == "Sortie":
        if p.quantite > stock:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Stock insuffisant : {stock:g} {lot['unite']} disponible(s).")
        apres = stock - p.quantite
    else:
        apres = p.quantite                     # ajustement d'inventaire : stock constaté
    num = _vide(p.num_echantillon)
    if num and not (await db.execute(text('SELECT 1 FROM echantillons WHERE "N° Echantillon" = :n'), {"n": num})).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Échantillon « {num} » introuvable.")
    await db.execute(text("""INSERT INTO reactifs_mouvements (lot_id, date_mouvement, type_mouvement, quantite,
        stock_apres, num_echantillon, motif, saisi_par) VALUES (:l, :d, :t, :q, :a, :n, :m, :u)"""),
        {"l": lid, "d": p.date_mouvement, "t": p.type_mouvement, "q": p.quantite, "a": apres, "n": num,
         "m": _vide(p.motif), "u": user["username"]})
    await db.execute(text("UPDATE reactifs_lots SET quantite = :a WHERE id = :id"), {"a": apres, "id": lid})
    db.add(AuditLog(utilisateur=user["username"], action="REACTIF_MOUVEMENT", table_cible="reactifs_mouvements",
                    cle=lot["code"], details=f"{p.type_mouvement} {p.quantite:g} → {apres:g}"))
    await db.commit()
    return await _lot(db, lid, user)


@router.get("/{lid}/utilisations")
async def utilisations(lid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    lot = await _lot(db, lid, user)
    rs = ROLE_SECTION.get(user["role"])
    return [{**u, "date_mise_en_analyse": u["date_mise_en_analyse"].isoformat() if u["date_mise_en_analyse"] else None}
            for u in await service.utilisations(db, lot["code"]) if not rs or u["section"] == rs]
