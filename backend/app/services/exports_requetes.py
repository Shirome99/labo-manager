"""
Exports du reporting (tâches 22 et 24) : Excel (openpyxl) et PDF (ReportLab).

Les fonctions travaillent sur le résultat de `services.requetes.mettre_en_forme` ; elles sont
partagées par l'export d'une requête et par le bilan mensuel (plusieurs résultats dans un
même fichier). Les chiffres écrits sont exactement ceux renvoyés à l'écran.
"""
from __future__ import annotations

import math
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.services import requetes as moteur
from app.services.rapport import _entete

VERT = "00875A"
NR = moteur.NR
TOTAL = "Total"


# ---------------------------------------------------------------------------
# Mise en forme des valeurs
# ---------------------------------------------------------------------------
def formater(v, fmt: str) -> str:
    if v is None:
        return "—"
    if fmt == "entier":
        return f"{int(v):,}".replace(",", " ")
    if fmt == "pourcent":
        return f"{v:.1f} %".replace(".", ",")
    if fmt == "montant":
        return f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{v:.1f}".replace(".", ",")


def _excel_format(fmt: str) -> str:
    return {"entier": "#,##0", "pourcent": '0.0" %"', "montant": "#,##0.00", "jours": "0.0"}.get(fmt, "General")


def parametres(definition: dict, resultat: dict, auteur: str, quand: datetime | None = None) -> list[tuple[str, str]]:
    """Description lisible de la requête (feuille « Paramètres », en-tête du PDF)."""
    quand = quand or datetime.now()
    f = definition.get("filtres") or {}
    jeu = moteur.JEUX[resultat["jeu"]].libelle
    p = resultat["periode"]
    if p["du"] or p["au"]:
        d = lambda x: datetime.fromisoformat(x).strftime("%d/%m/%Y") if x else "…"
        periode = f"du {d(p['du'])} au {d(p['au'])}"
        if f.get("periode"):
            periode += f" ({moteur.PERIODES_RELATIVES[f['periode']].lower()})"
    else:
        periode = "toutes dates"
    lignes = [("Jeu de données", jeu), ("Période", f"{periode}, sur la {p['libelle_date'].lower()}")]
    for k, v in f.items():
        if k in ("du", "au", "periode", "date_ref") or not v:
            continue
        lignes.append((moteur.DIMENSIONS[k].libelle, ", ".join(v)))
    if resultat.get("sections"):
        lignes.append(("Sections visibles", ", ".join(resultat["sections"])))
    lignes += [
        ("Regroupements", ", ".join(g["libelle"] for g in resultat["regroupements"]) or "aucun (total seul)"),
        ("Mesures", ", ".join(m["libelle"] for m in resultat["mesures"])),
        ("Généré le", quand.strftime("%d/%m/%Y à %H:%M")),
        ("Par", auteur),
    ]
    return lignes


def croise(resultat: dict, mesure: str) -> tuple[list, list, dict, dict, dict]:
    """Tableau croisé (2 regroupements) : lignes, colonnes, cellules, totaux de ligne et de colonne."""
    g1, g2 = (g["cle"] for g in resultat["regroupements"])
    lignes = [r[g1] for r in resultat["sous_totaux"][g1]]
    cols = [r[g2] for r in resultat["sous_totaux"][g2]]
    cell = {(r[g1], r[g2]): r[mesure] for r in resultat["lignes"]}
    tl = {r[g1]: r[mesure] for r in resultat["sous_totaux"][g1]}
    tc = {r[g2]: r[mesure] for r in resultat["sous_totaux"][g2]}
    return lignes, cols, cell, tl, tc


def tableau(resultat: dict) -> tuple[list[str], list[list], list]:
    """Tableau à plat : en-têtes, lignes (valeurs brutes), ligne de total."""
    regs = resultat["regroupements"]
    mes = resultat["mesures"]
    entetes = [g["libelle"] for g in regs] + [m["libelle"] for m in mes]
    corps = [[r.get(g["cle"]) for g in regs] + [r.get(m["cle"]) for m in mes] for r in resultat["lignes"]]
    total = ([TOTAL] + [""] * (len(regs) - 1) if regs else []) + [resultat["totaux"].get(m["cle"]) for m in mes]
    return entetes, corps, total


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
_FIN = Side(style="thin", color="D0D7DE")
_BORD = Border(left=_FIN, right=_FIN, top=_FIN, bottom=_FIN)
_ENTETE = dict(font=Font(bold=True, color="FFFFFF"), fill=PatternFill("solid", fgColor=VERT),
               alignment=Alignment(vertical="center", wrap_text=True))
_TOTAL = dict(font=Font(bold=True), fill=PatternFill("solid", fgColor="EAF5F0"))


