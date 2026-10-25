"""Build-day equity curves (1 NQ each, after costs) of the three finalists and their stack. Reads stored trades only."""
import sys, datetime as dt, numpy as np
sys.path.insert(0, '.')
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
J = json.load(open("daily_series.json")); days = J["days"]
specs = [("cl_fvg_oside_15_mid_r1_t2_gap0p1", "1  Open-side FVG", "#2a78d6"),
         ("cl_am_disp15_vwap_10to11", "2  10:00 displacement", "#eb6834"),
         ("cl_pm_first_bar_cdl_ema_15", "3  13:30 first bar", "#1baf7a")]
X = [dt.date.fromordinal(d) for d in days]
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.8), facecolor=SURF, sharey=True)
tot = np.zeros(len(days))
for name, label, col in specs:
    d = np.asarray(J[name]); tot += d
    c = np.cumsum(d) / 1000
    a1.plot(X, c, color=col, lw=2, label=label)
    a1.annotate(f"{label.split('  ')[1]}  ${c[-1]:.0f}k", (X[-1], c[-1]), xytext=(6, 0), textcoords="offset points", color=INK, va="center", fontsize=9)
ct = np.cumsum(tot) / 1000
a2.plot(X, ct, color="#2a78d6", lw=2)
a2.annotate(f"${ct[-1]:.0f}k", (X[-1], ct[-1]), xytext=(6, 0), textcoords="offset points", color=INK, va="center", fontsize=9)
for ax, title in ((a1, "Each strategy alone"), (a2, "All three on one account")):
    ax.set_facecolor(SURF); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    ax.set_xlim(X[0], X[-1] + dt.timedelta(days=260))
    ax.set_xticks([dt.date(y, m, 1) for y in (2022, 2023, 2024, 2025) for m in (1, 7)])
    ax.set_xticklabels([f"{y} {'Jan' if m == 1 else 'Jul'}" for y in (2022, 2023, 2024, 2025) for m in (1, 7)], rotation=0, fontsize=8)
a1.set_ylabel("Net, $ thousands (1 NQ each, after costs)")
a1.legend(frameon=False, loc="upper left", fontsize=9)
fig.suptitle("Build days only, 22 Sep 2021 to 30 Jun 2025. Out-of-sample not run.", x=0.01, ha="left", color=INK2, fontsize=10)
fig.tight_layout()
out = W + "/out/best_strategy_2026-10-20/equity_build_days.png"
fig.savefig(out, dpi=150, facecolor=SURF)
print(out)
