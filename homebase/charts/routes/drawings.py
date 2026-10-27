"""Drawings, chart-settings templates and named presets, with the validators that strip what the page sends."""
from __future__ import annotations

import json
import math
import re

from fastapi import HTTPException, Request

from ..presets import MAX_PRESET_BYTES
from .common import browser_write_ok, read_json, write_json

MAX_DRAWINGS = 500            # per symbol
# 2026-10-09: a ray, an extended line and a Fib retracement are two points like a trend line; a vertical line is one TIME
# 2026-10-11: an arrow (two points, a line with a head), a parallel channel (a line and a third point that sets the
# parallel), a note (one point and its text) and an anchored VWAP (one point: the bar it starts at)
DRAWING_POINTS = {"trend": 2, "ray": 2, "xline": 2, "rect": 2, "fib": 2, "hline": 1, "vline": 1, "long": 3, "short": 3,
                  "arrow": 2, "channel": 3, "note": 1, "avwap": 1}
POSITION_QTY_MAX = 10_000     # a long/short box's quantity
MAX_TEMPLATE_BYTES = 16 * 1024   # one chart-settings template, as JSON
MAX_TEMPLATE_NAME = 40
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
# 2026-09-27 draw-tools plan: a drawing's colour (and style.fillColor / style.textColor) may also
# carry opacity, the same shape the chart-settings colours already use (settings.js' fmtColor).
_RGBA_COLOR = re.compile(r"rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\)")
DRAWING_LINE_STYLES = ("solid", "dashed", "dotted")
_LINE_POS, _BOX_POS = ("above", "below", "middle"), ("top", "middle", "bottom")
DRAWING_LABEL_POS = {"trend": _LINE_POS, "ray": _LINE_POS, "xline": _LINE_POS, "hline": _LINE_POS, "rect": _BOX_POS, "vline": _BOX_POS,
                     "arrow": _LINE_POS}
DRAWING_LABEL_ALIGN = ("left", "center", "right")
_TEXT_FIELDS = {"text", "fontSize", "textColor", "bold", "labelPos"}
DRAWING_CAPS = ("none", "arrow", "circle")      # the mark at a line's end (2026-10-11); a field left out = none
MAX_DRAWING_WIDTH = 8
# a position box (2026-10-11): zone colours, label size / colour / weight, whether labels show (showLabels), on hover or always
# (hoverLabels), which label parts and the played-out path show, and its entry line's colour / width / style
_POS_FIELDS = {"profitColor", "lossColor", "fontSize", "showLabels", "entryColor", "width", "lineStyle", "textColor", "bold",
               "hoverLabels", "showTarget", "showStop", "showRR", "showResult", "showPrice", "showPoints", "showTicks", "showMoney", "showPath", "showZoneMoney"}
# exactly the style fields each drawing type takes (drawstyle.js' FIELDS mirrors this)
DRAWING_STYLE_FIELDS = {
    "trend": {"width", "lineStyle", "extendLeft", "extendRight", "priceLabel", "stats", "startCap", "endCap", "hoverLabels"} | _TEXT_FIELDS,
    "ray": {"width", "lineStyle", "priceLabel", "stats", "startCap", "endCap", "hoverLabels"} | _TEXT_FIELDS,
    "xline": {"width", "lineStyle", "priceLabel", "stats", "hoverLabels"} | _TEXT_FIELDS,
    "hline": {"width", "lineStyle", "axisLabel", "labelAlign"} | _TEXT_FIELDS,
    "vline": {"width", "lineStyle", "timeLabel"} | _TEXT_FIELDS,
    "rect": {"width", "lineStyle", "fillColor", "border", "midline", "quarters", "midStyle", "extendRight", "priceLabels", "hoverLabels"} | _TEXT_FIELDS,
    "fib": {"width", "lineStyle", "extendLeft", "extendRight", "levels", "showLevels", "showPrices", "fill", "fillOpacity", "reverse", "fontSize"},
    "arrow": {"width", "lineStyle", "priceLabel", "stats", "hoverLabels"} | _TEXT_FIELDS,
    "channel": {"width", "lineStyle", "extendLeft", "extendRight", "fillColor", "midline"},
    "note": {"text", "fontSize", "textColor", "bold", "fillColor"},
    "avwap": {"width", "lineStyle"},
    # a position box: its zone colours, its label size, whether its labels show
    "long": _POS_FIELDS, "short": _POS_FIELDS,
}
DRAWING_STYLE_BOOLS = ("extendLeft", "extendRight", "axisLabel", "bold", "priceLabel", "stats", "timeLabel", "border", "midline",
                       "quarters", "priceLabels", "showLevels", "showPrices", "fill", "reverse", "showLabels", "hoverLabels",
                       "showTarget", "showStop", "showRR", "showResult", "showPrice", "showPoints", "showTicks", "showMoney", "showPath", "showZoneMoney")
