"""Step B (B1): a promoted Lab strategy as a desk strategy -- its id, its limits, the in-memory overlay on the desk's
config and the sidecar the desk writes. The store is the conftest's temp folder (HOMEBASE_DESKLAB_ROOT): never the real one."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict

import pytest

from homebase import labcfg
from homebase.config import AccountCfg, AppCfg, StrategyCfg
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
    assert cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}]             # known accounts, a size above 0, one row each
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(**{**LIMITS, "max_risk_usd": 300.0})
    assert cfg.strategies["lab_pp_orb"].accept_until_et == "11:00"
    labcfg.persist_all(cfg)                                                      # what was left out leaves the file too
    assert store.get_desk("pp_orb")["book"] == [{"account": "main", "qty": 1}]


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
    cfg.book["lab_pp_orb"].append({"account": "ghost", "qty": 1})                # an account that is not on the desk
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}
    assert cfg.book["lab_pp_orb"] == [{"account": "eval1", "qty": 3}]
    assert sorted(notes(cfg, "lab_unbooked"), key=lambda n: n["why"]) == [
        {"strategy": "lab_pp_orb", "accounts": ["main"], "why": "above the size cap"},
        {"strategy": "lab_pp_orb", "accounts": ["ghost"], "why": "account not on the desk"}]
    labcfg.set_limits(cfg, "lab_pp_orb", None)                                   # limits gone, rows still there
    labcfg.overlay(cfg)
    assert "lab_pp_orb" not in cfg.book
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_pp_orb", "accounts": ["eval1"], "why": "no limits"}]


# ---- item 8: a book the desk drops on its own is said
def test_a_book_dropped_for_another_promotion_or_a_missing_account_is_said():
    cfg = desk_cfg()
    store.put(rec(promoted="2026-10-10T08:00:00+00:00"))
    store.put_desk("pp_orb", side(book=[{"account": "main", "qty": 1}, {"account": "eval1", "qty": 1}]))
    store.put(rec("other_one"))
    store.put_desk("other_one", side(book=[{"account": "main", "qty": 1}, {"account": "left_the_pool", "qty": 1}]))
    labcfg.overlay(cfg)
    assert sorted(notes(cfg, "lab_unbooked"), key=lambda n: n["strategy"]) == [
        {"strategy": "lab_other_one", "accounts": ["left_the_pool"], "why": "account not on the desk"},
        {"strategy": "lab_pp_orb", "accounts": ["main", "eval1"], "why": "promoted again"}]
    store.put(rec("other_one", promoted="2026-10-11T08:00:00+00:00"))            # promoted again while the desk runs
    labcfg.overlay(cfg)
    assert notes(cfg, "lab_unbooked") == [{"strategy": "lab_other_one", "accounts": ["main"], "why": "promoted again"}]
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
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2
    labcfg.release_store(a)                                                      # the first desk ends
    assert not labcfg.owns(a)
    assert labcfg.take_store(b) is False                                         # decided once: b stays read-only
    assert labcfg.take_store(c) is True                                          # a desk that starts now takes it
    labcfg.release_store(c)
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
    assert "lab_pp_orb" in second.strategies and "lab_pp_orb" not in second.book   # it sees the strategy, not the account
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
    (store.root() / "unreadable.json").write_text("{not json")                  # a record file that does not read
    store.put_desk("unreadable", side())
    store.put(rec("no_market", root=None))                                       # a record the desk cannot use is still there
    store.put_desk("no_market", side())
    assert labcfg.orphans(cfg, labcfg.read_store()) == ["kept_one", "old_one", "unreadable"]


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
