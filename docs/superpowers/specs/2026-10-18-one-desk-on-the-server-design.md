# One Desk on the server (the owner, 2026-10-18)

The owner: "i want them both to share and be in sync ... how am i supposed to know when i use the server or app".
Answer: there is ONE Desk, on the Chicago server (144.202.51.163). The Mac's Homebase app is its screen; the Lab
(backtests) stays on the Mac. Nothing to keep in sync by hand, and only one Desk can ever be armed.

## Before the switch (practice) -- LIVE 2026-10-18
- Mac Desk armed, trading. Server Desk disarmed, same logins, practising beside it.
- `deploy/linux/sync.sh` every 5 min (launchd `com.ramosquant.homebase-serversync`), Mac -> server: Lab strategy
  records + archive, groups, drafts, ideas, the Lab side switch, chart layouts, config (forced armed=false,
  chart trading off). The server re-reads the strategy store every 2 s; only a changed config restarts its desk.

## After the switch (one Desk)

| Port on the Mac | Is | Why |
|---|---|---|
| 8850 | the SERVER's desk, through an SSH tunnel (launchd `com.ramosquant.homebase-servertunnel`) | the Mac app's Desk tab, the chart pages' trade buttons (charts/desk.py DESK_URL), paperbook and the connector's desk tools all call 127.0.0.1:8850 -- they all reach the one Desk unchanged |
| 8852 | the Mac's own charts + Lab | backtests need the Mac's CPU and its full tick archive |
| 8849 | the Mac's helper desk: logins only, armed=false, Lab side off (no lab_desk.on), never shown | the Mac's charts and tick recorder take their live md token from a desk's token files on disk (charts/refresh.py, marketdata.py); without a desk on the Mac its charts go dark |

- The desk key: the chart service adds `homebase/.state/desk.key` to every trade call. The server's desk must hold the
  Mac's key (ensure_key keeps an existing file), so the switch copies the Mac's key to the server before it restarts.
- desklab ownership (store.py layout): the Mac writes `<name>.json` and `.archive/` (Lab promote / on-off / archive);
  the server writes `<name>/days`, `<name>/journal.jsonl`, `runner.json`, `<name>.desk.json`. sync.sh in one-Desk mode
  sends each side's files to the other, and never the config: the server owns it (arm, accounts, sizes).
- Mode switch: the file `homebase/.state/onedesk.on` on the Mac.

## The switch (owner clicks, in this order)
1. Owner: Disarm on the Mac's Desk.
2. `deploy/linux/switch.sh on root@<host>`: checks the Mac is disarmed and the server's accounts are connected,
   copies the desk key, moves the Mac desk to 8849 with Lab side off, stops the Mac's Lab runner, starts the tunnel,
   flips sync.sh to one-Desk mode. Refuses if the Mac desk is armed.
3. Owner: Arm in the Desk tab (now the server's).
Back: `switch.sh off` (owner disarms the server first) restores the Mac desk on 8850 and practice-mode sync.