MAX_FIB_LEVELS, FIB_MIN, FIB_MAX = 16, -10, 10      # a retracement's levels: how many, and the ratios they may be
DRAWING_VIS_MAX_S = 31 * 86400                      # `vis` (which intervals a drawing shows on): bar seconds, at most a month
MAX_DRAWING_LABEL_TEXT = 200


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_position(kind: str, pts: list) -> None:
    """A long/short box: [entry, target, stop], target and stop on the box's right edge (one t)."""
    entry, target, stop = (p["p"] for p in pts)
    if pts[1]["t"] != pts[2]["t"]:
        raise ValueError(f"a {kind}'s target and stop share the box's right edge (the same t)")
    if kind == "long" and not stop < entry < target:
        raise ValueError("a long has stop < entry < target")
    if kind == "short" and not target < entry < stop:
        raise ValueError("a short has target < entry < stop")


def _valid_color(s) -> bool:
    """#RRGGBB, or rgba(r,g,b,a) with r/g/b <= 255 and a in [0,1] (2026-09-27 draw-tools plan:
    widened from hex-only so a drawing's colour can carry opacity, the same shape the chart
    settings' own colours already use -- settings.js' fmtColor)."""
    if not isinstance(s, str):
        return False
    if _HEX_COLOR.fullmatch(s):
        return True
    m = _RGBA_COLOR.fullmatch(s)
    if not m:
        return False
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return r <= 255 and g <= 255 and b <= 255


