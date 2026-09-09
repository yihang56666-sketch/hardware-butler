import os
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "stm32-quadrotor-report.pdf"

FILES = [
    "README.md",
    "01-requirements.md",
    "02-architecture.md",
    "03-components.md",
    "04-constraints.md",
    "05-validation.md",
    "06-decisions.md",
    "07-schematics.md",
    "hardware-solution.md",
    "stm32-quadrotor-report.md",
    "plan.md",
]


def register_font() -> str:
    candidates = [
        Path(os.environ.get("WINDIR", "/Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", "/Windows")) / "Fonts" / "simhei.ttf",
        Path(os.environ.get("WINDIR", "/Windows")) / "Fonts" / "simsun.ttc",
    ]
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("CJK", str(path)))
            return "CJK"
    return "Helvetica"


def clean_inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def add_markdown(story, text: str, styles):
    in_code = False
    code_lines = []

    def flush_code():
        nonlocal code_lines
        if code_lines:
            body = "<br/>".join(clean_inline(line) for line in code_lines)
            story.append(Paragraph(body, styles["Code"]))
            story.append(Spacer(1, 3 * mm))
            code_lines = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            story.append(Spacer(1, 2.5 * mm))
            continue

        if line.startswith("# "):
            story.append(Paragraph(clean_inline(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(clean_inline(line[3:]), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(clean_inline(line[4:]), styles["Heading3"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + clean_inline(line[2:]), styles["Bullet"]))
        elif re.match(r"^\d+\. ", line):
            story.append(Paragraph(clean_inline(line), styles["Bullet"]))
        elif line.startswith("|"):
            story.append(Paragraph(clean_inline(line), styles["TableText"]))
        else:
            story.append(Paragraph(clean_inline(line), styles["Body"]))
    flush_code()


def main():
    font_name = register_font()
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#0F766E"),
            spaceAfter=8,
        ),
        "Heading2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1e8449"),
            spaceBefore=8,
            spaceAfter=5,
        ),
        "Heading3": ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            fontName=font_name,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#2e86c1"),
            spaceBefore=5,
            spaceAfter=3,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=14,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=14,
            leftIndent=8 * mm,
        ),
        "TableText": ParagraphStyle(
            "TableText",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#34495e"),
        ),
        "Code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            backColor=colors.HexColor("#f4f6f7"),
            borderColor=colors.HexColor("#d5dbdb"),
            borderWidth=0.4,
            borderPadding=4,
        ),
    }

    story = []
    for index, name in enumerate(FILES):
        path = ROOT / name
        if not path.exists():
            continue
        if index:
            story.append(PageBreak())
        add_markdown(story, path.read_text(encoding="utf-8"), styles)

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="STM32 Small Quadrotor Drone Hardware Report",
    )
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
