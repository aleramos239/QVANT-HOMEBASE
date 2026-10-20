"""Copy finished tick-archive day files from SRC into DST when SRC's copy is better.

The VPS runs the hourly tick job (it holds the live market-data login); the Mac pulls its day files with
deploy/linux/tickpull.sh, which rsyncs them to a staging folder and runs this. A day is copied when DST
lacks it, or SRC's is complete and DST's is not, or SRC has more ticks. Live recordings (*.live.*) are never
touched: each machine records its own. Holds the tick job's lock (homebase/.state/ticks.lock) while copying.

    python3 deploy/linux/tickmerge.py SRC DST [--lock PATH]
"""
import argparse
import fcntl
import json
import os
import shutil
import sys
from pathlib import Path


def info(sidecar: Path) -> tuple[bool, int]:
    try:
        d = json.loads(sidecar.read_text())
        return bool(d.get("complete")), int(d.get("ticks") or 0)
    except (OSError, ValueError):
        return False, -1


def better(src_json: Path, dst_json: Path) -> bool:
    if not dst_json.exists():
        return True
    (sc, sn), (dc, dn) = info(src_json), info(dst_json)
    return (sc and not dc) or (sc == dc and sn > dn)


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)          # readers see the old file or the new one, never half


def merge(src: Path, dst: Path) -> list[str]:
    done = []
    for sj in sorted(src.glob("*/*/*.json")):
        if ".live" in sj.name:
            continue
        gz = sj.with_name(sj.name[:-5] + ".csv.gz")
        rel = sj.relative_to(src)
        if gz.exists() and better(sj, dst / rel):
            put(gz, dst / gz.relative_to(src))
            put(sj, dst / rel)    # sidecar last: it says the data file is there
            done.append(str(rel))
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--lock", type=Path)
    a = ap.parse_args()
    lock = open(a.lock, "a") if a.lock else None
    if lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("tick job running, try next time")
            return 0
    done = merge(a.src, a.dst)
    print(f"copied {len(done)} day(s)" + (": " + ", ".join(done) if done else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