def check_style(kind: str, style) -> dict:
    """A drawing's optional visual style, stripped to exactly the fields that type takes (junk, a
    field the type does not carry, or one with a wrong type/range/length fails the whole PUT --
    fail closed, never silently dropped): width 1-4 and lineStyle solid/dashed/dotted (trend,
    hline, rect); extendLeft/extendRight (trend only); fillColor (rect only); axisLabel (hline
    only); text (<= 200 characters), fontSize 10-28, textColor, bold and labelPos (trend/hline:
    above/below/middle; rect: top/middle/bottom) on trend, hline and rect. long/short take no style
    object (DRAWING_STYLE_FIELDS[kind] is empty for them: any key at all raises). ValueError (with
    a message for the page) on anything outside this."""
    if not isinstance(style, dict):
        raise ValueError("style: an object")
    allowed = DRAWING_STYLE_FIELDS.get(kind, set())
    for key in style:
        if key not in allowed:
            raise ValueError(f"style.{key} does not apply to a {kind}")
    out = {}
    if "width" in style:
        w = style["width"]
        if not isinstance(w, int) or isinstance(w, bool) or not 1 <= w <= MAX_DRAWING_WIDTH:
            raise ValueError(f"style.width: a whole number from 1 to {MAX_DRAWING_WIDTH}")
        out["width"] = w
    if "lineStyle" in style:
        if style["lineStyle"] not in DRAWING_LINE_STYLES:
            raise ValueError("style.lineStyle: solid, dashed or dotted")
        out["lineStyle"] = style["lineStyle"]
    for key in DRAWING_STYLE_BOOLS:
        if key in style:
            if not isinstance(style[key], bool):
                raise ValueError(f"style.{key}: true or false")
            out[key] = style[key]
    if "midStyle" in style:
        if style["midStyle"] not in DRAWING_LINE_STYLES:
            raise ValueError("style.midStyle: solid, dashed or dotted")
        out["midStyle"] = style["midStyle"]
    if "labelAlign" in style:
        if style["labelAlign"] not in DRAWING_LABEL_ALIGN:
            raise ValueError("style.labelAlign: left, center or right")
        out["labelAlign"] = style["labelAlign"]
    if "levels" in style:
        out["levels"] = _check_levels(style["levels"])
    for key in ("startCap", "endCap"):
        if key in style:
            if style[key] not in DRAWING_CAPS:
                raise ValueError(f"style.{key}: none, arrow or circle")
            out[key] = style[key]
    for key in ("fillColor", "profitColor", "lossColor", "entryColor"):
        if key in style:
            if not _valid_color(style[key]):
                raise ValueError(f"style.{key}: #RRGGBB or rgba(r,g,b,a)")
            out[key] = style[key]
    if "text" in style:
        t = style["text"]
        if not isinstance(t, str) or len(t) > MAX_DRAWING_LABEL_TEXT:
            raise ValueError(f"style.text: a string of at most {MAX_DRAWING_LABEL_TEXT} characters")
        out["text"] = t
    if "fontSize" in style:
        fs = style["fontSize"]
        if not isinstance(fs, int) or isinstance(fs, bool) or not 10 <= fs <= 28:
            raise ValueError("style.fontSize: a whole number from 10 to 28")
        out["fontSize"] = fs
    if "fillOpacity" in style:
        fo = style["fillOpacity"]
        if not isinstance(fo, int) or isinstance(fo, bool) or not 0 <= fo <= 100:
            raise ValueError("style.fillOpacity: a whole number from 0 to 100")
        out["fillOpacity"] = fo
    if "textColor" in style:
        if not _valid_color(style["textColor"]):
            raise ValueError("style.textColor: #RRGGBB or rgba(r,g,b,a)")
        out["textColor"] = style["textColor"]
    if "labelPos" in style:
        choices = DRAWING_LABEL_POS.get(kind, ())
        if style["labelPos"] not in choices:
            raise ValueError(f"style.labelPos: {', '.join(choices)}")
        out["labelPos"] = style["labelPos"]
    return out


def _check_levels(levels) -> list:
    """A Fib retracement's levels: 1-16 of {v: the ratio (-10 .. 10), on: drawn or not, color?}; nothing else is kept."""
    if not isinstance(levels, list) or not 1 <= len(levels) <= MAX_FIB_LEVELS:
        raise ValueError(f"style.levels: a list of 1 to {MAX_FIB_LEVELS} levels")
    out = []
    for lv in levels:
        if not isinstance(lv, dict) or not _finite(lv.get("v")) or not FIB_MIN <= lv["v"] <= FIB_MAX:
            raise ValueError(f"style.levels: each level has v, a number from {FIB_MIN} to {FIB_MAX}")
        if not isinstance(lv.get("on"), bool):
            raise ValueError("style.levels: each level has on, true or false")
        item = {"v": lv["v"], "on": lv["on"]}
        if "color" in lv:
            if not _valid_color(lv["color"]):
                raise ValueError("style.levels: a level's color is #RRGGBB or rgba(r,g,b,a)")
            item["color"] = lv["color"]
        out.append(item)
    return out


