"""Picklable `features=` loaders that add the `wimb` column (wide.py) to the pilot's feature table: WideFeatures = the real
table (l2sim.L2Features with one extra column), WideC2 = its C2 null (score.C2Features: wimb of a random other session at the
same time of day). wimb is non-NaN ONLY on the 09:30 usable row of each date and NaN where book_ok is False."""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np

HERE = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930"
L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
for p in (HERE, L):
    if p not in sys.path:
        sys.path.insert(0, p)
import l2data  # noqa: E402
import l2sim  # noqa: E402
import score as SC  # noqa: E402
import wide as W  # noqa: E402

_CACHE: dict = {}


def add_wimb(df, allow_holdout=False):
    em = df["et_min"].to_numpy()
    idx = np.flatnonzero(em == 570)                       # 09:30 ET usable rows (the 09:29 snapshot)
    dts = df["date"].to_numpy()[idx]
    vals, _, _ = W.wide_imb_by_date(sorted(set(dts)), allow_holdout=allow_holdout)
    col = np.full(len(df), np.nan)
    for i, d in zip(idx, dts):
        col[i] = vals[d]
    col[~df["book_ok"].to_numpy(bool)] = np.nan
    df["wimb"] = col
    return df


class WideFeatures(l2sim.L2Features):
    def _frame(self):
        key = ("wide", self.columns, self.mask, self.allow_holdout)
        if key not in _CACHE:
            base = [c for c in self.columns if c != "wimb"] + ["et_min"]
            end = dt.date(2026, 12, 31) if self.allow_holdout else l2sim.IN_SAMPLE[1]
            df = l2data.load_features(l2sim.TABLE_START, end, allow_holdout=self.allow_holdout, columns=list(dict.fromkeys(base)), mask_bad_book=self.mask)
            _CACHE[key] = l2sim.features_from_frame(add_wimb(df, self.allow_holdout), self.columns)
        return _CACHE[key]


class WideC2(SC.C2Features):
    def frame(self):
        cols = list(dict.fromkeys([c for c in self.columns if c != "wimb"] + ["globex_date", "et_min", "date"]))
        df = l2data.load_features(l2sim.TABLE_START, l2sim.IN_SAMPLE[1], columns=cols, mask_bad_book=self.mask)
        add_wimb(df)
        return SC.c2_shuffle(df, list(self.shuffle_cols), self.seed, session_col="globex_date", tod_col="et_min", min_gap=self.min_gap,
                             strata=self.STRATA[self.strata], sessions=SC.in_sample_sessions(), allow_holdout=False)
