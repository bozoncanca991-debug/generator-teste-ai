import os
from datetime import datetime
from playwright.sync_api import sync_playwright
from flask import render_template

def _ensure_out_dir(out_path: str):
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

def render_pdf_from_html(html: str, out_path: str) -> str:
    _ensure_out_dir(out_path)
    with sync_playwright() as p:
        # Înlocuiește linia de launch cu varianta asta stabilă pentru servere:
        browser = p.chromium.launch(
    headless=True,
    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
)
        page = browser.new_page()

        page.set_content(html, wait_until="networkidle")

        page.pdf(
            path=out_path,
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                "<div style='width:100%; font-size:9px; color:#666; padding:0 16mm;'>"
                "<span style='float:right;'>Pagina <span class='pageNumber'></span> / <span class='totalPages'></span></span>"
                "</div>"
            ),
            margin={"top": "18mm", "right": "16mm", "bottom": "18mm", "left": "16mm"},
        )
        browser.close()
    return out_path

def export_bank_pdf_premium(rows, out_path: str = "banca_probleme.pdf") -> str:
    html = render_template(
        "pdf_bank.html",
        title="Banca de probleme (export)",
        subtitle="",
        generated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
        rows=rows,
    )
    return render_pdf_from_html(html, out_path)

def export_selected_only_text_pdf_premium(rows, out_path: str = "test_selectie.pdf") -> str:
    html = render_template(
        "pdf_selected.html",
        title="Test (selecție din banca de probleme)",
        generated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
        rows=rows,
    )
    return render_pdf_from_html(html, out_path)

def export_smart_test_pdf_premium(variants: list, subject: str, level: str, out_path: str = "teste_generate.pdf") -> str:
    html = render_template(
        "pdf_smart_test.html",
        title=f"Test: {subject}",
        subject=subject,
        level=level,
        variants=variants
    )
    return render_pdf_from_html(html, out_path)