const { test } = require("node:test");
const assert = require("node:assert/strict");
const AV = require("./algo-visibility.js");

function strat(overrides) {
  return Object.assign({
    cfg: { symbol: "NQ", enabled: false },
    day_status: "idle",
    killed: false,
    accounts: [],
  }, overrides);
}

const strategiesFixture = {
  nq930: strat({ cfg: { symbol: "NQ", enabled: true }, day_status: "live" }),
  ym_test: strat({ cfg: { symbol: "YM", enabled: false }, day_status: "idle" }),
  gc_open: strat({ cfg: { symbol: "GC", enabled: true }, day_status: "idle" }),
};

test("missing preference shows all algos", () => {
  const out = AV.computeVisibility(strategiesFixture, {}, undefined);
  assert.equal(out.length, 3);
  assert.ok(out.every((a) => a.visible === true));
});

test("corrupt/garbage stored value shows all algos", () => {
  const garbageInputs = [null, "not-an-array", 42, { oops: true }, ["ok", 5, null]];
  for (const g of garbageInputs) {
    const out = AV.computeVisibility(strategiesFixture, {}, g);
    assert.ok(out.every((a) => a.visible === true), `failed for ${JSON.stringify(g)}`);
  }
});

test("a tradable algo (enabled + booked) can never be hidden", () => {
  const book = { nq930: [{ account: "lucid-funded", qty: 3 }] };
  // user tried to hide it anyway
  const out = AV.computeVisibility(strategiesFixture, book, ["nq930", "ym_test"]);
  const nq = out.find((a) => a.name === "nq930");
  assert.equal(nq.visible, true);
  assert.equal(nq.locked, true);
  assert.equal(nq.lockReason, AV.LOCK_REASON.TRADABLE);
  // ym_test is enabled=false, idle, no activity, no check -> not locked, hide sticks
  const ym = out.find((a) => a.name === "ym_test");
  assert.equal(ym.locked, false);
  assert.equal(ym.visible, false);
});

test("enabled but unbooked + idle algo is not locked and can be hidden", () => {
  const out = AV.computeVisibility(strategiesFixture, {}, ["gc_open"]);
  const gc = out.find((a) => a.name === "gc_open");
  assert.equal(gc.enabled, true);
  assert.equal(gc.booked, false);
  assert.equal(gc.locked, false);
  assert.equal(gc.visible, false);
});

test("empty book but day_status 'live' is un-hideable (book emptied mid-trade)", () => {
  const strategies = {
    nq930: strat({ cfg: { symbol: "NQ", enabled: true }, day_status: "live" }),
  };
  // the book has resolved EMPTY — e.g. "account not on this login" — while
  // the strategy is still actually holding a position today
  const out = AV.computeVisibility(strategies, {}, ["nq930"]);
  const nq = out[0];
  assert.equal(nq.booked, false);
  assert.equal(nq.locked, true);
  assert.equal(nq.lockReason, AV.LOCK_REASON.ACTIVITY);
  assert.equal(nq.visible, true);
});

test("empty book but day_status 'placed' is un-hideable", () => {
  const strategies = {
    nq930: strat({ cfg: { symbol: "NQ", enabled: true }, day_status: "placed" }),
  };
  const out = AV.computeVisibility(strategies, {}, ["nq930"]);
  assert.equal(out[0].locked, true);
  assert.equal(out[0].lockReason, AV.LOCK_REASON.ACTIVITY);
  assert.equal(out[0].visible, true);
});

test("check_it on any account run is un-hideable", () => {
  const strategies = {
    nq930: strat({
      cfg: { symbol: "NQ", enabled: false }, day_status: "done",
      accounts: [{ account: "lucid-funded", status: "done", check_it: true }],
    }),
  };
  const out = AV.computeVisibility(strategies, {}, ["nq930"]);
  assert.equal(out[0].locked, true);
  assert.equal(out[0].lockReason, AV.LOCK_REASON.CHECK);
  assert.equal(out[0].visible, true);
});

test("killed today with a still-open run (placed/live) is un-hideable", () => {
  const strategies = {
    nq930: strat({
      cfg: { symbol: "NQ", enabled: false }, day_status: "placed", killed: true,
      accounts: [{ account: "lucid-funded", status: "placed", check_it: false }],
    }),
  };
  const out = AV.computeVisibility(strategies, {}, ["nq930"]);
  assert.equal(out[0].locked, true);
  // day_status "placed" already trips ACTIVITY first in priority order
  assert.equal(out[0].visible, true);
});

test("killed today but every run is done stays hideable (no open position, no check_it)", () => {
  const strategies = {
    nq930: strat({
      cfg: { symbol: "NQ", enabled: false }, day_status: "done", killed: true,
      accounts: [{ account: "lucid-funded", status: "done", check_it: false }],
    }),
  };
  const out = AV.computeVisibility(strategies, {}, ["nq930"]);
  assert.equal(out[0].locked, false);
  assert.equal(out[0].visible, false);
});

