"""
Gestion des referentiels reservee a l'admin.

Prefixe : /api/admin/ref
Garde   : require_admin (seul le role admin accede a ces routes)

Entites gerees :
  - fabricants            (id SERIAL, libelle, ville, adresse, telephone, fax)
  - categories            (id SERIAL, libelle, domaine)
  - types-echantillon     (id INTEGER, libelle)
  - soustypes-echantillon (id INTEGER, libelle, type_id -> types)

Relation respectee : 1 Type -> N Sous-types.
  * creer un sous-type impose de choisir un type existant ;
  * supprimer un type encore utilise par des sous-types est refuse
    (integrite garantie cote base par la FK, et verifiee ici pour
     renvoyer un message clair).

Acces en SQL direct (text()) : fonctionne des que la migration 012
est passee, sans dependre des modeles ORM.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import require_admin
from app.models import AuditLog
from app.services import facturation as fact

router = APIRouter(prefix="/api/admin/ref", tags=["admin-referentiels"])


# ------------------------------------------------------------------
#  Schemas d'entree
# ------------------------------------------------------------------
class FabricantIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)
    ville: str | None = None
    adresse: str | None = None
    telephone: str | None = None
    fax: str | None = None


class CategorieIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)
    domaine: str | None = None


class TypeIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)


class SousTypeIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)
    type_id: int


# ------------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------------
def _n(v):
    """Chaine vide -> None (pour ne pas stocker '')."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None


async def _audit(db, admin, action, table, cle, details=None):
    db.add(AuditLog(utilisateur=admin["username"], action=action,
                    table_cible=table, cle=str(cle), details=details))


async def _next_id(db, table):
    """Prochain id pour les tables a cle INTEGER non-serial (types / sous-types)."""
    r = await db.execute(text(f"SELECT COALESCE(MAX(id), 0) + 1 AS n FROM {table}"))
    return r.scalar_one()


# ==================================================================
#  FABRICANTS
# ==================================================================
@router.get("/fabricants")
async def liste_fabricants(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT id, libelle, ville, adresse, telephone, fax "
        "FROM ref_fabricants ORDER BY libelle"))
    return [dict(x) for x in r.mappings().all()]


@router.post("/fabricants", status_code=status.HTTP_201_CREATED)
async def creer_fabricant(p: FabricantIn, admin=Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    exists = await db.execute(text("SELECT 1 FROM ref_fabricants WHERE lower(libelle)=lower(:l)"),
                              {"l": p.libelle.strip()})
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce fabricant existe deja.")
    r = await db.execute(text(
        "INSERT INTO ref_fabricants (libelle, ville, adresse, telephone, fax) "
        "VALUES (:libelle, :ville, :adresse, :telephone, :fax) RETURNING id"),
        {"libelle": p.libelle.strip(), "ville": _n(p.ville), "adresse": _n(p.adresse),
         "telephone": _n(p.telephone), "fax": _n(p.fax)})
    new_id = r.scalar_one()
    await _audit(db, admin, "CREATE", "ref_fabricants", p.libelle.strip())
    await db.commit()
    return {"id": new_id, "libelle": p.libelle.strip(), "ville": _n(p.ville),
            "adresse": _n(p.adresse), "telephone": _n(p.telephone), "fax": _n(p.fax)}


@router.patch("/fabricants/{id}")
async def modifier_fabricant(id: int, p: FabricantIn, admin=Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "UPDATE ref_fabricants SET libelle=:libelle, ville=:ville, adresse=:adresse, "
        "telephone=:telephone, fax=:fax WHERE id=:id RETURNING id"),
        {"id": id, "libelle": p.libelle.strip(), "ville": _n(p.ville), "adresse": _n(p.adresse),
         "telephone": _n(p.telephone), "fax": _n(p.fax)})
    if not r.first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fabricant introuvable.")
    await _audit(db, admin, "UPDATE", "ref_fabricants", p.libelle.strip())
    await db.commit()
    return {"ok": True}


@router.delete("/fabricants/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_fabricant(id: int, admin=Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("DELETE FROM ref_fabricants WHERE id=:id RETURNING libelle"),
                         {"id": id})
    row = r.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fabricant introuvable.")
    await _audit(db, admin, "DELETE", "ref_fabricants", row[0])
    await db.commit()


