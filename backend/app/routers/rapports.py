"""
Rapports d'essai officiels et figés.

- 1re émission : numéro officiel NNNN/CODE/AAAA (séquence par section, remise à
  zéro chaque année, jamais réutilisée), PDF stocké dans `rapports_emis` avec son
  empreinte SHA-256, statut de l'échantillon -> « Rapport émis ».
- Ensuite, GET /api/rapports/{section}/{num} renvoie le PDF stocké, octet pour octet.
- Erratum : un responsable rouvre le dossier (motif obligatoire, statut -> « En cours »).
  Après correction, soumission et validation, la nouvelle émission crée la version
  suivante (« Annule et remplace… ») ; l'ancienne passe à « annulé » et reste consultable.
"""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, ROLE_SECTION, ROLES_RESPONSABLES
from app.models import Echantillon, AuditLog, RefCritereMicro, TRAITEMENT_MODELS
from app.services.paiements import exiger_paiement
from app.services.rapport import generer_rapport

router = APIRouter(prefix="/api/rapports", tags=["rapports"])

SECTION_ATTR = {"SMA": "sma", "SCHA": "scha", "SSA": "ssa"}
# Code du numéro officiel NNNN/CODE/AAAA
CODE_RAPPORT = {"SMA": "MA", "SCHA": "CH", "SSA": "SA"}
# Colonnes de rapports_emis renvoyées par l'historique (sans le PDF)
COLONNES_HISTO = """id, numero, num_echantillon, section, version, date_emission, emis_par,
                    sha256, statut, remplace_id, motif, erratum_motif, erratum_par, erratum_le,
                    octet_length(pdf) AS taille"""


def _to_dict(obj) -> dict:
    if obj is None:
        return {}
    return {c.key: getattr(obj, c.key) for c in obj.__mapper__.column_attrs}


async def _criteres_sma(db, categorie):
    if not categorie:
        return []
    r = await db.execute(
        select(RefCritereMicro)
        .where(RefCritereMicro.categorie_produit == categorie)
        .order_by(RefCritereMicro.numero_ordre)
    )
    return [{"famille": c.critere, "microorganisme": c.parametre,
             "n": c.n, "c": c.c, "m": c.m, "M": c.grand_m}
            for c in r.scalars().all()]


async def _criteres_scha(db, categorie):
    """Critères d'acceptabilité SCHA (table ref_criteres_scha, créée par 006)."""
    if not categorie:
        return []
    try:
        r = await db.execute(text("""
            SELECT critere_1, critere_2, critere_3, critere_4,
                   critere_5, critere_6, critere_7
            FROM ref_criteres_scha
            WHERE categorie_ch = :cat
            ORDER BY numero_ordre
        """), {"cat": categorie})
    except Exception:
        return []
    out = []
    for row in r.mappings().all():
        out.append({"analyse": categorie, **{f"critere_{i}": row[f"critere_{i}"] for i in range(1, 8)}})
    return out


def _s(v):
    """Valeur -> chaîne affichable (None ou 0 -> '')."""
    if v is None:
        return ""
    return str(v)


def _verifier_section(user: dict, section: str):
    role_section = ROLE_SECTION.get(user["role"])
    if role_section and role_section != section:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Votre role ne donne pas acces a la section {section}.")


def _reponse_pdf(pdf: bytes, numero: str, sha: str) -> Response:
    nom = f"Rapport_essai_{numero}.pdf".replace("/", "-")
    return Response(content=bytes(pdf), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nom}"',
                             "X-Rapport-Numero": numero, "X-Rapport-SHA256": sha})


async def _rapport_valide(db, num: str, section: str):
    r = await db.execute(text("""
        SELECT id, numero, version, date_emission, sha256, pdf, erratum_motif
        FROM rapports_emis
        WHERE num_echantillon = :num AND section = :sec AND statut = 'valide'
    """), {"num": num, "sec": section})
    return r.mappings().first()


