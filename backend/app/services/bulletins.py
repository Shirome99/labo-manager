"""
Bulletins (factures) et avoirs (tâche 36).

  * brouillon : échantillons d'un même client ; ses lignes = lignes facturables encore non facturées
    de ces échantillons (vivantes, modifiables) ;
  * émission : numéro de la séquence annuelle (verrou consultatif : pas de trou ni de doublon),
    copie figée des lignes (factures_details), totaux HT / TVA / TTC, PDF archivé + SHA-256,
    lignes verrouillées (factures_lignes.facture_id) ; plus rien ne change ensuite ;
  * avoir : bulletin négatif lié à un bulletin émis (lignes choisies ou montant), motif obligatoire,
    émis aussitôt ; les lignes annulées redeviennent modifiables (corriger puis refacturer, ou retirer).
"""
import hashlib
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text

from app.services import facturation as fact
from app.services.pdf_facturation import pdf_bulletin

# Format des numéros (seul endroit à modifier) : séquence annuelle par type, jamais réutilisée
FORMATS_NUMERO = {"facture": "BUL-{annee}-{sequence:05d}", "avoir": "AV-{annee}-{sequence:05d}",
                  "quittance": "Q-{annee}-{sequence:05d}"}
VERROU_NUMEROTATION = 7_361_036   # clé de pg_advisory_xact_lock propre à la numérotation des bulletins


def numero(type_: str, annee: int, sequence: int) -> str:
    return FORMATS_NUMERO[type_].format(annee=annee, sequence=sequence)


async def _prochain_numero(db, type_: str, annee: int) -> tuple[int, str]:
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": VERROU_NUMEROTATION})
    if type_ == "quittance":
        r = await db.execute(text("SELECT coalesce(max(sequence), 0) + 1 FROM paiements WHERE annee = :a"), {"a": annee})
    else:
        r = await db.execute(text("SELECT coalesce(max(sequence), 0) + 1 FROM factures WHERE type = :t AND annee = :a"),
                             {"t": type_, "a": annee})
    seq = r.scalar_one()
    return seq, numero(type_, annee, seq)


def _norm(s) -> str:
    return " ".join(str(s or "").split()).lower()


# ------------------------------------------------------------------
#  Client d'un échantillon : « Nom du Client », sinon fabricant / propriétaire
# ------------------------------------------------------------------
async def client_echantillon(db, num: str) -> dict:
    r = await db.execute(text("""
        SELECT e."N° Echantillon" AS num, e."Nature de l'échantillon" AS nature, e."Date reception" AS reception,
               e."Nom du Client" AS client, e."Adresse du Client" AS adresse,
               e."Fabricant ou Propriétaire" AS fabricant, f.adresse AS f_adresse, f.ville AS f_ville
        FROM echantillons e
        LEFT JOIN LATERAL (SELECT adresse, ville FROM ref_fabricants rf
                           WHERE lower(btrim(rf.libelle)) = lower(btrim(e."Fabricant ou Propriétaire")) LIMIT 1) f ON true
        WHERE e."N° Echantillon" = :n
    """), {"n": num})
    x = r.mappings().first()
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Échantillon « {num} » introuvable.")
    nom = (x["client"] or "").strip() or (x["fabricant"] or "").strip() or None
    adresse = (x["adresse"] or "").strip()
    if not adresse and not (x["client"] or "").strip():
        adresse = ", ".join(v.strip() for v in (x["f_adresse"], x["f_ville"]) if v and v.strip())
    return {"num": x["num"], "nature": x["nature"], "reception": x["reception"], "client": nom,
            "adresse": adresse or None}


# ------------------------------------------------------------------
#  Lecture
# ------------------------------------------------------------------
_COLS_FACTURE = """id, numero, type, statut, annee, sequence, client_nom, client_adresse, facture_origine_id, motif,
                   taux_tva, total_ht, montant_tva, total_ttc, date_emission, cree_par, cree_le, emise_par,
                   emise_le, annulee_par, annulee_le, sha256"""


async def facture(db, fid: int, verrou: bool = False) -> dict:
    r = await db.execute(text(f"SELECT {_COLS_FACTURE} FROM factures WHERE id = :id"
                              + (" FOR UPDATE" if verrou else "")), {"id": fid})
    x = r.mappings().first()
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bulletin introuvable.")
    return dict(x)


async def echantillons_facture(db, fid: int) -> list[str]:
    r = await db.execute(text("SELECT num_echantillon FROM factures_echantillons WHERE facture_id = :id "
                              "ORDER BY num_echantillon"), {"id": fid})
    return [x[0] for x in r]


