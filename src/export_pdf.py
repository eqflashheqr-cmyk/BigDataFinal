"""
export_pdf.py — Render `results/report.md` to `report.pdf`.

The assignment's Deliverable 3 specifies a `report.pdf` at the repository
root. This module converts the Markdown report into a PDF using ReportLab,
handling the subset of Markdown that the report actually uses: headings,
paragraphs, bullet lists, fenced code blocks, pipe tables, blockquotes and
image references.

Usage
-----
    python src/export_pdf.py
"""

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
INK = colors.HexColor("#1F2933")
ACCENT = colors.HexColor("#3D5A80")
MUTED = colors.HexColor("#52606D")
RULE = colors.HexColor("#CBD2D9")
BAND = colors.HexColor("#F0F4F8")
QUOTE_BAR = colors.HexColor("#3D5A80")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


def build_styles() -> dict:
    ss = getSampleStyleSheet()
    base = ParagraphStyle("Body", parent=ss["BodyText"], fontName="Helvetica",
                          fontSize=9.4, leading=13.6, textColor=INK,
                          spaceAfter=6, alignment=4)
    return {
        "h1": ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                              fontSize=17, leading=21, textColor=ACCENT,
                              spaceBefore=14, spaceAfter=8),
        "h2": ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12.6, leading=16, textColor=INK,
                              spaceBefore=11, spaceAfter=5),
        "h3": ParagraphStyle("H3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                              fontSize=10.6, leading=14, textColor=MUTED,
                              spaceBefore=9, spaceAfter=4),
        "body": base,
        "bullet": ParagraphStyle("Bullet", parent=base, leftIndent=11,
                                  bulletIndent=2, spaceAfter=3),
        "quote": ParagraphStyle("Quote", parent=base, leftIndent=9,
                                 textColor=MUTED, spaceBefore=4, spaceAfter=6),
        "code": ParagraphStyle("Code", parent=base, fontName="Courier",
                                fontSize=8.2, leading=10.6,
                                backColor=BAND, borderPadding=6),
        "caption": ParagraphStyle("Caption", parent=base, fontSize=8.2,
                                   leading=11, textColor=MUTED,
                                   alignment=TA_CENTER, spaceAfter=10),
        "cell": ParagraphStyle("Cell", parent=base, fontSize=7.9, leading=10.4,
                                spaceAfter=0),
        "cellb": ParagraphStyle("CellB", parent=base, fontSize=7.9, leading=10.4,
                                fontName="Helvetica-Bold", spaceAfter=0),
    }


