"""Step B (B1): a promoted Lab strategy as a desk strategy -- its id, its limits, the in-memory overlay on the desk's
config and the sidecar the desk writes. The store is the conftest's temp folder (HOMEBASE_DESKLAB_ROOT): never the real one."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict

import pytest

from homebase import labcfg
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.config import assignments as desk_config_assignments
from homebase.labcfg import LabLimits
from homebase.labrun import store

LIMITS = {"max_trades_day": 2, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}
MARK = ["ab", "2026-10-09T12:00:00+00:00"]


def rec(name="pp_orb", promoted=MARK[1], **kw):
    return {"name": name, "id": f"draft_{name}", "label": "PP ORB", "root": "NQ", "source": "class X: pass\n", "sha256": "ab",
            "params": {}, "qty": 2, "run": {"id": "r1"}, "notes": [], "promoted_utc": promoted, "enabled": False,
            "commission": 2.5, "slippage_ticks": 1.0, "session_window": ["09:25", "16:00"], "bar_minutes": 5, **kw}


def side(book=(), limits=LIMITS, mark=MARK):
    return {"mark": list(mark), "limits": limits, "book": list(book), "written_utc": "2026-10-10T00:00:00+00:00"}


def desk_cfg(own=True, **kw):
    """The desk's config. own: it holds the store (one desk does: only that one writes sidecars)."""
    cfg = AppCfg(accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN"), "eval1": AccountCfg(keyring_key="k", account_name="E1")},
                 book={"nq930": [{"account": "main", "qty": 3}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=5.0, sl_pts=5.0, tp_pts=15.0, enabled=True)}, **kw)
    if own:
        assert labcfg.take_store(cfg) is True
    return cfg


# ---- the id
def test_the_desk_id_is_lab_plus_the_name_and_back():
    assert (labcfg.LAB, labcfg.PREFIX) == ("lab", "lab_")
    assert labcfg.desk_id("pp_orb") == "lab_pp_orb" and labcfg.store_name("lab_pp_orb") == "pp_orb"
    for not_lab in ("nq930", "lab_", "", None, 5):
        assert labcfg.store_name(not_lab) is None


# ---- the limits
def test_good_limits_parse():
    assert labcfg.parse_limits(LIMITS, rec()) == LabLimits(2, 1, 300.0, "11:00", "15:55")
    edge = labcfg.parse_limits({"max_trades_day": 20, "max_qty": 10, "max_risk_usd": 0.5, "last_entry_et": "09:25", "flat_et": "09:26"}, rec())
    assert edge == LabLimits(20, 10, 0.5, "09:25", "09:26")                     # the edges are in: 20, 10, the window's start


BAD = {"max_trades_day": ([0, 21, 1.5, "2", None, True], "Trades a day: a whole number from 1 to 20."),
       "max_qty": ([0, 11, 2.0, "1", None, True], "Contracts: a whole number from 1 to 10."),
       "max_risk_usd": ([0, -5, "300", None, True, float("nan"), float("inf")], "At risk per trade: a dollar amount above 0."),
       "last_entry_et": (["", "11", "25:00", "11:60", None, 1100, "15:55", "16:10", "09:24"],
                         "No new trade after: a time like 11:00, before the flat time."),
       "flat_et": (["", "4pm", "24:00", None, "15:56", "16:00"], "Flat by: a time like 15:55, no later than 15:55.")}


@pytest.mark.parametrize("key", list(BAD))
def test_each_bad_limit_says_its_one_sentence(key):
    values, sentence = BAD[key]
    for v in values:
        with pytest.raises(ValueError) as e:
            labcfg.parse_limits({**LIMITS, key: v}, rec())
        assert str(e.value) == sentence, (key, v)
    with pytest.raises(ValueError) as e:                                        # the key left out
        labcfg.parse_limits({k: v for k, v in LIMITS.items() if k != key}, rec())
    assert str(e.value) == sentence


def test_limits_that_are_not_an_object_are_refused_with_the_first_sentence():
    for body in (None, [], "x", 5):
        with pytest.raises(ValueError, match="Trades a day"):
            labcfg.parse_limits(body, rec())


def test_no_new_trade_after_is_inside_the_strategys_own_window():
    r = rec(session_window=["09:30", "11:30"])
    assert labcfg.parse_limits({**LIMITS, "last_entry_et": "09:30"}, r).last_entry_et == "09:30"
    with pytest.raises(ValueError, match="No new trade after"):
        labcfg.parse_limits({**LIMITS, "last_entry_et": "09:29"}, r)


# ---- the desk strategy made from a record
def test_strategy_cfg_with_limits():
    s = labcfg.strategy_cfg(rec(enabled=True), LabLimits(2, 1, 300.0, "11:00", "15:50"))
    assert (s.symbol, s.kind, s.label, s.enabled, s.shadow, s.metrics) == ("NQ", "lab", "PP ORB", True, False, {})
    assert s.qty == 1                                                            # min(the record's 2, max_qty 1)
    assert (s.offset_pts, s.sl_pts, s.tp_pts) == (0.0, 0.0, 0.0)
    assert (s.cancel_et, s.flat_et, s.accept_from_et, s.accept_until_et) == ("15:50", "15:50", "09:25", "11:00")
    assert s.fee_rt == 2.5 and s.self_fire is True and s.gated is False and s.only_dates == []
    assert labcfg.strategy_cfg(rec(qty=2), LabLimits(2, 5, 300.0, "11:00", "15:50")).qty == 2


def test_strategy_cfg_with_no_limits_and_with_a_thin_record():
    s = labcfg.strategy_cfg(rec(), None)
    assert s.qty == 1 and s.enabled is False
    assert (s.cancel_et, s.flat_et, s.accept_from_et, s.accept_until_et) == ("15:55", "15:55", "09:25", "15:55")   # min(16:00, 15:55)
    s = labcfg.strategy_cfg(rec(session_window=["09:30", "11:30"], commission=None, qty=None, label=""), None)
    assert (s.flat_et, s.accept_from_et, s.fee_rt, s.qty, s.label) == ("11:30", "09:30", 4.0, 1, "pp_orb")
    for junk in (None, ["x", "y"], ["09:30"], "09:30-11:30", ["25:00", "26:00"]):   # a window that does not read: the default one
        s = labcfg.strategy_cfg(rec(session_window=junk), None)
        assert (s.accept_from_et, s.flat_et) == ("09:25", "15:55")
    assert labcfg.strategy_cfg(rec(enabled="yes"), None).enabled is False        # on is the JSON literal true, nothing else