async def lignes_a_facturer(db, nums: list[str]) -> list[dict]:
    """Lignes facturables non encore portées par un bulletin émis."""
    if not nums:
        return []
    r = await db.execute(text("""
        SELECT l.id, l.num_echantillon, l.section, l.libelle AS analyse, l.quantite, l.prix_unitaire, l.montant
        FROM factures_lignes l
        WHERE l.num_echantillon = ANY(CAST(:n AS text[]))
          AND (l.facture_id IS NULL OR NOT EXISTS (SELECT 1 FROM factures f WHERE f.id = l.facture_id
                                                   AND f.statut = 'émis'))
        ORDER BY l.num_echantillon, l.section NULLS LAST, l.id
    """), {"n": nums})
    return [dict(x) for x in r.mappings().all()]


async def details(db, fid: int) -> list[dict]:
    r = await db.execute(text("""
        SELECT id, ligne_id, detail_origine_id, num_echantillon, section, libelle AS analyse, quantite,
               prix_unitaire, montant
        FROM factures_details WHERE facture_id = :id ORDER BY ordre, id
    """), {"id": fid})
    return [dict(x) for x in r.mappings().all()]


def calculer_totaux(lignes: list[dict], taux_tva) -> dict:
    ht = fact.arrondi(sum((Decimal(str(l["montant"])) for l in lignes), Decimal("0")))
    tva = fact.arrondi(ht * Decimal(str(taux_tva)) / 100)
    return {"total_ht": ht, "montant_tva": tva, "total_ttc": fact.arrondi(ht + tva)}


async def avoirs_de(db, fid: int) -> list[dict]:
    r = await db.execute(text(f"SELECT {_COLS_FACTURE} FROM factures WHERE facture_origine_id = :id "
                              "AND type = 'avoir' AND statut = 'émis' ORDER BY id"), {"id": fid})
    return [dict(x) for x in r.mappings().all()]


async def contenu(db, fid: int) -> dict:
    """Bulletin complet : en-tête, échantillons, lignes (vivantes si brouillon, figées sinon), totaux, avoirs."""
    f = await facture(db, fid)
    nums = await echantillons_facture(db, fid)
    if f["statut"] == "brouillon":
        lignes = await lignes_a_facturer(db, nums)
        params = await fact.lire_parametres(db)
        f.update(taux_tva=params["taux_tva"], **calculer_totaux(lignes, params["taux_tva"]))
    else:
        lignes = await details(db, fid)
    avoirs = await avoirs_de(db, fid) if f["type"] == "facture" else []
    total_avoirs = fact.arrondi(sum((Decimal(str(a["total_ttc"])) for a in avoirs), Decimal("0")))
    origine = None
    if f["facture_origine_id"]:
        o = await facture(db, f["facture_origine_id"])
        origine = {"id": o["id"], "numero": o["numero"], "date_emission": o["date_emission"], "total_ttc": o["total_ttc"]}
    c = {**f, "echantillons": nums, "lignes": lignes, "avoirs": avoirs, "total_avoirs": total_avoirs,
         "net": fact.arrondi(Decimal(str(f["total_ttc"])) + total_avoirs), "origine": origine,
         "sans_prix": [l["analyse"] for l in lignes if l["prix_unitaire"] is None]}
    c.update(await etat_paiement(db, c))
    return c


# ------------------------------------------------------------------
#  Paiements et exonération d'un bulletin (tâche 37)
# ------------------------------------------------------------------
STATUTS_PAIEMENT = ["Non payé", "Partiellement payé", "Payé", "Exonéré", "Avoir total"]


async def paiements_de(db, fid: int) -> list[dict]:
    r = await db.execute(text("""
        SELECT id, facture_id, date_paiement, montant, mode, reference, banque, numero_quittance, trop_percu,
               observation, statut, motif_annulation, encaisse_par, cree_le, annule_par, annule_le, sha256
        FROM paiements WHERE facture_id = :f ORDER BY date_paiement, id
    """), {"f": fid})
    return [dict(x) for x in r.mappings().all()]


async def exoneration(db, facture_id: int | None = None, num: str | None = None) -> dict | None:
    r = await db.execute(text("""
        SELECT id, facture_id, num_echantillon, type, motif, montant, accorde_par, accorde_le
        FROM exonerations WHERE statut = 'valide'
          AND (facture_id = CAST(:f AS INTEGER) OR num_echantillon = CAST(:n AS TEXT))
    """), {"f": facture_id, "n": num})
    x = r.mappings().first()
    return dict(x) if x else None


