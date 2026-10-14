"""Launch kit for @qvanttrading: profile photo, highlight covers, the three
pinned posts' images (start-here cover, how-it-works carousel, risk slide).

    python -m tools.instagram.kit --out ~/Obsidian/Vault/30-Projects/Qvant/instagram/kit

Copy is deliberately number-free: no result, win rate or return appears in the
kit. Numbers only come from daily_card.py, from real fills, with a mode badge.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .brand import HANDLE, INK, PLATINUM, SILVER, WHITE, esc, header, mark, page, render

W, H = 1080, 1350


def profile() -> str:
    """White field, thin ink badge ring, ink open-ring Q."""
    body = f"""
<div class="slide" style="background:{WHITE};align-items:center;justify-content:center;padding:0">
  <div style="width:880px;height:880px;border-radius:50%;border:10px solid {INK};
    display:flex;align-items:center;justify-content:center">{mark(520, INK)}</div>
</div>"""
    return page(body, 1080, 1080)


def highlight(label: str) -> str:
    """1080x1920 canvas; the circle crop sits in the middle third."""
    body = f"""
<div class="slide" style="background:{PLATINUM};align-items:center;justify-content:center;padding:0;gap:44px">
  {mark(260, INK)}
  <div style="font-family:'Manrope';font-weight:700;font-size:64px;letter-spacing:.22em;color:{INK}">{esc(label.upper())}</div>
</div>"""
    return page(body, 1080, 1920)


def slide(n: int, total: int, theme: str, heading: str, text: str = "", big: bool = False) -> str:
    size = 112 if big else 84
    body = f"""
<div class="slide t-{theme}">
  {header(theme)}
  <div>
    <h1 style="font-size:{size}px;max-width:11em">{esc(heading)}</h1>
    {f'<p class="lead" style="margin-top:44px">{esc(text)}</p>' if text else ''}
  </div>
  <div class="bottom"><span class="handle">{HANDLE}</span><span class="handle">{n} / {total}</span></div>
</div>"""
    return page(body, W, H)


HOW = [
    ("ink", "How Qvant works", "Automated futures strategies, run on a fixed rule, posted every day.", True),
    ("platinum", "The rule is written first.",
     "Entry, stop, target and size are fixed before a single test. No discretion on the day.", False),
    ("white", "Tested on one period, read once on another.",
     "Tuning happens on the build days. The held-back days are looked at one time, and the result stands.", False),
    ("platinum", "The desk places the orders.",
     "At the set time the order goes in with its stop and target attached. One trade per strategy per day.", False),
    ("white", "Every trade is posted.",
     "Wins and losses, after fees, with the account type on the card: paper or live.", False),
    ("ink", "Trading futures involves substantial risk of loss.",
     "Simulated and past results do not guarantee future results. Nothing here is advice or a signal to trade.", False),
]


def start_here() -> str:
    """Reel cover, 4:5 grid crop."""
    body = f"""
<div class="slide t-ink">
  {header('ink')}
  <div>
    <h1 style="font-size:124px">Start here.</h1>
    <p class="lead" style="margin-top:44px;color:{SILVER}">What Qvant is, what it posts, and what it never will.</p>
  </div>
  <div class="bottom"><span class="handle">{HANDLE}</span><span class="handle">30 s</span></div>
</div>"""
    return page(body, W, H)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    out: Path = a.out
    made = [render(profile(), out / "profile.png", 1080, 1080)]
    for label in ("How it works", "Results", "Risk", "FAQ", "Desk"):
        slug = label.lower().replace(" ", "-")
        made.append(render(highlight(label), out / f"highlight-{slug}.png", 1080, 1920))
    made.append(render(start_here(), out / "pinned-1-start-here-cover.png", W, H))
    for i, (theme, h, t, big) in enumerate(HOW, 1):
        made.append(render(slide(i, len(HOW), theme, h, t, big), out / f"pinned-2-how-it-works-{i}.png", W, H))
    for p in made:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
