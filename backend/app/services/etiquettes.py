"""
Étiquettes d'échantillon (PDF) : une page par étiquette, au format de l'étiquette
(50 × 25 mm par défaut), pour les imprimantes d'étiquettes comme pour une impression
ordinaire. Code-barres Code 128 du n° d'échantillon (reportlab.graphics.barcode,
sans dépendance supplémentaire), section, nature, date de réception, n° de prélèvement.
"""
from io import BytesIO

from reportlab.graphics.barcode.code128 import Code128Auto
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

MARGE = 1.5 * mm
# Largeur minimale d'un module : 2 points d'une imprimante 203 dpi (0,25 mm)
MODULE_MIN = 0.25 * mm


def _tronquer(c, texte, police, taille, largeur):
    texte = texte or ""
    if c.stringWidth(texte, police, taille) <= largeur:
        return texte
    while texte and c.stringWidth(texte + "…", police, taille) > largeur:
        texte = texte[:-1]
    return texte + "…"


def generer_etiquettes(num: str, section: str, nature: str | None, date_reception: str | None,
                       nombre: int = 1, largeur_mm: float = 50, hauteur_mm: float = 25) -> bytes:
    larg, haut = largeur_mm * mm, hauteur_mm * mm
    utile = larg - 2 * MARGE
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(larg, haut))
    c.setTitle(f"Étiquettes {num}")
    c.setAuthor("LRAR Tanger - ONSSA")

    # Taille du module : la plus grande qui tient dans la largeur, zones de silence
    # comprises (10 modules de chaque côté, minimum de la norme Code 128 ; ReportLab
    # en mettrait au moins 6,35 mm par défaut)
    essai = Code128Auto(num, barWidth=1, quiet=True, lquiet=10, rquiet=10)
    module = max(MODULE_MIN, min(0.40 * mm, larg / essai.width))
    corps = 6 if hauteur_mm >= 22 else 5
    hauteur_barres = max(haut - 2 * MARGE - 3 * (corps + 1.5), 5 * mm)

    for i in range(1, max(1, nombre) + 1):
        y = haut - MARGE - corps
        # Ligne 1 : section + n° d'échantillon
        c.setFont("Helvetica-Bold", corps + 1)
        c.drawString(MARGE, y, f"{section}  {num}")
        # Code-barres (centré)
        bc = Code128Auto(num, barWidth=module, barHeight=hauteur_barres, quiet=True,
                         lquiet=10 * module, rquiet=10 * module)
        y -= hauteur_barres + 1.5
        bc.drawOn(c, (larg - bc.width) / 2, y)
        # Ligne 3 : nature ; ligne 4 : date de réception + prélèvement i/n
        c.setFont("Helvetica", corps)
        y -= corps + 1
        c.drawString(MARGE, y, _tronquer(c, nature or "—", "Helvetica", corps, utile))
        y -= corps + 1.5
        c.drawString(MARGE, y, f"Reçu le {date_reception or '—'}")
        c.drawRightString(larg - MARGE, y, f"Prlvt {i}/{max(1, nombre)}")
        c.showPage()

    c.save()
    return buf.getvalue()