async def etat_paiement(db, c: dict) -> dict:
    """
    Statut de paiement d'un bulletin émis : Exonéré (exonération en vigueur), Avoir total (net <= 0),
    Payé (encaissé >= net), Partiellement payé, Non payé. Encaissements annulés exclus.
    """
    if c["type"] != "facture" or c["statut"] != "émis":
        return {"paiements": [], "exoneration": None, "paye": None, "reste": None, "trop_percu": None,
                "statut_paiement": None}
    paiements = await paiements_de(db, c["id"])
    paye = fact.arrondi(sum((Decimal(str(p["montant"])) for p in paiements if p["statut"] == "valide"), Decimal("0")))
    net = Decimal(str(c["net"]))
    exo = await exoneration(db, facture_id=c["id"])
    if exo:
        statut = "Exonéré"
    elif net <= 0:
        statut = "Avoir total"
    elif paye >= net:
        statut = "Payé"
    elif paye > 0:
        statut = "Partiellement payé"
    else:
        statut = "Non payé"
    reste = Decimal("0.00") if statut in ("Exonéré", "Avoir total") else fact.arrondi(max(net - paye, Decimal("0")))
    return {"paiements": paiements, "exoneration": exo, "paye": paye, "reste": reste,
            "trop_percu": fact.arrondi(max(paye - max(net, Decimal("0")), Decimal("0"))), "statut_paiement": statut}


# ------------------------------------------------------------------
#  Brouillon
# ------------------------------------------------------------------
async def _controler_echantillons(db, nums: list[str], sauf_facture: int | None = None) -> dict:
    """Mêmes client pour tous, aucun dans un autre brouillon ; renvoie le client commun."""
    if not nums:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choisissez au moins un échantillon.")
    clients = [await client_echantillon(db, n) for n in dict.fromkeys(nums)]
    noms = {_norm(c["client"]) for c in clients}
    if len(noms) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Un bulletin ne regroupe que des échantillons d'un même client : "
                            + ", ".join(f"{c['num']} ({c['client'] or 'client non renseigné'})" for c in clients) + ".")
    r = await db.execute(text("""
        SELECT fe.num_echantillon FROM factures_echantillons fe JOIN factures f ON f.id = fe.facture_id
        WHERE f.statut = 'brouillon' AND fe.num_echantillon = ANY(CAST(:n AS text[]))
          AND (CAST(:s AS INTEGER) IS NULL OR f.id <> :s)
    """), {"n": list(nums), "s": sauf_facture})
    deja = [x[0] for x in r]
    exoneres = [n for n in nums if await exoneration(db, num=n)]
    if exoneres:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Échantillon exonéré, rien à facturer : " + ", ".join(exoneres) + ".")
    if deja:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Déjà dans un bulletin en brouillon : " + ", ".join(deja) + ".")
    return clients[0]


async def creer_brouillon(db, nums: list[str], utilisateur: str, client_nom=None, client_adresse=None) -> int:
    nums = list(dict.fromkeys(nums))
    client = await _controler_echantillons(db, nums)
    if not await lignes_a_facturer(db, nums):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aucune ligne à facturer pour ces échantillons.")
    r = await db.execute(text("""
        INSERT INTO factures (type, statut, client_nom, client_adresse, cree_par)
        VALUES ('facture', 'brouillon', :c, :a, :u) RETURNING id
    """), {"c": client_nom or client["client"], "a": client_adresse or client["adresse"], "u": utilisateur})
    fid = r.scalar_one()
    for n in nums:
        await db.execute(text("INSERT INTO factures_echantillons (facture_id, num_echantillon) VALUES (:f, :n)"),
                         {"f": fid, "n": n})
    return fid


def exiger_brouillon(f: dict):
    if f["statut"] != "brouillon":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Un bulletin émis n'est plus modifiable : faites un avoir." if f["statut"] == "émis"
                            else "Ce bulletin est annulé.")


async def modifier_brouillon(db, fid: int, nums: list[str] | None, client_nom, client_adresse):
    f = await facture(db, fid, verrou=True)
    exiger_brouillon(f)
    if nums is not None:
        nums = list(dict.fromkeys(nums))
        await _controler_echantillons(db, nums, sauf_facture=fid)
        await db.execute(text("DELETE FROM factures_echantillons WHERE facture_id = :f AND NOT "
                              "(num_echantillon = ANY(CAST(:n AS text[])))"), {"f": fid, "n": nums})
        for n in nums:
            await db.execute(text("INSERT INTO factures_echantillons (facture_id, num_echantillon) VALUES (:f, :n) "
                                  "ON CONFLICT DO NOTHING"), {"f": fid, "n": n})
    await db.execute(text("UPDATE factures SET client_nom = coalesce(:c, client_nom), "
                          "client_adresse = coalesce(:a, client_adresse) WHERE id = :f"),
                     {"c": client_nom, "a": client_adresse, "f": fid})


