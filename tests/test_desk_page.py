"""The desk page carries the chart-trading switch (no limit inputs: no order path reads them), and
switching it ON goes through the confirm dialog before the POST."""
from __future__ import annotations

from pathlib import Path

from tests.desk_page_util import desk_page

HTML = desk_page()


def test_the_desk_page_has_the_chart_trading_switch_and_no_limit_inputs():
    for needle in ('id="ctSwitch"', 'id="ctState"', 'post("/api/chart-trading"', "renderChartTrading(s.chart_trading)"):
        assert needle in HTML, needle
    for gone in ('id="ctMaxOrder"', 'id="ctMaxPos"', 'id="ctSave"', "Limits saved"):
        assert gone not in HTML, gone


def test_switching_on_asks_first():
    fn = HTML[HTML.index("async function setChartTrading"):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("confirmDlg(") < fn.index('post("/api/chart-trading"')


def _fn(name):
    start = HTML.index(name)
    fn = HTML[start:]
    ends = [i for i in (fn.find("\n}\n"), fn.find("\n};\n")) if i != -1]
    return fn[:min(ends)]


def test_chart_trading_toasts_fall_back_to_r_error():
    """Fix round 1 item 5: the write guard's 403/415 refusals carry `error`,
    not `detail` — the switch's toast must show it."""
    for fn in (_fn("async function setChartTrading"),):
        assert "r.detail || r.error" in fn


def test_chart_trading_toasts_survive_post_throwing():
    """A network failure or a non-JSON 500 makes post() throw (fetch itself
    rejects, or r.json() fails to parse) — both handlers must catch it and
    tell the user, not leave an unhandled rejection with no feedback."""
    for fn in (_fn("async function setChartTrading"),):
        assert "try {" in fn and "catch" in fn
        assert "Couldn't reach the desk" in fn
        # the catch must come after the post() call it's guarding
        assert fn.index('post("/api/chart-trading"') < fn.index("catch")


# ---- Step B, task B6: a promoted Lab strategy that the Desk itself knows ------------------------------------
STATIC = Path(__file__).resolve().parent.parent / "homebase" / "static"
DESKLAB = (STATIC / "desklab.js").read_text()


def _section(start, end):
    i = HTML.index(start)
    return HTML[i:HTML.index(end, i + 1)]


LAB_DESK = _section("/* ---- A Lab strategy the Desk itself knows (Step B, task B6) ----", "function renderMain(")


def test_the_limits_dialog_is_static_markup_with_every_field_and_button():
    markup = _section('<div class="overlay" id="labLimitsOverlay">', '<div class="overlay" id="settingsOverlay">')
    for needle in ('id="llTitle"', 'id="llTrades"', 'id="llQty"', 'id="llRisk"', 'id="llLast"', 'id="llFlat"', 'id="llNote"',
                   'id="llSave"', 'id="llCancel"', 'Trades a day', 'Most contracts, for accounts without their own Most', 'Most at risk per trade',
                   'Last entry', 'Flat by', 'Save limits', 'Cancel', 'role="dialog" aria-modal="true"'):
        assert needle in markup, needle
    assert HTML.count('id="labLimitsOverlay"') == 1
    assert "labLimitsOverlay: () => closeLabLimits()" in HTML          # Esc closes it through the page's one path
    # nothing that repaints writes into it
    assert "labLimitsOverlay" not in _section("function render() {", "async function refresh() {")


def test_the_desk_page_for_a_lab_strategy_posts_to_the_desks_own_routes():
    for needle in ('post("/api/lab-limits"', 'post("/api/lab-remove"', 'post("/api/lab-clear"'):
        assert needle in LAB_DESK, needle
    # the switch, the flatten and the book are the Desk's existing routes
    assert 'post("/api/strategy"' in HTML and 'post("/api/strategy-flatten"' in HTML and 'post("/api/book"' in HTML
    # a Lab strategy gets no Test fire
    assert "testFire" not in LAB_DESK
    assert "Test fire" not in LAB_DESK


def test_the_asset_versions_are_bumped():
    assert '<script src="/static/desklab.js?v=56"></script>' in HTML                 # 56: Team words (2026-11-03); 55: teams have no kind (2026-11-03); 54: one word per thing, Desk OFF (2026-11-03); 53: AlgoVisibility words gone (2026-11-03); 52: account cycle reads account group (2026-11-01); 51: a group's one Full sample block adds realized RR, Sharpe and trades a week, drops Days 2+ traded (2026-10-30); 50: the group page and the family page show the full sample only (2026-10-30); 49: a row that holds overnight says so (2026-10-30); 48: a 3:1 card shows its full sample (Both) only, one column, in the results and the prop sim (2026-10-30); 47: any window in the Desk day (18:00 -> 17:00), flat by 16:55 (2026-10-30); 46: an evening strategy's flat time may be up to 23:55 (2026-10-30); 45: the switch's words name each account's own size when a row is set (per-account settings, 2026-10-30); 44: Rename, Duplicate and mini/micro switch words (2026-10-28); 43: the Remove dialog no longer says it cannot go back (2026-10-28); 42: Last entry, Flat by and Expected payout words (2026-10-27); 41: nothing starts a walk-forward by itself; the notes say the card cannot get a new 3:1 today, and promise no start, promote or Lab run; an older 3:1 says the months it lacks; the Remove confirms say it cannot go back from the Lab, Archive keeps it (S4, 2026-10-27); 40: a switch size only when every booked row says it; switchOnAsk, the ON confirm's words for WP1.7 (2026-10-27); 39: while waiting the card and a group read the 3:1 words; the old record's columns are Build days | Test days (2026-10-27); 38: the switch title names the machine, the LIVE accounts and the size (2026-10-26); 37: the card says 3:1 in-sample / 3:1 test months, or Old record (before 3:1) (2026-10-26); 36: a group's curve and tables are the 3:1 (build, unseen, both) (2026-10-25); 35: a group's Orders row says its account cycle (2026-10-25); 34: a group trades only through its account cycle; 33: a Both column (Build + Unseen) in the 3:1 and prop sim tables (2026-10-24); 32: smooth curves that never overshoot (2026-10-24); 31: a host whose ticks do not reach 2021 says so instead of a walk-forward (2026-10-24); 30: each 3:1 curve line on its own traded days; 29: (earlier); 28: duplicate MONTHS removed (no behaviour change); 27: an account booked after the session opened starts as soon as the strategy has no open trade or order; 26: "Shadow today" for an account booked after the session opened; 25: the curve's third line, both together; 24: the Setup labels, Max drawdown, the build + unseen curve; 23: realized RR right under the win rate; 22: no Backtest block or Days row beside the 3:1; 21: no size cap for a strategy that sizes itself; 20: build and unseen days from the 3:1 of the strategy as set; 19: the unseen days are the 3:1 walk-forward + its pick; 18: a Desk straddle's Build | Unseen columns; 17: the page's current bundle (15: a Desk straddle's unseen note; 14: Desk groups; 13: shorter curve label; 12: the unseen-days curve; 11: the panel says when the unseen days are being read; 10: the unseen-days run and the prop sim; 9: adjustable settings; 8: one clock)
    assert '<script src="/static/desklabset.js?v=6"></script>' in HTML               # 6: the menu and Set button are back (owner 2026-11-01: "i still dont see where i would switch it"); 5: read-only text rows, no inputs (per-account settings, 2026-10-29); 4: plain Set when the menu holds no option for the value in force (2026-10-27); 3: the Set button reads old → new and passes `from` (2026-10-26)
    assert all(f'desklab.js?v={n}"' not in HTML for n in range(1, 17))
    assert '"version": 70' in (STATIC / "apple" / "manifest.json").read_text()     # 70: the sidebar sorts itself, .sh.sub gone (2026-11-03); 69: the Desk skin reads teams from the Desk (2026-11-03); 66: the chart's red LIVE ring removed (2026-11-02); 65: account cycle reads account group (2026-11-01); 64: the inspector heads a group Full sample on every repaint; 63: a group's one Full sample block (2026-10-30); 62: a group's days-traded heading reads Full sample, no 3:1 test months; the branch merged into main (2026-10-30); 59: the inspector heading reads Full sample (2026-10-30); 58: a group's Combined table keeps its row labels readable (2026-10-29); 57: a family page's wider number columns (2026-10-29); 56: a family's open chevron in the sidebar (2026-10-29); 53: icons and plain words (2026-10-27); 52: Lab layout polish (2026-10-27); 51: keyboard focus and reduced motion (2026-10-27); 50: tokens and zero-change cleanup (2026-10-27); 49: the Lab and Charts tables, sheets and bottom panel catch up with the Mac skin (2026-10-27); 48: Kill / ARMED / destructive red darkened so white text passes 4.5:1 (2026-10-27); 47: the chart toolbar's sound button joins the panels platter (2026-10-27); 46: the UX redesign (the Desk skin's toolbar, machine chip, readiness and inspector words, 2026-10-27); 45: the Activity page's Show and Period pickers (2026-10-26); 44: the inspector's group Orders row shows its account cycle (2026-10-25); 40-43: (earlier); 39: the inspector's three-column tables (Both, 2026-10-24); 37-38: (earlier); 36: the chart's FLAT button (2026-10-23); 35: a Trades / week row under Trades on the Desk card (2026-10-22); 34: TradingView's mouse on the chart (2026-10-22); 33: the picker's Best group removed (2026-10-22); 32: every indicator adjustable in its settings (2026-10-22); 31: dead rules out of system.css, the TradingView sections and the picker ranking (2026-10-22); 30: the build + unseen curve's dashed third line (both together); 29: the build + unseen curve's second line; 28: the Desk's switcher flows below 1360 px; 27: a Lab strategy's Backtest box is its 3:1 block; 26: the nq930 stop menu (24: the current skin bundle (21: Show on chart + tighter prop columns (20: a group's wider figure columns (19: the group buttons' icons (18: the inspector for a Desk group (17: a Lab strategy's unseen-days run and prop sim in the inspector (16: no watch-only page; 15: the Setup panel's controls; 14: one corner for every bubble, one clock, the stepper on the chart)


def test_the_old_step_a_caption_is_not_on_the_desks_page_for_a_lab_strategy():
    assert "ACCOUNTS_CAPTION" not in LAB_DESK
    assert "Accounts come with the Desk update" not in LAB_DESK
    assert "LIMITS_CAPTION" in DESKLAB and "Set the limits first. Then assign an account." in DESKLAB


def test_one_row_never_two_is_in_the_row_builder():
    assert "filter(w => !labOnDesk(w))" in _section("const labRowsHtml", "async function loadDeskLab")
    assert 'Object.prototype.hasOwnProperty.call(strategies, PREFIX + w.name)' in DESKLAB


def test_the_switch_flatten_and_book_branch_on_kind_lab_and_leave_the_others_alone():
    toggle = _section("async function toggleStrat", "async function setStratRr")
    assert '"It will run and execute on its assigned accounts from the next signal."' in toggle
    assert 'N + (enabled ? " is ON." : " is OFF — it ignores signals; open positions are untouched.")' in toggle
    flat = _section("async function flattenStrat", "/* ---- accounts popup ---- */")
    assert '"Cancels its resting entries, market-flattens its symbol on every account it acted on today, and switches the strategy OFF."' in flat
    book = _section("async function setBook", "function removeAsg")
    assert '"Book update failed — " + (r.detail || "unknown")' in book
    note = _section("function liveBookingNote", "async function pickAsg")
    assert 'c.kind === "lab"' in note and "DeskLab.LIVE_NOTE" in note


def test_the_words_on_the_lab_part_of_the_page_never_say_round_sidecar_intent_or_overlay():
    import re
    block = DESKLAB[DESKLAB.index("Step B (task B6)"):DESKLAB.index("  return {\n    TAG_TITLE")]
    literals = re.findall(r'"([^"\n]*)"', block)
    assert len(literals) > 60
    for text in literals:
        assert not re.search(r"\b(round|rounds|sidecar|intent|overlay)\b", text, re.I), text
    visible = re.sub(r"<[^>]*>", " ", LAB_DESK)                       # the markup's words, not its attributes
    for word in ("sidecar", "intent"):
        assert word not in re.sub(r"//.*|/\*[\s\S]*?\*/", "", visible).lower(), word


def test_the_activity_map_has_the_labs_journal_lines():
    act = _section("const ACTIVITY = {", "function activityLine(")
    for ev in ("lab_refused", "lab_runner_down", "lab_runner_back", "lab_stopped", "lab_flatten", "lab_cancelled", "lab_limits_set", "lab_settings_set"):
        assert f'{ev}: labAct("{ev}")' in act, ev


# ---- Task B6, fix round 1 -----------------------------------------------------------------------------------
def test_the_mac_skin_gives_the_warn_caption_its_colour():
    css = (STATIC / "apple" / "desk.css").read_text()
    assert "html.hb-apple .mcap.warn { color: var(--a-red-text); }" in css


def test_the_activity_list_and_the_last_event_time_leave_out_only_the_named_lab_bookkeeping():
    rule = 'r.event.indexOf("lab_") === 0 && typeof DeskLab !== "undefined" && DeskLab.hiddenEvent(r.event)'
    assert HTML.count(rule) == 2
    assert 'HIDDEN_EVENTS = ["lab_event", "lab_event_done"]' in DESKLAB      # final wave: lab_added is a line now
    act = _section("const ACTIVITY = {", "function activityLine(")
    for ev in ("lab_event", "lab_event_done"):
        assert f"{ev}:" not in act, ev          # bookkeeping: never a line
    assert 'lab_added: labAct("lab_added")' in act
    for ev in ("lab_event_error", "lab_intake_error", "lab_save_error", "lab_carry_fill", "lab_sidecar_replaced", "lab_unbooked", "lab_unreadable",
               "lab_restore_error", "lab_start_error", "lab_key_error", "lab_store_error", "lab_view_error", "lab_open_without_cfg", "lab_side"):
        assert f'{ev}: labAct("{ev}")' in act, ev
    assert "Something happened to a Lab strategy. Check it." in HTML


def test_the_risk_field_says_what_a_dollar_amount_looks_like():
    assert 'placeholder="300"' in HTML
    assert "At risk per trade: a dollar amount above 0, like 300 or 300.50." in DESKLAB


def test_no_visible_lab_line_says_round_sidecar_intent_overlay_or_carried():
    import re
    act = _section("const ACTIVITY = {", "function activityLine(")
    block = DESKLAB[DESKLAB.index("var activity = {"):DESKLAB.index("  return {\n    TAG_TITLE")]
    for text in re.findall(r'"([^"\n]*)"', block):
        assert not re.search(r"\b(round|rounds|sidecar|intent|overlay|carried)\b", text, re.I), text
    assert "plainWords" in DESKLAB


def test_the_desk_serves_the_page_uncached_and_every_desk_script_it_names(tmp_path, monkeypatch):
    """The page's code lives in static/desk/*.js (2026-10-26). The page itself always revalidates (no-cache), so a cached
    old page can never pair with newer code; its body is the file on disk, and every script it names is served as is."""
    import re

    from fastapi.testclient import TestClient

    import homebase.config as config_mod
    from homebase.config import AppCfg
    from homebase.server import create_app
    for target in ("homebase.paths.state_dir", "homebase.desk.engine.state_dir", "homebase.server.state_dir", "homebase.store.secrets_store.state_dir"):
        monkeypatch.setattr(target, lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    with TestClient(create_app(AppCfg(), {}, background=False), base_url="http://127.0.0.1:8850") as c:
        page = c.get("/")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-cache" and page.headers["etag"]
        assert page.content == (STATIC / "index.html").read_bytes()
        files = re.findall(r'<script src="/static/(desk/[\w-]+\.js)\?v=\d+"></script>', page.text)
        assert len(files) == 12 and len(set(files)) == 12
        for f in files:
            r = c.get(f"/static/{f}?v=1")
            assert r.status_code == 200 and r.content == (STATIC / f).read_bytes(), f
            assert r.headers["content-type"].startswith(("text/javascript", "application/javascript")), f


# Each desk/*.js is cached by the browser under its ?v= (no cache-control on /static), so a changed file must get a new ?v=
# or a fresh page can run with yesterday's code. Edited a desk file? Bump its ?v= in index.html, then its pin here (both).
DESK_PINS = {
    "desk/core.js": (6, "82c851d8ecdb8695"),
    "desk/topbar.js": (8, "abc693094e261082"),
    "desk/activity.js": (16, "2745d717148f29be"),
    "desk/views.js": (5, "4967dc250f948984"),
    "desk/groups.js": (23, "f044ce96e99ad546"),
    "desk/strategy.js": (27, "91518b4df9b48146"),
    "desk/labdesk.js": (22, "99426228dd100c03"),
    "desk/book.js": (19, "75ff8e26446c04e1"),
    "desk/acctset.js": (8, "0d6655f77918b014"),
    "desk/settings.js": (10, "1f99a7d9ce48635c"),
    "desk/popups.js": (13, "344d1fe491a71b9e"),
    "desk/start.js": (4, "6b26f57a63078d23"),
}


def test_every_changed_desk_script_gets_a_new_v():
    import hashlib
    import re

    page = (STATIC / "index.html").read_text(encoding="utf-8")
    tags = dict(re.findall(r'<script src="/static/(desk/[\w-]+\.js)\?v=(\d+)"></script>', page))
    assert sorted(tags) == sorted(DESK_PINS), "a desk/*.js added or removed: pin it here"
    for f, (v, sha) in DESK_PINS.items():
        now = hashlib.sha256((STATIC / f).read_bytes()).hexdigest()[:16]
        assert (int(tags[f]), now) == (v, sha), (f"{f}: index.html has ?v={tags[f]}, file sha {now}; pinned ({v}, {sha!r}). "
                                                     "A changed file needs a higher ?v= in index.html, then that pin here")


def test_the_page_has_no_whole_strategy_mini_micro_switch():
    """The contract is picked on each account (the gear), not for the whole strategy (owner, 2026-11-02)."""
    texts = [(STATIC / "index.html").read_text(encoding="utf-8")] + [p.read_text(encoding="utf-8") for p in (STATIC / "desk").glob("*.js")]
    assert not any("switchLabInstrument" in t for t in texts)


def test_the_red_behind_white_text_passes_contrast():
    """Kill, ARMED and the destructive buttons use --a-red-fill with white text: 4.5:1 or better in light and dark."""
    import re
    css = (STATIC / "apple" / "system.css").read_text()
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    fills = re.findall(r"--a-red-fill:\s*(#[0-9a-f]{6})", css)
    assert len(fills) == 2                         # light, then dark
    assert re.search(r"--a-on-red:\s*#ffffff", css)
    for f in fills:
        assert 1.05 / (lum(f) + 0.05) >= 4.5, f
    for name in ("desk.css", "charts.css"):        # no white-on-systemRed fill left
        for line in (STATIC / "apple" / name).read_text().splitlines():
            if "var(--a-on-red)" in line:
                assert "background: var(--a-red)" not in line, line


def test_group_full_sample_is_one_block_headed_full_sample():
    # a 3:1 group's figures, days and RR/Sharpe are one block; the separate days block (and its "3:1 test months" heading) is gone (2026-10-30)
    g = (STATIC / "desk" / "groups.js").read_text()
    assert 'data-h="${p.figs.full ? "Full sample" : "Combined, after costs"}"' in g
    assert '${p.figs.full ? "" : `<div class="sec"><h2>${esc(p.days.title)}' in g


def test_form_controls_share_one_look():
    """2026-10-28 (owner): the Account cycle inputs and tick boxes were raw browser controls. desk.css has a zero-specificity net for
    text fields and tick boxes, and the group / day-take fields carry the field class (2 in the manager since families went, 2026-11-03)."""
    css = (STATIC / "apple" / "desk.css").read_text()
    assert ':where(html.hb-apple) :where(input[type="checkbox"])' in css and ':where(input:not([type]))' in css
    pop = (STATIC / "desk" / "popups.js").read_text()
    assert pop.count('class="hb-field grp-sel"') == 2 and '<input class="hb-field" type="number"' in pop


def test_desk_page_has_no_families():
    """Desk makeover task 4: families (display-only folds of variants) are gone from the page and its scripts."""
    for gone in ("familyNewName", "loadDeskFamilies", "familyView", "DESKFAM", "deskfamilies", "famShort", "archiveFamily"):
        assert gone not in HTML, gone
    static = Path(__file__).resolve().parents[1] / "homebase" / "static"
    for f in (static / "desk").glob("*.js"):
        assert "DESKFAM" not in f.read_text() and "deskfamilies" not in f.read_text(), f.name
    assert '"family"' not in (static / "desk" / "views.js").read_text()


def test_removed_pieces_are_gone():
    """The settings panel, Manage algos, Remove from Desk, Duplicate and the ?demo=1 preview went (Desk makeover, Task 9)."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    for gone in ("acctSetOverlay", "algoOverlay", "algo-visibility.js", "desk/demo.js", "duplicateLabStrat", "removeLabStrat",
                 "HIDDEN_ALGOS", "under Accounts (+ Assign an account)"):
        assert gone not in HTML and gone not in page, gone
    assert not (STATIC / "algo-visibility.js").exists() and not (STATIC / "desk" / "demo.js").exists()
