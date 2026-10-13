/* Homebase Lab -- every metric of a run, from its trade list.
   Pure: no DOM, no fetch (tests/js/allmetrics.test.mjs runs it headless). lab.js draws the popup.
   A trade is {date 'YYYY-MM-DD', side, qty, net, commission, mfe_usd, mae_usd, seconds, bars, entry_ms, exit_ms}.
   Build days end 2025-06-30; unseen (test) days start 2025-07-01 -- the split is a date cut of the SAME trades, so
   showing it reads nothing new: a run that never touched the unseen days simply has an empty unseen column. */
(function () {
'use strict';

const UNSEEN_FROM = '2025-07-01';
const SCOPES = [['build', 'Build days'], ['unseen', 'Unseen days'], ['all', 'All days']];

/* [id, label, unit, hint]: unit = usd | pct | num | int | secs | date | text | ratio */
const CATS = [
  ['perf', 'Performance', [
    ['net', 'Net profit', 'usd', 'After fees'], ['net_pct', 'Net return', 'pct', 'Of the run\'s starting balance'],
    ['gross_profit', 'Gross profit', 'usd', 'Sum of winning trades'], ['gross_loss', 'Gross loss', 'usd', 'Sum of losing trades'],
    ['commission', 'Fees paid', 'cost', ''], ['profit_factor', 'Profit factor', 'num', 'Gross profit / gross loss'],
    ['expectancy', 'Average trade', 'usd', 'Expectancy per trade'], ['t_stat', 't-stat', 'num', 'Mean trade over its standard error'],
    ['trades', 'Trades', 'int', ''], ['qty_avg', 'Average size', 'num', 'Contracts per trade']]],
  ['winloss', 'Wins and losses', [
    ['wins', 'Winning trades', 'int', ''], ['losses', 'Losing trades', 'int', ''], ['flat', 'Break-even trades', 'int', ''],
    ['win_rate', 'Win rate', 'pct', ''], ['avg_win', 'Average win', 'usd', ''], ['avg_loss', 'Average loss', 'usd', ''],
    ['payoff', 'Average win : loss', 'ratio', ''], ['median_win', 'Median win', 'usd', ''], ['median_loss', 'Median loss', 'usd', ''],
    ['largest_win', 'Largest win', 'usd', ''], ['largest_loss', 'Largest loss', 'usd', ''],
    ['breakeven_wr', 'Win rate needed to break even', 'pct', 'From the average win and loss'], ['kelly', 'Kelly fraction', 'pct', 'Win rate − (1−win rate) / payoff']]],
  ['risk', 'Risk and drawdown', [
    ['max_dd', 'Max drawdown', 'usd', 'Closed trades, peak to trough'], ['max_dd_pct', 'Max drawdown %', 'pct', 'Of the peak balance'],
    ['max_runup', 'Max run-up', 'usd', 'Trough to peak'], ['recovery', 'Recovery factor', 'num', 'Net / max drawdown'],
    ['dd_days', 'Longest drawdown', 'int', 'Trading days from peak until a new peak (or the end)'],
    ['ulcer', 'Ulcer index', 'num', 'Depth and length of drawdowns, in % of the peak'],
    ['avg_mae', 'Average worst point (MAE)', 'cost', 'How far a trade went against you'], ['avg_mfe', 'Average best point (MFE)', 'cost', 'How far a trade went for you'],
    ['worst_mae', 'Worst MAE', 'cost', ''], ['best_mfe', 'Best MFE', 'cost', ''],
    ['sd_trade', 'Std deviation of a trade', 'usd', ''], ['sd_day', 'Std deviation of a day', 'usd', '']]],
  ['ratios', 'Risk-adjusted', [
    ['sharpe', 'Sharpe', 'num', 'Traded days, annualised x√252'], ['sortino', 'Sortino', 'num', 'Downside deviation only'],
    ['calmar', 'Return / drawdown', 'num', 'Net / max drawdown'], ['skew', 'Skew of trades', 'num', 'Negative = a long tail of losses'],
    ['pl_ratio_day', 'Best day / worst day', 'ratio', '']]],
  ['streaks', 'Streaks', [
    ['max_win_streak', 'Longest winning streak', 'int', ''], ['max_loss_streak', 'Longest losing streak', 'int', ''],
    ['avg_win_streak', 'Average winning streak', 'num', ''], ['avg_loss_streak', 'Average losing streak', 'num', ''],
    ['cur_streak', 'Streak at the end', 'text', '']]],
  ['time', 'Time in the market', [
    ['avg_secs', 'Average time in trade', 'secs', ''], ['avg_secs_win', 'Average time, winners', 'secs', ''], ['avg_secs_loss', 'Average time, losers', 'secs', ''],
    ['avg_bars', 'Average bars in trade', 'num', ''], ['first', 'First trade', 'date', ''], ['last', 'Last trade', 'date', '']]],
  ['days', 'Days', [
    ['days', 'Days traded', 'int', ''], ['trades_day', 'Trades a day', 'num', 'Over traded days'], ['win_days', 'Winning days', 'int', ''],
    ['loss_days', 'Losing days', 'int', ''], ['day_wr', 'Winning-day rate', 'pct', ''], ['avg_day', 'Average day', 'usd', ''],
    ['best_day', 'Best day', 'usd', ''], ['worst_day', 'Worst day', 'usd', '']]],
  ['months', 'Months', [
    ['months', 'Months traded', 'int', ''], ['win_months', 'Profitable months', 'int', ''], ['month_wr', 'Profitable-month rate', 'pct', ''],
    ['avg_month', 'Average month', 'usd', ''], ['best_month', 'Best month', 'usd', ''], ['worst_month', 'Worst month', 'usd', ''],
    ['month_trades', 'Trades a month', 'num', '']]],
  ['sides', 'Long and short', [
    ['long_n', 'Long trades', 'int', ''], ['long_net', 'Long net', 'usd', ''], ['long_wr', 'Long win rate', 'pct', ''], ['long_pf', 'Long profit factor', 'num', ''],
    ['short_n', 'Short trades', 'int', ''], ['short_net', 'Short net', 'usd', ''], ['short_wr', 'Short win rate', 'pct', ''], ['short_pf', 'Short profit factor', 'num', '']]],
  ['costs', 'Costs', [
    ['fee_trade', 'Fee per trade', 'cost', ''], ['fee_share', 'Fees as a share of gross profit', 'pct', ''], ['net_gross', 'Net of fees / gross', 'pct', '']]],
];
const ALL_IDS = CATS.flatMap(([, , rows]) => rows.map((r) => r[0]));

const sum = (a) => a.reduce((s, x) => s + x, 0);
const mean = (a) => (a.length ? sum(a) / a.length : null);
const sd = (a) => { if (a.length < 2) return null; const m = mean(a); return Math.sqrt(sum(a.map((x) => (x - m) ** 2)) / (a.length - 1)); };
const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
const ratio = (a, b) => (b ? a / b : null);

function groupBy(trades, f) { const m = new Map(); for (const t of trades) { const k = f(t); (m.get(k) || m.set(k, []).get(k)).push(t); } return m; }

function streaks(nets) {
  const wins = [], losses = [];
  let cur = 0;
  for (const n of nets) {
    const s = n > 0 ? 1 : n < 0 ? -1 : 0;
    if (s !== 0 && Math.sign(cur) === s) cur += s;
    else { if (cur > 0) wins.push(cur); else if (cur < 0) losses.push(-cur); cur = s; }
  }
  const tail = cur;
  if (cur > 0) wins.push(cur); else if (cur < 0) losses.push(-cur);
  return { wins, losses, tail };
}

function sidePart(ts, pre, out) {
  const w = ts.filter((t) => t.net > 0), l = ts.filter((t) => t.net < 0);
  out[`${pre}_n`] = ts.length; out[`${pre}_net`] = ts.length ? sum(ts.map((t) => t.net)) : null;
  out[`${pre}_wr`] = ts.length ? w.length / ts.length * 100 : null;
  out[`${pre}_pf`] = l.length ? sum(w.map((t) => t.net)) / -sum(l.map((t) => t.net)) : (w.length ? Infinity : null);
}

/* All metric values for a list of trades (already sorted by exit). capital: the run's starting balance. */
function compute(trades, capital) {
  const o = {}, n = trades.length;
  if (!n) { for (const id of ALL_IDS) o[id] = null; o.trades = 0; return o; }
  const nets = trades.map((t) => t.net), win = trades.filter((t) => t.net > 0), los = trades.filter((t) => t.net < 0);
  const gp = sum(win.map((t) => t.net)), gl = sum(los.map((t) => t.net)), fees = sum(trades.map((t) => t.commission || 0));
  const net = sum(nets);
  o.net = net; o.net_pct = capital ? net / capital * 100 : null; o.gross_profit = gp; o.gross_loss = gl; o.commission = fees;
  o.profit_factor = gl ? gp / -gl : (gp ? Infinity : null);
  o.expectancy = net / n; o.t_stat = sd(nets) ? mean(nets) / (sd(nets) / Math.sqrt(n)) : null;
  o.trades = n; o.qty_avg = mean(trades.map((t) => t.qty || 0));
  o.wins = win.length; o.losses = los.length; o.flat = n - win.length - los.length; o.win_rate = win.length / n * 100;
  o.avg_win = win.length ? gp / win.length : null; o.avg_loss = los.length ? gl / los.length : null;
  o.payoff = o.avg_win != null && o.avg_loss ? o.avg_win / -o.avg_loss : null;
  o.median_win = median(win.map((t) => t.net)); o.median_loss = median(los.map((t) => t.net));
  o.largest_win = win.length ? Math.max(...win.map((t) => t.net)) : null; o.largest_loss = los.length ? Math.min(...los.map((t) => t.net)) : null;
  o.breakeven_wr = o.payoff ? 100 / (1 + o.payoff) : null;
  o.kelly = o.payoff ? (o.win_rate / 100 - (1 - o.win_rate / 100) / o.payoff) * 100 : null;
  // closed-trade equity path
  let eq = capital || 0, peak = eq, dd = 0, ddPct = 0, trough = eq, runup = 0, ulc = 0;
  const dayOf = trades.map((t) => t.date), dates = [...new Set(dayOf)];
  const dayNet = new Map(); for (const t of trades) dayNet.set(t.date, (dayNet.get(t.date) || 0) + t.net);
  let ddStart = 0, longest = 0, di = 0;
  const dayIdx = new Map(dates.map((d, i) => [d, i]));
  for (const t of trades) {
    eq += t.net;
    if (eq > peak) { peak = eq; longest = Math.max(longest, dayIdx.get(t.date) - ddStart); ddStart = dayIdx.get(t.date); trough = eq; }
    trough = Math.min(trough, eq); runup = Math.max(runup, eq - trough);
    dd = Math.min(dd, eq - peak); if (peak > 0) { const p = (eq - peak) / peak * 100; ddPct = Math.min(ddPct, p); ulc += p * p; }
    di += 1;
  }
  longest = Math.max(longest, dates.length - 1 - ddStart);
  o.max_dd = dd; o.max_dd_pct = ddPct; o.max_runup = runup; o.recovery = dd ? net / -dd : null; o.dd_days = longest;
  o.ulcer = Math.sqrt(ulc / n);
  o.avg_mae = mean(trades.map((t) => Math.abs(t.mae_usd || 0))); o.avg_mfe = mean(trades.map((t) => t.mfe_usd || 0));
  o.worst_mae = Math.max(...trades.map((t) => Math.abs(t.mae_usd || 0))); o.best_mfe = Math.max(...trades.map((t) => t.mfe_usd || 0));
  o.sd_trade = sd(nets);
  const dv = dates.map((d) => dayNet.get(d));
  o.sd_day = sd(dv);
  const dm = mean(dv), dsd = sd(dv), down = Math.sqrt(sum(dv.map((x) => Math.min(x, 0) ** 2)) / dv.length);
  o.sharpe = dsd ? dm / dsd * Math.sqrt(252) : null; o.sortino = down ? dm / down * Math.sqrt(252) : null;
  o.calmar = o.recovery;
  const m3 = nets.length > 2 && o.sd_trade ? sum(nets.map((x) => (x - mean(nets)) ** 3)) / n / o.sd_trade ** 3 : null;
  o.skew = m3;
  const bestDay = Math.max(...dv), worstDay = Math.min(...dv);
  o.best_day = bestDay; o.worst_day = worstDay; o.pl_ratio_day = worstDay < 0 ? bestDay / -worstDay : null;
  const st = streaks(nets);
  o.max_win_streak = st.wins.length ? Math.max(...st.wins) : 0; o.max_loss_streak = st.losses.length ? Math.max(...st.losses) : 0;
  o.avg_win_streak = mean(st.wins); o.avg_loss_streak = mean(st.losses);
  o.cur_streak = st.tail > 0 ? `${st.tail} win${st.tail === 1 ? '' : 's'}` : st.tail < 0 ? `${-st.tail} loss${st.tail === -1 ? '' : 'es'}` : 'flat';
  o.avg_secs = mean(trades.map((t) => t.seconds || 0)); o.avg_secs_win = mean(win.map((t) => t.seconds || 0)); o.avg_secs_loss = mean(los.map((t) => t.seconds || 0));
  o.avg_bars = mean(trades.map((t) => t.bars || 0));
  o.first = dates[0]; o.last = dates[dates.length - 1];
  o.days = dates.length; o.trades_day = n / dates.length; o.win_days = dv.filter((x) => x > 0).length; o.loss_days = dv.filter((x) => x < 0).length;
  o.day_wr = o.win_days / dates.length * 100; o.avg_day = dm;
  const mo = groupBy(trades, (t) => t.date.slice(0, 7)), mv = [...mo.values()].map((g) => sum(g.map((t) => t.net)));
  o.months = mv.length; o.win_months = mv.filter((x) => x > 0).length; o.month_wr = o.win_months / mv.length * 100;
  o.avg_month = mean(mv); o.best_month = Math.max(...mv); o.worst_month = Math.min(...mv); o.month_trades = n / mv.length;
  sidePart(trades.filter((t) => t.side === 'long'), 'long', o); sidePart(trades.filter((t) => t.side === 'short'), 'short', o);
  o.fee_trade = fees / n; o.fee_share = gp ? fees / gp * 100 : null; o.net_gross = gp + gl ? net / (gp + gl + fees) * 100 : null;
  return o;
}

/* The trade list cut to a scope ('build' | 'unseen' | 'all'), a year ('' = every year) and a side ('' = both). */
function pick(trades, scope, year, side) {
  return trades.filter((t) => {
    if (scope === 'build' && t.date >= UNSEEN_FROM) return false;
    if (scope === 'unseen' && t.date < UNSEEN_FROM) return false;
    if (year && t.date.slice(0, 4) !== year) return false;
    return !side || t.side === side;
  });
}
const years = (trades) => [...new Set(trades.map((t) => t.date.slice(0, 4)))].sort();

/* One row per calendar year (the year's own trades, whichever scope they fall in). */
function yearly(trades, capital) {
  return years(trades).map((y) => ({ year: y, unseen: y >= UNSEEN_FROM.slice(0, 4), ...compute(trades.filter((t) => t.date.slice(0, 4) === y), capital) }));
}

const fmt = {
  usd: (v) => (v == null ? '—' : `${v < 0 ? '−' : v > 0 ? '+' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`),
  cost: (v) => (v == null ? '—' : `$${Math.abs(Math.round(v)).toLocaleString('en-US')}`),
  pct: (v) => (v == null ? '—' : `${v.toFixed(1)}%`),
  num: (v) => (v == null ? '—' : v === Infinity ? '∞' : v.toFixed(2)),
  int: (v) => (v == null ? '—' : Math.round(v).toLocaleString('en-US')),
  ratio: (v) => (v == null ? '—' : v === Infinity ? '1 : ∞' : `1 : ${(1 / v).toFixed(2)}`.replace(/^1 : /, v >= 1 ? '' : '1 : ')),
  secs: (v) => { if (v == null) return '—'; if (v < 90) return `${Math.round(v)} s`; if (v < 5400) return `${(v / 60).toFixed(1)} min`; return `${(v / 3600).toFixed(1)} h`; },
  date: (v) => v || '—',
  text: (v) => v || '—',
};
// payoff reads "1.8 : 1" (win : loss); pl_ratio_day the same
fmt.ratio = (v) => (v == null ? '—' : v === Infinity ? '∞' : `${v.toFixed(2)} : 1`);
const format = (unit, v) => (fmt[unit] || fmt.num)(v);

const api = { UNSEEN_FROM, SCOPES, CATS, ALL_IDS, compute, pick, years, yearly, format };
if (typeof window !== 'undefined') window.HBAllMetrics = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