# ==================================================================
#  CATEGORIES
# ==================================================================
@router.get("/categories")
async def liste_categories(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("SELECT id, libelle, domaine FROM ref_categories ORDER BY libelle"))
    return [dict(x) for x in r.mappings().all()]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def creer_categorie(p: CategorieIn, admin=Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    exists = await db.execute(text("SELECT 1 FROM ref_categories WHERE lower(libelle)=lower(:l)"),
                              {"l": p.libelle.strip()})
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette categorie existe deja.")
    r = await db.execute(text(
        "INSERT INTO ref_categories (libelle, domaine) VALUES (:libelle, :domaine) RETURNING id"),
        {"libelle": p.libelle.strip(), "domaine": _n(p.domaine)})
    new_id = r.scalar_one()
    await _audit(db, admin, "CREATE", "ref_categories", p.libelle.strip())
    await db.commit()
    return {"id": new_id, "libelle": p.libelle.strip(), "domaine": _n(p.domaine)}


@router.patch("/categories/{id}")
async def modifier_categorie(id: int, p: CategorieIn, admin=Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "UPDATE ref_categories SET libelle=:libelle, domaine=:domaine WHERE id=:id RETURNING id"),
        {"id": id, "libelle": p.libelle.strip(), "domaine": _n(p.domaine)})
    if not r.first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categorie introuvable.")
    await _audit(db, admin, "UPDATE", "ref_categories", p.libelle.strip())
    await db.commit()
    return {"ok": True}


@router.delete("/categories/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_categorie(id: int, admin=Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("DELETE FROM ref_categories WHERE id=:id RETURNING libelle"),
                         {"id": id})
    row = r.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categorie introuvable.")
    await _audit(db, admin, "DELETE", "ref_categories", row[0])
    await db.commit()


# ==================================================================
#  TYPES D'ECHANTILLON
# ==================================================================
@router.get("/types")
async def liste_types(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT t.id, t.libelle, "
        "  (SELECT COUNT(*) FROM ref_soustypes_echantillon s WHERE s.type_id = t.id) AS nb_soustypes "
        "FROM ref_types_echantillon t ORDER BY t.libelle"))
    return [dict(x) for x in r.mappings().all()]


@router.post("/types", status_code=status.HTTP_201_CREATED)
async def creer_type(p: TypeIn, admin=Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    exists = await db.execute(text("SELECT 1 FROM ref_types_echantillon WHERE lower(libelle)=lower(:l)"),
                              {"l": p.libelle.strip()})
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce type existe deja.")
    new_id = await _next_id(db, "ref_types_echantillon")
    await db.execute(text("INSERT INTO ref_types_echantillon (id, libelle) VALUES (:id, :libelle)"),
                     {"id": new_id, "libelle": p.libelle.strip()})
    await _audit(db, admin, "CREATE", "ref_types_echantillon", p.libelle.strip())
    await db.commit()
    return {"id": new_id, "libelle": p.libelle.strip(), "nb_soustypes": 0}


@router.patch("/types/{id}")
async def modifier_type(id: int, p: TypeIn, admin=Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "UPDATE ref_types_echantillon SET libelle=:libelle WHERE id=:id RETURNING id"),
        {"id": id, "libelle": p.libelle.strip()})
    if not r.first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Type introuvable.")
    await _audit(db, admin, "UPDATE", "ref_types_echantillon", p.libelle.strip())
    await db.commit()
    return {"ok": True}


