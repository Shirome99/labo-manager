"""
Generation du Rapport d'Essai PDF (LRARVY / ONSSA) — 3 sections.

Chaque section a sa propre structure de blocs, calquee sur les rapports Access :

  SMA  : I client / II labo / III criteres micro (n,c,m,M) / IV resultats RP1-5 / V conformite
  SCHA : I client / II labo / III criteres chimiques (7 criteres) / IV resultats RP1-5 / V conformite
  SSA  : I client (avec espece) / II labo / III resultats (resultat + interpretation) / IV interpretation

Moteur : ReportLab (pur Python).
"""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.services.reception import liste_non_conformites

# ------------------------------------------------------------------
# Parametres par section
# ------------------------------------------------------------------
SECTIONS = {
    "SMA": {
        "libelle": "Microbiologie Alimentaire",
        "sigle_rapport": "MA",
        "signataire": "Le Chef de Section de\nMicrobiologie Alimentaire",
        "code_qualite": "FE01/PG5.9.01-V:10 du 01/12/2022",
        "type_bloc3": "criteres_micro",      # n,c,m,M
        "cinq_blocs": True,
    },
    "SCHA": {
        "libelle": "Securite Chimie Hygiene Alimentaire",
        "sigle_rapport": "CH",
        "signataire": "Le Chef de Section de\nChimie Alimentaire",
        "code_qualite": "FE01/PG5.9.01-V:10 du 01/12/2022",
        "type_bloc3": "criteres_chimie",     # 7 criteres textuels
        "cinq_blocs": True,
    },
    "SSA": {
        "libelle": "Sante Animale",
        "sigle_rapport": "SAV",
        "signataire": "Le Chef de Section de Sante\nAnimale et Vegetale",
        "code_qualite": "FE01/PG5.9.01-V:10 du 01/12/2022",
        "type_bloc3": "resultats_ssa",       # resultat + interpretation, pas de criteres
        "cinq_blocs": False,                 # 4 blocs : III=resultats, IV=interpretation
    },
}

LOGO_DIR = Path(__file__).resolve().parents[1] / "static" / "logos"
LOGO_ONSSA = LOGO_DIR / "onssa.png"
LOGO_LRARVY = LOGO_DIR / "lrarvy.png"

MARGE = 14 * mm
LARGEUR_UTILE = A4[0] - 2 * MARGE