def _style(c, **kw):
    for k, v in kw.items():
        setattr(c, k, v)
    c.border = _BORD


def _largeurs(ws, mini=8, maxi=60):
    for col in ws.columns:
        n = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(mini, min(maxi, n + 2))


def feuille_resultat(ws, resultat: dict, titre: str | None = None, ligne: int = 1) -> int:
    """Écrit un résultat à plat (et ses totaux) à partir de `ligne` ; renvoie la ligne suivante."""
    entetes, corps, total = tableau(resultat)
    fmts = [None] * len(resultat["regroupements"]) + [m["format"] for m in resultat["mesures"]]
    if titre:
        ws.cell(ligne, 1, titre).font = Font(bold=True, size=12)
        ligne += 1
    for j, e in enumerate(entetes, 1):
        _style(ws.cell(ligne, j, e), **_ENTETE)
    ligne += 1
    for r in corps + [total]:
        est_total = r is total
        for j, v in enumerate(r, 1):
            c = ws.cell(ligne, j, v)
            if fmts[j - 1]:
                c.number_format = _excel_format(fmts[j - 1])
            _style(c, **(_TOTAL if est_total else {}))
        ligne += 1
    if resultat.get("tronque"):
        ws.cell(ligne, 1, f"Résultat limité à {len(corps)} lignes sur {resultat['nb_lignes']}.").font = Font(italic=True)
        ligne += 1
    return ligne + 1


def feuille_croisee(ws, resultat: dict, mesure: dict, ligne: int = 1) -> int:
    lignes, cols, cell, tl, tc = croise(resultat, mesure["cle"])
    g1, g2 = (g["libelle"] for g in resultat["regroupements"])
    ws.cell(ligne, 1, f"{mesure['libelle']} — {g1} × {g2}").font = Font(bold=True, size=12)
    ligne += 1
    for j, e in enumerate([g1] + cols + [TOTAL], 1):
        _style(ws.cell(ligne, j, e), **_ENTETE)
    ligne += 1
    fmt = _excel_format(mesure["format"])
    for v1 in lignes + [TOTAL]:
        rang = [v1] + [(tc.get(v2) if v1 == TOTAL else cell.get((v1, v2))) for v2 in cols] \
            + [resultat["totaux"].get(mesure["cle"]) if v1 == TOTAL else tl.get(v1)]
        for j, v in enumerate(rang, 1):
            c = ws.cell(ligne, j, v)
            if j > 1:
                c.number_format = fmt
            _style(c, **(_TOTAL if v1 == TOTAL or j == len(rang) else {}))
        ligne += 1
    return ligne + 1


def feuille_parametres(ws, params: list[tuple[str, str]], ligne: int = 1) -> int:
    for k, v in params:
        ws.cell(ligne, 1, k).font = Font(bold=True)
        ws.cell(ligne, 2, v)
        ligne += 1
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 90
    return ligne + 1


def feuille_detail(ws, detail: dict) -> None:
    for j, c in enumerate(detail["colonnes"], 1):
        _style(ws.cell(1, j, c["libelle"]), **_ENTETE)
    for i, r in enumerate(detail["lignes"], 2):
        for j, c in enumerate(detail["colonnes"], 1):
            v = r.get(c["cle"])
            if c["cle"] == "reception" and v:
                v = datetime.fromisoformat(v)
            cel = ws.cell(i, j, v)
            if isinstance(v, datetime):
                cel.number_format = "DD/MM/YYYY HH:MM"
    if detail.get("tronque"):
        ws.cell(len(detail["lignes"]) + 3, 1, f"Détail limité à {len(detail['lignes'])} lignes.").font = Font(italic=True)
    ws.freeze_panes = "A2"
    _largeurs(ws, maxi=40)


