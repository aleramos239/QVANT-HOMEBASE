"""The indicator catalog (JS) and the study factory (Python) agree: every wire key the catalog can send, at its defaults and
at the edges of every setting, is a key `studies.make()` accepts, with and without a timeframe (`@3600`). The `tv_*` entries
also match the Python spec (`studies_tv.PARAMS` + `studies_tv2.PARAMS`) one for one: default, range, words. Skipped where Node
is not installed."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from homebase.charts import studies
from homebase.charts.studies_tv import PARAMS as TV1
from homebase.charts.studies_tv2 import PARAMS as TV2

CATALOG_JS = Path(__file__).parent.parent / "homebase" / "static" / "charts" / "catalog.js"
TV = {**TV1, **TV2}
NOT_A_STUDY = {"profile"}   # the hub builds the volume profile itself (hub.py), make() never sees it

# Every catalog entry, asked for its wire key(s) with: its defaults; each number at its min and at its max; each word;
# each switch flipped; all numbers at min; all at max; and, for a timeframe-capable entry, every one of those with tf 3600.
_DUMP_JS = r"""
const C = require(process.argv[1]);
const out = {};
for (const d of C.CATALOG) {
  const ps = (d.params || []).filter((p) => p.key !== 'tf');
  const variants = [{}];
  for (const p of ps) {
    if (p.type === 'int' || p.type === 'num') variants.push({ [p.key]: p.min }, { [p.key]: p.max });
    else if (p.type === 'choice') for (const [v] of p.choices) variants.push({ [p.key]: v });
    else if (p.type === 'bool') variants.push({ [p.key]: !p.def });
  }
  const num = ps.filter((p) => p.type === 'int' || p.type === 'num');
  if (num.length > 1) {
    variants.push(Object.fromEntries(num.map((p) => [p.key, p.min])), Object.fromEntries(num.map((p) => [p.key, p.max])));
  }
  const htf = C.HTF_IDS.includes(d.id);
  const keys = new Set();
  for (const v of variants) for (const tf of htf ? ['0', '3600'] : ['0']) {
    for (const k of C.serverKeys([C.instance(d.id, { ...v, tf })])) keys.add(k);
  }
  out[d.id] = { htf, keys: [...keys] };
}
const tv = {};
for (const d of C.CATALOG.filter((x) => x.id.startsWith('tv_'))) tv[d.id.slice(3)] = d.params.filter((p) => p.key !== 'tf');
process.stdout.write(JSON.stringify({ ids: out, tv }));
"""


def _dump() -> dict:
    r = subprocess.run(["node", "-e", _DUMP_JS, str(CATALOG_JS)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


DUMP = _dump() if shutil.which("node") else {"ids": {}, "tv": {}}
NO_NODE = [pytest.param(None, marks=pytest.mark.skip(reason="node is not installed"))]


@pytest.mark.parametrize("cid", sorted(DUMP["ids"]) or NO_NODE)
def test_every_key_the_catalog_can_send_is_one_the_server_accepts(cid):
    entry = DUMP["ids"][cid]
    bad = []
    for key in (k for k in entry["keys"] if k not in NOT_A_STUDY):
        try:
            studies.make(key)
        except Exception as e:  # noqa: BLE001 -- any raise is the finding; the key goes in the message
            bad.append(f"{key!r}: {e}")
    assert not bad, f"{cid}: " + "; ".join(bad)


@pytest.mark.parametrize("cid", sorted(i for i, e in DUMP["ids"].items() if e["htf"]) or NO_NODE)
def test_a_timeframe_entry_sends_the_at_seconds_variant(cid):
    keys = DUMP["ids"][cid]["keys"]
    assert any(k.endswith("@3600") for k in keys), f"{cid}: no @3600 key among {keys[:4]}"
    for k in (k for k in keys if k.endswith("@3600")):
        assert studies.make(k) is not None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_catalog_has_one_tv_entry_per_python_study():
    assert set(DUMP["tv"]) == set(TV), (set(DUMP["tv"]) ^ set(TV))
    assert len(TV) == 90


@pytest.mark.parametrize("name", sorted(DUMP["tv"]) or NO_NODE)
def test_a_tv_entry_matches_its_python_spec(name):
    """Same arguments in the same order, same default, same range (an int default is a whole-number setting), same words."""
    spec = TV[name][1]
    params = DUMP["tv"][name]
    assert len(params) == len(spec), f"tv_{name}: {len(params)} settings in the catalog, {len(spec)} in the server"
    for i, (q, s) in enumerate(zip(params, spec, strict=True)):
        where = f"tv_{name} setting {i + 1} ({q['key']})"
        if len(s) == 2:
            default, words = s
            assert q["type"] == "choice", where
            assert q["def"] == default, f"{where}: default {q['def']!r} vs {default!r}"
            assert sorted(v for v, _ in q["choices"]) == sorted(words), f"{where}: words"
        else:
            default, lo, hi = s
            assert q["type"] == ("int" if isinstance(default, int) else "num"), f"{where}: type {q['type']} for default {default!r}"
            assert (q["def"], q["min"], q["max"]) == (default, lo, hi), f"{where}: {(q['def'], q['min'], q['max'])} vs {(default, lo, hi)}"


# Names make() accepts that no catalog entry sends, on purpose (none today; add one WITH a reason).
SERVER_ONLY: set[str] = set()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_every_house_study_the_server_makes_has_a_catalog_entry():
    """The reverse of the check above: a TA / flow / registry study with no catalog entry can never be drawn from the picker."""
    sent = {k.partition("@")[0].split(":")[0] for e in DUMP["ids"].values() for k in e["keys"]}
    house = {*studies.TA_NAMES, *studies.FLOW_NAMES, *studies.REGISTRY}
    missing = house - sent - SERVER_ONLY
    assert not missing, f"server studies with no catalog entry: {sorted(missing)}"
