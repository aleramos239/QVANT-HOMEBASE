"""CHECK-year (2025) data for the engine: ES / GC session tapes (engine/cache/tape, the tester's own TapeStore code), the NQ
daily-bar file of the CHECK switch (cache/daily_NQ_check.json) and the 2025 evening ATR30 files (cache/eve_atr30_<root>_check.json).
Everything goes through l2sim's CHECK switch (allow_check=True): 2025-01-01..2025-12-31 only, a 2026 date raises HoldoutSealed.
Restartable: a session that already has a tape / an ATR value is skipped.
  python out/check2025/build_data.py tapes <ROOT> [workers]      python out/check2025/build_data.py caches [workers]"""
import json
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402

if __name__ == "__main__":
    what = sys.argv[1]
    t0 = time.monotonic()
    if what == "tapes":
        root, workers = sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2
        print(root, S.build_tapes(root, S.CHECK[0], S.CHECK[1], workers=workers, allow_check=True), f"{time.monotonic() - t0:.0f} s", flush=True)
    elif what == "caches":
        workers = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        p = S.build_daily("NQ", S.IN_SAMPLE[0], S.CHECK[1], workers=workers, allow_holdout=S.ALLOW_CHECK)
        rows = json.loads(p.read_text())["rows"]
        print("daily", p.name, len(rows), rows[0]["date"], rows[-1]["date"], f"{time.monotonic() - t0:.0f} s", flush=True)
        for root in ("NQ", "ES", "GC"):
            a = S.load_eve_atr(root, workers=workers, allow_holdout=S.ALLOW_CHECK)
            y = {k: v for k, v in a.items() if k >= "2025"}
            print("eve_atr", root, "2025 dates", len(y), "none", sum(v is None for v in y.values()), "max date", max(a), f"{time.monotonic() - t0:.0f} s", flush=True)