def inline(text: str) -> str:
    """Convert the inline Markdown that the report uses into ReportLab markup."""
    # Escape the characters that ReportLab treats as markup.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Images: ![alt](path)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                   lambda m: f"@@IMAGE:{m.group(2)}|{m.group(1)}@@", text)
    # Bold, then italic, then inline code.
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8.4">\1</font>', text)
    # Explicit <br/> tags written by the report generator are kept as line
    # breaks; everything else was escaped above.
    text = text.replace("&lt;br/&gt;", "<br/>")
    return text


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def build_table(rows: list[list[str]], styles: dict) -> Table:
    header, body = rows[0], rows[1:]
    data = [[Paragraph(inline(c), styles["cellb"]) for c in header]]
    for r in body:
        data.append([Paragraph(inline(c), styles["cell"]) for c in r])

    ncols = len(header)
    usable = PAGE_W - 2 * MARGIN
    # Width proportional to the longest cell in each column, capped.
    weights = []
    for i in range(ncols):
        longest = max(
            [len(re.sub(r"[*`]", "", header[i]))]
            + [len(re.sub(r"[*`]", "", r[i])) for r in body if i < len(r)]
        )
        # A header word must fit on one line, so the minimum is the header
        # length plus a little padding, never less than 8.
        weights.append(min(max(longest, len(header[i]) + 3, 8), 44))
    total = sum(weights)
    widths = [usable * w / total for w in weights]

    # Short-value columns such as "Agree" still need room for their header.
    for i, h in enumerate(header):
        need = len(h) * 5.0 + 12
        if widths[i] < need:
            deficit = need - widths[i]
            # take the space from the widest column
            j = max(range(ncols), key=lambda k: widths[k])
            take = min(deficit, widths[j] - need if j != i else 0)
            if take > 0:
                widths[j] -= take
                widths[i] += take

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def markdown_to_flowables(md: str, styles: dict, project_root: Path) -> list:
    flow = []
    lines = md.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ---- fenced code ------------------------------------------------
        if stripped.startswith("```"):
            i += 1
            block = []
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            flow.append(Preformatted("\n".join(block), styles["code"]))
            flow.append(Spacer(1, 6))
            continue

        # ---- table ------------------------------------------------------
        if stripped.startswith("|") and i + 1 < n and set(
                lines[i + 1].strip().replace("|", "").replace(" ", "")
        ) <= set("-:") and lines[i + 1].strip():
            rows = [split_table_row(lines[i])]
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            flow.append(build_table(rows, styles))
            flow.append(Spacer(1, 9))
            continue

        # ---- image ------------------------------------------------------
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if m:
            rel, alt = m.group(2), m.group(1)
            path = (project_root / rel).resolve()
            if path.exists():
                from PIL import Image as PILImage
                with PILImage.open(path) as im:
                    iw, ih = im.size
                max_w = PAGE_W - 2 * MARGIN
                max_h = 92 * mm
                scale = min(max_w / iw, max_h / ih)
                img = Image(str(path), width=iw * scale, height=ih * scale)
                img.hAlign = "CENTER"
                cap = alt or Path(rel).stem.replace("_", " ")
                flow.append(KeepTogether([
                    img,
                    Spacer(1, 3),
                    Paragraph(inline(cap), styles["caption"]),
                ]))
                i += 1
                continue
            flow.append(Paragraph(f"<i>[missing image: {inline(rel)}]</i>", styles["caption"]))
            i += 1
            continue

        # ---- headings ----------------------------------------------------
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level, text = len(m.group(1)), m.group(2)
            style = {1: styles["h1"], 2: styles["h2"], 3: styles["h3"]}.get(
                level, styles["h3"])
            flow.append(Paragraph(inline(text), style))
            if level == 1:
                flow.append(Spacer(1, 2))
            i += 1
            continue

        # ---- horizontal rule --------------------------------------------
        if stripped in ("---", "***", "___"):
            flow.append(Spacer(1, 6))
            i += 1
            continue

        # ---- blockquote ---------------------------------------------------
        if stripped.startswith(">"):
            block = []
            while i < n and lines[i].strip().startswith(">"):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            text = " ".join(x for x in block if x)
            t = Table([[Paragraph(inline(text), styles["quote"])]],
                      colWidths=[PAGE_W - 2 * MARGIN - 8])
            t.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, QUOTE_BAR),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 5))
            continue

        # ---- bullet list --------------------------------------------------
        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            items = []
            while i < n:
                mm2 = re.match(r"^([-*]|\d+\.)\s+(.*)$", lines[i].strip())
                if not mm2:
                    break
                items.append(mm2.group(2))
                i += 1
            for it in items:
                flow.append(Paragraph(inline(it), styles["bullet"], bulletText="\u2022"))
            flow.append(Spacer(1, 3))
            continue

        # ---- numbered list -------------------------------------------------
        m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            num = int(re.match(r"^(\d+)", stripped).group(1))
            items = []
            while i < n:
                mm2 = re.match(r"^\d+[.)]\s+(.*)$", lines[i].strip())
                if not mm2:
                    break
                items.append(mm2.group(1))
                i += 1
            for it in items:
                flow.append(Paragraph(inline(it), styles["bullet"], bulletText=f"{num}."))
                num += 1
            flow.append(Spacer(1, 3))
            continue

        # ---- blank ---------------------------------------------------------
        if not stripped:
            i += 1
            continue

        # ---- paragraph ------------------------------------------------------
        block = []
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|[-*]\s|\d+[.)]\s|\||>|```|!\[)", lines[i].strip()):
            block.append(lines[i].strip())
            i += 1
        if block:
            # `inline()` already converts the Markdown emphasis to ReportLab
            # markup, so it must not be pre-converted here — doing so would
            # make `inline()` escape the tags and render them literally.
            text = " ".join(block)
            flow.append(Paragraph(inline(text), styles["body"]))

    return flow


def _page_furniture(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.4)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 9.6 * mm,
                      "Big Data Analysis — HMDA 2024: Joint vs. Single Mortgage Applications")
    canvas.drawRightString(PAGE_W - MARGIN, 9.6 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    md_path = C.RESULTS_DIR / "report.md"
    if not md_path.exists():
        raise SystemExit(f"Not found: {md_path}. Run `python src/report.py` first.")

    md = md_path.read_text(encoding="utf-8")
    styles = build_styles()
    project_root = C.ROOT

    out = C.ROOT / "report.pdf"
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=19 * mm,
        title="Joint vs. Single Mortgage Applications in HMDA 2024",
        author="Big Data Analysis — Final Project",
        subject="Large-Scale Analysis of Mortgage Lending Data (HMDA 2024)",
    )
    flow = markdown_to_flowables(md, styles, project_root)
    doc.build(flow, onFirstPage=_page_furniture, onLaterPages=_page_furniture)

    size = out.stat().st_size / 1024
    print(f"Written: {out}  ({size:,.0f} KB)")


if __name__ == "__main__":
    main()
