"""
Build a formatted PDF from docs/Azraq_Monte_Carlo_API_Reference.md (single canonical doc).

Usage (repo root):
  python scripts/build_api_reference_pdf.py

Steps:
  1. Reads docs/Azraq_Monte_Carlo_API_Reference.md (does not modify it)
  2. Renders Markdown -> HTML -> PDF -> docs/Azraq_Monte_Carlo_API_Reference.pdf

PDF engine (first available):
  A) Microsoft Edge/Chromium --headless --print-to-pdf (no extra installs)
  B) Google Chrome --headless (same)
  C) npx md-to-pdf (Node + Puppeteer; slow first run)

Pure-Python deps: pip install markdown
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import markdown
except ImportError:
    print("pip install markdown", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
SOURCE_MD = ROOT / "docs" / "Azraq_Monte_Carlo_API_Reference.md"
PDF_OUT = ROOT / "docs" / "Azraq_Monte_Carlo_API_Reference.pdf"
HTML_TMP = Path(tempfile.gettempdir()) / "azraq_api_ref_print.html"

PRINT_CSS = """
@page { size: A4; margin: 18mm 15mm; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 10.5pt; line-height: 1.35; color: #111; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 6pt; page-break-after: avoid; }
h2 { font-size: 14pt; margin-top: 16pt; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 12pt; page-break-after: avoid; }
h4 { font-size: 11pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 8.8pt; page-break-inside: auto; }
thead { display: table-header-group; }
th, td { border: 1px solid #888; padding: 4pt 6pt; vertical-align: top; }
th { background: #f0f0f0; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; background: #f5f5f5; padding: 1px 3px; }
pre { font-family: Consolas, "Courier New", monospace; font-size: 7.8pt; line-height: 1.25; background: #f8f8f8; border: 1px solid #ddd; padding: 7pt; overflow-x: auto; page-break-inside: avoid; white-space: pre-wrap; word-break: break-word; }
hr { border: none; border-top: 1px solid #ccc; margin: 12pt 0; }
a { color: #0b57d0; word-break: break-all; }
ul { margin: 6pt 0; padding-left: 18pt; }
"""


def _find_chrome() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH"),
        os.environ.get("EDGE_PATH"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if p and Path(p).is_file():
            return p
    return shutil.which("msedge.exe") or shutil.which("chrome.exe")


def md_to_html_document(md: str) -> str:
    body = markdown.markdown(
        md,
        extensions=["tables", "fenced_code", "toc"],
        extension_configs={"toc": {"title": "Contents", "permalink": False}},
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Azraq Monte Carlo API Reference</title>
<style>{PRINT_CSS}</style>
</head><body>
{body}
</body></html>"""


def print_html_to_pdf(chrome: str, html_path: Path, pdf_path: Path) -> bool:
    # file:// URL
    url = html_path.resolve().as_uri()
    pdf_path = pdf_path.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        url,
    ]
    print("Running:", " ".join(args[:4]), "...")
    r = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout or "headless print failed", file=sys.stderr)
        return False
    return pdf_path.is_file()


def try_md_to_pdf_npx() -> bool:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return False
    cmd = f'"{npx}" --yes md-to-pdf "{SOURCE_MD}"'
    r = subprocess.run(cmd, cwd=str(ROOT), shell=True, timeout=300)
    return r.returncode == 0 and PDF_OUT.is_file()


def main() -> int:
    if not SOURCE_MD.is_file():
        print(f"Missing {SOURCE_MD}", file=sys.stderr)
        return 1

    md_text = SOURCE_MD.read_text(encoding="utf-8")
    html = md_to_html_document(md_text)
    HTML_TMP.write_text(html, encoding="utf-8")

    chrome = _find_chrome()
    if chrome and print_html_to_pdf(chrome, HTML_TMP, PDF_OUT):
        print(f"Wrote {PDF_OUT} (via headless browser)")
        return 0

    print("Headless Chrome/Edge not found or failed; trying npx md-to-pdf ...")
    if try_md_to_pdf_npx():
        print(f"Wrote {PDF_OUT} (via md-to-pdf)")
        return 0

    # Fallback: leave HTML next to docs for manual Print to PDF
    fallback_html = ROOT / "docs" / "Azraq_Monte_Carlo_API_Reference.html"
    fallback_html.write_text(html, encoding="utf-8")
    print(
        f"Could not run headless PDF. Wrote {fallback_html} — open in a browser and use Print -> Save as PDF.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