def excel_requete(resultat: dict, detail: dict, params: list[tuple[str, str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Résultat"
    feuille_resultat(ws, resultat)
    ws.freeze_panes = "A2"
    _largeurs(ws)
    if len(resultat["regroupements"]) == 2:
        wc = wb.create_sheet("Tableau croisé")
        ligne = 1
        for m in resultat["mesures"]:
            ligne = feuille_croisee(wc, resultat, m, ligne)
        _largeurs(wc, maxi=30)
    feuille_parametres(wb.create_sheet("Paramètres"), params)
    feuille_detail(wb.create_sheet("Détail"), detail)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
_base = getSampleStyleSheet()
S_TITRE = ParagraphStyle("rt", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=15, spaceAfter=2)
S_SOUS = ParagraphStyle("rs", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                        spaceBefore=8, spaceAfter=3)
S_TXT = ParagraphStyle("rx", parent=_base["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5)
S_CEL = ParagraphStyle("rc", parent=S_TXT, fontSize=7, leading=8.5)
S_CEL_G = ParagraphStyle("rg", parent=S_CEL, fontName="Helvetica-Bold")
S_NOTE = ParagraphStyle("rn", parent=S_TXT, fontName="Helvetica-Oblique", fontSize=6.5, textColor=colors.HexColor("#57606A"))
MARGE = 14 * mm


def _p(v, style=S_CEL) -> Paragraph:
    return Paragraph(escape(str(v)), style)


def pdf_parametres(params: list[tuple[str, str]], largeur: float) -> Table:
    t = Table([[_p(k, S_CEL_G), _p(v)] for k, v in params], colWidths=[38 * mm, largeur - 38 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5)]))
    return t


def _style_table(t, n_corps: int, alignes_droite_depuis: int, total: bool = True):
    st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D7DE")),
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + VERT)),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("ALIGN", (alignes_droite_depuis, 1), (-1, -1), "RIGHT"),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if total:
        st.append(("BACKGROUND", (0, n_corps + 1), (-1, n_corps + 1), colors.HexColor("#EAF5F0")))
    t.setStyle(TableStyle(st))


def pdf_tableau(resultat: dict, largeur: float) -> Table:
    entetes, corps, total = tableau(resultat)
    nreg = len(resultat["regroupements"])
    fmts = [m["format"] for m in resultat["mesures"]]
    S_ENT = ParagraphStyle("re", parent=S_CEL_G, textColor=colors.white)

    def rang(r, gras=False):
        st = S_CEL_G if gras else S_CEL
        return [_p(v if v is not None else NR, st) for v in r[:nreg]] + \
               [Paragraph(formater(v, f), st) for v, f in zip(r[nreg:], fmts)]
    data = [[_p(e, S_ENT) for e in entetes]] + [rang(r) for r in corps] + [rang(total, True)]
    lm = min(30 * mm, (largeur * 0.5) / max(1, len(fmts)))
    lg = (largeur - lm * len(fmts)) / nreg if nreg else 0
    t = Table(data, colWidths=[lg] * nreg + [lm] * len(fmts), repeatRows=1, hAlign="LEFT")
    _style_table(t, len(corps), nreg)
    return t


def pdf_croise(resultat: dict, mesure: dict, largeur: float) -> Table:
    lignes, cols, cell, tl, tc = croise(resultat, mesure["cle"])
    S_ENT = ParagraphStyle("rec", parent=S_CEL_G, textColor=colors.white)
    f = mesure["format"]
    data = [[_p(resultat["regroupements"][0]["libelle"], S_ENT)] + [_p(c, S_ENT) for c in cols] + [_p(TOTAL, S_ENT)]]
    for v1 in lignes:
        data.append([_p(v1)] + [Paragraph(formater(cell.get((v1, v2)), f) if (v1, v2) in cell else "", S_CEL)
                                for v2 in cols] + [Paragraph(formater(tl.get(v1), f), S_CEL_G)])
    data.append([_p(TOTAL, S_CEL_G)] + [Paragraph(formater(tc.get(v2), f), S_CEL_G) for v2 in cols]
                + [Paragraph(formater(resultat["totaux"].get(mesure["cle"]), f), S_CEL_G)])
    l0 = min(60 * mm, largeur * 0.3)
    lc = min(28 * mm, (largeur - l0) / (len(cols) + 1))
    t = Table(data, colWidths=[l0] + [lc] * (len(cols) + 1), repeatRows=1, hAlign="LEFT")
    _style_table(t, len(lignes), 1)
    return t


def pdf_graphique(resultat: dict, largeur: float, max_barres: int = 20) -> Drawing | None:
    """Barres horizontales de la 1re mesure (sous-totaux du 1er regroupement s'il y en a deux)."""
    if not resultat["regroupements"]:
        return None
    g = resultat["regroupements"][0]["cle"]
    m = resultat["mesures"][0]
    src = resultat["sous_totaux"][g] if len(resultat["regroupements"]) == 2 else resultat["lignes"]
    pts = [(str(r[g]), r[m["cle"]] or 0) for r in src][:max_barres]
    if not pts:
        return None
    pts.reverse()                                   # 1re ligne du tableau en haut
    h_barre = 13
    hauteur = len(pts) * h_barre + 30
    d = Drawing(largeur, hauteur)
    bc = HorizontalBarChart()
    bc.x, bc.y = 52 * mm, 18
    bc.width, bc.height = largeur - 52 * mm - 20 * mm, len(pts) * h_barre
    bc.data = [[v for _, v in pts]]
    bc.categoryAxis.categoryNames = [n if len(n) <= 40 else n[:39] + "…" for n, _ in pts]
    bc.categoryAxis.labels.fontName, bc.categoryAxis.labels.fontSize = "Helvetica", 6.5
    bc.categoryAxis.labels.boxAnchor = "e"
    bc.categoryAxis.strokeColor = colors.HexColor("#8C959F")
    bc.valueAxis.valueMin = 0
    maxi = max(v for _, v in pts)
    if m["format"] == "entier" and maxi:
        bc.valueAxis.valueStep = max(1, math.ceil(maxi / 6))     # graduations entières
        bc.valueAxis.valueMax = bc.valueAxis.valueStep * math.ceil(maxi / bc.valueAxis.valueStep)
    bc.valueAxis.labels.fontName, bc.valueAxis.labels.fontSize = "Helvetica", 6
    bc.valueAxis.strokeColor = colors.HexColor("#8C959F")
    bc.valueAxis.visibleGrid, bc.valueAxis.gridStrokeColor = True, colors.HexColor("#EAEEF2")
    bc.bars[0].fillColor = colors.HexColor("#" + VERT)
    bc.bars[0].strokeColor = None
    bc.barWidth, bc.groupSpacing = 8, 5
    bc.barLabelFormat = lambda v: formater(v, m["format"])
    bc.barLabels.fontName, bc.barLabels.fontSize, bc.barLabels.boxAnchor = "Helvetica", 6, "w"
    bc.barLabels.dx = 3
    d.add(bc)
    titre = f"{m['libelle']} par {resultat['regroupements'][0]['libelle'].lower()}"
    if len(src) > max_barres:
        titre += f" ({max_barres} premières valeurs sur {len(src)})"
    d.add(String(0, hauteur - 8, titre, fontName="Helvetica-Bold", fontSize=7.5))
    return d


def elements_resultat(resultat: dict, largeur: float, titre: str | None = None, graphique: bool = True) -> list:
    """Bloc PDF d'un résultat : titre, tableau (croisé si 2 regroupements), graphique."""
    els = []
    if titre:
        els.append(CondPageBreak(40 * mm))
        els.append(Paragraph(escape(titre), S_SOUS))
    if len(resultat["regroupements"]) == 2:
        for m in resultat["mesures"]:
            els += [Paragraph(escape(m["libelle"]), S_TXT), Spacer(1, 1.5 * mm), pdf_croise(resultat, m, largeur),
                    Spacer(1, 3 * mm)]
    else:
        els += [pdf_tableau(resultat, largeur), Spacer(1, 3 * mm)]
    if resultat.get("tronque"):
        els.append(Paragraph(f"Résultat limité à {len(resultat['lignes'])} lignes sur {resultat['nb_lignes']}.", S_NOTE))
    g = pdf_graphique(resultat, largeur) if graphique else None
    if g:
        els.append(KeepTogether([g, Spacer(1, 3 * mm)]))
    return els


def document_pdf(titre: str, contenu, auteur: str, paysage: bool = False, quand: datetime | None = None) -> bytes:
    """Document avec l'en-tête ONSSA / LRAR, le titre, et en pied la date, l'auteur et la pagination.
    `contenu(largeur)` renvoie la liste des éléments."""
    quand = quand or datetime.now()
    taille = landscape(A4) if paysage else A4
    largeur = taille[0] - 2 * MARGE
    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=taille, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE,
                          bottomMargin=MARGE + 4 * mm, title=titre, author=f"{auteur} - LRAR Tanger - ONSSA")

    def pied(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#57606A"))
        canvas.drawString(MARGE, MARGE - 2 * mm, f"{titre} - généré le {quand:%d/%m/%Y à %H:%M} par {auteur}")
        canvas.drawRightString(taille[0] - MARGE, MARGE - 2 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(MARGE, MARGE + 4 * mm, largeur,
                                                             taille[1] - 2 * MARGE - 4 * mm, id="f")],
                                       onPage=pied)])
    entete = _entete()
    entete._argW = [26 * mm, largeur - 47 * mm, 21 * mm]
    doc.build([entete, Spacer(1, 5 * mm), Paragraph(escape(titre), S_TITRE), *contenu(largeur)])
    return buf.getvalue()


def pdf_requete(resultat: dict, params: list[tuple[str, str]], titre: str, auteur: str) -> bytes:
    paysage = len(resultat["regroupements"]) == 2 or len(resultat["mesures"]) > 4

    def contenu(largeur):
        return [pdf_parametres(params, largeur), Spacer(1, 4 * mm), *elements_resultat(resultat, largeur)]
    return document_pdf(titre, contenu, auteur, paysage)
