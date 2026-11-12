"""
Encaissements, quittances, exonérations et statut de paiement des échantillons (tâche 37).

  * un encaissement porte sur un bulletin émis ; paiements partiels acceptés ; un montant au-delà
    du reste dû exige une confirmation explicite (trop-perçu signalé) ;
  * jamais de suppression : annulation (statut 'annulé' + motif), réservée aux responsables ;
  * exonération d'un bulletin ou d'un échantillon : motif obligatoire, responsables ;
  * le statut calculé de chaque échantillon est recopié dans les champs historiques (migration 012) :
    « Payement » (statut), « TOTAL » (montant dû), « Montant payé », « Mode de paiement »,
    « Date de payement », « N° QUITTANCE », « DATE » — ils alimentent déjà la liste, l'export et le reporting.
"""
import hashlib
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text

from app.services import bulletins, facturation as fact
from app.services.pdf_facturation import pdf_quittance

MODES = ("espèces", "chèque", "virement", "autre")
TYPES_EXONERATION = ("contrôle officiel", "convention", "autre")


# ------------------------------------------------------------------
#  Encaissement
# ------------------------------------------------------------------
async def encaisser(db, fid: int, utilisateur: str, date_paiement: date, montant, mode: str, reference=None,
                    banque=None, numero_quittance=None, observation=None, confirmer_trop_percu=False) -> dict:
    f = await bulletins.facture(db, fid, verrou=True)
    if f["type"] != "facture" or f["statut"] != "émis":
        raise HTTPException(status.HTTP_409_CONFLICT, "Un encaissement ne se fait que sur un bulletin émis.")
    c = await bulletins.contenu(db, fid)
    if c["statut_paiement"] == "Exonéré":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ce bulletin est exonéré : aucun encaissement.")
    montant = fact.arrondi(montant)
    if montant <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le montant encaissé doit être positif.")
    if date_paiement > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date du paiement ne peut pas être dans le futur.")
    trop = montant > c["reste"]
    if trop and not confirmer_trop_percu:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Le montant ({fact.format_dh(montant)}) dépasse le reste dû ({fact.format_dh(c['reste'])}). "
                            "Confirmez pour enregistrer un trop-perçu.")
    numero_quittance = (numero_quittance or "").strip() or None
    annee = seq = None
    if numero_quittance:
        r = await db.execute(text("SELECT 1 FROM paiements WHERE numero_quittance = :q"), {"q": numero_quittance})
        if r.first():
            raise HTTPException(status.HTTP_409_CONFLICT, f"La quittance n° {numero_quittance} existe déjà.")
    else:
        annee = date.today().year
        seq, numero_quittance = await bulletins._prochain_numero(db, "quittance", annee)
    r = await db.execute(text("""
        INSERT INTO paiements (facture_id, date_paiement, montant, mode, reference, banque, numero_quittance, annee,
                               sequence, trop_percu, observation, encaisse_par)
        VALUES (:f, :d, :m, :mode, :ref, :b, :q, :a, :s, :t, :o, :u) RETURNING id
    """), {"f": fid, "d": date_paiement, "m": montant, "mode": mode, "ref": (reference or "").strip() or None,
           "b": (banque or "").strip() or None, "q": numero_quittance, "a": annee, "s": seq, "t": trop,
           "o": (observation or "").strip() or None, "u": utilisateur})
    pid = r.scalar_one()
    c = await bulletins.contenu(db, fid)
    p = next(x for x in c["paiements"] if x["id"] == pid)
    pdf = pdf_quittance(p, c, await bulletins._infos_echantillons(db, c["echantillons"]))
    await db.execute(text("UPDATE paiements SET pdf = :p, sha256 = :h WHERE id = :id"),
                     {"p": pdf, "h": hashlib.sha256(pdf).hexdigest(), "id": pid})
    await recalculer_echantillons(db, c["echantillons"])
    return {"paiement_id": pid, "numero_quittance": numero_quittance, **await bulletins.contenu(db, fid)}


async def paiement(db, pid: int) -> dict:
    r = await db.execute(text("SELECT id, facture_id, statut, numero_quittance, montant FROM paiements WHERE id = :id"),
                         {"id": pid})
    x = r.mappings().first()
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encaissement introuvable.")
    return dict(x)


