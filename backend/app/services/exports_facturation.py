"""
Exports de la facturation (tâches 39 et 40) : journal de caisse (Excel, PDF signé) et
export mensuel de la facturation (Excel).
"""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.services.exports_requetes import _ENTETE, _TOTAL, _largeurs, _style
from app.services.facturation import format_dh
from app.services.pdf_facturation import (
    GRIS, S_CEL, S_CEL_D, S_CEL_G, S_CEL_GD, S_LAB, S_NOTE, S_SIGN, S_SOUS, S_TITRE, _date, _document, _p,
)
from app.services.rapport import LARGEUR_UTILE, _entete

FORMAT_DH = '#,##0.00" DH"'


def _periode(du, au) -> str:
    return f"du {_date(du)}" if du == au else f"du {_date(du)} au {_date(au)}"


def _feuille(ws, titre: str, entetes: list[str], lignes: list[list], formats: dict | None = None, ligne: int = 1,
             total: list | None = None) -> int:
    """Tableau stylé (en-tête vert, total) à partir de la ligne donnée ; renvoie la ligne suivante."""
    ws.cell(ligne, 1, titre).font = Font(bold=True, size=12)
    ligne += 1
    for j, e in enumerate(entetes, 1):
        _style(ws.cell(ligne, j, e), **_ENTETE)
    for l in lignes:
        ligne += 1
        for j, v in enumerate(l, 1):
            c = ws.cell(ligne, j, float(v) if hasattr(v, "is_finite") else v)
            if formats and j in formats:
                c.number_format = formats[j]
    if total:
        ligne += 1
        for j, v in enumerate(total, 1):
            c = ws.cell(ligne, j, float(v) if hasattr(v, "is_finite") else v)
            _style(c, **_TOTAL)
            if formats and j in formats:
                c.number_format = formats[j]
    return ligne + 2


# ------------------------------------------------------------------
#  Journal de caisse
# ------------------------------------------------------------------
def excel_caisse(j: dict, agent: str, quand: datetime | None = None) -> bytes:
    quand = quand or datetime.now()
    wb = Workbook()
    ws = wb.active
    ws.title = "Journal de caisse"
    ligne = _feuille(
        ws, f"Journal de caisse {_periode(j['du'], j['au'])}",
        ["Date", "Quittance", "Bulletin", "Client", "Mode", "Référence", "Encaissé par", "Montant"],
        [[p["date_paiement"], p["numero_quittance"], p["bulletin"], p["client_nom"], p["mode"],
          " — ".join(x for x in (p["reference"], p["banque"]) if x), p["encaisse_par"], p["montant"]]
         for p in j["paiements"]],
        {1: "DD/MM/YYYY", 8: FORMAT_DH}, total=["Total", "", "", "", "", "", f"{j['nb']} encaissement(s)", j["total"]])
    ligne = _feuille(ws, "Totaux par mode de paiement", ["Mode", "Nombre", "Montant"],
                     [[m, v["nb"], v["montant"]] for m, v in j["par_mode"].items()], {3: FORMAT_DH}, ligne,
                     total=["Total", j["nb"], j["total"]])
    if j["annules"]:
        ligne = _feuille(ws, "Encaissements annulés (exclus des totaux)",
                         ["Date", "Quittance", "Bulletin", "Montant", "Motif", "Annulé par"],
                         [[p["date_paiement"], p["numero_quittance"], p["bulletin"], p["montant"], p["motif_annulation"],
                           p["annule_par"]] for p in j["annules"]], {1: "DD/MM/YYYY", 4: FORMAT_DH}, ligne)
    ws.cell(ligne, 1, f"Établi par {agent} le {quand:%d/%m/%Y à %H:%M}.").font = Font(italic=True)
    _largeurs(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf_caisse(j: dict, agent: str, quand: datetime | None = None) -> bytes:
    quand = quand or datetime.now()
    larg = [18 * mm, 27 * mm, 27 * mm, LARGEUR_UTILE - 18 * mm - 27 * mm * 2 - 40 * mm - 26 * mm, 40 * mm, 26 * mm]
    data = [[_p(h, S_CEL_G if i < 5 else S_CEL_GD) for i, h in
             enumerate(["Date", "Quittance", "Bulletin", "Client", "Mode / référence", "Montant"])]]
    for p in j["paiements"]:
        ref = " — ".join(x for x in (p["reference"], p["banque"]) if x)
        data.append([_p(_date(p["date_paiement"])), _p(p["numero_quittance"]), _p(p["bulletin"]), _p(p["client_nom"]),
                     _p(p["mode"] + (f" ({ref})" if ref else "")), _p(format_dh(p["montant"]), S_CEL_D)])
    data.append(["", "", "", "", _p(f"Total ({j['nb']})", S_CEL_G), _p(format_dh(j["total"]), S_CEL_GD)])
    t = Table(data, colWidths=larg, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, 0), (-1, 0), GRIS),
                           ("BACKGROUND", (0, -1), (-1, -1), GRIS), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    modes = Table([[_p("Mode", S_CEL_G), _p("Nombre", S_CEL_GD), _p("Montant", S_CEL_GD)]]
                  + [[_p(m.capitalize()), _p(str(v["nb"]), S_CEL_D), _p(format_dh(v["montant"]), S_CEL_D)]
                     for m, v in j["par_mode"].items()]
                  + [[_p("Total", S_CEL_G), _p(str(j["nb"]), S_CEL_GD), _p(format_dh(j["total"]), S_CEL_GD)]],
                  colWidths=[40 * mm, 22 * mm, 34 * mm], hAlign="LEFT")
    modes.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("BACKGROUND", (0, 0), (-1, 0), GRIS),
                               ("BACKGROUND", (0, -1), (-1, -1), GRIS)]))
    flow = [_entete(), Spacer(1, 5 * mm), Paragraph("JOURNAL DE CAISSE", S_TITRE),
            Paragraph(f"Encaissements {_periode(j['du'], j['au'])}", S_SOUS), Spacer(1, 5 * mm), t, Spacer(1, 4 * mm),
            Paragraph("Totaux par mode de paiement", S_LAB), Spacer(1, 1 * mm), modes]
    if j["annules"]:
        flow += [Spacer(1, 3 * mm), Paragraph(
            "Encaissements annulés (exclus des totaux) : " + "; ".join(
                f"{escape(p['numero_quittance'])} ({escape(format_dh(p['montant']))}, {escape(p['motif_annulation'] or '')})"
                for p in j["annules"]), S_NOTE)]
    sign = Table([[Paragraph(f"Établi par {escape(agent)}<br/>le {quand:%d/%m/%Y à %H:%M}", S_SIGN),
                   Paragraph("Visa du régisseur", S_SIGN)]], colWidths=[LARGEUR_UTILE / 2] * 2, rowHeights=[24 * mm])
    sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow += [Spacer(1, 8 * mm), sign]
    return _document(flow, f"Journal de caisse {_periode(j['du'], j['au'])} — établi par {agent} le {quand:%d/%m/%Y %H:%M}")