_base = getSampleStyleSheet()
S_ENTETE = ParagraphStyle("e", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=8, alignment=TA_CENTER)
S_TITRE = ParagraphStyle("t", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11)
S_BLOC = ParagraphStyle("b", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, spaceBefore=4, spaceAfter=2)
S_LABEL = ParagraphStyle("l", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=9.5)
S_VAL = ParagraphStyle("v", parent=_base["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5)
S_PETIT = ParagraphStyle("p", parent=_base["Normal"], fontName="Helvetica", fontSize=6, leading=7.5)
S_PETIT_IT = ParagraphStyle("pi", parent=_base["Normal"], fontName="Helvetica-Oblique", fontSize=5.5, leading=7)
S_SIGN = ParagraphStyle("s", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_CENTER)


def _v(valeur, defaut=""):
    if valeur is None:
        return defaut
    s = str(valeur).strip()
    return s if s else defaut


def _date(valeur, avec_heure=False):
    if not valeur:
        return ""
    s = str(valeur)
    d, _, h = (s.partition("T") if "T" in s else s.partition(" "))
    try:
        a, m, j = d.split("-")
        d = f"{j}/{m}/{a}"
    except ValueError:
        pass
    return f"{d} a {h[:5]}" if (avec_heure and h) else d


# ------------------------------------------------------------------
# En-tete / pied
# ------------------------------------------------------------------
def _cadre(canvas, doc):
    canvas.saveState()
    canvas.setLineWidth(0.8)
    canvas.rect(MARGE - 3 * mm, MARGE - 3 * mm, LARGEUR_UTILE + 6 * mm, A4[1] - 2 * MARGE + 6 * mm)
    canvas.setFont("Helvetica-Oblique", 5)
    y = MARGE - 0.5 * mm
    for i, ligne in enumerate([
        "Ce rapport d'essai ne concerne que l'echantillon soumis a l'essai et qu'il a ete recu. Le rapport ne doit etre reproduit, sauf dans son integralite, sans l'approbation du LRAR Tanger",
        "LRAR de Tanger, Rue Ibn Taimiate BP: 3 Tanger, Tel:0539940540 Fax:0539943919 Email:lrar.tanger@gmail.com",
    ]):
        canvas.drawCentredString(A4[0] / 2, y + (1 - i) * 6, ligne)
    canvas.setFont("Helvetica", 5)
    canvas.drawRightString(A4[0] - MARGE, y, f"Page {doc.page} sur {doc.page}")
    canvas.restoreState()


def _entete(direction="DIRECTION REGIONALE DE TANGER TETOUAN"):
    def _logo(chemin, largeur, hauteur):
        if chemin.exists():
            return Image(str(chemin), width=largeur, height=hauteur)
        return Paragraph(f'<font size="5" color="#999">[{chemin.stem.upper()}]</font>', S_ENTETE)

    texte = Paragraph(
        "OFFICE NATIONAL DE LA SECURITE SANITAIRE DES PRODUITS ALIMENTAIRES<br/>"
        f"{direction}<br/>* * * * *<br/>"
        "LABORATOIRE REGIONAL D'ANALYSES ET DE RECHERCHES DE TANGER", S_ENTETE)
    t = Table([[_logo(LOGO_ONSSA, 22 * mm, 13 * mm), texte, _logo(LOGO_LRARVY, 17 * mm, 13 * mm)]],
              colWidths=[26 * mm, LARGEUR_UTILE - 47 * mm, 21 * mm], rowHeights=[15 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return t


def _paires(lignes):
    data = []
    for ligne in lignes:
        if len(ligne) == 2:
            lab, val = ligne
            data.append([Paragraph(lab, S_LABEL), Paragraph(f": {escape(_v(val))}", S_VAL), "", ""])
        else:
            lab, val, lab2, val2 = ligne
            data.append([Paragraph(lab, S_LABEL), Paragraph(f": {escape(_v(val))}", S_VAL),
                         Paragraph(lab2, S_LABEL), Paragraph(escape(_v(val2)), S_VAL)])
    t = Table(data, colWidths=[38 * mm, LARGEUR_UTILE - 38 * mm - 60 * mm, 32 * mm, 28 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 1),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def _titre_bloc(numero, titre, complement=""):
    txt = f"<u>{numero}. {titre} :</u>"
    if complement:
        txt += f'  <font name="Helvetica">{complement}</font>'
    return Paragraph(txt, S_BLOC)


# ---- Bloc III : 3 variantes ----
def _tableau_criteres_micro(criteres):
    entetes = ["Criteres", "Microorganismes", "n", "c", "m", "M"]
    data = [[Paragraph(f"<b>{h}</b>", S_PETIT) for h in entetes]]
    for c in (criteres or [{}, {}, {}]):
        data.append([Paragraph(_v(c.get("famille")), S_PETIT), Paragraph(_v(c.get("microorganisme")), S_PETIT),
                     Paragraph(_v(c.get("n")), S_PETIT), Paragraph(_v(c.get("c")), S_PETIT),
                     Paragraph(_v(c.get("m")), S_PETIT), Paragraph(_v(c.get("M")), S_PETIT)])
    t = Table(data, colWidths=[38 * mm, LARGEUR_UTILE - 38 * mm - 62 * mm, 12 * mm, 12 * mm, 19 * mm, 19 * mm])
    _grille(t)
    return t


def _tableau_criteres_chimie(criteres):
    """SCHA : analyse effectuee + critere de conformite (fusion des 7 criteres non vides)."""
    data = [[Paragraph("<b>Analyse effectuee</b>", S_PETIT), Paragraph("<b>Critere de conformite</b>", S_PETIT)]]
    for c in (criteres or [{}, {}]):
        crits = [c.get(f"critere_{i}") for i in range(1, 8)]
        crit_txt = " ; ".join(_v(x) for x in crits if _v(x) and _v(x) != "-")
        data.append([Paragraph(_v(c.get("analyse")), S_PETIT), Paragraph(crit_txt, S_PETIT)])
    t = Table(data, colWidths=[LARGEUR_UTILE * 0.35, LARGEUR_UTILE * 0.65])
    _grille(t)
    return t


def _tableau_resultats(analyses, nb=5):
    entetes = ["Analyse effectuee", "Ref. methode"] + [f"RP {i}" for i in range(1, nb + 1)]
    data = [[Paragraph(f"<b>{h}</b>", S_PETIT) for h in entetes]]
    for a in (analyses or [{}, {}]):
        res = list(a.get("resultats") or [])
        res += [""] * (nb - len(res))
        data.append([Paragraph(_v(a.get("analyse")), S_PETIT), Paragraph(_v(a.get("methode")), S_PETIT)]
                    + [Paragraph(_v(r), S_PETIT) for r in res[:nb]])
    col = 15 * mm
    reste = LARGEUR_UTILE - nb * col
    t = Table(data, colWidths=[reste * 0.55, reste * 0.45] + [col] * nb)
    _grille(t)
    return t


def _tableau_resultats_scha(analyses):
    """SCHA : Analyse / Methode / RP1-9 / Moyenne / Conclusion (conforme Access)."""
    from reportlab.lib.styles import ParagraphStyle as _PS
    petit = _PS("scha_p", parent=S_PETIT, fontSize=5, leading=6)
    entetes = ["Analyse", "Ref. methode"] + [f"RP{i}" for i in range(1, 10)] + ["Moy.", "Conclusion"]
    data = [[Paragraph(f"<b>{h}</b>", petit) for h in entetes]]
    for a in (analyses or [{}, {}]):
        res = list(a.get("resultats") or [])
        res += [""] * (9 - len(res))
        ligne = [Paragraph(_v(a.get("analyse")), petit), Paragraph(_v(a.get("methode")), petit)]
        ligne += [Paragraph(_v(r), petit) for r in res[:9]]
        ligne += [Paragraph(_v(a.get("moyenne")), petit), Paragraph(_v(a.get("conclusion")), petit)]
        data.append(ligne)
    rp = 9.5 * mm
    reste = LARGEUR_UTILE - 9 * rp - 11 * mm - 18 * mm  # RP + Moy + Conclusion
    t = Table(data, colWidths=[reste * 0.58, reste * 0.42] + [rp] * 9 + [11 * mm, 18 * mm])
    _grille(t)
    return t


def _tableau_resultats_ssa(analyses):
    """SSA : Analyse / Methode / Resultat / Detectes / Non detectes / Douteux."""
    entetes = ["Analyses effectuees", "Ref. methode", "Resultat", "Detectes", "Non detectes", "Douteux"]
    data = [[Paragraph(f"<b>{h}</b>", S_PETIT) for h in entetes]]
    for a in (analyses or [{}, {}]):
        data.append([Paragraph(_v(a.get("analyse")), S_PETIT), Paragraph(_v(a.get("methode")), S_PETIT),
                     Paragraph(_v(a.get("resultat")), S_PETIT), Paragraph(_v(a.get("positifs")), S_PETIT),
                     Paragraph(_v(a.get("negatifs")), S_PETIT), Paragraph(_v(a.get("douteux")), S_PETIT)])
    t = Table(data, colWidths=[LARGEUR_UTILE * 0.28, LARGEUR_UTILE * 0.22, LARGEUR_UTILE * 0.24,
                               LARGEUR_UTILE * 0.09, LARGEUR_UTILE * 0.10, LARGEUR_UTILE * 0.07])
    _grille(t)
    return t


def _grille(t):
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.94, 0.94, 0.94)),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))


def _signatures(section):
    cfg = SECTIONS[section]
    t = Table([[Paragraph(cfg["signataire"].replace("\n", "<br/>"), S_SIGN),
                Paragraph("Le Directeur du LRAR<br/>de Tanger", S_SIGN)]],
              colWidths=[LARGEUR_UTILE / 2, LARGEUR_UTILE / 2], rowHeights=[26 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


# ------------------------------------------------------------------
# Point d'entree
# ------------------------------------------------------------------
def generer_rapport(section, echantillon, traitement, criteres=None, analyses=None,
                    numero=None, date_emission=None, remplace=None):
    """
    numero        : numéro officiel du rapport (ex. « 0001/MA/2026 ») ; à défaut, ancien en-tête.
    date_emission : date d'émission imprimée (« Date Emission RE »).
    remplace      : erratum -> {"numero", "date", "motif"} du rapport annulé et remplacé.
    """
    if section not in SECTIONS:
        raise ValueError(f"Section inconnue : {section}")
    cfg = SECTIONS[section]
    e, t = echantillon or {}, traitement or {}

    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE,
                          topMargin=MARGE, bottomMargin=MARGE + 4 * mm,
                          title=f"Rapport d'essai {_v(e.get('num_echantillon'))}", author="LRAR Tanger - ONSSA")
    frame = Frame(MARGE, MARGE + 4 * mm, LARGEUR_UTILE, A4[1] - 2 * MARGE - 4 * mm, id="c",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="r", frames=[frame], onPage=_cadre)])

    direction = ("DIRECTION REGIONALE DE TANGER TETOUAN AL HOCEIMA" if section == "SSA"
                 else "DIRECTION REGIONALE DE TANGER TETOUAN")
    flow = [_entete(direction), Spacer(1, 3 * mm)]

    if numero:
        libelle_numero = numero
    else:
        num_ordre = _v(t.get("num_ordre")) or _v(e.get("ordre"))
        annee = (_v(e.get("date_reception")) or "")[:4]
        libelle_numero = f"{num_ordre} /{cfg['sigle_rapport']}/{annee}"
    titre = Table([[Paragraph(f"RAPPORT D'ESSAI N°  {libelle_numero}", S_TITRE),
                    Paragraph(f'<font size="7">Code: {cfg["code_qualite"]}</font>', S_TITRE)]],
                  colWidths=[LARGEUR_UTILE * 0.55, LARGEUR_UTILE * 0.45])
    titre.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    flow += [titre, Spacer(1, 2 * mm)]

    # Erratum : mention « Annule et remplace » et motif
    if remplace:
        mention = Table([[Paragraph(
            f"Annule et remplace le rapport n° {remplace['numero']} du {_date(remplace['date'])}."
            f"<br/><font name=\"Helvetica\">Motif : {escape(_v(remplace.get('motif')))}</font>", S_LABEL)]],
            colWidths=[LARGEUR_UTILE])
        mention.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        flow += [mention, Spacer(1, 2 * mm)]

    # --- BLOC I : donnees client (SSA a une variante avec espece) ---
    flow.append(_titre_bloc("I", "DONNEES FOURNIES PAR LE CLIENT"))
    if section == "SSA":
        flow.append(_paires([
            ("Nature de l'echantillon", e.get("nature")),
            ("Espece", e.get("espece_animale"), "Nombre d'individus preleves", e.get("nbre_prlvmts_ssa")),
            ("Proprietaire", e.get("fabricant")),
            ("Prelevement effectue par", e.get("organisme_preleveur")),
            ("Reference Fiche de prelevement", e.get("ref_fiche_prelevement")),
            ("Nom du Client", e.get("client_nom") or e.get("fabricant")),
            ("Adresse du Client", e.get("adresse_client")),
            ("Cadre de l'analyse", e.get("cadre_demande")),
        ]))
    else:
        flow.append(_paires([
            ("Nature de l'echantillon", e.get("nature"), "N° de lot", e.get("num_lot")),
            ("Fabricant ou Proprietaire", e.get("fabricant")),
            ("Nom du Client", e.get("client_nom") or e.get("fabricant")),
            ("Adresse du Client", e.get("adresse_client")),
            ("Ref. Fiche de prelevement", e.get("ref_fiche_prelevement"),
             "Nombre d'unite(s)", e.get(f"nbre_prlvmts_{section.lower()}")),
            ("Organisme preleveur", e.get("organisme_preleveur"),
             "Date prelevement", _date(e.get("date_prelevement"))),
            ("Cadre de la demande", e.get("cadre_demande")),
        ]))

    # --- BLOC II : donnees labo ---
    flow.append(_titre_bloc("II", "DONNEES RELEVEES PAR LE LABORATOIRE"))
    # Réception structurée (migration 017) : température, état (non-conformités), réserve
    nc = liste_non_conformites(e)
    if nc:
        etat = "Non conforme : " + ", ".join(nc)
    else:
        etat = t.get("etat_echantillon") or ("Conforme" if e.get("decision_reception") else None)
    temperature = (f"{e['temperature_reception']} °C".replace(".", ",")
                   if e.get("temperature_reception") is not None else t.get("temperature_reception"))
    lignes_ii = [("Etat", etat, "T° Reception", temperature),
                 ("Date et heure de reception", _date(e.get("date_reception"), avec_heure=True))]
    if section != "SSA":
        lignes_ii[1] = ("Date et heure de reception", _date(e.get("date_reception"), avec_heure=True),
                        "N° de lot", e.get("num_lot"))
    if e.get("decision_reception") == "Accepté sous réserve":
        lignes_ii.append(("Reserve", e.get("motif_decision")))
    lignes_ii.append(("Observations", t.get("observations") or e.get("non_conformite")))
    flow.append(_paires(lignes_ii))

    if section == "SSA":
        # --- SSA : BLOC III = RESULTATS, BLOC IV = INTERPRETATION ---
        flow.append(_titre_bloc("III", "RESULTATS D'ANALYSES"))
        flow.append(_paires([
            ("Suspicion clinique", t.get("suspicion_clinique"), "Site d'essai", t.get("site_essai") or "LRAR Tanger"),
            ("Critere d'interpretation", t.get("critere_interpretation")),
            ("Date de mise en analyse", _date(t.get("date_mise_en_analyse")),
             "Date de sortie des resultats", _date(t.get("date_sortie_resultats"))),
        ]))
        flow.append(Spacer(1, 1 * mm))
        flow.append(_tableau_resultats_ssa(analyses))
        flow.append(Spacer(1, 1 * mm))
        flow.append(Paragraph("(+) Nombre Detectes ou positifs  (#) Nombre non detectes ou negatifs.", S_PETIT_IT))
        flow.append(_titre_bloc("IV", "INTERPRETATION DES RESULTATS"))
        flow.append(Paragraph(_v(t.get("interpretation_resultats")) or "&nbsp;", S_VAL))
    else:
        # --- SMA / SCHA : BLOC III = CRITERES, IV = RESULTATS, V = CONFORMITE ---
        flow.append(_titre_bloc("III", "CRITERES DE CONFORMITE", _v(e.get("categorie"))))
        if cfg["type_bloc3"] == "criteres_chimie":
            flow.append(_tableau_criteres_chimie(criteres))
        else:
            flow.append(_tableau_criteres_micro(criteres))

        flow.append(_titre_bloc("IV", "RESULTATS D'ANALYSES"))
        flow.append(_paires([
            ("Date de mise en analyse", _date(t.get("date_mise_en_analyse")),
             "Site d'essai", t.get("site_essai") or "LRAR Tanger"),
            ("Date de sortie des resultats", _date(t.get("date_sortie_resultats"))),
        ]))
        flow.append(Spacer(1, 1 * mm))
        if section == "SCHA":
            flow.append(_tableau_resultats_scha(analyses))
        else:
            flow.append(_tableau_resultats(analyses))
        flow.append(Spacer(1, 1 * mm))
        flow.append(Paragraph(
            "- 10(x) : 10 Puissance n - Abs : Absence - Prsce : Presence  RPn° : Resultat du prelevement n° - NR : Analyse Non realisee<br/>"
            "* : Essai non couvert par l'accreditation", S_PETIT_IT))

        flow.append(_titre_bloc("V", "DECLARATION DE CONFORMITE"))
        flow.append(Paragraph(_v(t.get("declaration_conformite")) or "&nbsp;", S_VAL))

    flow.append(Spacer(1, 2 * mm))
    flow.append(Paragraph(
        f'<u>Date Emission RE:</u>    <font name="Helvetica">{_date(date_emission or t.get("date_rapport_essai"))}</font>', S_LABEL))
    flow.append(_signatures(section))

    doc.build(flow)
    return buf.getvalue()