async def annuler_paiement(db, pid: int, motif: str, utilisateur: str) -> dict:
    p = await paiement(db, pid)
    if p["statut"] != "valide":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet encaissement est déjà annulé.")
    if not (motif or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le motif de l'annulation est obligatoire.")
    await db.execute(text("""
        UPDATE paiements SET statut = 'annulé', motif_annulation = :m, annule_par = :u, annule_le = now() WHERE id = :id
    """), {"m": motif.strip(), "u": utilisateur, "id": pid})
    c = await bulletins.contenu(db, p["facture_id"])
    await recalculer_echantillons(db, c["echantillons"])
    return c


async def quittance_pdf(db, pid: int) -> tuple[bytes, str, str]:
    r = await db.execute(text("SELECT pdf, sha256, numero_quittance FROM paiements WHERE id = :id"), {"id": pid})
    x = r.first()
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encaissement introuvable.")
    return bytes(x.pdf), x.sha256, x.numero_quittance


# ------------------------------------------------------------------
#  Exonération
# ------------------------------------------------------------------
async def exonerer_facture(db, fid: int, type_: str, motif: str, utilisateur: str) -> dict:
    f = await bulletins.facture(db, fid, verrou=True)
    if f["type"] != "facture" or f["statut"] != "émis":
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un bulletin émis peut être exonéré.")
    c = await bulletins.contenu(db, fid)
    if c["exoneration"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce bulletin est déjà exonéré.")
    await db.execute(text("""
        INSERT INTO exonerations (facture_id, type, motif, montant, accorde_par) VALUES (:f, :t, :m, :mt, :u)
    """), {"f": fid, "t": type_, "m": motif.strip(), "mt": c["reste"], "u": utilisateur})
    await recalculer_echantillons(db, c["echantillons"])
    return await bulletins.contenu(db, fid)


async def exonerer_echantillon(db, num: str, type_: str, motif: str, utilisateur: str):
    if await bulletins.exoneration(db, num=num):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet échantillon est déjà exonéré.")
    r = await db.execute(text("""
        SELECT f.id, f.numero, f.statut FROM factures f JOIN factures_echantillons fe ON fe.facture_id = f.id
        WHERE fe.num_echantillon = :n AND f.type = 'facture' AND f.statut IN ('brouillon', 'émis')
    """), {"n": num})
    for x in r.all():
        if x.statut == "brouillon":
            raise HTTPException(status.HTTP_409_CONFLICT, "Cet échantillon est dans un bulletin en brouillon : "
                                                          "retirez-le ou abandonnez le brouillon d'abord.")
        if (await bulletins.contenu(db, x.id))["reste"] > 0:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Cet échantillon figure sur le bulletin émis {x.numero} : exonérez le bulletin.")
    lignes = await bulletins.lignes_a_facturer(db, [num])
    montant = fact.arrondi(sum((Decimal(str(l["montant"])) for l in lignes), Decimal("0")))
    await db.execute(text("""
        INSERT INTO exonerations (num_echantillon, type, motif, montant, accorde_par) VALUES (:n, :t, :m, :mt, :u)
    """), {"n": num, "t": type_, "m": motif.strip(), "mt": montant, "u": utilisateur})
    await recalculer_echantillons(db, [num])


async def annuler_exoneration(db, eid: int, motif: str, utilisateur: str) -> dict:
    r = await db.execute(text("SELECT id, facture_id, num_echantillon, statut FROM exonerations WHERE id = :id"),
                         {"id": eid})
    e = r.mappings().first()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exonération introuvable.")
    if e["statut"] != "valide":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette exonération est déjà annulée.")
    if not (motif or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le motif de l'annulation est obligatoire.")
    await db.execute(text("""
        UPDATE exonerations SET statut = 'annulé', motif_annulation = :m, annule_par = :u, annule_le = now()
        WHERE id = :id
    """), {"m": motif.strip(), "u": utilisateur, "id": eid})
    nums = [e["num_echantillon"]] if e["num_echantillon"] else await bulletins.echantillons_facture(db, e["facture_id"])
    await recalculer_echantillons(db, nums)
    return dict(e)


# ------------------------------------------------------------------
#  Statut de paiement d'un échantillon
# ------------------------------------------------------------------
async def etat_echantillon(db, num: str) -> dict:
    """
    Montant dû, encaissé et statut de l'échantillon, à partir de ses bulletins émis et de ses lignes
    non encore facturées. Un bulletin qui regroupe plusieurs échantillons est réparti au prorata
    de la part de chaque échantillon dans son total HT (arrondi au centime).
    """
    exo = await bulletins.exoneration(db, num=num)
    non_facture = fact.arrondi(sum((Decimal(str(l["montant"])) for l in await bulletins.lignes_a_facturer(db, [num])),
                                   Decimal("0")))
    r = await db.execute(text("""
        SELECT f.id, f.total_ht,
               (SELECT coalesce(sum(d.montant), 0) FROM factures_details d
                 WHERE d.facture_id = f.id AND d.num_echantillon = :n) AS part_ht,
               (SELECT count(*) FROM factures_echantillons x WHERE x.facture_id = f.id) AS nb
        FROM factures f JOIN factures_echantillons fe ON fe.facture_id = f.id
        WHERE fe.num_echantillon = :n AND f.type = 'facture' AND f.statut = 'émis'
        ORDER BY f.id
    """), {"n": num})
    du = paye = Decimal("0")
    statuts, derniers = [], []
    for x in r.all():
        c = await bulletins.contenu(db, x.id)
        part = (Decimal(str(x.part_ht)) / Decimal(str(x.total_ht))) if x.total_ht else Decimal(1) / x.nb
        statuts.append(c["statut_paiement"])
        derniers += [p for p in c["paiements"] if p["statut"] == "valide"]
        if c["statut_paiement"] not in ("Exonéré", "Avoir total"):
            du += fact.arrondi(Decimal(str(c["net"])) * part)
        paye += fact.arrondi(c["paye"] * part)
    du = fact.arrondi(du + (0 if exo else non_facture))
    if exo:
        statut = "Exonéré"
    elif not statuts and non_facture == 0:
        statut = "Non concerné"
    elif du <= 0:
        statut = "Exonéré" if "Exonéré" in statuts else "Avoir total" if "Avoir total" in statuts else "Non concerné"
    elif paye >= du:
        statut = "Payé"
    elif paye > 0:
        statut = "Partiellement payé"
    else:
        statut = "Non payé"
    dernier = max(derniers, key=lambda p: (p["date_paiement"], p["id"])) if derniers else None
    return {"statut": statut, "du": du, "paye": fact.arrondi(paye), "reste": fact.arrondi(max(du - paye, Decimal("0"))),
            "non_facture": non_facture, "exoneration": exo, "dernier_paiement": dernier}


async def facturation_active(db, num: str) -> bool:
    """L'échantillon a une activité de facturation (lignes, bulletin ou exonération) : son statut est calculé."""
    r = await db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM factures_lignes WHERE num_echantillon = :n)
            OR EXISTS (SELECT 1 FROM factures_echantillons WHERE num_echantillon = :n)
            OR EXISTS (SELECT 1 FROM exonerations WHERE num_echantillon = :n)
    """), {"n": num})
    return bool(r.scalar())


async def recalculer_echantillons(db, nums):
    """Recopie l'état calculé dans les champs historiques de paiement de chaque échantillon."""
    for num in dict.fromkeys(n for n in nums if n):
        e = await etat_echantillon(db, num)
        d = e["dernier_paiement"]
        await db.execute(text("""
            UPDATE echantillons SET "Payement" = :s, "TOTAL" = :t, "Montant payé" = :p, "Mode de paiement" = :m,
                   "Date de payement" = :dp, "N° QUITTANCE" = :q, "DATE" = :dq
            WHERE "N° Echantillon" = :n
        """), {"s": e["statut"], "t": f"{e['du']:.2f}", "p": e["paye"], "m": d["mode"] if d else None,
               "dp": d["date_paiement"] if d else None, "q": d["numero_quittance"] if d else None,
               "dq": d["date_paiement"].strftime("%d/%m/%Y") if d else None, "n": num})


# ------------------------------------------------------------------
#  Paiement exigé à une étape (tâche 38, réglage facturation.etape_paiement)
# ------------------------------------------------------------------
STATUTS_REGLES = ("Payé", "Exonéré", "Avoir total")
LIBELLE_ETAPE = {"mise_en_analyse": "avant la mise en analyse", "remise_rapport": "avant la remise du rapport"}


async def exiger_paiement(db, num: str, etape: str):
    """
    Réglage « aucune » (défaut) : ne bloque rien. Sinon, à l'étape configurée, un échantillon ni payé
    ni exonéré (ni soldé par avoir) est refusé avec un message clair (409).
    """
    if (await fact.lire_parametres(db))["etape_paiement"] != etape:
        return
    e = await etat_echantillon(db, num)
    if e["statut"] not in STATUTS_REGLES:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Paiement exigé {LIBELLE_ETAPE[etape]} : l'échantillon {num} est « {e['statut']} »"
                            + (f" (reste dû {fact.format_dh(e['reste'])})" if e["reste"] > 0 else "")
                            + ". Facturez et encaissez le bulletin, ou faites exonérer l'échantillon.")


# ------------------------------------------------------------------
#  Bulletins impayés (notifications, page Impayés)
# ------------------------------------------------------------------
SQL_IMPAYES = """
    WITH b AS (
        SELECT f.id, f.numero, f.client_nom, f.date_emission, f.total_ttc,
               f.total_ttc + coalesce((SELECT sum(a.total_ttc) FROM factures a WHERE a.facture_origine_id = f.id
                                        AND a.type = 'avoir' AND a.statut = 'émis'), 0) AS net,
               coalesce((SELECT sum(p.montant) FROM paiements p WHERE p.facture_id = f.id
                          AND p.statut = 'valide'), 0) AS paye,
               (SELECT string_agg(fe.num_echantillon, ', ' ORDER BY fe.num_echantillon) FROM factures_echantillons fe
                 WHERE fe.facture_id = f.id) AS echantillons
        FROM factures f
        WHERE f.type = 'facture' AND f.statut = 'émis'
          AND NOT EXISTS (SELECT 1 FROM exonerations x WHERE x.facture_id = f.id AND x.statut = 'valide')
    )
    SELECT id, numero, client_nom, date_emission, echantillons, net, paye, net - paye AS reste,
           (CAST(:auj AS DATE) - date_emission) AS jours
    FROM b WHERE net > 0 AND paye < net
"""


async def bulletins_impayes(db, depuis_jours: int = 0, au: date | None = None) -> list[dict]:
    """Bulletins émis non soldés (ni exonérés, ni soldés par avoir), émis depuis au moins depuis_jours."""
    r = await db.execute(text(SQL_IMPAYES + " AND (CAST(:auj AS DATE) - date_emission) >= :j "
                                            "ORDER BY date_emission, id"),
                         {"auj": au or date.today(), "j": depuis_jours})
    return [dict(x) for x in r.mappings().all()]


# ------------------------------------------------------------------
#  Liste des bulletins avec leur statut de paiement (page Facturation, reporting)
# ------------------------------------------------------------------
SQL_BULLETINS = """
    SELECT b.*,
           CASE WHEN b.net IS NULL THEN NULL WHEN b.exonere THEN 'Exonéré' WHEN b.net <= 0 THEN 'Avoir total'
                WHEN b.paye >= b.net THEN 'Payé' WHEN b.paye > 0 THEN 'Partiellement payé' ELSE 'Non payé' END
               AS statut_paiement,
           CASE WHEN b.net IS NULL OR b.exonere OR b.net <= 0 THEN 0 ELSE greatest(b.net - b.paye, 0) END AS reste
    FROM (
        SELECT f.id, f.numero, f.type, f.statut, f.client_nom, f.total_ht, f.montant_tva, f.total_ttc, f.date_emission,
               f.cree_par, f.cree_le, f.emise_par, f.emise_le, f.facture_origine_id, f.motif, f.sha256,
               (SELECT string_agg(num_echantillon, ', ' ORDER BY num_echantillon) FROM factures_echantillons fe
                 WHERE fe.facture_id = f.id) AS echantillons,
               CASE WHEN f.type = 'facture' AND f.statut = 'émis' THEN f.total_ttc + coalesce((
                   SELECT sum(a.total_ttc) FROM factures a WHERE a.facture_origine_id = f.id AND a.type = 'avoir'
                      AND a.statut = 'émis'), 0) END AS net,
               CASE WHEN f.type = 'facture' AND f.statut = 'émis' THEN coalesce((
                   SELECT sum(p.montant) FROM paiements p WHERE p.facture_id = f.id AND p.statut = 'valide'), 0) END AS paye,
               EXISTS (SELECT 1 FROM exonerations x WHERE x.facture_id = f.id AND x.statut = 'valide') AS exonere
        FROM factures f
    ) b
"""
COLONNE_SECTION = {"SMA": '"SMA"', "SCHA": '"SCHA"', "SSA": '"SSA"'}


# ------------------------------------------------------------------
#  Impayés par client, par ancienneté (page Facturation)
# ------------------------------------------------------------------
TRANCHES = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("plus de 90", 91, None)]


