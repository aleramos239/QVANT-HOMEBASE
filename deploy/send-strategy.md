# Strategy: Lab -> Mac Desk -> server Desk

1. **Lab (Mac):** build it, run it, then *Put it on the Desk* (Promote). It lands OFF with its code frozen (sha256).
2. **Mac Desk:** pick group/accounts, switch ON to run it here. The Mac Desk is idle/shadow: the server is the live one.
3. **Send to the server (Mac terminal):**
   ```
   deploy/linux/send_strategy.py NAME          # dry run: says what would happen, writes nothing
   deploy/linux/send_strategy.py NAME --go     # send it
   ```
   It lands on the server **OFF with no account**. Then, on the server Desk: set group/accounts, limits, switch ON.
4. Code the strategy imports from `homebase/` ships by vpssync (committed main). The sender waits until the server runs main
   (`--even-if-behind` overrides).

It refuses (and changes nothing) when: the code no longer matches its hash, the server already has a *different* version
(`--replace` to overwrite, only while it is OFF with no account; the old one is kept in `<store>/.replaced/`), the server's copy is
ON or booked, it is in the server's Archive, or the server runs older code. Sending the same thing twice is a no-op.

Do not book the same strategy on both Desks (same broker accounts). `sync.sh` / `mirror.sh` are blocked on purpose: they
overwrite the live server's records, books and config (override: `HOMEBASE_OVERWRITE_SERVER=yes-overwrite-the-server`).