async def _contenu_rapport(db, section: str, ech, trt) -> dict:
    """Données du rapport (blocs I à V), lues dans la base au moment de l'émission."""
    num = ech.num_echantillon
    if section == "SMA":
        criteres = await _criteres_sma(db, ech.categorie)
    elif section == "SCHA":
        criteres = await _criteres_scha(db, ech.categorie)
    else:
        criteres = []

    # --- Résultats saisis (SQL direct : accès à toutes les colonnes) ---
    r = await db.execute(text("""
        SELECT analyse_effectuee, reference_methode,
               rp1, rp2, rp3, rp4, rp5, rp6, rp7, rp8, rp9,
               moyenne, conclusion,
               resultat_analyse, nbre_positifs, nbre_negatif, nbre_douteux,
               date_analyse, date_sortie
        FROM resultats_analyses
        WHERE num_echantillon = :num AND section = :sec
        ORDER BY id
    """), {"num": num, "sec": section})
    lignes_res = r.mappings().all()

    if section == "SSA":
        analyses = [{
            "analyse": _s(a["analyse_effectuee"]),
            "methode": _s(a["reference_methode"]),
            "resultat": _s(a["resultat_analyse"]) or _s(a["rp1"]),
            "positifs": _s(a["nbre_positifs"]),
            "negatifs": _s(a["nbre_negatif"]),
            "douteux": _s(a["nbre_douteux"]),
        } for a in lignes_res]
    elif section == "SCHA":
        analyses = [{
            "analyse": _s(a["analyse_effectuee"]),
            "methode": _s(a["reference_methode"]),
            "resultats": [a["rp1"], a["rp2"], a["rp3"], a["rp4"], a["rp5"],
                          a["rp6"], a["rp7"], a["rp8"], a["rp9"]],
            "moyenne": _s(a["moyenne"]),
            "conclusion": _s(a["conclusion"]),
        } for a in lignes_res]
    else:
        analyses = [{
            "analyse": _s(a["analyse_effectuee"]),
            "methode": _s(a["reference_methode"]),
            "resultats": [a["rp1"], a["rp2"], a["rp3"], a["rp4"], a["rp5"]],
        } for a in lignes_res]

    # --- Dates du bloc résultats : depuis la 1re ligne saisie ---
    trt_dict = _to_dict(trt)
    if lignes_res:
        premiere = lignes_res[0]
        if premiere["date_analyse"]:
            trt_dict["date_mise_en_analyse"] = premiere["date_analyse"]
        if premiere["date_sortie"]:
            trt_dict["date_sortie_resultats"] = premiere["date_sortie"]

    return {"echantillon": _to_dict(ech), "traitement": trt_dict,
            "criteres": criteres, "analyses": analyses}


async def _emettre(db, user: dict, section: str, ech, trt, ancien) -> dict:
    """
    Émet une nouvelle version : numéro officiel, PDF figé + SHA-256.
    `ancien` : rapport valide faisant l'objet d'un erratum (None pour la 1re émission).
    """
    # Verrou transactionnel : deux émissions simultanées ne peuvent pas prendre le même numéro
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('rapports_emis'))"))
    maintenant = datetime.now(timezone.utc)
    annee = maintenant.year
    r = await db.execute(text("""
        SELECT COALESCE(MAX(sequence), 0) + 1 FROM rapports_emis
        WHERE section = :sec AND annee = :an
    """), {"sec": section, "an": annee})
    sequence = r.scalar_one()
    numero = f"{sequence:04d}/{CODE_RAPPORT[section]}/{annee}"

    r = await db.execute(text("""
        SELECT COALESCE(MAX(version), 0) + 1 FROM rapports_emis
        WHERE num_echantillon = :num AND section = :sec
    """), {"num": ech.num_echantillon, "sec": section})
    version = r.scalar_one()

    remplace = None
    if ancien is not None:
        remplace = {"numero": ancien["numero"], "date": ancien["date_emission"].date().isoformat(),
                    "motif": ancien["erratum_motif"]}

    contenu = await _contenu_rapport(db, section, ech, trt)
    pdf = generer_rapport(section=section, numero=numero,
                          date_emission=maintenant.date().isoformat(), remplace=remplace, **contenu)
    sha = hashlib.sha256(pdf).hexdigest()

    if ancien is not None:
        await db.execute(text("UPDATE rapports_emis SET statut = 'annulé' WHERE id = :id"),
                         {"id": ancien["id"]})
    await db.execute(text("""
        INSERT INTO rapports_emis (numero, num_echantillon, section, version, annee, sequence,
                                   date_emission, emis_par, sha256, pdf, statut, remplace_id, motif)
        VALUES (:numero, :num, :sec, :version, :annee, :sequence,
                :date, :par, :sha, :pdf, 'valide', :remplace, :motif)
    """), {"numero": numero, "num": ech.num_echantillon, "sec": section, "version": version,
           "annee": annee, "sequence": sequence, "date": maintenant, "par": user["username"],
           "sha": sha, "pdf": pdf, "remplace": ancien["id"] if ancien is not None else None,
           "motif": ancien["erratum_motif"] if ancien is not None else None})

    # Première émission (ou nouvelle version) -> statut « Rapport émis »
    ech.statut = "Rapport émis"
    details = f"Rapport {numero} (version {version}) emis, SHA-256 {sha}"
    if ancien is not None:
        details += f" ; annule et remplace {ancien['numero']}"
    db.add(AuditLog(utilisateur=user["username"], action="RAPPORT",
                    table_cible="rapports_emis", cle=ech.num_echantillon, details=details))
    await db.commit()
    return {"numero": numero, "sha256": sha, "pdf": pdf}