def test_a_lab_strategy_survives_its_own_dict_like_any_strategy():
    s = labcfg.strategy_cfg(rec(), LabLimits(**LIMITS))
    assert StrategyCfg(**asdict(s)) == s                                         # no new field on StrategyCfg (D2)


# ---- the overlay
def test_overlay_adds_a_promoted_strategy_off_and_with_no_account():
    cfg = desk_cfg()
    before = asdict(cfg)
    store.put(rec())
    assert labcfg.overlay(cfg) == {"added": ["lab_pp_orb"], "removed": [], "changed": []}
    s = cfg.strategies["lab_pp_orb"]
    assert (s.kind, s.symbol, s.enabled, s.label) == ("lab", "NQ", False, "PP ORB")
    assert "lab_pp_orb" not in cfg.book and labcfg.limits_of(cfg, "lab_pp_orb") is None
    assert labcfg.mark_of(cfg, "lab_pp_orb") == MARK
    assert asdict(cfg.strategies["nq930"]) == before["strategies"]["nq930"] and cfg.book["nq930"] == before["book"]["nq930"]
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}   # again: nothing to do
    assert store.get_desk("pp_orb") is None                                      # reading writes nothing


def test_overlay_of_an_empty_store_changes_nothing():
    cfg = desk_cfg(own=False)
    before = asdict(cfg)
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}
    assert asdict(cfg) == before and labcfg.lab_ids(cfg) == []


def test_overlay_reads_the_limits_and_the_book_from_the_sidecar():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}, {"account": "gone", "qty": 1}, {"account": "eval1", "qty": 0},
                                        {"account": "main", "qty": 2}, "junk", {"account": "eval1", "qty": True}]))
    labcfg.overlay(cfg)
    # a size above 0, one row an account; the row of an account this desk does not have is KEPT (fix round 2, A)
    assert cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}, {"account": "gone", "qty": 1}]
    assert desk_config_assignments(cfg, "lab_pp_orb") == [{"account": "main", "qty": 1}]     # ... and is not active
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(**{**LIMITS, "max_risk_usd": 300.0})
    assert cfg.strategies["lab_pp_orb"].accept_until_et == "11:00"
    labcfg.persist_all(cfg)                                                      # what is not a booking leaves the file
    assert store.get_desk("pp_orb")["book"] == [{"account": "main", "qty": 1}, {"account": "gone", "qty": 1}]


def test_a_sidecar_with_rows_that_do_not_read_never_breaks_the_overlay():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": "two"}, {"account": ["x"], "qty": 1}], mark="junk"))
    store.put(rec("other_one"))
    store.put_desk("other_one", ["not", "an", "object"])
    assert sorted(labcfg.overlay(cfg)["added"]) == ["lab_other_one", "lab_pp_orb"]
    assert "lab_pp_orb" not in cfg.book and "lab_other_one" not in cfg.book
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [] and store.get_desk("pp_orb")["mark"] == MARK


def test_a_sidecar_of_another_promotion_loses_its_book_and_keeps_its_limits():
    cfg = desk_cfg()
    store.put(rec(promoted="2026-10-10T08:00:00+00:00"))                         # promoted again since the sidecar
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    assert "lab_pp_orb" not in cfg.book
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(**{**LIMITS, "max_risk_usd": 300.0})
    assert labcfg.mark_of(cfg, "lab_pp_orb") == ["ab", "2026-10-10T08:00:00+00:00"]


def test_a_strategy_promoted_again_while_the_desk_runs_loses_its_book_and_keeps_its_limits():
    cfg = desk_cfg()
    store.put(rec(enabled=True))
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    assert cfg.book["lab_pp_orb"] and cfg.strategies["lab_pp_orb"].enabled is True
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", sha256="cd"))            # promoted again: other code, lands off
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": ["lab_pp_orb"]}
    assert "lab_pp_orb" not in cfg.book and cfg.strategies["lab_pp_orb"].enabled is False
    assert labcfg.limits_of(cfg, "lab_pp_orb") is not None and labcfg.mark_of(cfg, "lab_pp_orb") == ["cd", "2026-10-10T08:00:00+00:00"]


def test_limits_that_no_longer_fit_the_new_records_window_are_dropped():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(limits={**LIMITS, "last_entry_et": "09:26"}))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb").last_entry_et == "09:26"
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", session_window=["09:30", "16:00"]))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None                           # 09:26 is before the new window: set them again


def test_sidecar_limits_that_do_not_read_are_no_limits_and_no_book():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}], limits={**LIMITS, "max_qty": 99}))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None and "lab_pp_orb" not in cfg.book    # fix round 1, item 2


def test_overlay_removes_a_strategy_whose_record_is_gone():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    store.remove("pp_orb")
    assert labcfg.overlay(cfg) == {"added": [], "removed": ["lab_pp_orb"], "changed": []}
    assert "lab_pp_orb" not in cfg.strategies and "lab_pp_orb" not in cfg.book and labcfg.lab_ids(cfg) == []
    assert set(cfg.strategies) == {"nq930"} and cfg.book == {"nq930": [{"account": "main", "qty": 3}]}


def test_overlay_keeps_a_strategy_whose_record_is_gone_while_the_engine_holds_an_open_round():
    cfg = desk_cfg()
    store.put(rec(enabled=True))
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    store.remove("pp_orb")
    held = {"lab_pp_orb"}
    assert labcfg.overlay(cfg, held=lambda n: n in held) == {"added": [], "removed": [], "changed": ["lab_pp_orb"]}
    s = cfg.strategies["lab_pp_orb"]
    assert s.kind == "lab" and s.enabled is False                                # kept for its open round, and switched off
    assert cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}]
    assert labcfg.overlay(cfg, held=lambda n: n in held) == {"added": [], "removed": [], "changed": []}
    held.clear()                                                                 # the round is over
    assert labcfg.overlay(cfg, held=lambda n: n in held)["removed"] == ["lab_pp_orb"]
    assert "lab_pp_orb" not in cfg.strategies and "lab_pp_orb" not in cfg.book


