"""
Bilan mensuel (tâche 24) : synthèse et blocs du modèle (`bilan_modele`), calculés avec le
moteur de requêtes (mêmes chiffres que la page Requêtes), puis fichier PDF ou Excel archivé
dans `bilans_mensuels` (une régénération crée la version suivante, rien n'est écrasé).

Chaque bloc « requête » est une requête enregistrée exécutée sur le mois et la section du
bilan : sa période (relative ou fixe) est remplacée par le mois du bilan ; une requête sans
période (ex. retards) décrit la situation à la date de génération.
"""
from __future__ import annotations

import copy
import hashlib
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from sqlalchemy import text

from app.services import exports_requetes as ex

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"]


def premier_jour(m: date) -> date:
    return m.replace(day=1)


def mois_precedent(m: date) -> date:
    return (premier_jour(m) - timedelta(days=1)).replace(day=1)


def fin_mois(m: date) -> date:
    return (premier_jour(m) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def libelle_mois(m: date) -> str:
    return f"{MOIS_FR[m.month - 1]} {m.year}"


def libelle_section(section: str | None) -> str:
    return f"section {section}" if section else "toutes sections"


def titre_bilan(mois: date, section: str | None) -> str:
    return f"Bilan mensuel - {libelle_mois(mois)} - {libelle_section(section)}"


def lire_mois(texte: str) -> date:
    """« AAAA-MM » → premier jour du mois (ValueError sinon)."""
    a, m = texte.strip().split("-")
    return date(int(a), int(m), 1)


def definition_du_mois(definition: dict, mois: date, section: str | None) -> tuple[dict, bool]:
    """Période remplacée par le mois du bilan, section imposée ; renvoie aussi « a une période »."""
    d = copy.deepcopy(definition)
    f = d.setdefault("filtres", {})
    a_periode = any(k in f for k in ("periode", "du", "au"))
    if a_periode:
        for k in ("periode", "du", "au"):
            f.pop(k, None)
        f["du"], f["au"] = premier_jour(mois).isoformat(), fin_mois(mois).isoformat()
    if section:
        f["section"] = [section]
    d.pop("limite", None)
    return d, a_periode


# Indicateurs de la synthèse : (clé, libellé, format, filtres supplémentaires, mesure)
SYNTHESE = [
    ("recus", "Échantillons reçus", "entier", {}, "nb_echantillons"),
    ("rapports", "Rapports émis (1re émission)", "entier", {"date_ref": "rapport"}, "nb_echantillons"),
    ("en_cours", "Reçus dans le mois, encore en cours (Reçu, En cours)", "entier", {"statut": ["Reçu", "En cours"]}, "nb_echantillons"),
    ("a_valider", "Reçus dans le mois, à valider", "entier", {"statut": ["À valider"]}, "nb_echantillons"),
    ("retard", "Reçus dans le mois, en retard à ce jour", "entier", {}, "nb_retard"),
    ("taux_nc", "Taux de non-conformité (reçus dans le mois)", "pourcent", {}, "taux_non_conformite"),
    ("delai", "Délai moyen réception - rapport (rapports émis, jours)", "jours", {"date_ref": "rapport"}, "delai_moyen"),
]


def _evolution(v, p, fmt) -> str:
    if v is None or p is None:
        return "—"
    d = v - p
    signe = "+" if d > 0 else ("" if d == 0 else "-")
    unite = {"pourcent": " pt", "jours": " j"}.get(fmt, "")
    val = ex.formater(abs(d), "jours" if fmt in ("pourcent", "jours") else fmt)
    return f"{signe}{val}{unite}" if d else "="


async def modele(db, actifs_seulement: bool = False) -> list[dict]:
    r = await db.execute(text("""
        SELECT m.id, m.ordre, m.type_bloc, m.titre, m.requete_id, m.actif, q.nom AS requete_nom
        FROM bilan_modele m LEFT JOIN requetes_enregistrees q ON q.id = m.requete_id
        WHERE (:tous OR m.actif) ORDER BY m.ordre, m.id"""), {"tous": not actifs_seulement})
    return [dict(x) for x in r.mappings().all()]


async def calculer(db, mois: date, section: str | None, user: dict) -> dict:
    from app.routers.requetes import executer_definition   # évite un import circulaire

    mois = premier_jour(mois)
    prec = mois_precedent(mois)

    async def indicateur(m: date, extra: dict, mesure: str):
        f = {"du": m.isoformat(), "au": fin_mois(m).isoformat(), **extra}
        if section:
            f["section"] = [section]
        res = await executer_definition(db, {"jeu": "echantillons", "filtres": f, "mesures": [mesure]}, user)
        return res["totaux"].get(mesure)

    synthese = []
    for cle, lib, fmt, extra, mesure in SYNTHESE:
        v, p = await indicateur(mois, extra, mesure), await indicateur(prec, extra, mesure)
        synthese.append({"cle": cle, "libelle": lib, "format": fmt, "valeur": v, "precedent": p,
                         "evolution": _evolution(v, p, fmt)})

    blocs = []
    for b in await modele(db, actifs_seulement=True):
        if b["type_bloc"] == "synthese":
            blocs.append({"titre": b["titre"], "type": "synthese"})
            continue
        r = (await db.execute(text("SELECT definition FROM requetes_enregistrees WHERE id = :id"),
                              {"id": b["requete_id"]})).first()
        if r is None:
            blocs.append({"titre": b["titre"], "type": "erreur", "note": "Requête enregistrée introuvable."})
            continue
        definition, a_periode = definition_du_mois(r[0], mois, section)
        try:
            res = await executer_definition(db, definition, user)
        except HTTPException as e:
            blocs.append({"titre": b["titre"], "type": "erreur", "note": f"Bloc non calculé : {e.detail}"})
            continue
        res.pop("sql", None)
        res.pop("parametres", None)
        blocs.append({"titre": b["titre"], "type": "requete", "requete": b["requete_nom"], "definition": definition,
                      "resultat": res, "note": None if a_periode else "Situation à la date de génération du bilan."})
    return {"mois": mois.isoformat(), "libelle_mois": libelle_mois(mois), "precedent": libelle_mois(prec),
            "section": section, "titre": titre_bilan(mois, section), "synthese": synthese, "blocs": blocs}


# ---------------------------------------------------------------------------
# Fichiers
# ---------------------------------------------------------------------------
def _parametres(bilan: dict, auteur: str, quand: datetime) -> list[tuple[str, str]]:
    m = date.fromisoformat(bilan["mois"])
    return [("Mois", f"{bilan['libelle_mois']} (du {m:%d/%m/%Y} au {fin_mois(m):%d/%m/%Y}, date de réception)"),
            ("Sections", bilan["section"] or "toutes"),
            ("Comparaison", bilan["precedent"]),
            ("Généré le", quand.strftime("%d/%m/%Y à %H:%M")), ("Par", auteur)]


def pdf(bilan: dict, auteur: str, quand: datetime) -> bytes:
    def contenu(largeur):
        els = [ex.pdf_parametres(_parametres(bilan, auteur, quand), largeur), Spacer(1, 3)]
        n = 0
        for b in bilan["blocs"]:
            n += 1
            titre = f"{n}. {b['titre']}"
            if b["type"] == "synthese":
                entete = ["Indicateur", bilan["libelle_mois"], bilan["precedent"], "Évolution"]
                st_ent = ex.ParagraphStyle("se", parent=ex.S_CEL_G, textColor=colors.white)
                data = [[ex._p(e, st_ent) for e in entete]] + [
                    [ex._p(s["libelle"]), Paragraph(ex.formater(s["valeur"], s["format"]), ex.S_CEL_G),
                     Paragraph(ex.formater(s["precedent"], s["format"]), ex.S_CEL), ex._p(s["evolution"])]
                    for s in bilan["synthese"]]
                t = Table(data, colWidths=[largeur - 3 * 32 * ex.mm, 32 * ex.mm, 32 * ex.mm, 32 * ex.mm],
                          repeatRows=1, hAlign="LEFT")
                ex._style_table(t, len(data) - 1, 1, total=False)
                els += [Paragraph(titre, ex.S_SOUS), t]
                continue
            if b["type"] == "erreur":
                els += [Paragraph(titre, ex.S_SOUS), Paragraph(ex.escape(b["note"]), ex.S_NOTE)]
                continue
            els += ex.elements_resultat(b["resultat"], largeur, titre)
            if b.get("note"):
                els.append(Paragraph(ex.escape(b["note"]), ex.S_NOTE))
        return els
    return ex.document_pdf(bilan["titre"], contenu, auteur, quand=quand)


def excel(bilan: dict, auteur: str, quand: datetime) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Synthèse"
    ws.cell(1, 1, bilan["titre"]).font = Font(bold=True, size=13)
    ligne = ex.feuille_parametres(ws, _parametres(bilan, auteur, quand), 3)
    for j, e in enumerate(["Indicateur", bilan["libelle_mois"], bilan["precedent"], "Évolution"], 1):
        ex._style(ws.cell(ligne, j, e), **ex._ENTETE)
    for s in bilan["synthese"]:
        ligne += 1
        ex._style(ws.cell(ligne, 1, s["libelle"]))
        for j, k in ((2, "valeur"), (3, "precedent")):
            c = ws.cell(ligne, j, s[k])
            c.number_format = ex._excel_format(s["format"])
            ex._style(c)
        ex._style(ws.cell(ligne, 4, s["evolution"]))
    ws.column_dimensions["A"].width = 58
    for col in "BCD":
        ws.column_dimensions[col].width = 18
    noms = {"Synthèse"}
    n = 0
    for b in bilan["blocs"]:
        n += 1
        if b["type"] == "synthese":
            continue
        nom = f"{n}. {b['titre']}"[:31].rstrip()
        for c in "[]:*?/\\":
            nom = nom.replace(c, "-")
        while nom in noms:
            nom = nom[:29] + f"{len(noms)}"
        noms.add(nom)
        wf = wb.create_sheet(nom)
        if b["type"] == "erreur":
            wf.cell(1, 1, b["note"])
            continue
        lig = ex.feuille_resultat(wf, b["resultat"], f"{n}. {b['titre']}")
        if b.get("note"):
            wf.cell(lig - 1, 1, b["note"]).font = Font(italic=True)
            lig += 1
        if len(b["resultat"]["regroupements"]) == 2:
            for m in b["resultat"]["mesures"]:
                lig = ex.feuille_croisee(wf, b["resultat"], m, lig)
        ex._largeurs(wf, maxi=45)
    from io import BytesIO
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def generer(db, mois: date, section: str | None, fmt: str, user: dict, source: str = "application") -> dict:
    """Calcule, produit le fichier et l'archive (nouvelle version). Renvoie la ligne archivée et le contenu."""
    quand = datetime.now()
    bilan = await calculer(db, mois, section, user)
    contenu = pdf(bilan, user["username"], quand) if fmt == "pdf" else excel(bilan, user["username"], quand)
    empreinte = hashlib.sha256(contenu).hexdigest()
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('bilans_mensuels'))"))
    version = (await db.execute(text("""
        SELECT coalesce(max(version), 0) + 1 FROM bilans_mensuels
        WHERE mois = :m AND coalesce(section, 'TOUT') = coalesce(CAST(:s AS VARCHAR), 'TOUT') AND format = :f"""),
        {"m": premier_jour(mois), "s": section, "f": fmt})).scalar_one()
    bid = (await db.execute(text("""
        INSERT INTO bilans_mensuels (mois, section, format, version, pdf, taille, sha256, auteur, source)
        VALUES (:m, :s, :f, :v, :pdf, :t, :h, :a, :src) RETURNING id"""),
        {"m": premier_jour(mois), "s": section, "f": fmt, "v": version, "pdf": contenu, "t": len(contenu),
         "h": empreinte, "a": user["username"], "src": source})).scalar_one()
    return {"id": bid, "version": version, "sha256": empreinte, "contenu": contenu, "bilan": bilan,
            "nom_fichier": f"bilan_{mois:%Y-%m}_{section or 'toutes'}_v{version}.{fmt}"}
