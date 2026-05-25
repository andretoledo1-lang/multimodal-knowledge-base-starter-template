"""
One-click sample data generator.

Generates a small, self-contained set of demo files using PIL + fitz so the
tutorial works fully offline. Every asset is procedurally created here -
no external downloads, no licensing concerns.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

SAMPLES_DIR = Path("samples")


def _font(size: int = 32) -> ImageFont.ImageFont:
    """Best-effort font lookup with fallback."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",          # macOS
        "/System/Library/Fonts/Supplemental/Arial.ttf", # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _image_with_text(
    text: str,
    *,
    bg: tuple[int, int, int],
    fg: tuple[int, int, int] = (255, 255, 255),
    accent: tuple[int, int, int] | None = None,
    size: tuple[int, int] = (1024, 1024),
) -> Image.Image:
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    if accent:
        # Decorative accent bar
        draw.rectangle((0, size[1] - 80, size[0], size[1]), fill=accent)
    title_font = _font(64)
    body_font = _font(28)
    lines = text.split("\n")
    title = lines[0]
    body = "\n".join(lines[1:])
    draw.text((60, 80), title, fill=fg, font=title_font)
    draw.multiline_text((60, 220), body, fill=fg, font=body_font, spacing=12)
    draw.text(
        (60, size[1] - 60),
        "multimodal_kb_demo · sample asset",
        fill=(255, 255, 255),
        font=_font(18),
    )
    return img


def _make_logo(text: str, palette: tuple, path: Path) -> None:
    img = _image_with_text(
        text,
        bg=palette[0],
        fg=palette[1],
        accent=palette[2],
        size=(1024, 1024),
    )
    img.save(path, "PNG")


def _make_chart_image(path: Path) -> None:
    """A fake bar chart so vision RAG has something visual to reason about."""
    w, h = 1280, 720
    img = Image.new("RGB", (w, h), (250, 250, 252))
    draw = ImageDraw.Draw(img)
    title_font = _font(40)
    label_font = _font(22)
    draw.text((40, 30), "Q3 2026 — Revenue by Region", fill=(20, 20, 30), font=title_font)
    bars = [("EMEA", 420, (66, 133, 244)),
            ("Americas", 580, (52, 168, 83)),
            ("APAC", 310, (251, 188, 5)),
            ("LATAM", 180, (234, 67, 53))]
    base_y = 620
    x = 120
    for label, value, color in bars:
        bar_h = value
        draw.rectangle((x, base_y - bar_h, x + 180, base_y), fill=color)
        draw.text((x + 20, base_y + 10), label, fill=(40, 40, 50), font=label_font)
        draw.text((x + 20, base_y - bar_h - 30), f"${value}M", fill=(20, 20, 30), font=label_font)
        x += 260
    # Caption
    draw.text(
        (40, h - 40),
        "Americas leads ($580M); LATAM trailing ($180M).",
        fill=(80, 80, 100),
        font=label_font,
    )
    img.save(path, "PNG")


def _make_pdf(path: Path) -> None:
    """Multi-page PDF with mixed content (text + a 'chart' shape)."""
    doc = fitz.open()
    pages = [
        ("Acme Corp — Q3 2026 Internal Report",
         "Executive summary\n\n"
         "Q3 saw record revenue of $1.49B across all regions, driven primarily by Americas ($580M) "
         "and EMEA ($420M). APAC continues to expand but underperformed plan by 8%. LATAM remains "
         "our smallest segment but grew 41% YoY off a small base.\n\n"
         "Strategic initiatives: launching localized Spanish and Portuguese SKUs in LATAM in Q4, "
         "doubling APAC field engineering headcount, opening Tokyo office Jan 2027."),
        ("Product roadmap — H1 2027",
         "We will ship three flagship features in H1 2027:\n\n"
         "1. Multimodal search — index and retrieve across images, video, and documents in a single "
         "vector space (target: GA in February).\n\n"
         "2. Real-time collaboration — cursor presence, live cursors, and shared annotations.\n\n"
         "3. Offline mode — full local-first sync with conflict-free merging."),
        ("Engineering principles",
         "Reliability > performance > convenience.\n\n"
         "We optimize for: clear ownership, small reversible changes, evidence over opinion, "
         "and pushing complexity down rather than up. When in doubt, write less code."),
        ("Hiring plan — 2027",
         "Engineering: +24 (12 backend, 6 ML, 4 SRE, 2 security)\n"
         "Design: +6\n"
         "GTM: +18\n\n"
         "Geographies: 60% remote, 25% Berlin HQ, 15% NYC. No new offices in 2027 beyond Tokyo."),
    ]
    for title, body in pages:
        page = doc.new_page(width=595, height=842)  # A4
        rect_title = fitz.Rect(50, 50, 545, 110)
        rect_body = fitz.Rect(50, 130, 545, 800)
        page.insert_textbox(
            rect_title, title, fontsize=20, fontname="helv", color=(0.1, 0.1, 0.4)
        )
        page.insert_textbox(rect_body, body, fontsize=12, fontname="helv", color=(0.15, 0.15, 0.2))
        # Footer
        page.insert_text(
            (50, 820),
            "Acme Corp · Confidential · multimodal_kb_demo sample",
            fontsize=8,
            color=(0.5, 0.5, 0.5),
        )
    doc.save(str(path))
    doc.close()


def _make_text(path: Path) -> None:
    path.write_text(
        "# Engineering team retrospective\n\n"
        "## What went well\n"
        "- The new ingestion pipeline cut indexing latency by 60%.\n"
        "- The multimodal search prototype shipped two weeks ahead of plan.\n"
        "- Strong cross-team collaboration with the LATAM expansion taskforce.\n\n"
        "## What to improve\n"
        "- We over-invested in the experimental UI before validating retrieval quality.\n"
        "- Documentation is still thin; new hires take ~3 weeks to ramp.\n\n"
        "## Decisions\n"
        "- Adopt Gemini Embedding 2 as our default embedding model across products.\n"
        "- Move all vector storage to a unified Chroma cluster by end of Q4.\n",
        encoding="utf-8",
    )


def generate_samples(target_dir: Path = SAMPLES_DIR) -> list[Path]:
    """Generate (or regenerate) all sample files. Returns absolute paths."""
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # 3 procedurally-generated images with distinct visual styles
    _make_logo(
        "Acme Corp\nMultimodal KB Demo",
        ((30, 60, 120), (255, 255, 255), (255, 196, 0)),
        target_dir / "acme_branding.png",
    )
    paths.append(target_dir / "acme_branding.png")

    _make_logo(
        "Engineering\nDesign Principles",
        ((20, 20, 25), (240, 240, 245), (52, 168, 83)),
        target_dir / "engineering_design.png",
    )
    paths.append(target_dir / "engineering_design.png")

    # A "chart" image - vision RAG can describe what it sees
    chart = target_dir / "q3_revenue_chart.png"
    _make_chart_image(chart)
    paths.append(chart)

    # Multi-page PDF
    pdf = target_dir / "acme_q3_report.pdf"
    _make_pdf(pdf)
    paths.append(pdf)

    # Text doc
    txt = target_dir / "engineering_retro.md"
    _make_text(txt)
    paths.append(txt)

    return paths


if __name__ == "__main__":
    paths = generate_samples()
    print(f"Generated {len(paths)} sample files in {SAMPLES_DIR.resolve()}/")
    for p in paths:
        print(f"  - {p.name}")