@router.delete("/types/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_type(id: int, admin=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    # Respect de la relation : on refuse si des sous-types y sont rattaches.
    used = await db.execute(text(
        "SELECT COUNT(*) FROM ref_soustypes_echantillon WHERE type_id=:id"), {"id": id})
    n = used.scalar_one()
    if n:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ce type est utilise par {n} sous-type(s). Reaffectez ou supprimez-les d'abord.")
    r = await db.execute(text("DELETE FROM ref_types_echantillon WHERE id=:id RETURNING libelle"),
                         {"id": id})
    row = r.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Type introuvable.")
    await _audit(db, admin, "DELETE", "ref_types_echantillon", row[0])
    await db.commit()


# ==================================================================
#  SOUS-TYPES D'ECHANTILLON  (rattaches a un type)
# ==================================================================
@router.get("/soustypes")
async def liste_soustypes(type_id: int | None = None, admin=Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    sql = ("SELECT s.id, s.libelle, s.type_id, t.libelle AS type_libelle "
           "FROM ref_soustypes_echantillon s "
           "LEFT JOIN ref_types_echantillon t ON t.id = s.type_id ")
    params = {}
    if type_id is not None:
        sql += "WHERE s.type_id = :tid "
        params["tid"] = type_id
    sql += "ORDER BY t.libelle NULLS FIRST, s.libelle"
    r = await db.execute(text(sql), params)
    return [dict(x) for x in r.mappings().all()]


async def _type_existe(db, type_id):
    r = await db.execute(text("SELECT 1 FROM ref_types_echantillon WHERE id=:id"), {"id": type_id})
    return bool(r.first())


@router.post("/soustypes", status_code=status.HTTP_201_CREATED)
async def creer_soustype(p: SousTypeIn, admin=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    if not await _type_existe(db, p.type_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type parent inexistant.")
    exists = await db.execute(text(
        "SELECT 1 FROM ref_soustypes_echantillon "
        "WHERE lower(libelle)=lower(:l) AND type_id=:tid"),
        {"l": p.libelle.strip(), "tid": p.type_id})
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce sous-type existe deja pour ce type.")
    new_id = await _next_id(db, "ref_soustypes_echantillon")
    await db.execute(text(
        "INSERT INTO ref_soustypes_echantillon (id, libelle, type_id) "
        "VALUES (:id, :libelle, :tid)"),
        {"id": new_id, "libelle": p.libelle.strip(), "tid": p.type_id})
    await _audit(db, admin, "CREATE", "ref_soustypes_echantillon", p.libelle.strip(),
                 f"type_id={p.type_id}")
    await db.commit()
    return {"id": new_id, "libelle": p.libelle.strip(), "type_id": p.type_id}


@router.patch("/soustypes/{id}")
async def modifier_soustype(id: int, p: SousTypeIn, admin=Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    if not await _type_existe(db, p.type_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type parent inexistant.")
    r = await db.execute(text(
        "UPDATE ref_soustypes_echantillon SET libelle=:libelle, type_id=:tid "
        "WHERE id=:id RETURNING id"),
        {"id": id, "libelle": p.libelle.strip(), "tid": p.type_id})
    if not r.first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sous-type introuvable.")
    await _audit(db, admin, "UPDATE", "ref_soustypes_echantillon", p.libelle.strip(),
                 f"type_id={p.type_id}")
    await db.commit()
    return {"ok": True}


@router.delete("/soustypes/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_soustype(id: int, admin=Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("DELETE FROM ref_soustypes_echantillon WHERE id=:id RETURNING libelle"),
                         {"id": id})
    row = r.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sous-type introuvable.")
    await _audit(db, admin, "DELETE", "ref_soustypes_echantillon", row[0])
    await db.commit()


# ==================================================================
#  DELAIS DE TRAITEMENT (ref_delais, migration 013)
# ==================================================================
class DelaiIn(BaseModel):
    jours: int = Field(ge=1, le=365)


@router.get("/delais")
async def liste_delais(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("SELECT section, jours FROM ref_delais ORDER BY section"))
    return [dict(x) for x in r.mappings().all()]


@router.patch("/delais/{section}")
async def modifier_delai(section: str, p: DelaiIn, admin=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    if section not in ("SMA", "SCHA", "SSA"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Section inconnue.")
    await db.execute(text(
        "INSERT INTO ref_delais (section, jours) VALUES (:s, :j) "
        "ON CONFLICT (section) DO UPDATE SET jours = EXCLUDED.jours"),
        {"s": section, "j": p.jours})
    await _audit(db, admin, "UPDATE", "ref_delais", section, details=f"{p.jours} jours")
    await db.commit()
    return {"section": section, "jours": p.jours}


# ==================================================================
#  TARIFS DES ANALYSES (ref_tarifs, migrations 018 et 027)
#  Prix datés : ref_tarifs_prix (une période par changement de prix)
# ==================================================================
class TarifIn(BaseModel):
    nom_analyse: str = Field(min_length=1, max_length=150)
    section: str = Field(pattern="^(SMA|SCHA|SSA)$")
    prix: Decimal = Field(ge=0, le=1_000_000, max_digits=12, decimal_places=2)
    actif: bool = True
    par_prelevement: bool = False
    a_valider: bool = False
    date_effet: date | None = None   # début du nouveau prix (aujourd'hui par défaut)


def _tarif_sortie(x) -> dict:
    return {
        "id": x["tarif_id"], "nom_analyse": x["nom_analyse"], "section": x["section"],
        "prix": x["prix"], "depuis": x["date_debut"], "jusqu_au": x["date_fin"],
        "actif": x["actif"], "par_prelevement": x["par_prelevement"], "a_valider": x["a_valider"],
        "analyse_id": x["analyse_id"],
    }


@router.get("/tarifs")
async def liste_tarifs(date_ref: date | None = Query(None, alias="date"),
                       admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Grille à une date (aujourd'hui par défaut) : prix de la période qui couvre cette date."""
    lignes = await fact.grille_a_date(db, date_ref)
    r = await db.execute(text("SELECT tarif_id, count(*) AS n FROM ref_tarifs_prix GROUP BY tarif_id"))
    periodes = {x.tarif_id: x.n for x in r}
    return [{**_tarif_sortie(x), "nb_periodes": periodes.get(x["tarif_id"], 0)} for x in lignes]


@router.get("/tarifs/sans-prix")
async def tarifs_sans_prix(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Analyses du catalogue sans prix en vigueur (« prix à renseigner »)."""
    return await fact.analyses_sans_prix(db)


async def _tarif_existe(db, p: TarifIn, sauf_id: int | None = None) -> bool:
    r = await db.execute(text(
        "SELECT 1 FROM ref_tarifs WHERE lower(btrim(nom_analyse)) = lower(btrim(:a)) "
        "AND section = :s AND (CAST(:id AS INTEGER) IS NULL OR id <> :id)"),
        {"a": p.nom_analyse, "s": p.section, "id": sauf_id})
    return r.first() is not None


async def _analyse_id(db, p: TarifIn):
    r = await db.execute(text(
        "SELECT id FROM ref_analyses WHERE lower(btrim(nom_analyse)) = lower(btrim(:a)) AND section = :s "
        "ORDER BY id LIMIT 1"), {"a": p.nom_analyse, "s": p.section})
    return r.scalar()


@router.post("/tarifs", status_code=status.HTTP_201_CREATED)
async def creer_tarif(p: TarifIn, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if await _tarif_existe(db, p):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette analyse a déjà un tarif dans cette section.")
    r = await db.execute(text(
        "INSERT INTO ref_tarifs (nom_analyse, section, prix, actif, par_prelevement, a_valider, analyse_id) "
        "VALUES (:a, :s, :p, :act, :pp, :av, :aid) RETURNING id"),
        {"a": p.nom_analyse.strip(), "s": p.section, "p": p.prix, "act": p.actif,
         "pp": p.par_prelevement, "av": p.a_valider, "aid": await _analyse_id(db, p)})
    new_id = r.scalar_one()
    await fact.fixer_prix(db, new_id, p.prix, p.date_effet or date.today(), admin["username"])
    await _audit(db, admin, "CREATE", "ref_tarifs", new_id, f"{p.nom_analyse.strip()} ({p.section}) : {p.prix}")
    await db.commit()
    return {"id": new_id}


@router.patch("/tarifs/{tarif_id}")
async def modifier_tarif(tarif_id: int, p: TarifIn, admin=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    """Un prix différent ouvre une nouvelle période à la date d'effet ; l'ancienne est conservée."""
    if await _tarif_existe(db, p, tarif_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette analyse a déjà un tarif dans cette section.")
    r = await db.execute(text(
        "UPDATE ref_tarifs SET nom_analyse = :a, section = :s, actif = :act, par_prelevement = :pp, "
        "a_valider = :av, analyse_id = :aid WHERE id = :id RETURNING id"),
        {"a": p.nom_analyse.strip(), "s": p.section, "act": p.actif, "pp": p.par_prelevement,
         "av": p.a_valider, "aid": await _analyse_id(db, p), "id": tarif_id})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarif introuvable.")
    nouveau = await fact.fixer_prix(db, tarif_id, p.prix, p.date_effet or date.today(), admin["username"])
    details = f"{p.nom_analyse.strip()} ({p.section}) : {p.prix}"
    if nouveau:
        details += f" à partir du {(p.date_effet or date.today()):%d/%m/%Y}"
    await _audit(db, admin, "UPDATE", "ref_tarifs", tarif_id, details)
    await db.commit()
    return {"id": tarif_id, "nouvelle_periode": nouveau}


@router.get("/tarifs/{tarif_id}/historique")
async def historique_tarif(tarif_id: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await fact.historique_prix(db, tarif_id)


@router.delete("/tarifs/{tarif_id}", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_tarif(tarif_id: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Suppression seulement sans historique de prix ; sinon désactiver le tarif."""
    r = await db.execute(text("SELECT count(*) FROM ref_tarifs_prix WHERE tarif_id = :id"), {"id": tarif_id})
    if (r.scalar() or 0) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ce tarif a un historique de prix : désactivez-le plutôt que de le supprimer.")
    r = await db.execute(text("DELETE FROM ref_tarifs WHERE id = :id RETURNING id"), {"id": tarif_id})
    if r.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarif introuvable.")
    await _audit(db, admin, "DELETE", "ref_tarifs", tarif_id)
    await db.commit()
