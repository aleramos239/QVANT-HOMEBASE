"""Pre-build the ES tape cache (2021-09-22..2024-12-31) on idle cores so tester runs skip it.
Same TapeStore code path as the tester; writes are atomic (tmp + os.replace), so racing the
tester on a session is harmless. Pauses 09:18-09:36 ET on weekdays (desk window)."""
import datetime as dt, sys, time
from concurrent.futures import ProcessPoolExecutor
from zoneinfo import ZoneInfo
from homebase.backtest.tape import TapeStore

ET = ZoneInfo("America/New_York")

def desk_pause():
    while True:
        n = dt.datetime.now(ET)
        if n.weekday() < 5 and dt.time(9, 18) <= n.time() < dt.time(9, 36):
            time.sleep(30); continue
        return

def one(d):
    desk_pause()
    s = TapeStore()
    if s.cached("ES", d):
        return 0
    s.build("ES", d)
    return 1

if __name__ == "__main__":
    s = TapeStore()
    days = s.sessions("ES", dt.date(2021, 9, 22), dt.date(2024, 12, 31))
    t0, built = time.time(), 0
    with ProcessPoolExecutor(3) as ex:
        for i, b in enumerate(ex.map(one, days, chunksize=4)):
            built += b
            if i % 50 == 0:
                print(f"{i}/{len(days)} built={built} {time.time()-t0:.0f}s", flush=True)
    print(f"done {len(days)} sessions, built {built}, {time.time()-t0:.0f}s", flush=True)