async def impayes_par_client(db, au: date | None = None) -> dict:
    """Reste dû des bulletins émis non soldés, par client et par ancienneté (jours depuis l'émission)."""
    lignes = await bulletins_impayes(db, 0, au)
    clients: dict[str, dict] = {}
    for b in lignes:
        tranche = next(t for t, mini, maxi in TRANCHES if b["jours"] >= mini and (maxi is None or b["jours"] <= maxi))
        b["tranche"] = tranche
        c = clients.setdefault(b["client_nom"] or "Client non renseigné",
                               {"client": b["client_nom"] or "Client non renseigné", "nb": 0, "total": Decimal("0"),
                                **{t: Decimal("0") for t, _, _ in TRANCHES}})
        c["nb"] += 1
        c[tranche] += Decimal(str(b["reste"]))
        c["total"] += Decimal(str(b["reste"]))
    lignes_clients = sorted(clients.values(), key=lambda c: (-c["total"], c["client"]))
    totaux = {t: fact.arrondi(sum((c[t] for c in lignes_clients), Decimal("0"))) for t, _, _ in TRANCHES}
    totaux["total"] = fact.arrondi(sum((c["total"] for c in lignes_clients), Decimal("0")))
    return {"tranches": [t for t, _, _ in TRANCHES], "clients": lignes_clients, "bulletins": lignes,
            "totaux": totaux, "au": au or date.today()}


