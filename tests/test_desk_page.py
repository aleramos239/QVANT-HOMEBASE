"""The desk page carries the chart-trading switch + limits, and switching
it ON goes through the confirm dialog before the POST."""
from __future__ import annotations

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "homebase" / "static" / "index.html").read_text()


def test_the_desk_page_has_the_chart_trading_switch_and_limits():
    for needle in ('id="ctSwitch"', 'id="ctState"', 'id="ctMaxOrder"', 'id="ctMaxPos"',
                   'id="ctSave"', 'post("/api/chart-trading"', "renderChartTrading(s.chart_trading)"):
        assert needle in HTML, needle


def test_switching_on_asks_first():
    fn = HTML[HTML.index("async function setChartTrading"):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("confirmDlg(") < fn.index('post("/api/chart-trading"')


def test_the_preview_data_carries_chart_trading():
    demo = HTML[HTML.index("function demoStatus()"):]
    assert "chart_trading: {enabled: false, max_order_qty: 10, max_position_qty: 20}" in demo


def _fn(name):
    start = HTML.index(name)
    fn = HTML[start:]
    ends = [i for i in (fn.find("\n}\n"), fn.find("\n};\n")) if i != -1]
    return fn[:min(ends)]


def test_chart_trading_toasts_fall_back_to_r_error():
    """Fix round 1 item 5: the write guard's 403/415 refusals carry `error`,
    not `detail` — both the switch and Save-limits toasts must show it."""
    for fn in (_fn("async function setChartTrading"), _fn("$(\"#ctSave\").onclick")):
        assert "r.detail || r.error" in fn


def test_chart_trading_toasts_survive_post_throwing():
    """A network failure or a non-JSON 500 makes post() throw (fetch itself
    rejects, or r.json() fails to parse) — both handlers must catch it and
    tell the user, not leave an unhandled rejection with no feedback."""
    for fn in (_fn("async function setChartTrading"), _fn("$(\"#ctSave\").onclick")):
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
                   'id="llSave"', 'id="llCancel"', 'Trades a day', 'Most contracts per account', 'Most at risk per trade',
                   'No new trade after', 'Flat by', 'Save limits', 'Cancel', 'role="dialog" aria-modal="true"'):
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
    assert '<script src="/static/desklab.js?v=5"></script>' in HTML                  # 5: the window note (final wave I1)
    assert all(f"desklab.js?v={n}" not in HTML for n in (1, 2, 3, 4))
    assert '"version": 7' in (STATIC / "apple" / "manifest.json").read_text()      # 7: the window note (final wave I1)


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
    for ev in ("lab_refused", "lab_runner_down", "lab_runner_back", "lab_stopped", "lab_flatten", "lab_cancelled", "lab_limits_set"):
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
    assert "Something happened to a Lab strategy: see the Activity log." in HTML


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
