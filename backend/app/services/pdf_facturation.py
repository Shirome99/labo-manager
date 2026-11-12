"""
PDF de la facturation (ReportLab) : bulletin / avoir (tâche 36) et reçu de paiement (tâche 37).
En-tête ONSSA / LRAR repris du rapport d'essai ; montants en dirhams et en lettres.
"""
from collections import OrderedDict
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from app.services.facturation import format_dh, montant_en_lettres
from app.services.rapport import LARGEUR_UTILE, MARGE, _entete

LIBELLE_SECTION = {"SMA": "Microbiologie Alimentaire", "SCHA": "Sécurité Chimie Hygiène Alimentaire",
                   "SSA": "Santé Animale", None: "Frais divers"}

_b = getSampleStyleSheet()["Normal"]
S_TITRE = ParagraphStyle("ft", parent=_b, fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_CENTER)
S_SOUS = ParagraphStyle("fs", parent=_b, fontName="Helvetica", fontSize=8, leading=10, alignment=TA_CENTER)
S_LAB = ParagraphStyle("fl", parent=_b, fontName="Helvetica-Bold", fontSize=8, leading=10)
S_VAL = ParagraphStyle("fv", parent=_b, fontName="Helvetica", fontSize=8, leading=10)
S_CEL = ParagraphStyle("fc", parent=_b, fontName="Helvetica", fontSize=7.5, leading=9.5)
S_CEL_D = ParagraphStyle("fd", parent=S_CEL, alignment=TA_RIGHT)
S_CEL_G = ParagraphStyle("fg", parent=S_CEL, fontName="Helvetica-Bold")
S_CEL_GD = ParagraphStyle("fgd", parent=S_CEL_G, alignment=TA_RIGHT)
S_NOTE = ParagraphStyle("fn", parent=_b, fontName="Helvetica-Oblique", fontSize=7, leading=9)
S_SIGN = ParagraphStyle("fsi", parent=_b, fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER)
GRIS = colors.Color(0.94, 0.94, 0.94)


def _p(v, style=S_CEL):
    return Paragraph(escape("" if v is None else str(v)), style)


def _date(d):
    return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else (str(d) if d else "")


def _qte(q):
    q = float(q)
    return f"{q:g}".replace(".", ",")


def _document(flow, pied: str, brouillon: bool = False) -> bytes:
    buf = BytesIO()

    def _page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 6)
        canvas.drawString(MARGE, MARGE - 6 * mm, pied)
        canvas.drawRightString(A4[0] - MARGE, MARGE - 6 * mm, f"Page {doc.page}")
        canvas.drawCentredString(A4[0] / 2, MARGE - 9 * mm,
                                 "LRAR de Tanger, Rue Ibn Taimiate BP: 3 Tanger, Tél : 0539940540 Fax : 0539943919")
        if brouillon:
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.Color(0.85, 0.85, 0.85))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "BROUILLON")
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE,
                          bottomMargin=MARGE, title="Bulletin", author="LRAR Tanger")
    doc.addPageTemplates([PageTemplate(frames=[Frame(MARGE, MARGE, LARGEUR_UTILE, A4[1] - 2 * MARGE, id="f")],
                                       onPage=_page)])
    doc.build(flow)
    return buf.getvalue()


def _bloc_client(c: dict, echantillons: list[dict]) -> list:
    t = Table([
        [_p("Client", S_LAB), _p(c.get("client_nom") or "Non renseigné", S_VAL)],
        [_p("Adresse", S_LAB), _p(c.get("client_adresse") or "", S_VAL)],
    ], colWidths=[30 * mm, LARGEUR_UTILE - 30 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), GRIS)]))
    data = [[_p("N° échantillon", S_CEL_G), _p("Nature", S_CEL_G), _p("Réception", S_CEL_G)]]
    for e in echantillons:
        data.append([_p(e["num"]), _p(e.get("nature")), _p(_date(e.get("reception")))])
    te = Table(data, colWidths=[40 * mm, LARGEUR_UTILE - 70 * mm, 30 * mm], repeatRows=1)
    te.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, 0), (-1, 0), GRIS)]))
    return [t, Spacer(1, 3 * mm), Paragraph("Échantillons concernés", S_LAB), Spacer(1, 1 * mm), te]


def _tableau_lignes(c: dict) -> Table:
    larg = [26 * mm, LARGEUR_UTILE - 26 * mm - 16 * mm - 28 * mm - 28 * mm, 16 * mm, 28 * mm, 28 * mm]
    data = [[_p(h, S_CEL_G if i < 2 else S_CEL_GD) for i, h in
             enumerate(["Échantillon", "Analyse / libellé", "Qté", "Prix unitaire", "Montant"])]]
    styles = [("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, 0), (-1, 0), GRIS),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    groupes: OrderedDict = OrderedDict()
    for l in c["lignes"]:
        groupes.setdefault(l["section"], []).append(l)
    for section, lignes in groupes.items():
        data.append([_p(LIBELLE_SECTION.get(section, section), S_CEL_G), "", "", "", ""])
        styles += [("SPAN", (0, len(data) - 1), (-1, len(data) - 1)),
                   ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), colors.Color(0.97, 0.97, 0.97))]
        for l in lignes:
            data.append([_p(l["num_echantillon"] or ""), _p(l["analyse"]), _p(_qte(l["quantite"]), S_CEL_D),
                         _p("" if l["prix_unitaire"] is None else format_dh(abs(l["prix_unitaire"])), S_CEL_D),
                         _p(format_dh(l["montant"]), S_CEL_D)])
        sous_total = sum(float(l["montant"]) for l in lignes)
        data.append(["", _p(f"Sous-total {section or 'divers'}", S_CEL_G), "", "", _p(format_dh(sous_total), S_CEL_GD)])
        styles.append(("SPAN", (1, len(data) - 1), (3, len(data) - 1)))
    t = Table(data, colWidths=larg, repeatRows=1)
    t.setStyle(TableStyle(styles))
    return t


