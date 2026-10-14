# Mac mini: same app as the laptop

Code is shared through GitHub `main`. Laptop pushes, the mini pulls itself.

## One time, on the mini

```bash
git clone https://github.com/aleramos239/QVANT-HOMEBASE.git ~/ramos-quant-homebase
cd ~/ramos-quant-homebase
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./deploy/install.sh              # starts desk, charts, ticks, pipeline, lab runner
./deploy/autopull.sh install     # mini only: pulls main every 5 min
```

Then copy what git does not carry (laptop -> mini, run on the laptop):

```bash
# Lab strategy drafts (1 GB)
rsync -a ~/.homebase/ideas/ MINI:~/.homebase/ideas/
# market data / tape cache (big, optional: the mini can rebuild)
rsync -a ~/ramos-quant-homebase/homebase/.state/ MINI:~/ramos-quant-homebase/homebase/.state/
```

Accounts and logins (`homebase/config.json`) are NOT copied. Add the accounts on the mini
in the app. Each Mac keeps its own.

## Daily use

- Change the app on the laptop, `git push`. Within 5 minutes the mini has it.
- The mini restarts desk + charts only when: app code changed, every account is flat with no
  working orders, it is not 09:10-09:35 ET, and no tester/pipeline job is running. Otherwise it
  waits and tries again. Log: `homebase/.state/autopull.log`.
- A local edit on the mini that blocks the pull is left alone and logged. Never edit code on
  the mini; edit on the laptop.

## One rule

Run the live desk on real accounts on ONE Mac only. Two desks on one account double the orders.
On the other Mac leave the accounts disarmed (research only).

## Turn it off

```bash
./deploy/autopull.sh remove
```
