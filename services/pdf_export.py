import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_NAME = "DejaVuSans"

def _ensure_font(font_path: str):
    # înregistrează fontul o singură dată
    try:
        pdfmetrics.getFont(_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(TTFont(_FONT_NAME, font_path))

def export_bank_pdf(rows, out_path: str = "banca_probleme.pdf") -> str:
    font_path = os.path.join(os.getcwd(), "assets", "DejaVuSans.ttf")

    c = canvas.Canvas(out_path, pagesize=A4)
    page_w, page_h = A4

    left_margin = 50
    right_margin = 50
    top_margin = 60
    bottom_margin = 60
    max_width = page_w - left_margin - right_margin

    if os.path.exists(font_path):
        _ensure_font(font_path)
        c.setFont(_FONT_NAME, 11)
        font_name = _FONT_NAME
    else:
        c.setFont("Helvetica", 11)
        font_name = "Helvetica"

    y = page_h - top_margin
    c.drawString(left_margin, y, "Banca de probleme (export)")
    y -= 25

    for i, r in enumerate(rows, start=1):
        text = f"{i}. [{r['subject']} | {r['level']} | {r['difficulty']} | {r['source']}] {r['text']}"

        words = text.split(" ")
        line = ""

        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, font_name, 11) <= max_width:
                line = test
            else:
                c.drawString(left_margin, y, line)
                y -= 14
                line = w
                if y < bottom_margin:
                    c.showPage()
                    if os.path.exists(font_path):
                        c.setFont(_FONT_NAME, 11)
                        font_name = _FONT_NAME
                    else:
                        c.setFont("Helvetica", 11)
                        font_name = "Helvetica"
                    y = page_h - top_margin

        if line:
            c.drawString(left_margin, y, line)
            y -= 16

        if y < bottom_margin:
            c.showPage()
            if os.path.exists(font_path):
                c.setFont(_FONT_NAME, 11)
                font_name = _FONT_NAME
            else:
                c.setFont("Helvetica", 11)
                font_name = "Helvetica"
            y = page_h - top_margin

    c.save()
    return out_path
def export_selected_only_text_pdf(rows, out_path: str = "test_selectie.pdf") -> str:
    font_path = os.path.join(os.getcwd(), "assets", "DejaVuSans.ttf")

    c = canvas.Canvas(out_path, pagesize=A4)
    page_w, page_h = A4

    left_margin = 50
    right_margin = 50
    top_margin = 60
    bottom_margin = 60
    max_width = page_w - left_margin - right_margin

    if os.path.exists(font_path):
        _ensure_font(font_path)
        c.setFont(_FONT_NAME, 11)
        font_name = _FONT_NAME
    else:
        c.setFont("Helvetica", 11)
        font_name = "Helvetica"

    y = page_h - top_margin
    c.drawString(left_margin, y, "Test (selecție din banca de probleme)")
    y -= 25

    for i, r in enumerate(rows, start=1):
        text = f"{i}. {r['text']}"

        words = text.split(" ")
        line = ""

        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, font_name, 11) <= max_width:
                line = test
            else:
                c.drawString(left_margin, y, line)
                y -= 14
                line = w
                if y < bottom_margin:
                    c.showPage()
                    if os.path.exists(font_path):
                        c.setFont(_FONT_NAME, 11)
                        font_name = _FONT_NAME
                    else:
                        c.setFont("Helvetica", 11)
                        font_name = "Helvetica"
                    y = page_h - top_margin

        if line:
            c.drawString(left_margin, y, line)
            y -= 18

        if y < bottom_margin:
            c.showPage()
            if os.path.exists(font_path):
                c.setFont(_FONT_NAME, 11)
                font_name = _FONT_NAME
            else:
                c.setFont("Helvetica", 11)
                font_name = "Helvetica"
            y = page_h - top_margin

    c.save()
    return out_path

