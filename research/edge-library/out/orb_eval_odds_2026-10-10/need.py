# Account maths only: what win rate does a one-trade-a-day strategy need to pass LucidPro 50K (target 3000, EOD trail 2000,
# lock +100 at +2100) within 30 days more than half the time, after the "live is worse" haircut (win rate -5 pts, winners -15 %)?
import numpy as np
rng = np.random.default_rng(1)
def passp(p, R, L, days=30, n=20000, hair=True, freq=1.0):
    pw = p - 0.05 if hair else p
    win = R * L * (0.85 if hair else 1.0)
    trade = rng.random((n, days)) < freq
    w = rng.random((n, days)) < pw
    pnl = np.where(trade, np.where(w, win, -L), 0.0)
    profit = np.zeros(n); peak = np.zeros(n); floor = np.full(n, -2000.0); live = np.ones(n, bool); out = np.zeros(n, bool)
    for d in range(days):
        # open loss: a loser reaches -L intraday; treat a winner's open loss as 0.5 L
        o = np.where(trade[:, d], np.where(w[:, d], 0.5 * L, L), 0)
        hit = live & (profit - o <= floor)
        go = live & ~hit
        profit = np.where(go, profit + pnl[:, d], profit)
        bust = go & (profit <= floor); ok = go & ~bust
        up = ok & (profit > peak); peak = np.where(up, profit, peak)
        floor = np.where(up, np.where(peak >= 2100, 100.0, peak - 2000), floor)
        won = ok & (profit >= 3000); out |= won; live = ok & ~won
    return out.mean()
for R in (0.5, 1, 2, 3):
    print(f"\nRR {R}: rows = raw win rate, cols = best over risk a day; (haircut) [no haircut]")
    be = 1 / (1 + R)
    for p in np.arange(be - 0.02, be + 0.22, 0.03):
        best = max((passp(p, R, L), L) for L in (150, 250, 400, 600, 900, 1300, 1900))
        bestn = max((passp(p, R, L, hair=False), L) for L in (150, 250, 400, 600, 900, 1300, 1900))
        ev = p * R - (1 - p)
        print(f"  win {p:.2f} (EV {ev:+.2f}R)  pass {best[0]:.2f} at ${best[1]} risk   [raw {bestn[0]:.2f} at ${bestn[1]}]")
