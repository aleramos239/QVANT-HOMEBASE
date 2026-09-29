"""Desk-bridge tools: read the live trading desk (:8850) and its charts service (:8852), and run
its two safe, non-trading OPERATE calls. A `DeskMixin` (see tools.Toolbox, which inherits it) --
kept in its own module so the tester tools above stay exactly as they were.

READ tools go through DeskClient (desk_client.py, an EXACT route allowlist) or the charts
service's existing Client with a widened prefix (export routes only -- still never /api/tester/
work done by anything but the tester tools already above). `data_coverage` is the one exception:
it reads a local file (homebase/.state/tick_coverage.json) straight off disk, same as this
package's own draftstore reads/writes -- no request goes out for it.

OPERATE tools (account_reconnect, account_remove, export_start, export_status) all:
  * refuse inside the 09:10-09:35 ET weekday window -- cheaply, before any request (2026-09-29
    review: widened from 09:20, to match the desk's own server-side MCP refusal window on
    account_remove -- GONE_CHECK_QUIET in server.py -- rather than the tester tools' narrower
    "not 09:20-09:35 ET", which stays as it was: no live account is at risk there);
  * go through a client that sends the Origin header the target's write-guard wants (netguard on
    the desk, the same origin check on the charts service);
  * pass `source: "mcp"` on desk writes, so the desk's own journal (already written by these two
    routes for a UI click) adds one extra `mcp_action` line distinguishing Claude from the user.

What can NEVER be reached from here, by construction: DeskClient.ALLOWED_GET/ALLOWED_POST is a
two-and-two allowlist with no order, flatten, kill, arm-or-disarm, book or strategy-or-chart-
trading-switch route in it; the charts export client's prefix is the export routes only. No tool
here can place or cancel an order, flatten, kill, arm, disarm, book or unbook an account, touch a
strategy or chart-trading switch, or reach the charts service's own desk relay (which places
orders) -- tests/test_claude_mcp.py and test_claude_mcp_desk.py assert this structurally, not
just by review.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import paths
from .client import Client, ToolError
from .desk_client import DeskClient

ET = ZoneInfo("America/New_York")
QUIET = (dt.time(9, 10), dt.time(9, 35))          # weekdays ET: no OPERATE tool starts here
EXPORT_PREFIX = "/api/export/"
LAUNCHD_LABELS = {"desk": "com.ramosquant.homebase", "charts": "com.ramosquant.homebase-charts",
                  "ticks": "com.ramosquant.homebase-ticks"}
TICKS_LOG_TAIL = 20
JOURNAL_LIMIT_DEFAULT = 50
JOURNAL_LIMIT_MAX = 500


def _now_et() -> dt.datetime:
    return dt.datetime.now(ET)


def _in_quiet(now: dt.datetime) -> bool:
    return now.weekday() < 5 and QUIET[0] <= now.time() < QUIET[1]


def _refuse_if_quiet(now: dt.datetime) -> None:
    if _in_quiet(now):
        raise ToolError("refused: not 09:10-09:35 ET on weekdays (the 9:30 window) -- try again after 09:35")


def _usd(v):
    if v is None:
        return "—"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def _table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) if rows else "(none)"


def _kv(d) -> str:
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items()) or "(none)"


# ---------------------------------------------------------------- schemas

def _spec(name, description, props=None, required=()):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {}, "required": list(required),
                            "additionalProperties": False}}


SPECS = [
    _spec("desk_status", "The live desk's status: armed, each account (connected, broker account "
          "name, last error, reconnect cool-down, open positions, working order count), the "
          "account bookings per strategy, and each strategy's timer stage (late/wait reasons)."),
    _spec("desk_journal", "The desk's journal events for one day (default today ET), newest "
          "first, optionally filtered by event type or account.",
          {"date": {"type": "string", "description": "YYYY-MM-DD (default: today ET)."},
           "event": {"type": "string", "description": "Only this event type, e.g. broker_connected."},
           "account": {"type": "string", "description": "Only events naming this account."},
           "limit": {"type": "integer", "minimum": 1, "maximum": JOURNAL_LIMIT_MAX,
                     "default": JOURNAL_LIMIT_DEFAULT}}),
    _spec("desk_readiness", "The desk's morning readiness checks (accounts connected, power, "
          "strategies armed/assigned, the 9:30 timer gated): ready or not, and every check."),
    _spec("data_coverage", "Tick/depth archive holes per root, session and hour, from the last "
          "coverage report (homebase/.state/tick_coverage.json), and which sessions need a Massive "
          "backfill. Empty if no report has been written yet.",
          {"root": {"type": "string", "description": "Only this root, e.g. NQ (default: every root)."}}),
    _spec("services_health", "Whether the desk and charts service answer, their launchd PIDs, the "
          "nightly tick job's last log lines, and each recorder's most recent archive file time."),
    _spec("account_reconnect", "Reconnect disconnected accounts: clears their login backoff and "
          "reconciles positions, exactly like the dashboard's Reconnect button. Named account: only "
          "that one, and only if it's disconnected. No account named: every disconnected account "
          "(never a healthy one). Pass force=true to reconnect a specific account (or, with none "
          "named, every account) even if it's already connected. Refused 09:10-09:35 ET on weekdays.",
          {"account": {"type": "string", "description": "An account id (default: every "
                      "disconnected account)."},
           "force": {"type": "boolean", "description": "Reconnect even an already-connected "
                    "account (default: false -- disconnected only)."}}),
    _spec("account_remove", "Remove one account from the pool: unassigns it from every strategy, "
          "closes its connection, drops it. Refused (409) unless the account is connected with its "
          "caches seeded, its cached view shows no position in any symbol and no working order, and "
          "it is not placing, placed or live in any strategy today -- and refused 09:10-09:35 ET on "
          "weekdays (both here and, again, on the desk itself).",
          {"account": {"type": "string"}}, ["account"]),
    _spec("export_start", "Start a data export job on the charts service (candles, ticks, level 1 "
          "quotes or level 2 depth, to a CSV file) -- needs feat/data-export merged and the charts "
          "service restarted; refused 09:10-09:35 ET on weekdays and while another export runs.",
          {"root": {"type": "string", "description": "e.g. NQ."},
           "type": {"type": "string", "enum": ["candles", "ticks", "level1", "level2"]},
           "start": {"type": "string", "description": "YYYY-MM-DD"},
           "end": {"type": "string", "description": "YYYY-MM-DD"},
           "contract": {"type": "string", "description": "\"front\" (default) or a contract code."},
           "timeframe": {"type": "string", "description": "candles only, e.g. 1m, 5m, 1h."},
           "hours": {"type": "string", "enum": ["full", "rth"]},
           "tz": {"type": "string", "enum": ["et", "utc"]},
           "ts_format": {"type": "string", "enum": ["iso", "epoch"]},
           "format": {"type": "string", "enum": ["csv", "gz"]},
           "levels": {"type": "integer", "minimum": 1, "maximum": 10,
                      "description": "level2 only, default 10."}},
          ["root", "type", "start", "end"]),
    _spec("export_status", "An export job's status (queued/running/done/error/cancelled, "
          "progress, and its file once done). Refused 09:10-09:35 ET on weekdays.",
          {"id": {"type": "string", "description": "A job id from export_start."}}, ["id"]),
]


class DeskMixin:
    """Mixed into tools.Toolbox. Uses self.desk (DeskClient) and self.charts_export (Client,
    /api/export/ prefix) -- both built lazily, same pattern as tools.Toolbox.c / self._client."""

    _desk: DeskClient | None = None
    _charts_export: Client | None = None
    _tick_archive: Path = Path.home() / "futures_ticks"
    _now_et = staticmethod(_now_et)
    _launchctl = staticmethod(lambda args: subprocess.run(args, capture_output=True, text=True, timeout=5))

    @property
    def desk(self) -> DeskClient:
        if self._desk is None:
            self._desk = DeskClient()
        return self._desk

    @property
    def charts_export(self) -> Client:
        if self._charts_export is None:
            self._charts_export = Client(url=self.c.url, prefix=EXPORT_PREFIX)
        return self._charts_export

    # ---- desk_status

    def t_desk_status(self) -> str:
        st = self.desk.get("/api/status")
        lines = [f"Desk: {'ARMED' if st.get('armed') else 'disarmed'} · {st.get('et_now')}", ""]
        accts = st.get("accounts") or {}
        rows = [[aid, "yes" if a.get("connected") else "NO", a.get("account") or "—",
                 (a.get("error") or "—")[:60], f"{a.get('cooldown_s') or 0:g}s" if a.get("cooldown_s") else "—",
                 a.get("open_position_count", 0), a.get("working_orders", "—")]
                for aid, a in accts.items()]
        lines += ["Accounts:", _table(["id", "connected", "broker acct", "last error", "cooldown",
                                       "positions", "working orders"], rows), ""]
        book = st.get("book") or {}
        lines += [f"Bookings: {_kv({k: ', '.join(a.get('account', '?') for a in v) for k, v in book.items()})}", ""]
        tstat = (st.get("timer") or {}).get("strategies") or {}
        rows = [[name, t.get("stage"), t.get("late_reason") or t.get("wait_reason") or "—"]
                for name, t in tstat.items()]
        lines += ["Timer:", _table(["strategy", "stage", "late/wait reason"], rows)]
        return "\n".join(lines)

    # ---- desk_journal

    def t_desk_journal(self, date=None, event=None, account=None, limit=JOURNAL_LIMIT_DEFAULT) -> str:
        limit = max(1, min(int(limit), JOURNAL_LIMIT_MAX))
        params = {"limit": limit}
        if date:
            params["date"] = date
        if event:
            params["event"] = event
        if account:
            params["account"] = account
        r = self.desk.get("/api/journal", params=params)
        events = r.get("events") or []
        rows = [[e.get("et"), e.get("event"), _kv({k: v for k, v in e.items() if k not in ("ts", "et", "event")})]
                for e in events]
        head = f"Journal {r.get('date')}: {len(events)} of {r.get('count', len(events))} event(s), newest first"
        return head + "\n" + _table(["et", "event", "detail"], rows)

    # ---- desk_readiness

    def t_desk_readiness(self) -> str:
        r = (self.desk.get("/api/status") or {}).get("readiness") or {}
        rows = [[c.get("level"), c.get("label"), c.get("detail")] for c in r.get("checks") or []]
        head = f"Readiness: {'READY' if r.get('ready') else 'NOT READY'}"
        return head + "\n" + _table(["level", "check", "detail"], rows)

    # ---- data_coverage

    def t_data_coverage(self, root=None) -> str:
        p = paths.state_dir() / "tick_coverage.json"
        if not p.exists():
            return ("No coverage report yet (homebase/.state/tick_coverage.json is missing) -- "
                    "needs fix/tick-archive-gaps merged and a coverage run "
                    "(python -m homebase.ticks --coverage).")
        try:
            rep = json.loads(p.read_text())
        except ValueError as e:
            raise ToolError(f"tick_coverage.json is not valid JSON: {e}") from None
        by_root = rep.get("roots") or {}
        roots = [root.upper()] if root else sorted(by_root)
        s = rep.get("summary") or {}
        lines = [f"Coverage as of {rep.get('generated_at_utc')} · last {rep.get('sessions_per_root')} sessions/root · "
                 f"{s.get('complete', 0)} complete, {s.get('partial', 0)} partial "
                 f"({s.get('hole_hours', 0):g} hole-hours), {s.get('live_only', 0)} live-only, "
                 f"{s.get('missing', 0)} missing", ""]
        needs_massive = []
        for r in roots:
            entries = by_root.get(r)
            if entries is None:
                lines.append(f"{r}: no entries in the report.")
                continue
            counts = {}
            for e in entries:
                counts[e.get("status")] = counts.get(e.get("status"), 0) + 1
            lines.append(f"{r}: " + _kv(counts))
            for e in entries:
                if e.get("status") in ("partial", "missing"):
                    needs_massive.append([r, e.get("session"), e.get("status"),
                                          e.get("hole_hours", "—"), e.get("missing_ids", "—")])
        lines += ["", "Needs Massive (partial or missing sessions):",
                  _table(["root", "session", "status", "hole hours", "missing ids"], needs_massive[:100])]
        if len(needs_massive) > 100:
            lines.append(f"... and {len(needs_massive) - 100} more.")
        return "\n".join(lines)

    # ---- services_health

    def _reach(self, fn) -> dict:
        t0 = time.monotonic()
        try:
            fn()
            return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000)}
        except ToolError as e:
            return {"ok": False, "error": str(e)}

    def _launchd_pids(self) -> dict:
        try:
            r = self._launchctl(["launchctl", "list"])
        except Exception as e:  # noqa: BLE001 -- report, never crash the tool
            return {k: f"launchctl error: {e}" for k in LAUNCHD_LABELS}
        out_text = getattr(r, "stdout", "") or ""
        pids = {}
        for key, label in LAUNCHD_LABELS.items():
            pid = "not running"
            for line in out_text.splitlines():
                cols = line.split("\t")
                if len(cols) >= 3 and cols[2] == label:
                    pid = cols[0] if cols[0] != "-" else "not running"
                    break
            pids[key] = pid
        return pids

    def _recorder_latest(self) -> dict:
        base = self._tick_archive
        out = {}
        if not base.is_dir():
            return out
        year = str(self._now_et().year)
        for root_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            newest = None
            for p in (root_dir / year).glob("*.csv.gz") if (root_dir / year).is_dir() else []:
                m = p.stat().st_mtime
                if newest is None or m > newest:
                    newest = m
            if newest is not None:
                out[root_dir.name] = dt.datetime.fromtimestamp(newest, ET).strftime("%Y-%m-%d %H:%M:%S ET")
        return out

    def t_services_health(self) -> str:
        desk = self._reach(lambda: self.desk.get("/api/status"))
        charts = self._reach(lambda: self.c.get("/api/tester/strategies"))
        pids = self._launchd_pids()
        log_p = paths.state_dir() / "ticks.log"
        tail = log_p.read_text().splitlines()[-TICKS_LOG_TAIL:] if log_p.exists() else []
        recorders = self._recorder_latest()
        lines = [f"Desk (:8850): {'reachable' if desk['ok'] else 'DOWN'}"
                 + (f" ({desk['latency_ms']} ms)" if desk.get("ok") else f" -- {desk.get('error')}"),
                 f"Charts (:8852): {'reachable' if charts['ok'] else 'DOWN'}"
                 + (f" ({charts['latency_ms']} ms)" if charts.get("ok") else f" -- {charts.get('error')}"),
                 "", f"launchd PIDs: {_kv(pids)}", "",
                 f"Nightly tick job log (last {len(tail)} line(s)):"] + (tail or ["(no log yet)"]) + [
                "", "Recorders' latest archive file (this year):", _kv(recorders) if recorders else "(none found)"]
        return "\n".join(lines)

    # ---- account_reconnect / account_remove

    def t_account_reconnect(self, account=None, force=False) -> str:
        """Disconnected accounts only, by default -- a healthy one is left alone unless force=true
        (2026-09-29 review: this used to reconnect EVERYTHING, named account or not, even one that
        was already fine). Named + already connected + no force: refused outright, before any
        write. No account named: every disconnected account (or, with force, every account) --
        the desk's own endpoint takes one account at a time, so this loops."""
        _refuse_if_quiet(self._now_et())
        force = bool(force)
        accounts = (self.desk.get("/api/status") or {}).get("accounts") or {}
        if account:
            if not force and (accounts.get(account) or {}).get("connected"):
                raise ToolError(f"{account} is already connected -- pass force=true to reconnect "
                                "it anyway (account_reconnect only touches disconnected accounts "
                                "by default)")
            targets = [account]
        else:
            targets = (list(accounts) if force
                      else [aid for aid, a in accounts.items() if not a.get("connected")])
            if not targets:
                return ("Every account is already connected -- nothing to do "
                        "(pass force=true to reconnect anyway).")
        results = {}
        for aid in targets:
            r = self.desk.post("/api/accounts/reconnect", {"source": "mcp", "account": aid})
            results.update(r.get("results") or {})
        rows = [[aid, "ok" if v.get("ok") else "FAILED", v.get("mode") or v.get("error") or ""]
                for aid, v in results.items()]
        label = account or ("every account" if force else "every disconnected account")
        ok = bool(results) and all(v.get("ok") for v in results.values())
        return (f"Reconnect {label}: {'ok' if ok else 'one or more failed'}\n"
                + _table(["account", "result", "detail"], rows))

    def t_account_remove(self, account: str) -> str:
        _refuse_if_quiet(self._now_et())
        r = self.desk.post("/api/accounts/remove", {"account": account, "source": "mcp"})
        return f"Removed {r.get('removed', account)}." if r.get("ok") else f"Could not remove {account}."

    # ---- export_start / export_status

    def _export_call(self, method: str, path: str, body=None) -> dict:
        try:
            return self.charts_export.get(path) if method == "GET" else self.charts_export.post(path, body)
        except ToolError as e:
            if "404" in str(e):
                raise ToolError("the charts service does not support data export yet "
                                "(needs feat/data-export merged and the service restarted)") from None
            raise

    def t_export_start(self, root: str, type: str, start: str, end: str, contract=None,  # noqa: A002
                       timeframe=None, hours=None, tz=None, ts_format=None, format=None,  # noqa: A002
                       levels=None) -> str:
        _refuse_if_quiet(self._now_et())
        body = {"root": root, "type": type, "start": start, "end": end}
        for k, v in (("contract", contract), ("timeframe", timeframe), ("hours", hours), ("tz", tz),
                    ("ts_format", ts_format), ("format", format), ("levels", levels)):
            if v is not None:
                body[k] = v
        r = self._export_call("POST", "/api/export/start", body)
        jid = r.get("id")
        return f"Export {jid} started ({root} {type} {start}..{end}).\nNext: export_status(id={jid!r})"

    def t_export_status(self, id: str) -> str:  # noqa: A002
        _refuse_if_quiet(self._now_et())
        r = self._export_call("GET", f"/api/export/{id}")
        lines = [f"Export {id}: {r.get('status')}" + (f" ({r.get('phase')})" if r.get("phase") else "")]
        if r.get("sessions_total"):
            lines.append(f"Sessions: {r.get('sessions_done', 0)}/{r['sessions_total']} · rows {r.get('rows', 0):,}")
        if r.get("error"):
            lines.append(f"Error: {r['error']}")
        res = r.get("result")
        if res:
            lines.append(f"Done: {res.get('name')} · {res.get('rows', 0):,} rows · {res.get('bytes', 0):,} bytes "
                         f"· {res.get('path')}")
        return "\n".join(lines)