async def annuler_brouillon(db, fid: int, utilisateur: str):
    f = await facture(db, fid, verrou=True)
    exiger_brouillon(f)
    await db.execute(text("UPDATE factures SET statut = 'annulé', annulee_par = :u, annulee_le = now() WHERE id = :f"),
                     {"u": utilisateur, "f": fid})
    # les échantillons sont libérés (ils peuvent entrer dans un autre bulletin)
    await db.execute(text("DELETE FROM factures_echantillons WHERE facture_id = :f"), {"f": fid})


# ------------------------------------------------------------------
#  PDF
# ------------------------------------------------------------------
async def _infos_echantillons(db, nums: list[str]) -> list[dict]:
    return [await client_echantillon(db, n) for n in nums]


async def generer_pdf(db, c: dict) -> bytes:
    params = await fact.lire_parametres(db)
    return pdf_bulletin(c, await _infos_echantillons(db, c["echantillons"]),
                        taux_tva=c["taux_tva"] if c["statut"] != "brouillon" else params["taux_tva"])


async def _archiver(db, fid: int, pdf: bytes):
    await db.execute(text("UPDATE factures SET pdf = :p, sha256 = :h WHERE id = :f"),
                     {"p": pdf, "h": hashlib.sha256(pdf).hexdigest(), "f": fid})


async def pdf_archive(db, fid: int) -> tuple[bytes, str]:
    r = await db.execute(text("SELECT pdf, sha256 FROM factures WHERE id = :f"), {"f": fid})
    x = r.first()
    return bytes(x.pdf), x.sha256


# ------------------------------------------------------------------
#  Émission
# ------------------------------------------------------------------
async def emettre(db, fid: int, utilisateur: str) -> dict:
    f = await facture(db, fid, verrou=True)
    exiger_brouillon(f)
    nums = await echantillons_facture(db, fid)
    lignes = await lignes_a_facturer(db, nums)
    if not lignes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aucune ligne à facturer : le bulletin ne peut pas être émis.")
    sans_prix = [f"{l['analyse']} ({l['num_echantillon']})" for l in lignes if l["prix_unitaire"] is None]
    if sans_prix:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Prix à renseigner avant l'émission : " + ", ".join(sans_prix) + ".")
    params = await fact.lire_parametres(db)
    totaux = calculer_totaux(lignes, params["taux_tva"])
    aujourd_hui = date.today()
    seq, num = await _prochain_numero(db, "facture", aujourd_hui.year)
    for i, l in enumerate(lignes):
        await db.execute(text("""
            INSERT INTO factures_details (facture_id, ligne_id, num_echantillon, section, libelle, quantite,
                                          prix_unitaire, montant, ordre)
            VALUES (:f, :l, :n, :s, :a, :q, :pu, :m, :o)
        """), {"f": fid, "l": l["id"], "n": l["num_echantillon"], "s": l["section"], "a": l["analyse"],
               "q": l["quantite"], "pu": l["prix_unitaire"], "m": l["montant"], "o": i})
        await db.execute(text("UPDATE factures_lignes SET facture_id = :f WHERE id = :l"), {"f": fid, "l": l["id"]})
    await db.execute(text("""
        UPDATE factures SET statut = 'émis', numero = :num, annee = :a, sequence = :s, taux_tva = :t,
               total_ht = :ht, montant_tva = :tva, total_ttc = :ttc, date_emission = :d,
               emise_par = :u, emise_le = :le, pdf = '', sha256 = '-'
        WHERE id = :f
    """), {"num": num, "a": aujourd_hui.year, "s": seq, "t": params["taux_tva"], "ht": totaux["total_ht"],
           "tva": totaux["montant_tva"], "ttc": totaux["total_ttc"], "d": aujourd_hui, "u": utilisateur,
           "le": datetime.now(), "f": fid})
    # (PDF provisoire ci-dessus pour la contrainte « émis => PDF », remplacé dans la même transaction)
    c = await contenu(db, fid)
    await _archiver(db, fid, await generer_pdf(db, c))
    return await contenu(db, fid)