def _totaux(c: dict, taux_tva) -> Table:
    lignes = []
    if float(taux_tva or 0) > 0:
        lignes += [("Total HT", c["total_ht"]), (f"TVA {float(taux_tva):g} %".replace(".", ","), c["montant_tva"])]
    lignes.append(("Total TTC" if float(taux_tva or 0) > 0 else "Total", c["total_ttc"]))
    data = [[_p(l, S_CEL_G), _p(format_dh(v), S_CEL_GD)] for l, v in lignes]
    t = Table(data, colWidths=[40 * mm, 34 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, -1), (-1, -1), GRIS)]))
    return t


def pdf_bulletin(c: dict, echantillons: list[dict], taux_tva) -> bytes:
    """Bulletin ou avoir ; c = contenu (services.bulletins.contenu)."""
    avoir = c["type"] == "avoir"
    brouillon = c["statut"] == "brouillon"
    titre = "AVOIR" if avoir else "BULLETIN DE VERSEMENT"
    numero = c["numero"] or "(brouillon, sans numéro)"
    flow = [_entete(), Spacer(1, 5 * mm), Paragraph(f"{titre} N° {escape(numero)}", S_TITRE),
            Paragraph(f"Date : {_date(c['date_emission']) or '—'}", S_SOUS), Spacer(1, 4 * mm)]
    if avoir and c.get("origine"):
        o = c["origine"]
        partiel = abs(float(c["total_ttc"])) < float(o["total_ttc"])
        flow += [Paragraph(f"<b>Annule {'partiellement ' if partiel else ''}"
                           f"le bulletin n° {escape(o['numero'])} du {_date(o['date_emission'])}.</b> "
                           f"Motif : {escape(c.get('motif') or '')}", S_VAL), Spacer(1, 3 * mm)]
    flow += _bloc_client(c, echantillons)
    flow += [Spacer(1, 4 * mm), _tableau_lignes(c), Spacer(1, 2 * mm), _totaux(c, taux_tva), Spacer(1, 4 * mm)]
    mot = "le présent avoir" if avoir else "le présent bulletin"
    flow.append(Paragraph(f"Arrêté {mot} à la somme de : <b>{escape(montant_en_lettres(c['total_ttc']))}</b>"
                          f"{' (à déduire)' if avoir else ''}.", S_VAL))
    flow.append(Spacer(1, 3 * mm))
    if not avoir:
        flow.append(Paragraph(
            "Paiement à effectuer auprès de la régie du laboratoire (espèces, chèque ou virement), en rappelant le "
            "numéro du bulletin. Une quittance est remise pour chaque encaissement. Le rapport d'essai peut être "
            "subordonné au règlement du bulletin.", S_NOTE))
    flow.append(Spacer(1, 10 * mm))
    sign = Table([[Paragraph("Le Régisseur", S_SIGN), Paragraph("Le Directeur du LRAR<br/>de Tanger", S_SIGN)]],
                 colWidths=[LARGEUR_UTILE / 2] * 2, rowHeights=[22 * mm])
    sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(sign)
    pied = (f"{titre.capitalize()} {numero} — émis le {_date(c['date_emission'])} par {c.get('emise_par') or ''}"
            if not brouillon else "Brouillon : sans valeur comptable")
    return _document(flow, pied, brouillon=brouillon)


def pdf_quittance(p: dict, c: dict, echantillons: list[dict]) -> bytes:
    """Reçu de paiement : n° de quittance, montant en chiffres et en lettres, mode, bulletin concerné."""
    mode = p["mode"] + (f" n° {p['reference']}" if p.get("reference") else "") + (f" — {p['banque']}" if p.get("banque") else "")
    lignes = [
        ("Reçu de", c.get("client_nom") or "Non renseigné"),
        ("Bulletin", f"{c['numero']} du {_date(c['date_emission'])} — net à payer {format_dh(c['net'])}"),
        ("Échantillon(s)", ", ".join(e["num"] for e in echantillons)),
        ("Date du paiement", _date(p["date_paiement"])),
        ("Mode de paiement", mode),
        ("Montant", format_dh(p["montant"])),
        ("Reste dû après ce paiement", format_dh(c["reste"])),
    ]
    if p.get("trop_percu"):
        lignes.append(("Observation", "Trop-perçu signalé"))
    if p.get("observation"):
        lignes.append(("Observation", p["observation"]))
    t = Table([[_p(a, S_LAB), _p(b, S_VAL)] for a, b in lignes], colWidths=[50 * mm, LARGEUR_UTILE - 50 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, 0), (0, -1), GRIS),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow = [_entete(), Spacer(1, 6 * mm),
            Paragraph(f"REÇU DE PAIEMENT — QUITTANCE N° {escape(p['numero_quittance'])}", S_TITRE),
            Spacer(1, 6 * mm), t, Spacer(1, 5 * mm),
            Paragraph(f"Reçu la somme de : <b>{escape(montant_en_lettres(p['montant']))}</b>.", S_VAL),
            Spacer(1, 12 * mm)]
    sign = Table([["", Paragraph(f"Le Régisseur<br/><font name='Helvetica'>{escape(p.get('encaisse_par') or '')}</font>", S_SIGN)]],
                 colWidths=[LARGEUR_UTILE / 2] * 2, rowHeights=[22 * mm])
    sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(sign)
    return _document(flow, f"Quittance {p['numero_quittance']} — encaissée le {_date(p['date_paiement'])} "
                           f"par {p.get('encaisse_par') or ''}")