def test_overlay_follows_the_records_switch():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    store.set_enabled("pp_orb", True)
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": ["lab_pp_orb"]}
    assert cfg.strategies["lab_pp_orb"].enabled is True


def test_the_desks_own_book_and_limits_win_over_a_sidecar_read_earlier():
    """The desk is the only writer of the book and the limits: once a strategy is known, what the desk holds in memory is
    the truth. A store read that started before a booking must not undo it."""
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    stale = labcfg.read_store()                                                  # read before the owner's change
    cfg.book["lab_pp_orb"] = []                                                  # the owner takes the account off
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(1, 1, 100.0, "10:00", "15:00"))
    labcfg.apply(cfg, stale)
    assert cfg.book["lab_pp_orb"] == [] and labcfg.limits_of(cfg, "lab_pp_orb").max_risk_usd == 100.0
    assert cfg.strategies["lab_pp_orb"].flat_et == "15:00"


def test_a_record_that_cannot_be_a_strategy_is_left_out():
    cfg = desk_cfg()
    store.put(rec("no_root", root=None))
    store.put(rec("ok_one"))
    assert labcfg.overlay(cfg)["added"] == ["lab_ok_one"]
    assert "lab_no_root" not in cfg.strategies


def test_overlay_never_takes_over_a_strategy_that_is_not_from_the_lab():
    cfg = desk_cfg()
    cfg.strategies["lab_pp_orb"] = StrategyCfg(symbol="ES", qty=1, offset_pts=1.0, sl_pts=1.0, tp_pts=1.0)   # not kind lab
    store.put(rec())
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}
    assert cfg.strategies["lab_pp_orb"].symbol == "ES" and labcfg.lab_ids(cfg) == []


# ---- the sidecar the desk writes
def test_persist_all_writes_a_sidecar_only_when_its_content_changed():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") is None                                      # no limits, no account: nothing to say
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    cfg.book["lab_pp_orb"] = [{"account": "main", "qty": 1}]
    assert labcfg.pending(cfg) != []
    labcfg.persist_all(cfg)
    got = store.get_desk("pp_orb")
    assert got["mark"] == MARK and got["book"] == [{"account": "main", "qty": 1}] and got["written_utc"]
    assert got["limits"] == {**LIMITS, "max_risk_usd": 300.0}
    assert labcfg.pending(cfg) == []
    store.put_desk("pp_orb", {**got, "written_utc": "untouched"})
    labcfg.persist_all(cfg)                                                      # nothing changed: not written again
    assert store.get_desk("pp_orb")["written_utc"] == "untouched"
    cfg.book["lab_pp_orb"] = []
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [] and store.get_desk("pp_orb")["written_utc"] != "untouched"


def test_persist_all_of_a_config_with_no_lab_strategy_touches_nothing(desklab_root):
    labcfg.persist_all(desk_cfg(own=False))
    assert list(desklab_root.iterdir()) == []


def test_what_overlay_read_is_not_written_back():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", {**side(book=[{"account": "main", "qty": 1}]), "written_utc": "untouched"})
    labcfg.overlay(cfg)
    assert labcfg.pending(cfg) == []
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["written_utc"] == "untouched"


def test_a_dropped_book_is_written_to_the_sidecar_with_the_new_mark():
    cfg = desk_cfg()
    store.put(rec(promoted="2026-10-10T08:00:00+00:00"))
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))         # the older promotion's sidecar
    labcfg.overlay(cfg)
    labcfg.persist_all(cfg)
    got = store.get_desk("pp_orb")
    assert got["mark"] == ["ab", "2026-10-10T08:00:00+00:00"] and got["book"] == [] and got["limits"] == {**LIMITS, "max_risk_usd": 300.0}


def test_a_sidecar_that_could_not_be_written_stays_pending(monkeypatch):
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))

    def busy(*a, **k):
        raise TimeoutError("busy")
    real = store.put_desk
    monkeypatch.setattr(store, "put_desk", busy)
    with pytest.raises(TimeoutError):
        labcfg.persist_all(cfg)
    assert labcfg.pending(cfg) != []                                             # not forgotten
    monkeypatch.setattr(store, "put_desk", real)
    labcfg.persist_all(cfg)
    assert labcfg.pending(cfg) == [] and store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2


def test_forget_takes_a_strategy_off_the_config_and_out_of_what_is_written():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    labcfg.forget(cfg, "lab_pp_orb")
    assert "lab_pp_orb" not in cfg.strategies and "lab_pp_orb" not in cfg.book and labcfg.pending(cfg) == []
    labcfg.forget(cfg, "nq930")                                                  # never a strategy that is not from the Lab
    assert "nq930" in cfg.strategies and cfg.book["nq930"]