def check_alert(kind: str, alert) -> dict:
    """A price alert, which only a horizontal line carries: {dir: "up" | "down" (which way the price must cross it),
    fired: true | false (it has gone off; armed again by the page)}. Anything else fails the whole PUT."""
    if kind != "hline":
        raise ValueError("alert: only a horizontal line carries one")
    if not isinstance(alert, dict) or set(alert) - {"dir", "fired"} or alert.get("dir") not in ("up", "down"):
        raise ValueError("alert: {dir: up or down, fired: true or false}")
    fired = alert.get("fired", False)
    if not isinstance(fired, bool):
        raise ValueError("alert.fired: true or false")
    return {"dir": alert["dir"], "fired": fired}


def check_vis(vis) -> dict | None:
    """Which intervals a drawing shows on: {min, max} in bar SECONDS, either one null (no bound); None when both are
    (it shows everywhere, and nothing is stored). ValueError on anything else."""
    if not isinstance(vis, dict) or set(vis) - {"min", "max"}:
        raise ValueError("vis: {min, max} in bar seconds, either one null")
    out = {}
    for key in ("min", "max"):
        v = vis.get(key)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= DRAWING_VIS_MAX_S):
            raise ValueError(f"vis.{key}: null, or whole seconds from 1 to {DRAWING_VIS_MAX_S}")
        out[key] = v
    if out["min"] is None and out["max"] is None:
        return None
    if out["min"] is not None and out["max"] is not None and out["min"] > out["max"]:
        raise ValueError("vis: min is at most max")
    return out


def check_drawings(body) -> list:
    """The page's drawings for one symbol, validated and stripped to what
    the page draws: [{id, type, points: [{t?, p?}], color?, qty?, locked?,
    style?, vis?}] (a horizontal line's point is a price, a vertical line's a
    time; `vis` = the intervals it shows on, check_vis). A long / short position is [entry, target, stop] with target
    and stop on the box's right edge (same t), stop < entry < target (long)
    or target < entry < stop (short), and an optional qty 1-10000 (kept for
    positions only). `style` (2026-09-27 draw-tools plan) is per-type --
    see check_style. ValueError (with a message for the page) on anything
    else."""
    if not isinstance(body, list) or len(body) > MAX_DRAWINGS:
        raise ValueError(f"drawings are a list of at most {MAX_DRAWINGS}")
    out = []
    for d in body:
        if not isinstance(d, dict):
            raise ValueError("each drawing is an object")
        did, kind, pts = d.get("id"), d.get("type"), d.get("points")
        if not isinstance(did, str) or not 1 <= len(did) <= 40:
            raise ValueError("id: a string of 1-40 characters")
        n = DRAWING_POINTS.get(kind)
        if n is None:
            raise ValueError("type: trend, ray, xline, arrow, hline, vline, rect, fib, channel, note, avwap, long or short")
        if not isinstance(pts, list) or len(pts) != n or not all(isinstance(p, dict) for p in pts):
            raise ValueError(f"a {kind} has exactly {n} point(s)")
        clean = []
        for p in pts:
            t = p.get("t")
            if kind == "vline":                       # a time and nothing else
                if not isinstance(t, int) or isinstance(t, bool):
                    raise ValueError("a point's t is an integer (epoch ms)")
                clean.append({"t": t})
                continue
            if not _finite(p.get("p")):
                raise ValueError("a point's p is a finite number")
            if kind == "hline":
                clean.append({"p": p["p"]})
                continue
            if not isinstance(t, int) or isinstance(t, bool):
                raise ValueError("a point's t is an integer (epoch ms)")
            clean.append({"t": t, "p": p["p"]})
        item = {"id": did, "type": kind, "points": clean}
        if kind in ("long", "short"):
            _check_position(kind, clean)
            if "qty" in d:
                q = d["qty"]
                if not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= POSITION_QTY_MAX:
                    raise ValueError(f"qty: a whole number from 1 to {POSITION_QTY_MAX}")
                item["qty"] = q
        if "color" in d:
            if not _valid_color(d["color"]):
                raise ValueError("color: #RRGGBB or rgba(r,g,b,a)")
            item["color"] = d["color"]
        if "locked" in d:
            if not isinstance(d["locked"], bool):
                raise ValueError("locked: true or false")
            item["locked"] = d["locked"]
        if "style" in d:
            style = check_style(kind, d["style"])
            if style:
                item["style"] = style
        if "vis" in d:
            vis = check_vis(d["vis"])
            if vis:
                item["vis"] = vis
        if "alert" in d:
            item["alert"] = check_alert(kind, d["alert"])
        out.append(item)
    return out


