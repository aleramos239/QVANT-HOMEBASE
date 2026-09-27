const { test } = require("node:test");
const assert = require("node:assert/strict");
const AV = require("./algo-visibility.js");

const strategiesFixture = {
  nq930: { cfg: { symbol: "NQ", enabled: true }, day_status: "live" },
  ym930: { cfg: { symbol: "YM", enabled: false }, day_status: "idle" },
  gc_open: { cfg: { symbol: "GC", enabled: true }, day_status: "idle" },
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

test("a live algo (enabled + booked) can never be hidden", () => {
  const book = { nq930: [{ account: "lucid-funded", qty: 3 }] };
  // user tried to hide it anyway
  const out = AV.computeVisibility(strategiesFixture, book, ["nq930", "ym930"]);
  const nq = out.find((a) => a.name === "nq930");
  assert.equal(nq.live, true);
  assert.equal(nq.visible, true);
  assert.equal(nq.locked, true);
  // ym930 is enabled=false, so it's not live and the hide sticks
  const ym = out.find((a) => a.name === "ym930");
  assert.equal(ym.live, false);
  assert.equal(ym.visible, false);
  assert.equal(ym.locked, false);
});

test("enabled but unbooked algo is not live and can be hidden", () => {
  const out = AV.computeVisibility(strategiesFixture, {}, ["gc_open"]);
  const gc = out.find((a) => a.name === "gc_open");
  assert.equal(gc.enabled, true);
  assert.equal(gc.booked, false);
  assert.equal(gc.live, false);
  assert.equal(gc.visible, false);
});

test("a hidden algo that becomes live reappears automatically", () => {
  const hidden = ["gc_open"];
  let out = AV.computeVisibility(strategiesFixture, {}, hidden);
  assert.equal(out.find((a) => a.name === "gc_open").visible, false);

  // now it gets booked -> enabled(true) + booked -> live
  const book = { gc_open: [{ account: "sandbox", qty: 1 }] };
  out = AV.computeVisibility(strategiesFixture, book, hidden);
  const gc = out.find((a) => a.name === "gc_open");
  assert.equal(gc.live, true);
  assert.equal(gc.visible, true);
});

test("withHidden adds and removes names, and refuses to add a live one", () => {
  let list = AV.withHidden([], "gc_open", true, false);
  assert.deepEqual(list.sort(), ["gc_open"]);

  list = AV.withHidden(list, "gc_open", false, false);
  assert.deepEqual(list, []);

  // trying to hide a live algo is a no-op
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
  AV.saveHidden(["ym930", "gc_open"], storage);
  assert.deepEqual(AV.loadHidden(storage).sort(), ["gc_open", "ym930"]);
});