# ---- strategy code never runs in the desk process
def test_importing_labcfg_loads_nothing_of_the_tester():
    code = ("import sys; import homebase.labcfg\n"
            "bad = sorted(m for m in sys.modules if m.startswith('homebase.backtest'))\n"
            "print(bad); sys.exit(1 if bad else 0)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_a_config_bound_to_a_store_reads_and_writes_there(tmp_path, desklab_root):
    """The fake desk (and any desk handed its own store) never touches the default one: config.save's hook is handed
    only the config, so the config itself names its store."""
    other = tmp_path / "other-store"
    store.put(rec(), other)
    cfg = desk_cfg(own=False)
    labcfg.bind(cfg, other)
    assert labcfg.take_store(cfg) is True                                        # the store it is bound to, not the default
    assert labcfg.overlay(cfg)["added"] == ["lab_pp_orb"]
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb", other)["limits"]["max_trades_day"] == 2
    assert list(desklab_root.iterdir()) == []


def test_asking_about_a_config_that_never_held_a_lab_strategy_leaves_it_as_it_was():
    cfg = desk_cfg(own=False)
    before = dict(vars(cfg))
    assert labcfg.pending(cfg) == [] and labcfg.lab_ids(cfg) == [] and not labcfg.is_lab(cfg, "nq930")
    assert labcfg.limits_of(cfg, "nq930") is None and labcfg.mark_of(cfg, "nq930") is None
    labcfg.persist_all(cfg)
    labcfg.forget(cfg, "nq930")
    assert vars(cfg) == before                                                   # config.save's hook sees every config saved


def test_a_store_held_by_another_writer_costs_one_bounded_wait_not_one_per_sidecar(monkeypatch):
    cfg = desk_cfg()
    for n in ("one_a", "two_b", "three_c"):
        store.put(rec(n))
    labcfg.overlay(cfg)
    for n in ("one_a", "two_b", "three_c"):
        labcfg.set_limits(cfg, labcfg.desk_id(n), LabLimits(**LIMITS))
    tried = []

    def busy(name, *a, **k):
        tried.append(name)
        raise TimeoutError("busy")
    monkeypatch.setattr(store, "put_desk", busy)
    with pytest.raises(TimeoutError):
        labcfg.persist_all(cfg)
    assert len(tried) == 1 and len(labcfg.pending(cfg)) == 3                     # one wait; all three still to write


# =====================================================================================================================
# Fix round 1 (review of B1). The load path holds the same rules as the routes; one desk owns the store; a record or a
# sidecar the desk cannot read never breaks the others and is never overwritten.
# =====================================================================================================================
import threading
import time

L3 = {**LIMITS, "max_qty": 3}                                                    # most contracts: 3


def notes(cfg, event=None):
    got = labcfg.take_notes(cfg)
    return [f for e, f in got if e == event] if event else got


def hold_the_store(at=None):
    """Another writer holds the store's write lock (a thread here; a process is the same flock). Returns release()."""
    inside, release = threading.Event(), threading.Event()

    def holder():
        with store.write_lock(at):
            inside.set()
            release.wait(10)
    t = threading.Thread(target=holder)
    t.start()
    assert inside.wait(5)

    def done():
        release.set()
        t.join(5)
    return done


# ---- item 2: no limits -> no book; a row above the cap is dropped; limits that do not parse are never overwritten
def test_a_sidecar_with_book_rows_and_no_limits_has_no_book():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}], limits=None))
    labcfg.overlay(cfg)
    assert "lab_pp_orb" not in cfg.book and labcfg.limits_of(cfg, "lab_pp_orb") is None and not labcfg.frozen(cfg, "lab_pp_orb")
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["main"], "why": "no limits"}]
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [] and store.get_desk("pp_orb")["limits"] is None   # there were none to keep


def test_limits_on_disk_that_do_not_parse_mean_no_book_and_the_sidecar_is_left_as_it_is():
    """The reviewer's probe 1: the same promotion, flat_et 16:30 (no longer allowed), a row of 5."""
    cfg = desk_cfg()
    store.put(rec())
    disk = side(book=[{"account": "eval1", "qty": 5}], limits={**L3, "flat_et": "16:30"})
    store.put_desk("pp_orb", disk)
    labcfg.overlay(cfg)
    assert "lab_pp_orb" not in cfg.book and labcfg.limits_of(cfg, "lab_pp_orb") is None
    assert labcfg.frozen(cfg, "lab_pp_orb") is True
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["eval1"], "why": "limits unreadable"}]
    assert labcfg.pending(cfg) == []
    for _ in range(3):                                                           # a start, the hook, every refresh
        labcfg.overlay(cfg)
        labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") == disk                                      # never `limits: null` over his limits
    assert notes(cfg) == []                                                      # and it is said once
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))                    # he saves limits again
    assert labcfg.frozen(cfg, "lab_pp_orb") is False
    labcfg.persist_all(cfg)
    got = store.get_desk("pp_orb")
    assert got["limits"]["flat_et"] == "15:55" and got["book"] == []


@pytest.mark.parametrize("junk", ["x", 5, [], {"max_qty": 1}, {**LIMITS, "max_risk_usd": "300"}])
def test_any_limits_that_do_not_parse_freeze_the_sidecar(junk):
    cfg = desk_cfg()
    store.put(rec())
    disk = side(book=[{"account": "main", "qty": 1}], limits=junk)
    store.put_desk("pp_orb", disk)
    labcfg.overlay(cfg)
    labcfg.persist_all(cfg)
    assert labcfg.frozen(cfg, "lab_pp_orb") and "lab_pp_orb" not in cfg.book and store.get_desk("pp_orb") == disk


def test_a_book_row_above_the_cap_is_dropped_and_the_others_stay():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 4}, {"account": "eval1", "qty": 3}], limits=L3))
    labcfg.overlay(cfg)
    assert cfg.book["lab_pp_orb"] == [{"account": "eval1", "qty": 3}]
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["main"], "why": "above the size cap"}]
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 3}]


def test_every_refresh_holds_the_same_rules_over_what_the_desk_has_in_memory():
    """A row can reach the desk's memory without a route (the "account is back" re-booking): the next read drops it."""
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "eval1", "qty": 3}], limits=L3))
    labcfg.overlay(cfg)
    notes(cfg)
    cfg.book["lab_pp_orb"].append({"account": "main", "qty": 9})                 # above the cap
    cfg.book["lab_pp_orb"].append({"account": "ghost", "qty": 9})                # an account this desk does not have
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}
    assert cfg.book["lab_pp_orb"] == [{"account": "eval1", "qty": 3}, {"account": "ghost", "qty": 9}]   # ghost is not ours to judge
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["main"], "why": "above the size cap"}]
    labcfg.set_limits(cfg, "lab_pp_orb", None)                                   # limits gone, rows still there
    labcfg.overlay(cfg)
    assert cfg.book["lab_pp_orb"] == [{"account": "ghost", "qty": 9}]
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["eval1"], "why": "no limits"}]