# ---- Routes fixes : déclarées AVANT /{section}/{num} ----

@router.get("/historique/{num}")
async def historique(
    num: str,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toutes les versions émises pour un échantillon (sans le PDF)."""
    role_section = ROLE_SECTION.get(user["role"])
    r = await db.execute(text(f"""
        SELECT {COLONNES_HISTO} FROM rapports_emis
        WHERE num_echantillon = :num AND (CAST(:sec AS VARCHAR) IS NULL OR section = :sec)
        ORDER BY section, version DESC
    """), {"num": num, "sec": role_section})
    return [dict(x) for x in r.mappings().all()]


@router.get("/fichier/{rapport_id}")
async def fichier(
    rapport_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """PDF stocké d'une version précise (valide ou annulée), octet pour octet."""
    r = await db.execute(text("SELECT numero, section, sha256, pdf FROM rapports_emis WHERE id = :id"),
                         {"id": rapport_id})
    rap = r.mappings().first()
    if not rap:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rapport introuvable.")
    _verifier_section(user, rap["section"])
    return _reponse_pdf(rap["pdf"], rap["numero"], rap["sha256"])


@router.post("/{section}/{num}/erratum")
async def erratum(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    payload: dict = Body(default={}),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Un responsable rouvre un dossier dont le rapport est émis (motif obligatoire)."""
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Seul un responsable peut lancer un erratum.")
    motif = ((payload or {}).get("motif") or "").strip()
    if not motif:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le motif de l'erratum est obligatoire.")

    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    valide = await _rapport_valide(db, num, section)
    if valide is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun rapport emis pour cette section.")
    if valide["erratum_motif"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un erratum est deja en cours pour ce rapport.")
    if ech.statut != "Rapport émis":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Erratum impossible : statut actuel « {ech.statut} ».")

    Model = TRAITEMENT_MODELS[section]
    res = await db.execute(select(Model).where(Model.num_echantillon == num))
    trt = res.scalar_one_or_none()
    if trt is not None:
        # La fiche redevient modifiable ; le circuit normal reprend (soumission, validation)
        trt.valide_par = None
        trt.date_validation = None
    await db.execute(text("""
        UPDATE rapports_emis SET erratum_motif = :motif, erratum_par = :par, erratum_le = now()
        WHERE id = :id
    """), {"motif": motif, "par": user["username"], "id": valide["id"]})
    ech.statut = "En cours"
    db.add(AuditLog(utilisateur=user["username"], action="ERRATUM",
                    table_cible="rapports_emis", cle=num,
                    details=f"Rapport {valide['numero']} rouvert : {motif}"))
    await db.commit()
    return {"numero": valide["numero"], "statut": ech.statut, "motif": motif}


@router.get("/{section}/{num}")
async def rapport_essai(
    section: str = Path(pattern="^(SMA|SCHA|SSA)$"),
    num: str = Path(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rapport d'essai d'une section :
    - déjà émis : renvoie le PDF stocké (jamais régénéré) ;
    - sinon (1re émission, ou nouvelle version après erratum et revalidation) :
      l'émet (numéro officiel, PDF figé, statut « Rapport émis »).
    """
    _verifier_section(user, section)

    res = await db.execute(select(Echantillon).where(Echantillon.num_echantillon == num))
    ech = res.scalar_one_or_none()
    if not ech:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Echantillon "{num}" introuvable.')
    if getattr(ech, SECTION_ATTR[section]) != "Yes":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Cet echantillon n'est pas assigne a la section {section}.")

    valide = await _rapport_valide(db, num, section)
    # Rapport émis sans nouvelle version prête : PDF figé, octet pour octet
    if valide is not None and not (valide["erratum_motif"] and ech.statut == "Validé"):
        return _reponse_pdf(valide["pdf"], valide["numero"], valide["sha256"])

    Model = TRAITEMENT_MODELS[section]
    res = await db.execute(select(Model).where(Model.num_echantillon == num))
    trt = res.scalar_one_or_none()
    if trt is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Aucune fiche de traitement : le rapport ne peut pas etre genere.")

    # --- Verrou de validation : pas de rapport avant que la fiche soit validée ---
    if ech.statut not in ("Validé", "Rapport émis"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Le rapport d'essai ne peut etre emis qu'apres validation de la fiche "
            f"(statut actuel : {ech.statut}).")

    # Émettre (1re émission ou nouvelle version) est réservé aux responsables
    if user["role"] not in ROLES_RESPONSABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Le rapport n'est pas encore emis : seul un responsable peut l'emettre.")
    # Facturation (tâche 38) : paiement éventuellement exigé avant la remise du rapport
    await exiger_paiement(db, num, "remise_rapport")
    emis = await _emettre(db, user, section, ech, trt, valide)
    return _reponse_pdf(emis["pdf"], emis["numero"], emis["sha256"])
