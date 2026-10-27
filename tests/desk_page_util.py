"""The Desk page as one text, for the tests that read its code: index.html with its run of /static/desk/*.js tags put
back as the one inline <script> the code was until the split (2026-10-26). tests/js/deskpage.mjs is the same rule."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "homebase" / "static"
TAG = re.compile(r'<script src="/static/(desk/[\w-]+\.js)\?v=\d+"></script>\n')


def desk_page() -> str:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    files = TAG.findall(page)
    assert sorted(files) == sorted(f"desk/{p.name}" for p in (STATIC / "desk").glob("*.js")), "a desk/*.js without its tag"
    code = "".join((STATIC / f).read_text(encoding="utf-8") for f in files)
    return re.sub(f"(?:{TAG.pattern})+", lambda _: "<script>\n" + code + "</script>\n", page, count=1)