test("'done' and 'idle' with an empty book stay hideable", () => {
  const strategies = {
    a: strat({ cfg: { symbol: "NQ", enabled: true }, day_status: "done" }),
    b: strat({ cfg: { symbol: "YM", enabled: false }, day_status: "idle" }),
  };
  const out = AV.computeVisibility(strategies, {}, ["a", "b"]);
  assert.equal(out.find((x) => x.name === "a").locked, false);
  assert.equal(out.find((x) => x.name === "a").visible, false);
  assert.equal(out.find((x) => x.name === "b").locked, false);
  assert.equal(out.find((x) => x.name === "b").visible, false);
});

test("a hidden algo whose day_status turns 'live' reappears automatically", () => {
  const hidden = ["gc_open"];
  let strategies = {
    gc_open: strat({ cfg: { symbol: "GC", enabled: true }, day_status: "idle" }),
  };
  let out = AV.computeVisibility(strategies, {}, hidden);
  assert.equal(out[0].visible, false);

  // now it fires and is placing/live today
  strategies = {
    gc_open: strat({ cfg: { symbol: "GC", enabled: true }, day_status: "live" }),
  };
  out = AV.computeVisibility(strategies, {}, hidden);
  assert.equal(out[0].locked, true);
  assert.equal(out[0].visible, true);
});

test("a hidden algo that becomes tradable (enabled + booked) reappears automatically", () => {
  const hidden = ["gc_open"];
  let out = AV.computeVisibility(strategiesFixture, {}, hidden);
  assert.equal(out.find((a) => a.name === "gc_open").visible, false);

  const book = { gc_open: [{ account: "sandbox", qty: 1 }] };
  out = AV.computeVisibility(strategiesFixture, book, hidden);
  const gc = out.find((a) => a.name === "gc_open");
  assert.equal(gc.locked, true);
  assert.equal(gc.visible, true);
});

test("withHidden adds and removes names, and refuses to add a locked one", () => {
  let list = AV.withHidden([], "gc_open", true, false);
  assert.deepEqual(list.sort(), ["gc_open"]);

  list = AV.withHidden(list, "gc_open", false, false);
  assert.deepEqual(list, []);

  // trying to hide a locked algo is a no-op
  list = AV.withHidden([], "nq930", true, true);
  assert.deepEqual(list, []);
});

test("loadHidden fails closed on a storage that throws", () => {
  const throwingStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  assert.deepEqual(AV.loadHidden(throwingStorage), []);
  assert.equal(AV.saveHidden(["x"], throwingStorage), false);
});

test("loadHidden fails closed on unparsable JSON", () => {
  const badStorage = {
    getItem() { return "{not json"; },
  };
  assert.deepEqual(AV.loadHidden(badStorage), []);
});

test("loadHidden round-trips a clean list through a working storage", () => {
  const store = {};
  const storage = {
    getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v) { store[k] = v; },
  };
  AV.saveHidden(["ym_test", "gc_open"], storage);
  assert.deepEqual(AV.loadHidden(storage).sort(), ["gc_open", "ym_test"]);
});

// An "error" day whose placement never reached the broker (the 2026-09-29 429 on
// nq930_1030): no order id on any run, and the broker shows each account flat with
// no working orders -> hideable. Anything short of that stays locked.
function failedRun(extra) {
  return Object.assign({ account: "apex053", status: "error", upper_id: null, lower_id: null,
                         up_sl_id: null, up_tp_id: null, dn_sl_id: null, dn_tp_id: null,
                         entry_fill: null, entry_qty: 0, check_it: false }, extra);
}
const FLAT = { apex053: { connected: true, open_position_count: 0, working_orders: 0 } };

function errorStrategies(run) {
  return { nq930_1030: strat({ day_status: "error", accounts: [run] }) };
}

test("an error that placed nothing, on a flat account, can be hidden", () => {
  const out = AV.computeVisibility(errorStrategies(failedRun()), {}, ["nq930_1030"], FLAT);
  assert.equal(out[0].locked, false);
  assert.equal(out[0].visible, false);
});

test("an error stays locked without the broker's view, or when it is not flat", () => {
  const s = errorStrategies(failedRun());
  assert.equal(AV.computeVisibility(s, {}, [])[0].locked, true);            // no broker view
  for (const b of [{ connected: false, open_position_count: 0, working_orders: 0 },
                   { connected: true, open_position_count: 1, working_orders: 0 },
                   { connected: true, open_position_count: 0, working_orders: 2 }]) {
    const out = AV.computeVisibility(s, {}, [], { apex053: b });
    assert.equal(out[0].locked, true);
    assert.equal(out[0].lockReason, AV.LOCK_REASON.ACTIVITY);
  }
  assert.equal(AV.computeVisibility(s, {}, [], {})[0].locked, true);         // account unknown
});

test("an error with any order id or fill stays locked", () => {
  for (const extra of [{ upper_id: "123" }, { dn_tp_id: "9" }, { entry_fill: 30000 },
                       { entry_qty: 1 }, { status: "live" }]) {
    const out = AV.computeVisibility(errorStrategies(failedRun(extra)), {}, [], FLAT);
    assert.equal(out[0].locked, true, JSON.stringify(extra));
  }
});

test("a placed or live day is never unlocked by a flat broker view", () => {
  const s = { nq930: strat({ day_status: "live", accounts: [failedRun({ status: "live" })] }) };
  assert.equal(AV.computeVisibility(s, {}, [], FLAT)[0].locked, true);
});