# ---- item 8: a book the desk drops on its own is said
def test_a_book_dropped_for_another_promotion_is_said_and_a_row_of_another_pool_is_not_dropped():
    cfg = desk_cfg()
    store.put(rec(promoted="2026-10-10T08:00:00+00:00"))
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}, {"account": "eval1", "qty": 1}]))
    store.put(rec("other_one"))
    store.put_desk("other_one", side(book=[{"account": "main", "qty": 1}, {"account": "not_in_this_pool", "qty": 1}]))
    labcfg.overlay(cfg)
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["main", "eval1"], "why": "promoted again"}]
    assert cfg.book["lab_other_one"] == [{"account": "main", "qty": 1}, {"account": "not_in_this_pool", "qty": 1}]
    store.put(rec("other_one", promoted="2026-10-11T08:00:00+00:00"))            # promoted again while the desk runs
    labcfg.overlay(cfg)
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_other_one", "accounts": ["main", "not_in_this_pool"], "why": "promoted again"}]
    labcfg.overlay(cfg)
    assert notes(cfg) == []


def test_limits_that_no_longer_fit_a_new_promotion_are_kept_on_disk_too():
    cfg = desk_cfg()
    store.put(rec())
    disk = side(limits={**LIMITS, "last_entry_et": "09:26"})
    store.put_desk("pp_orb", disk)
    labcfg.overlay(cfg)
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", session_window=["09:30", "16:00"]))
    labcfg.overlay(cfg)
    labcfg.persist_all(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None and labcfg.frozen(cfg, "lab_pp_orb")
    assert store.get_desk("pp_orb") == disk


# ---- item 7: one record the desk cannot read never stops the others; numbers that are not numbers
def test_a_record_with_an_absurd_number_is_read_like_any_other():
    """The reviewer's probe 4: a 400-digit commission made math.isfinite raise, and with it every later refresh."""
    cfg = desk_cfg()
    store.put(rec("huge_fee", commission=10 ** 400, qty=10 ** 400))
    store.put(rec("good_one"))
    assert sorted(labcfg.overlay(cfg)["added"]) == ["lab_good_one", "lab_huge_fee"]
    assert cfg.strategies["lab_huge_fee"].fee_rt == 4.0 and cfg.strategies["lab_huge_fee"].qty == 1


def test_one_record_that_cannot_be_made_a_strategy_is_skipped_and_the_others_load(monkeypatch):
    cfg = desk_cfg()
    store.put(rec("bad_one"))
    store.put(rec("good_one"))
    store.put(rec("int_root", root=5))                                           # no market
    real = labcfg.strategy_cfg

    def picky(r, limits):
        if r["name"] == "bad_one":
            raise OverflowError("int too large to convert to float")
        return real(r, limits)
    monkeypatch.setattr(labcfg, "strategy_cfg", picky)
    assert labcfg.overlay(cfg) == {"added": ["lab_good_one"], "removed": [], "changed": []}
    assert labcfg.lab_ids(cfg) == ["lab_good_one"]                               # no entry is left without its strategy
    assert "lab_bad_one" not in cfg.strategies and "lab_int_root" not in cfg.strategies
    said = sorted(notes(cfg, "lab_unreadable"), key=lambda n: n["strategy"])
    assert [(n["strategy"], n["mark"]) for n in said] == [("lab_bad_one", MARK), ("lab_int_root", MARK)]
    assert "int too large" in said[0]["error"]
    labcfg.overlay(cfg)
    assert notes(cfg) == []                                                      # once per promotion, not every 2 s
    store.put(rec("bad_one", promoted="2026-10-11T00:00:00+00:00"))
    labcfg.overlay(cfg)
    assert [n["strategy"] for n in notes(cfg, "lab_unreadable")] == ["lab_bad_one"]   # a new promotion: said again
    monkeypatch.setattr(labcfg, "strategy_cfg", real)
    assert labcfg.overlay(cfg)["added"] == ["lab_bad_one"]                       # it reads again: it loads


def test_a_known_strategy_whose_record_stops_reading_is_kept_switched_off(monkeypatch):
    cfg = desk_cfg()
    store.put(rec(enabled=True))
    store.put_desk("pp_orb", side(book=[{"account": "eval1", "qty": 1}]))
    labcfg.overlay(cfg)
    assert cfg.strategies["lab_pp_orb"].enabled is True and not labcfg.unreadable(cfg, "lab_pp_orb")
    real = labcfg.strategy_cfg

    def boom(r, limits):
        raise ValueError("cannot read")
    monkeypatch.setattr(labcfg, "strategy_cfg", boom)
    store.put(rec(enabled=True, label="New label"))
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": ["lab_pp_orb"]}
    s = cfg.strategies["lab_pp_orb"]
    assert s.kind == "lab" and s.enabled is False and s.label == "PP ORB"        # what it last read, off
    assert labcfg.unreadable(cfg, "lab_pp_orb") and cfg.book["lab_pp_orb"] == [{"account": "eval1", "qty": 1}]
    assert len(notes(cfg, "lab_unreadable")) == 1
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []} and notes(cfg) == []
    monkeypatch.setattr(labcfg, "strategy_cfg", real)
    assert labcfg.overlay(cfg)["changed"] == ["lab_pp_orb"]
    assert cfg.strategies["lab_pp_orb"].enabled is True and not labcfg.unreadable(cfg, "lab_pp_orb")


@pytest.mark.parametrize("key, value, sentence", [
    ("max_risk_usd", 10 ** 400, "At risk per trade: a dollar amount above 0."),
    ("max_risk_usd", 1e300, "At risk per trade: a dollar amount above 0."),
    ("max_risk_usd", float("-inf"), "At risk per trade: a dollar amount above 0."),
    ("max_trades_day", 10 ** 400, "Trades a day: a whole number from 1 to 20."),
    ("max_qty", -10 ** 400, "Contracts: a whole number from 1 to 10.")])
def test_an_absurd_number_in_the_limits_is_its_fields_sentence(key, value, sentence):
    with pytest.raises(ValueError) as e:
        labcfg.parse_limits({**LIMITS, key: value}, rec())
    assert str(e.value) == sentence


# ---- item 3: the after-save hook never waits for the store
def test_persist_all_never_waits_for_the_store_unless_told_to():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    done = hold_the_store()
    try:
        t0 = time.perf_counter()
        with pytest.raises(TimeoutError):
            labcfg.persist_all(cfg)                                              # as config.save's hook calls it
        assert time.perf_counter() - t0 < 0.05
        assert labcfg.pending(cfg) != [] and store.get_desk("pp_orb") is None    # left for the next refresh
    finally:
        done()
    labcfg.persist_all(cfg)
    assert labcfg.pending(cfg) == [] and store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2


