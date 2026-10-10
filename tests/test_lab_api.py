"""The Lab's draft routes on the chart service: list, validate, save, delete, templates, request review.
Text in, text out: no draft code runs in the chart service (the sandboxed backtest child is the only place)."""
from __future__ import annotations

import datetime as dt
import json
import sys
import time

from fastapi.testclient import TestClient

import pytest

from homebase import draftstore
from homebase.backtest import sandbox
from homebase.charts import lab_forms, lab_templates, reviewpack
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

OK = {"origin": "http://localhost:8852"}
EVIL = {"origin": "https://evil.example"}
MARCH = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}


def client(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    return TestClient(app, base_url="http://localhost:8852")


def poll(c, rid, s=60.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/run/{rid}").json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_every_template_is_a_valid_draft():
    ts = lab_templates.templates()
    assert [t["id"] for t in ts] == ["straddle", "bar_breakout", "blank"]
    for t in ts:
        draftstore.check_source(t["code"])
        assert draftstore.static_meta(t["code"])["root"] == "NQ"


def test_the_straddle_starter_is_short_and_the_reference_carries_the_contract(tmp_path):
    assert lab_templates.STRADDLE.count("\n") < 50 and "class MyDraft(Strategy)" in lab_templates.STRADDLE
    ref = lab_templates.reference()
    assert "ctx.stop_entry" in ref and "on_bar" in ref and "MyDraft" not in ref
    with client(tmp_path) as c:
        assert c.get("/api/tester/drafts/reference").json()["text"] == ref


def test_the_template_route_serves_them(tmp_path):
    with client(tmp_path) as c:
        got = c.get("/api/tester/drafts/templates").json()
        assert [t["id"] for t in got] == ["straddle", "bar_breakout", "blank"]
        assert all(t["code"] and t["title"] for t in got)


def test_validate_reads_the_text_and_says_which_line(tmp_path):
    with client(tmp_path) as c:
        good = c.post("/api/tester/drafts/validate", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK).json()
        assert good["ok"] is True and good["meta"]["root"] == "NQ"
        assert [i["key"] for i in good["meta"]["inputs"]] == ["lookback", "sl_pts", "tp_pts"]
        bad = c.post("/api/tester/drafts/validate", json={"code": "class X(Strategy:\n  pass\n"}, headers=OK).json()
        assert bad["ok"] is False and bad["line"] == 1 and "SyntaxError" in bad["error"]
        noclass = c.post("/api/tester/drafts/validate", json={"code": "x = 1\n"}, headers=OK).json()
        assert noclass["ok"] is False and "exactly one class" in noclass["error"]
        assert c.post("/api/tester/drafts/validate", json={}, headers=OK).status_code == 400


def test_save_lists_reads_and_deletes_a_draft(tmp_path, drafts_dir):
    with client(tmp_path) as c:
        assert c.get("/api/tester/drafts").json() == []
        r = c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == "draft_nq_bars" and r.json()["meta"]["bar_minutes"] == 5
        assert (drafts_dir / "nq_bars.py").read_text() == lab_templates.BAR_BREAKOUT
        listed = c.get("/api/tester/drafts").json()
        assert [d["name"] for d in listed] == ["nq_bars"] and listed[0]["ok"] is True and listed[0]["bytes"] > 100
        # the catalog the tester already serves picks it up, and its source is readable
        assert "draft_nq_bars" in {s["id"] for s in c.get("/api/tester/strategies").json()}
        assert c.get("/api/tester/strategies/draft_nq_bars/source").json()["files"][0]["text"] == lab_templates.BAR_BREAKOUT
        assert c.delete("/api/tester/drafts/nq_bars", headers=OK).json() == {"deleted": True}
        assert c.delete("/api/tester/drafts/nq_bars", headers=OK).json() == {"deleted": False}
        assert c.get("/api/tester/drafts").json() == []
    assert not any(m.startswith("homebase_draft_") for m in sys.modules), "saving never imports a draft"


def test_a_draft_that_does_not_read_is_listed_with_its_error(tmp_path, drafts_dir):
    (drafts_dir / "broken.py").write_text("class A(Strategy):\n    root = 3 + 4\n")
    with client(tmp_path) as c:
        row = c.get("/api/tester/drafts").json()[0]
        assert row["name"] == "broken" and row["ok"] is False and row["error"]


def _listing_the_old_way(check=draftstore.check_source):
    """What GET /drafts answered before 2026-10-04: every draft read and parsed on every call."""
    import re
    keep = ("class", "name", "root", "session_window", "bar_minutes", "session_independent", "doc")
    out = []
    for name, path in draftstore.list_files():
        st, code = path.stat(), path.read_text(encoding="utf-8")
        try:
            check(code)
            meta, err, line = draftstore.static_meta(code), None, None
        except ValueError as e:
            m = re.search(r"\(line (\d+)\)", str(e))
            meta, err, line = None, str(e), int(m.group(1)) if m else None
        out.append({"name": name, "id": draftstore.draft_id(name), "bytes": st.st_size,
                    "modified": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
                    "ok": meta is not None,
                    "meta": None if meta is None else {**{k: meta[k] for k in keep if k in meta},
                                                       "inputs": meta.get("inputs") or []},
                    **({"error": err, "line": line} if err else {})})
    return out


def test_the_drafts_listing_parses_a_draft_only_when_its_file_changed(tmp_path, drafts_dir, monkeypatch):
    """47 drafts of ~16 KB, the real folder's shape (2026-10-04), plus two that do not read: the first
    listing parses them all, the ones after it only what changed -- and the answer is the same."""
    import os
    helper = ('\n\ndef _helper_{i}(bars, n={i}):\n    """A rolling range over the last n bars."""\n'
              '    hi = max((b["high"] for b in bars[-n:]), default=None)\n'
              '    lo = min((b["low"] for b in bars[-n:]), default=None)\n'
              '    return None if hi is None or lo is None else {{"hi": hi, "lo": lo, "width": hi - lo}}\n')
    src = lab_templates.BAR_BREAKOUT + "".join(helper.format(i=i) for i in range(50))
    assert 14_000 < len(src) < 20_000
    for k in range(47):
        (drafts_dir / f"idea_{k:02d}.py").write_text(src)
    (drafts_dir / "broken.py").write_text("class A(Strategy):\n    root = 3 + 4\n")
    (drafts_dir / "syntax.py").write_text("class X(Strategy:\n  pass\n")
    parsed, real = [], draftstore.check_source

    def counting(code):
        parsed.append(len(code))
        return real(code)

    monkeypatch.setattr(draftstore, "check_source", counting)

    def get(c):
        t = time.perf_counter()
        r = c.get("/api/tester/drafts")
        return r, (time.perf_counter() - t) * 1000

    with client(tmp_path) as c:
        first, cold = get(c)
        assert first.json() == _listing_the_old_way(real) and len(first.json()) == len(parsed) == 49
        assert [d["name"] for d in first.json() if not d["ok"]] == ["broken", "syntax"]   # failures are kept too
        again = [get(c) for _ in range(5)]
        assert all(r.content == first.content for r, _ in again) and len(parsed) == 49   # byte for byte, no parse
        warm = min(ms for _, ms in again)
        print(f"/api/tester/drafts: first {cold:.1f} ms, then {warm:.2f} ms")
        assert warm * 5 < cold
        # an edit (another size), a rewrite of the same size (another mtime), a delete, a new file
        (drafts_dir / "idea_07.py").write_text(src + "\n# edited\n")
        assert get(c)[0].json() == _listing_the_old_way(real) and len(parsed) == 50
        p = drafts_dir / "idea_08.py"
        st = p.stat()
        p.write_text(src.replace("rolling", "ROLLING"))
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
        rows = get(c)[0].json()
        assert rows == _listing_the_old_way(real) and len(parsed) == 51
        was, now = ({d["name"]: d for d in x}["idea_08"] for x in (first.json(), rows))
        assert now["bytes"] == was["bytes"] == st.st_size and now["modified"] != was["modified"]
        (drafts_dir / "idea_09.py").unlink()
        (drafts_dir / "fresh.py").write_text(lab_templates.BLANK)
        rows = get(c)[0].json()
        assert rows == _listing_the_old_way(real) and len(parsed) == 52 and len(rows) == 49
        assert "idea_09" not in {d["name"] for d in rows} and "fresh" in {d["name"] for d in rows}


def test_saving_refuses_bad_names_builtins_and_bad_code(tmp_path):
    with client(tmp_path) as c:
        for name in ("Bad-Name", "nq930", "draft_x", "json"):
            r = c.put(f"/api/tester/drafts/{name}", json={"code": lab_templates.BLANK}, headers=OK)
            assert r.status_code == 400, name
        r = c.put("/api/tester/drafts/okname", json={"code": "def ("}, headers=OK)
        assert r.status_code == 400 and "SyntaxError" in r.json()["detail"]
        assert c.put("/api/tester/drafts/okname", json={}, headers=OK).status_code == 400


def test_writes_keep_the_origin_host_and_json_guards(tmp_path):
    with client(tmp_path) as c:
        body = {"code": lab_templates.BLANK}
        assert c.put("/api/tester/drafts/guarded", json=body, headers=EVIL).status_code == 403
        assert c.put("/api/tester/drafts/guarded", json=body, headers={**OK, "host": "evil.example"}).status_code == 403
        assert c.delete("/api/tester/drafts/guarded", headers=EVIL).status_code == 403
        assert c.post("/api/tester/drafts/validate", json=body, headers=EVIL).status_code == 403
        assert c.put("/api/tester/drafts/guarded", content="code=x", headers={**OK, "content-type": "text/plain"}).status_code == 415
        assert c.get("/api/tester/drafts").json() == []


def test_a_saved_bar_draft_backtests_in_the_sandbox(tmp_path):
    with client(tmp_path) as c:
        c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        rid = c.post("/api/tester/run", json={"strategy": "draft_nq_bars", "range": MARCH}, headers=OK).json()["id"]
        st = poll(c, rid)
        assert st["status"] == "done", st.get("error")
        b = c.get(f"/api/tester/run/{rid}/bundle").json()
        assert b["run"]["strategy"]["id"] == "draft_nq_bars"


def test_request_review_writes_text_only_and_judges_the_run(tmp_path, monkeypatch):
    rdir = tmp_path / "reviews"
    monkeypatch.setenv(reviewpack.ENV, str(rdir))
    with client(tmp_path) as c:
        c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        assert c.post("/api/tester/drafts/nope/review-request", json={}, headers=OK).status_code == 404
        r = c.post("/api/tester/drafts/nq_bars/review-request", json={"note": "worth a look"}, headers=OK)
        assert r.status_code == 200, r.text
        got = r.json()
        pack = json.loads((rdir / f"{got['id']}.json").read_text())
        assert pack["strategy"] == "draft_nq_bars" and pack["note"] == "worth a look" and pack["status"] == "requested"
        assert pack["code"] == lab_templates.BAR_BREAKOUT and len(pack["sha256"]) == 64
        assert {x["id"]: x["ok"] for x in pack["checks"]}["ran"] is False      # no backtest attached
        md = (rdir / f"{got['id']}.md").read_text()
        assert "Review request: draft_nq_bars" in md and "```python" in md and "For the reviewer" in md
        # with a finished run attached the pack carries its numbers
        rid = c.post("/api/tester/run", json={"strategy": "draft_nq_bars", "range": MARCH}, headers=OK).json()["id"]
        assert poll(c, rid)["status"] == "done"
        got2 = c.post("/api/tester/drafts/nq_bars/review-request", json={"run_id": rid}, headers=OK).json()
        pack2 = json.loads((rdir / f"{got2['id']}.json").read_text())
        assert pack2["backtest"]["all"] is not None and {x["id"] for x in pack2["checks"]} >= {"trades", "holdout", "costs"}
        assert c.post("/api/tester/drafts/nq_bars/review-request", json={"run_id": "nope"}, headers=OK).status_code == 404
    # nothing ran, nothing was promoted: the desk's strategy config is untouched by a review request
    assert not any("review" in m and m.startswith("homebase.server") for m in sys.modules)


def test_listing_many_drafts_walks_the_package_once(drafts_dir, monkeypatch):
    calls = []
    real = draftstore._shadow_names
    monkeypatch.setattr(draftstore, "_SHADOW", None)
    monkeypatch.setattr(draftstore, "_shadow_names", lambda: (calls.append(1), real())[1])
    for i in range(12):
        (drafts_dir / f"d_{i}.py").write_text(lab_templates.BLANK)
    assert len(draftstore.list_files()) == 12 and len(calls) == 1
    assert "json" in draftstore.shadow_names() and "engine" in draftstore.shadow_names()


# ---- the form's three routes: answers in, a draft's text out (nothing here runs or writes a draft) ------------

FORM = "/api/tester/drafts/form"
RULES = ("open_straddle", "opening_range", "bar_breakout", "at_time")


def answers_for(base, /, name="form_one", **over):
    a = {**lab_forms.schema()["defaults"][base], "name": name}
    a.update(over)
    return a


def test_the_form_route_serves_the_schema(tmp_path):
    with client(tmp_path) as c:
        got = c.get(FORM).json()
        assert got == lab_forms.schema()
        assert [r["id"] for r in got["rules"]] == list(RULES) and "NQ" in got["markets"]
        assert set(got["defaults"]) == set(RULES) and "name" not in got["defaults"]["open_straddle"]


def test_every_rule_builds_validates_saves_and_lists(tmp_path, drafts_dir):
    with client(tmp_path) as c:
        for rule in RULES:
            a = answers_for(rule, name=f"form_{rule}")
            r = c.post(f"{FORM}/build", json={"answers": a}, headers=OK)
            assert r.status_code == 200, r.text
            got = r.json()
            assert got["ok"] is True and got["name"] == f"form_{rule}"
            assert got["code"] == lab_forms.build(a) and got["sentence"] == lab_forms.sentence(a)
            v = c.post("/api/tester/drafts/validate", json={"code": got["code"]}, headers=OK).json()
            assert v["ok"] is True and v["meta"]["root"] == "NQ", v
            s = c.put(f"/api/tester/drafts/{got['name']}", json={"code": got["code"]}, headers=OK)
            assert s.status_code == 200, s.text
            assert (drafts_dir / f"form_{rule}.py").read_text() == got["code"]
        listed = c.get("/api/tester/drafts").json()
        assert sorted(d["name"] for d in listed) == sorted(f"form_{r}" for r in RULES)
        assert all(d["ok"] for d in listed)
    assert not any(m.startswith("homebase_draft_") for m in sys.modules), "building never imports a draft"


def test_building_never_writes_a_file(tmp_path, drafts_dir):
    with client(tmp_path) as c:
        assert c.post(f"{FORM}/build", json={"answers": answers_for("at_time", side="long")}, headers=OK).json()["ok"]
        assert c.post(f"{FORM}/build", json={"answers": answers_for("at_time", stop={"kind": "range"})}, headers=OK).json()["ok"] is False
        assert list(drafts_dir.iterdir()) == [] and c.get("/api/tester/drafts").json() == []


@pytest.mark.skipif(not sandbox.available(), reason="the macOS sandbox is not available here")
def test_a_built_form_draft_backtests_in_the_sandbox(tmp_path):
    with client(tmp_path) as c:
        a = answers_for("bar_breakout", name="form_bars", bar_min=5, lookback=6)
        code = c.post(f"{FORM}/build", json={"answers": a}, headers=OK).json()["code"]
        assert c.put("/api/tester/drafts/form_bars", json={"code": code}, headers=OK).status_code == 200
        rid = c.post("/api/tester/run", json={"strategy": "draft_form_bars", "range": MARCH}, headers=OK).json()["id"]
        st = poll(c, rid)
        assert st["status"] == "done", st.get("error")
        assert c.get(f"/api/tester/run/{rid}/bundle").json()["run"]["strategy"]["id"] == "draft_form_bars"


def test_a_refused_answer_comes_back_under_its_field_with_status_200(tmp_path):
    cases = [
        ("open_straddle", {"market": "ZZ"}, "market", "Pick one from the list."),
        ("open_straddle", {"rule": "nope"}, "rule", "Pick one from the list."),
        ("at_time", {"side": "both"}, "side", "Pick long or short for this rule."),
        ("open_straddle", {"stop": {"kind": "points", "value": 0}}, "stop", "Every entry needs a stop."),
        ("open_straddle", {"stop": {"kind": "range"}}, "stop", "That stop only works with the opening range."),
        ("open_straddle", {"target": {"kind": "rr", "value": 99}}, "target", "Give a target, or pick None."),
        ("open_straddle", {"distance": 0}, "distance", "The distance must be at least one tick."),
        ("bar_breakout", {"lookback": 1}, "lookback", "Between 2 and 40 bars."),
        ("bar_breakout", {"trades": 9}, "trades", "Between 1 and 5."),
        ("opening_range", {"range_min": 7}, "range_min", "Pick one from the list."),
        ("open_straddle", {"time": "9:30am"}, "time", "A New York time from 00:05 to 15:55, like 09:30."),
        ("open_straddle", {"last_entry": "09:00"}, "last_entry", "It must be after the start."),
        ("open_straddle", {"out_by": "10:00"}, "out_by", "It must be after the last entry, and 15:55 at the latest."),
        ("open_straddle", {"name": "Bad-Name"}, "name", None),
    ]
    with client(tmp_path) as c:
        for rule, over, field, sentence in cases:
            r = c.post(f"{FORM}/build", json={"answers": answers_for(rule, **over)}, headers=OK)
            assert r.status_code == 200, (field, r.text)
            got = r.json()
            assert got["ok"] is False and list(got["errors"]) == [field], (field, got)
            assert sentence is None or got["errors"][field] == sentence, (field, got)
            assert "code" not in got
        a = answers_for("open_straddle")
        del a["distance"]
        got = c.post(f"{FORM}/build", json={"answers": a}, headers=OK).json()
        assert got == {"ok": False, "errors": {"distance": "The form is incomplete."}}


def test_a_name_already_taken_is_refused_unless_it_replaces(tmp_path):
    with client(tmp_path) as c:
        a = answers_for("at_time", name="form_taken")
        first = c.post(f"{FORM}/build", json={"answers": a}, headers=OK).json()
        assert first["ok"] is True
        assert c.put("/api/tester/drafts/form_taken", json={"code": first["code"]}, headers=OK).status_code == 200
        taken = {"ok": False, "errors": {"name": "That name is taken."}}
        r = c.post(f"{FORM}/build", json={"answers": a}, headers=OK)
        assert r.status_code == 200 and r.json() == taken
        assert c.post(f"{FORM}/build", json={"answers": a, "replace": False}, headers=OK).json() == taken
        again = c.post(f"{FORM}/build", json={"answers": {**a, "side": "short"}, "replace": True}, headers=OK).json()
        assert again["ok"] is True and again["name"] == "form_taken" and again["code"] != first["code"]
        # a built-in's name stays taken, replace or not (saving it would be refused too)
        for body in ({"answers": {**a, "name": "gc_nfp"}}, {"answers": {**a, "name": "gc_nfp"}, "replace": True}):
            got = c.post(f"{FORM}/build", json=body, headers=OK).json()
            assert got["ok"] is False and list(got["errors"]) == ["name"] and "built-in" in got["errors"]["name"], got
        # other refusals still come first
        got = c.post(f"{FORM}/build", json={"answers": {**a, "side": "both"}}, headers=OK).json()
        assert list(got["errors"]) == ["side"]


def test_build_and_read_take_only_the_strict_bodies(tmp_path):
    good = answers_for("at_time")
    with client(tmp_path) as c:
        for body in ({}, {"answers": []}, {"answers": "x"}, {"answers": None}, [], "x", 3,
                     {"answers": good, "replace": "yes"}, {"answers": good, "replace": 1}):
            r = c.post(f"{FORM}/build", json=body, headers=OK)
            assert r.status_code == 400, body
        assert c.post(f"{FORM}/build", content="{not json", headers={**OK, "content-type": "application/json"}).status_code == 400
        for body in ({}, {"code": 3}, {"code": None}, {"code": ["x"]}, [], "x"):
            assert c.post(f"{FORM}/read", json=body, headers=OK).status_code == 400, body
        assert c.post(f"{FORM}/read", content="{not json", headers={**OK, "content-type": "application/json"}).status_code == 400
        big = "x" * (draftstore.MAX_BYTES + 1)
        assert c.post(f"{FORM}/read", json={"code": big}, headers=OK).status_code == 400
        assert c.post(f"{FORM}/read", json={"code": "x" * draftstore.MAX_BYTES}, headers=OK).status_code == 200


def test_read_gives_the_answers_back_and_whether_the_file_is_untouched(tmp_path):
    a = answers_for("opening_range", name="form_read")
    with client(tmp_path) as c:
        code = c.post(f"{FORM}/build", json={"answers": a}, headers=OK).json()["code"]
        got = c.post(f"{FORM}/read", json={"code": code}, headers=OK).json()
        assert got == {"answers": lab_forms.read(code)["answers"], "intact": True} and got["answers"]["name"] == "form_read"
        edited = c.post(f"{FORM}/read", json={"code": code + "# my own line\n"}, headers=OK).json()
        assert edited["intact"] is False and edited["answers"] == got["answers"]
        plain = c.post(f"{FORM}/read", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK).json()
        assert plain == {"answers": None, "intact": False}
        assert c.post(f"{FORM}/read", json={"code": ""}, headers=OK).json() == {"answers": None, "intact": False}


def test_the_form_posts_keep_the_origin_host_and_json_guards(tmp_path):
    body = {"answers": answers_for("at_time")}
    with client(tmp_path) as c:
        for path, b in ((f"{FORM}/build", body), (f"{FORM}/read", {"code": "x"})):
            assert c.post(path, json=b, headers=EVIL).status_code == 403
            assert c.post(path, json=b, headers={**OK, "host": "evil.example"}).status_code == 403
            assert c.post(path, content="x=1", headers={**OK, "content-type": "text/plain"}).status_code == 415
            assert c.post(path, json=b, headers=OK).status_code == 200


def test_read_never_500s_on_a_header_json_cannot_answer(tmp_path, monkeypatch):
    code = lab_forms.build(answers_for("at_time", name="form_nan"))
    with client(tmp_path) as c:
        for bad in ("NaN", "Infinity", "-Infinity"):
            text = "\n".join('# form: {"name": %s, "x": %s}' % (bad, bad) if x.startswith("# form: ") else x
                            for x in code.split("\n"))
            r = c.post(f"{FORM}/read", json={"code": text}, headers=OK)
            assert r.status_code == 200 and r.json() == {"answers": None, "intact": False}, bad
        # belt and braces: whatever read() gives that JSON cannot carry is answered as "not a form file"
        monkeypatch.setattr(lab_forms, "read", lambda _code: {"answers": {"x": float("nan")}, "intact": True})
        r = c.post(f"{FORM}/read", json={"code": code}, headers=OK)
        assert r.status_code == 200 and r.json() == {"answers": None, "intact": False}


def test_a_body_nested_too_deep_is_a_400_not_a_500(tmp_path):
    hdr = {**OK, "content-type": "application/json"}
    with client(tmp_path) as c:
        for path in (f"{FORM}/build", f"{FORM}/read"):
            assert c.post(path, content="[" * 200000, headers=hdr).status_code == 400, path


def test_read_answers_200_for_a_header_the_response_cannot_encode(tmp_path, monkeypatch):
    code = lab_forms.build(answers_for("at_time", name="form_sur"))
    def with_header(h):
        return "\n".join("# form: " + h if x.startswith("# form: ") else x for x in code.split("\n"))
    nothing = {"answers": None, "intact": False}
    with client(tmp_path) as c:
        for h in ('{"name": "\\ud800"}', '{"\\ud800": 1}', '{"a": [{"b": "\\udc00"}]}', '{"t": 1e999}', '{"t": -1e999}'):
            r = c.post(f"{FORM}/read", json={"code": with_header(h)}, headers=OK)
            assert r.status_code == 200 and r.json() == nothing, h
        # the route's own guard, with read() itself fooled: it encodes exactly as the response will
        for bad in ({"name": "\ud800"}, {"\ud800": 1}, {"t": float("inf")}):
            monkeypatch.setattr(lab_forms, "read", lambda _c, bad=bad: {"answers": bad, "intact": True})
            r = c.post(f"{FORM}/read", json={"code": code}, headers=OK)
            assert r.status_code == 200 and r.json() == nothing, bad