# ------------------------------------------------------------------
#  Journal de caisse (encaissements d'une période, totaux par mode)
# ------------------------------------------------------------------
async def journal_caisse(db, du: date, au: date) -> dict:
    """Encaissements valides de la période (date du paiement), totaux par mode ; annulés listés à part, exclus."""
    r = await db.execute(text("""
        SELECT p.id, p.date_paiement, p.numero_quittance, p.montant, p.mode, p.reference, p.banque, p.encaisse_par,
               p.trop_percu, p.statut, p.motif_annulation, p.annule_par, f.id AS facture_id, f.numero AS bulletin,
               f.client_nom
        FROM paiements p JOIN factures f ON f.id = p.facture_id
        WHERE p.date_paiement BETWEEN :du AND :au
        ORDER BY p.date_paiement, p.id
    """), {"du": du, "au": au})
    tous = [dict(x) for x in r.mappings().all()]
    valides = [p for p in tous if p["statut"] == "valide"]
    par_mode = {m: {"nb": 0, "montant": Decimal("0.00")} for m in MODES}
    for p in valides:
        par_mode[p["mode"]]["nb"] += 1
        par_mode[p["mode"]]["montant"] = fact.arrondi(par_mode[p["mode"]]["montant"] + Decimal(str(p["montant"])))
    return {"du": du, "au": au, "paiements": valides, "annules": [p for p in tous if p["statut"] != "valide"],
            "par_mode": par_mode, "nb": len(valides),
            "total": fact.arrondi(sum((Decimal(str(p["montant"])) for p in valides), Decimal("0")))}