# ---- item 5: one desk owns the store
def test_only_the_desk_that_took_the_store_writes_sidecars(desklab_root):
    store.put(rec())
    a, b, c = desk_cfg(own=False), desk_cfg(own=False), desk_cfg(own=False)
    for cfg in (a, b, c):
        labcfg.overlay(cfg)
        labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    labcfg.persist_all(c)                                                        # never took it: writes nothing
    assert store.get_desk("pp_orb") is None and not labcfg.owns(c) and not (desklab_root / "desk.lock").exists()
    assert labcfg.take_store(a) is True and labcfg.owns(a) and (desklab_root / "desk.lock").is_file()
    assert labcfg.take_store(a) is True                                          # asked again: still its own
    assert labcfg.take_store(b) is False and not labcfg.owns(b)
    labcfg.set_limits(b, "lab_pp_orb", LabLimits(**{**LIMITS, "max_trades_day": 9}))
    labcfg.persist_all(b)
    assert store.get_desk("pp_orb") is None                                      # the second desk reads only
    labcfg.persist_all(a)
    assert store.get_desk("pp_orb") is None and not labcfg.ready(a)              # a holds the lock but owes its re-read (round 3, N1)
    labcfg.overlay(a)                                                            # the re-read: what it held as a reader gives way
    assert labcfg.ready(a) and labcfg.limits_of(a, "lab_pp_orb") is None
    labcfg.set_limits(a, "lab_pp_orb", LabLimits(**LIMITS))
    labcfg.persist_all(a)
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2
    assert (labcfg.store_state(a), labcfg.store_state(b), labcfg.store_state(c)) == ("owner", "busy", None)
    labcfg.release_store(a)                                                      # the first desk ends
    assert not labcfg.owns(a) and labcfg.store_state(a) == "released"
    assert labcfg.take_store(a) is False                                         # a desk that let go never takes it back
    assert labcfg.take_store(b) is True and labcfg.store_state(b) == "owner"     # read-only is not for life (fix round 2, A)
    assert labcfg.take_store(c) is False
    labcfg.release_store(b)
    assert [s["name"] for s in store.listing()] == ["pp_orb"]                    # desk.lock is not a record


def test_a_second_desk_with_other_accounts_never_rewrites_the_first_desks_sidecar():
    """The reviewer's probe 2."""
    store.put(rec(enabled=True))
    disk = side(book=[{"account": "main", "qty": 1}])
    store.put_desk("pp_orb", disk)
    first = desk_cfg()                                                           # holds the store
    labcfg.overlay(first)
    second = AppCfg(accounts={"demo": AccountCfg(keyring_key="k", account_name="D")}, strategies=dict(desk_cfg(own=False).strategies))
    assert labcfg.take_store(second) is False
    labcfg.overlay(second)
    assert "lab_pp_orb" in second.strategies and desk_config_assignments(second, "lab_pp_orb") == []   # the strategy, no account of its own
    for _ in range(3):
        labcfg.overlay(second)
        labcfg.persist_all(second)
    assert store.get_desk("pp_orb") == disk and store.booked("pp_orb") is True
    store.put_desk("old_one", side())                                            # a sidecar whose record is gone
    snap = labcfg.read_store()
    assert labcfg.orphans(first, snap) == ["old_one"]                            # the owner's to remove
    assert labcfg.orphans(second, snap) == []                                    # never a reader's


# ---- item 6: a sidecar whose record is gone
def test_orphans_are_the_sidecars_with_no_record_that_the_desk_is_not_holding():
    cfg = desk_cfg()
    store.put(rec("kept_one", enabled=True))
    store.put_desk("kept_one", side(book=[{"account": "main", "qty": 1}]))
    store.put(rec("live_one", enabled=True))
    store.put_desk("live_one", side(book=[{"account": "eval1", "qty": 1}]))
    store.put_desk("old_one", side(book=[{"account": "main", "qty": 1}]))        # its record went while the desk was down
    labcfg.overlay(cfg)
    assert labcfg.orphans(cfg, labcfg.read_store()) == ["old_one"]
    store.remove("kept_one")
    store.remove("live_one")
    snap = labcfg.read_store()
    labcfg.apply(cfg, snap, held=lambda d: d == "lab_live_one")
    assert labcfg.orphans(cfg, snap) == ["kept_one", "old_one"]                  # live_one has a round open: it stays
    assert "lab_live_one" in cfg.strategies and "lab_kept_one" not in cfg.strategies
    (store.root() / "unreadable.json").write_text("{not json")                  # a record FILE that does not read is still there
    store.put_desk("unreadable", side())
    store.put(rec("no_market", root=None))                                       # and so is a record the desk cannot use
    store.put_desk("no_market", side())
    assert labcfg.orphans(cfg, labcfg.read_store()) == ["kept_one", "old_one"]   # fix round 2, C: only when the file is absent


# ---- item 10: what is pending is per strategy
def test_pending_can_be_asked_for_one_strategy():
    cfg = desk_cfg()
    for n in ("one_a", "two_b"):
        store.put(rec(n))
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_one_a", LabLimits(**LIMITS))
    assert [n for n, _ in labcfg.pending(cfg)] == ["one_a"]
    assert labcfg.pending(cfg, "lab_two_b") == [] and [n for n, _ in labcfg.pending(cfg, "lab_one_a")] == ["one_a"]


def test_a_strategy_with_a_write_in_flight_is_left_alone_by_the_hook():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    labcfg.set_busy(cfg, "lab_pp_orb", True)
    assert labcfg.any_busy(cfg) and labcfg.pending(cfg) == []
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") is None
    labcfg.set_busy(cfg, "lab_pp_orb", False)
    assert not labcfg.any_busy(cfg) and labcfg.pending(cfg) != []