# ------------------------------------------------------------------
#  Avoir
# ------------------------------------------------------------------
async def creer_avoir(db, fid: int, motif: str, utilisateur: str, detail_ids: list[int] | None = None,
                      montant=None) -> dict:
    origine = await facture(db, fid, verrou=True)
    if origine["type"] != "facture" or origine["statut"] != "émis":
        raise HTTPException(status.HTTP_409_CONFLICT, "Un avoir ne se fait que sur un bulletin émis.")
    if not (motif or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le motif de l'avoir est obligatoire.")
    if bool(detail_ids) == (montant is not None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choisissez les lignes à annuler ou un montant, pas les deux.")
    lignes_origine = {d["id"]: d for d in await details(db, fid)}
    r = await db.execute(text("""
        SELECT d.detail_origine_id FROM factures_details d JOIN factures a ON a.id = d.facture_id
        WHERE a.facture_origine_id = :f AND a.statut = 'émis' AND d.detail_origine_id IS NOT NULL
    """), {"f": fid})
    deja = {x[0] for x in r}
    deja_credite = -sum((Decimal(str(a["total_ht"])) for a in await avoirs_de(db, fid)), Decimal("0"))
    reste_ht = fact.arrondi(Decimal(str(origine["total_ht"])) - deja_credite)
    a_creer = []
    if detail_ids:
        for did in dict.fromkeys(detail_ids):
            d = lignes_origine.get(did)
            if d is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"La ligne {did} n'appartient pas à ce bulletin.")
            if did in deja:
                raise HTTPException(status.HTTP_409_CONFLICT, f"La ligne « {d['analyse']} » a déjà fait l'objet d'un avoir.")
            a_creer.append({**d, "quantite": d["quantite"], "montant": -Decimal(str(d["montant"])),
                            "detail_origine_id": did})
    else:
        m = fact.arrondi(montant)
        if m <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le montant de l'avoir doit être positif.")
        a_creer.append({"ligne_id": None, "num_echantillon": None, "section": None,
                        "analyse": f"Avoir sur le bulletin n° {origine['numero']}", "quantite": 1,
                        "prix_unitaire": -m, "montant": -m, "detail_origine_id": None})
    total_ht = -sum((Decimal(str(d["montant"])) for d in a_creer), Decimal("0"))
    if total_ht > reste_ht:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"L'avoir ({fact.format_dh(total_ht)}) dépasse le montant restant du bulletin "
                            f"({fact.format_dh(reste_ht)}).")
    totaux = calculer_totaux(a_creer, origine["taux_tva"])
    aujourd_hui = date.today()
    seq, num = await _prochain_numero(db, "avoir", aujourd_hui.year)
    r = await db.execute(text("""
        INSERT INTO factures (numero, type, statut, annee, sequence, client_nom, client_adresse, facture_origine_id,
                              motif, taux_tva, total_ht, montant_tva, total_ttc, date_emission, cree_par, emise_par,
                              emise_le, pdf, sha256)
        VALUES (:num, 'avoir', 'émis', :a, :s, :c, :adr, :o, :m, :t, :ht, :tva, :ttc, :d, :u, :u, now(), '', '-')
        RETURNING id
    """), {"num": num, "a": aujourd_hui.year, "s": seq, "c": origine["client_nom"], "adr": origine["client_adresse"],
           "o": fid, "m": motif.strip(), "t": origine["taux_tva"], "ht": totaux["total_ht"],
           "tva": totaux["montant_tva"], "ttc": totaux["total_ttc"], "d": aujourd_hui, "u": utilisateur})
    aid = r.scalar_one()
    for n in await echantillons_facture(db, fid):
        await db.execute(text("INSERT INTO factures_echantillons (facture_id, num_echantillon) VALUES (:f, :n)"),
                         {"f": aid, "n": n})
    for i, d in enumerate(a_creer):
        await db.execute(text("""
            INSERT INTO factures_details (facture_id, ligne_id, detail_origine_id, num_echantillon, section, libelle,
                                          quantite, prix_unitaire, montant, ordre)
            VALUES (:f, NULL, :o, :n, :s, :a, :q, :pu, :m, :i)
        """), {"f": aid, "o": d["detail_origine_id"], "n": d["num_echantillon"], "s": d["section"], "a": d["analyse"],
               "q": d["quantite"], "pu": d["prix_unitaire"], "m": d["montant"], "i": i})
        # la ligne annulée redevient modifiable (à corriger puis refacturer, ou à retirer)
        if d.get("ligne_id"):
            await db.execute(text("UPDATE factures_lignes SET facture_id = NULL WHERE id = :l AND facture_id = :f"),
                             {"l": d["ligne_id"], "f": fid})
    c = await contenu(db, aid)
    await _archiver(db, aid, await generer_pdf(db, c))
    return await contenu(db, aid)