def check_template_name(name) -> str:
    """A chart-settings template's name: 1-40 characters, no / \\ .. and no
    control characters (it rides in the URL path), and not "." on its own
    (the browser resolves /api/templates/. as a path step, landing on the
    list route rather than this name). ValueError otherwise."""
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_TEMPLATE_NAME:
        raise ValueError(f"a template name has 1-{MAX_TEMPLATE_NAME} characters")
    if name == ".":
        raise ValueError('a template name cannot be "."')
    if "/" in name or "\\" in name or ".." in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("a template name has no / \\ .. or control characters")
    return name


def _no_constant(c: str):
    """json.loads hook: NaN / Infinity are not JSON (the page's r.json() could not read them back)."""
    raise ValueError(f"{c} is not JSON")


def register(app, *, drawings_path, templates_path, presets_store, known_root) -> None:
    @app.get("/api/drawings/{root}")
    async def get_drawings(root: str):
        return read_json(drawings_path).get(known_root(root), [])

    @app.put("/api/drawings/{root}")
    async def put_drawings(root: str, request: Request):
        browser_write_ok(request)
        r = known_root(root)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        try:
            clean = check_drawings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        all_ = read_json(drawings_path)
        all_[r] = clean
        write_json(drawings_path, all_)
        return {"ok": True, "count": len(clean)}

    @app.get("/api/templates")
    async def get_templates():
        return read_json(templates_path)

    @app.put("/api/templates/{name:path}")
    async def put_template(name: str, request: Request):
        browser_write_ok(request)
        try:
            check_template_name(name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        raw = await request.body()
        if len(raw) > MAX_TEMPLATE_BYTES:
            raise HTTPException(400, f"a template is at most {MAX_TEMPLATE_BYTES // 1024} KB of JSON")
        try:
            body = json.loads(raw, parse_constant=_no_constant)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "a template is a JSON object of chart settings")
        all_ = read_json(templates_path)
        all_[name] = body
        write_json(templates_path, all_)
        return {"ok": True}

    @app.delete("/api/templates/{name:path}")
    async def delete_template(name: str, request: Request):
        browser_write_ok(request)
        all_ = read_json(templates_path)
        all_.pop(name, None)
        write_json(templates_path, all_)
        return {"ok": True}

    # 2026-09-27 draw-tools plan: a generic named-preset store, by "kind" ("drawing:<tool>" today,
    # "indicator:<tool>" once the indicator dialog reuses it). Same write guard, same atomic write,
    # same body-size cap and JSON-object-only rule as templates above.
    @app.get("/api/preset-defaults/{family}")
    async def get_preset_defaults(family: str):
        try:
            return presets_store.defaults(family)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/presets/{kind}")
    async def get_presets(kind: str):
        try:
            return presets_store.list(kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.put("/api/presets/{kind}/{name:path}")
    async def put_preset(kind: str, name: str, request: Request):
        browser_write_ok(request)
        raw = await request.body()
        if len(raw) > MAX_PRESET_BYTES:
            raise HTTPException(400, f"a preset is at most {MAX_PRESET_BYTES // 1024} KB of JSON")
        try:
            body = json.loads(raw, parse_constant=_no_constant)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "a preset is a JSON object")
        try:
            presets_store.put(kind, name, body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True}

    @app.delete("/api/presets/{kind}/{name:path}")
    async def delete_preset(kind: str, name: str, request: Request):
        browser_write_ok(request)
        try:
            presets_store.delete(kind, name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True}