def test_commit_makes_what_was_written_the_desks_memory():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    lim, rows = LabLimits(**LIMITS), [{"account": "eval1", "qty": 1}]
    want = labcfg.sidecar(cfg, "lab_pp_orb", lim, rows)
    assert want == {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": rows}
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None and "lab_pp_orb" not in cfg.book    # asking changes nothing
    labcfg.commit(cfg, "lab_pp_orb", lim, rows, want)
    assert labcfg.limits_of(cfg, "lab_pp_orb") == lim and cfg.book["lab_pp_orb"] == rows and labcfg.pending(cfg) == []
    assert cfg.strategies["lab_pp_orb"].accept_until_et == "11:00"


# =====================================================================================================================
# Fix round 2
# =====================================================================================================================
# ---- A: a row of an account this desk does not have is kept, never dropped, never said
def test_a_desk_with_no_accounts_leaves_every_book_row_where_it_is(desklab_root):
    """The reviewer's probe A, step 1: a worktree has no config.json, so its desk has no accounts."""
    store.put(rec(enabled=True))
    disk = side(book=[{"account": "eval1", "qty": 1}, {"account": "main", "qty": 1}], limits={**LIMITS, "max_risk_usd": 300.0})
    store.put_desk("pp_orb", disk)
    dev = AppCfg(strategies=dict(desk_cfg(own=False).strategies))
    assert labcfg.take_store(dev) is True                                        # the real desk is down: it is the owner
    for _ in range(3):
        labcfg.overlay(dev)
        labcfg.persist_all(dev)
    assert dev.book["lab_pp_orb"] == disk["book"] and desk_config_assignments(dev, "lab_pp_orb") == []
    assert store.get_desk("pp_orb") == disk and store.booked("pp_orb") is True   # nothing written, nothing un-booked
    assert notes(dev) == [] and labcfg.pending(dev) == []


def test_the_rules_judge_only_the_rows_of_accounts_this_desk_has():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "other_pool", "qty": 9}, {"account": "main", "qty": 9}], limits=L3))
    store.put(rec("no_limits"))
    store.put_desk("no_limits", side(book=[{"account": "other_pool", "qty": 1}, {"account": "main", "qty": 1}], limits=None))
    labcfg.overlay(cfg)
    assert cfg.book["lab_pp_orb"] == [{"account": "other_pool", "qty": 9}]       # main is above the cap; other_pool is not ours
    assert cfg.book["lab_no_limits"] == [{"account": "other_pool", "qty": 1}]
    assert sorted((n["strategy"], n["accounts"], n["why"]) for n in notes(cfg, "lab_unbooked")) == [
        ("lab_no_limits", ["main"], "no limits"), ("lab_pp_orb", ["main"], "above the size cap")]
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [{"account": "other_pool", "qty": 9}]


# ---- A: read-only is not for life, and "could not try the lock" is not "another desk"
def test_a_lock_that_cannot_be_tried_is_unknown_and_is_tried_again(monkeypatch):
    cfg = desk_cfg(own=False)
    real = store.desk_lock

    def broken(at=None):
        raise OSError(24, "Too many open files")
    monkeypatch.setattr(store, "desk_lock", broken)
    assert labcfg.take_store(cfg) is False and labcfg.store_state(cfg) == "unknown" and not labcfg.owns(cfg)
    monkeypatch.setattr(store, "desk_lock", real)
    assert labcfg.take_store(cfg) is True and labcfg.store_state(cfg) == "owner"


def test_a_reader_follows_the_owners_sidecar_and_takes_over_with_what_is_on_disk():
    """A reader's limits and book are what the OWNER last wrote, re-read on every apply(reload=True): when it becomes
    the owner it must not write back what it read at its start."""
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    owner, reader = desk_cfg(), desk_cfg(own=False)
    labcfg.overlay(owner)
    assert labcfg.take_store(reader) is False
    labcfg.overlay(reader)
    want = labcfg.sidecar(owner, "lab_pp_orb", LabLimits(**L3), [{"account": "eval1", "qty": 2}])   # the owner changes both
    store.put_desk("pp_orb", labcfg.stamped(want))
    labcfg.commit(owner, "lab_pp_orb", LabLimits(**L3), [{"account": "eval1", "qty": 2}], want)
    labcfg.apply(reader, labcfg.read_store())                                    # an owner's apply never re-reads the sidecar ...
    assert reader.book["lab_pp_orb"] == [{"account": "main", "qty": 1}]
    assert labcfg.apply(reader, labcfg.read_store(), reload=True)["changed"] == ["lab_pp_orb"]     # ... a reader's does
    assert reader.book["lab_pp_orb"] == [{"account": "eval1", "qty": 2}] and labcfg.limits_of(reader, "lab_pp_orb").max_qty == 3
    labcfg.release_store(owner)
    assert labcfg.take_store(reader) is True
    labcfg.apply(reader, labcfg.read_store(), reload=True)
    labcfg.persist_all(reader)
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 2}] and labcfg.pending(reader) == []


def test_a_reload_re_reads_every_strategy_also_one_this_desk_holds_differently():
    """Fix round 3, N2: a reload is for a desk that did not own the store until now. It has changed nothing on disk, so
    it has nothing to keep: what it holds differently in memory (its own rule dropped a row in its view) gives way."""
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    cfg.book["lab_pp_orb"] = []                                                  # its memory differs from the disk
    assert labcfg.pending(cfg) != []
    labcfg.apply(cfg, labcfg.read_store(), reload=True)
    assert cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}] and labcfg.pending(cfg) == []


# ---- C: a record FILE that is there but does not read is not a record that is gone
def test_a_record_file_that_does_not_read_keeps_the_strategy_switched_off_and_its_sidecar():
    cfg = desk_cfg()
    store.put(rec(enabled=True))
    disk = side(book=[{"account": "eval1", "qty": 1}])
    store.put_desk("pp_orb", disk)
    labcfg.overlay(cfg)
    f = store.root() / "pp_orb.json"
    good = f.read_text()
    f.write_text("{not json")
    snap = labcfg.read_store()
    assert labcfg.apply(cfg, snap) == {"added": [], "removed": [], "changed": ["lab_pp_orb"]}
    assert labcfg.unreadable(cfg, "lab_pp_orb") and cfg.strategies["lab_pp_orb"].enabled is False
    assert cfg.book["lab_pp_orb"] == [{"account": "eval1", "qty": 1}] and labcfg.limits_of(cfg, "lab_pp_orb") is not None
    assert labcfg.orphans(cfg, snap) == [] and store.get_desk("pp_orb") == disk
    assert [n["strategy"] for n in notes(cfg, "lab_unreadable")] == ["lab_pp_orb"]
    labcfg.overlay(cfg)
    assert notes(cfg) == []                                                      # said once
    f.write_text(good)
    assert labcfg.overlay(cfg)["changed"] == ["lab_pp_orb"]
    assert not labcfg.unreadable(cfg, "lab_pp_orb") and cfg.strategies["lab_pp_orb"].enabled is True


