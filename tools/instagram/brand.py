"""Qvant Instagram: brand tokens, base CSS, open-ring Q mark, headless-Chrome renderer.

Palette v2 (2026-10-12): ink, white, platinum, silver. No brown. Mark = open-ring Q, one colour.
Images are plain HTML rendered by headless Chrome, so a card is just a template.
Fonts come from Google Fonts at render time (Manrope / Inter / JetBrains Mono).
"""
from __future__ import annotations

import html
import subprocess
import tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

INK = "#16171A"
SILVER = "#C9CCD1"     # quiet text and rules on ink
PLATINUM = "#E9EAEC"
WHITE = "#FFFFFF"
STEEL = "#7B7F86"      # large type / hairlines only: 3.2:1 on platinum
MUTED = "#565A61"      # secondary text: 5.9:1 on platinum, 7:1 on white
GAIN = "#2E6B4F"       # profit only; losses stay ink with a minus sign

HANDLE = "@qvanttrading"

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600'
    '&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@600;700;800'
    '&display=swap" rel="stylesheet">'
)

BASE_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:{PLATINUM}}}
body{{font-family:'Inter',-apple-system,'SF Pro Text',system-ui,sans-serif;color:{INK};
  -webkit-font-smoothing:antialiased;font-feature-settings:'tnum' 1}}
.slide{{position:relative;overflow:hidden;display:flex;flex-direction:column;
  justify-content:space-between;padding:96px}}
.t-platinum{{background:{PLATINUM};color:{INK}}}
.t-white{{background:{WHITE};color:{INK}}}
.t-ink{{background:{INK};color:{WHITE}}}
.top,.bottom{{display:flex;align-items:center;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:20px;font-family:'Manrope',sans-serif;
  font-weight:700;font-size:30px;letter-spacing:.34em}}
.handle{{font-size:28px;font-weight:500;color:{MUTED}}}
.t-ink .handle{{color:{SILVER}}}
.mono{{font-family:'JetBrains Mono',ui-monospace,Menlo,monospace}}
h1,h2{{font-family:'Manrope',sans-serif;font-weight:700;letter-spacing:-.025em;
  line-height:1.04;text-wrap:balance}}
.lead{{font-size:40px;line-height:1.38;font-weight:400;max-width:20em;text-wrap:pretty}}
.small{{font-size:27px;line-height:1.4;color:{MUTED}}}
.t-ink .small{{color:{SILVER}}}
.hair{{height:2px;background:rgba(22,23,26,.14)}}
.t-ink .hair{{background:rgba(255,255,255,.22)}}
"""


def mark(size: int = 44, color: str = INK, width: float = 12) -> str:
    """Open-ring Q: the ring breaks where the tail leaves. One colour."""
    gap = 24.3
    dash = 2 * 3.14159265 * 33 - gap
    return (
        f'<svg width="{size}" height="{size}" viewBox="-0.5 -0.5 100 100" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<circle cx="46" cy="46" r="33" stroke="{color}" stroke-width="{width}" '
        f'stroke-dasharray="{dash:.1f} {gap}" transform="rotate(64 46 46)"/>'
        f'<path d="M58 58 L86 86" stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>'
        f"</svg>"
    )


def esc(s: object) -> str:
    return html.escape(str(s))


def page(body: str, w: int, h: int, extra_css: str = "") -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}'
        f"<style>{BASE_CSS}{extra_css}.slide{{width:{w}px;height:{h}px}}</style>"
        f"</head><body>{body}</body></html>"
    )


def render(doc: str, out: Path, w: int, h: int) -> Path:
    """HTML string -> PNG at exactly w x h via headless Chrome."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qvant-ig-") as td:
        src = Path(td) / "card.html"
        src.write_text(doc, encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={w},{h}",
             "--virtual-time-budget=8000", f"--screenshot={out}", src.as_uri()],
            check=True, capture_output=True, timeout=90,
        )
    return out


def header(theme: str = "platinum") -> str:
    c = WHITE if theme == "ink" else INK
    return f'<div class="top"><div class="brand">{mark(46, c)}QVANT</div></div>'