def test_a_record_file_the_desk_never_read_is_said_once_and_is_not_an_orphan():
    cfg = desk_cfg()
    (store.root() / "garbage.json").write_text("{not json")
    store.put_desk("garbage", side(book=[{"account": "eval1", "qty": 1}]))
    snap = labcfg.read_store()
    assert labcfg.apply(cfg, snap) == {"added": [], "removed": [], "changed": []}
    assert labcfg.orphans(cfg, snap) == []
    assert [n["strategy"] for n in notes(cfg, "lab_unreadable")] == ["lab_garbage"]
    labcfg.overlay(cfg)
    assert notes(cfg) == []


# ---- F: the accounts that went with a record that is gone
def test_a_record_that_is_gone_says_which_accounts_went_with_it():
    cfg = desk_cfg()
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "eval1", "qty": 1}, {"account": "main", "qty": 1}]))
    labcfg.overlay(cfg)
    store.remove("pp_orb")
    labcfg.overlay(cfg)
    assert notes(cfg, "lab_removed") == [{"strategy": "lab_pp_orb", "why": "record gone", "unbooked": ["eval1", "main"]}]


# ---- G: a sidecar the desk does not know, but whose strategy the engine still holds a round for
def test_orphans_ask_about_every_name_not_only_the_ones_the_desk_knows():
    cfg = desk_cfg()
    store.put_desk("old_one", side(book=[{"account": "eval1", "qty": 1}]))       # the record went; the desk restarted
    snap = labcfg.read_store()
    labcfg.apply(cfg, snap, reload=True)
    assert labcfg.orphans(cfg, snap, held=lambda did: did == "lab_old_one") == []
    assert labcfg.orphans(cfg, snap, held=lambda did: False) == ["old_one"] and labcfg.orphans(cfg, snap) == ["old_one"]


# =====================================================================================================================
# Fix round 3
# =====================================================================================================================
# ---- M1: an account that leaves the desk is remembered, and its rows are stripped after any re-read
def test_the_rows_of_an_account_that_left_the_desk_are_stripped_after_a_reload_and_said():
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}, {"account": "eval1", "qty": 1}, {"account": "other_pool", "qty": 1}]))
    cfg = desk_cfg()
    labcfg.overlay(cfg)
    notes(cfg)
    cfg.book["lab_pp_orb"] = [r for r in cfg.book["lab_pp_orb"] if r["account"] != "eval1"]     # the server's own strip ...
    cfg.accounts.pop("eval1")                                                    # ... and the account leaves the pool
    labcfg.note_accounts(cfg)                                                    # (config.save's hook does this)
    assert notes(cfg) == []                                                      # nothing more to strip: nothing said
    labcfg.apply(cfg, labcfg.read_store(), reload=True)                          # a re-read brings the row back from disk ...
    assert cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}, {"account": "other_pool", "qty": 1}]     # ... and it goes again
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["eval1"], "why": "account removed"}]
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb")["book"] == [{"account": "main", "qty": 1}, {"account": "other_pool", "qty": 1}]


def test_an_account_that_was_never_on_this_desk_is_not_a_removed_one():
    store.put(rec())
    store.put_desk("pp_orb", side(book=[{"account": "other_pool", "qty": 1}]))
    cfg = desk_cfg()
    for _ in range(2):
        labcfg.overlay(cfg)
        labcfg.note_accounts(cfg)
    assert cfg.book["lab_pp_orb"] == [{"account": "other_pool", "qty": 1}] and notes(cfg) == []


# ---- M7: a sidecar file that is there and does not read
def test_a_sidecar_that_is_there_and_does_not_read_freezes_like_limits_that_do_not_parse():
    store.put(rec())
    f = store.root() / "pp_orb.desk.json"
    f.write_text("{not json")
    store.put(rec("list_one"))
    (store.root() / "list_one.desk.json").write_text("[1, 2]")
    cfg = desk_cfg()
    labcfg.overlay(cfg)
    for did in ("lab_pp_orb", "lab_list_one"):
        assert labcfg.frozen(cfg, did) and labcfg.blind(cfg, did) and labcfg.limits_of(cfg, did) is None and did not in cfg.book
    assert labcfg.pending(cfg) == []
    labcfg.persist_all(cfg)
    assert f.read_text() == "{not json" and (store.root() / "list_one.desk.json").read_text() == "[1, 2]"
    want = labcfg.sidecar(cfg, "lab_pp_orb", LabLimits(**LIMITS), [])
    labcfg.commit(cfg, "lab_pp_orb", LabLimits(**LIMITS), [], want)              # he saved limits: no longer blind
    assert not labcfg.frozen(cfg, "lab_pp_orb") and not labcfg.blind(cfg, "lab_pp_orb")


# ---- M6: nothing is written for a desk that let the store go
def test_persist_all_writes_nothing_once_the_desk_let_go():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    labcfg.release_store(cfg)
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") is None


def test_a_sidecar_write_checks_the_lease_again_once_it_has_the_stores_lock(monkeypatch):
    import contextlib
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    labcfg.set_limits(cfg, "lab_pp_orb", LabLimits(**LIMITS))
    real = store.write_lock

    @contextlib.contextmanager
    def let_go_while_waiting(at=None, wait_s=None):
        labcfg.release_store(cfg)                                                # the desk shuts down while the write waits
        with real(at, wait_s):
            yield
    monkeypatch.setattr(store, "write_lock", let_go_while_waiting)
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") is None
