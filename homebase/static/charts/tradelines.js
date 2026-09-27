/* Homebase Charts — HBTradeLines: trading on the chart itself, one overlay per chart (rebuilt with it,
   like every host.overlays() entry):
     - the Buy/Sell block under the legend, bid/ask "as of last trade" (ruling S10);
     - position / order / SL / TP lines (native price lines) with DOM chips that carry their text and a ×
       (ruling S8), draggable by the chip's text (order/SL/TP only — positions are not draggable: ruling S11);
     - the execution markers, through cell.setExtraMarkers('fills', …) (ruling S22).
   Trading is per chart (2026-09-27 plan, Task 2): the block, the chart's account chips, and draggable / × lines
   exist only while THIS chart's Trading can trade, and only for this chart's accounts; every other line (every
   account's, on a chart with Trading off) is view only: no drag, no ×.
   The chart's algo (2026-09-27 plan, Task 3), only while the chart's config carries one: a legend badge (bot icon,
   name, state pill, today's P&L, a red Kill -- offered whatever the Trading switch says), the bot's working orders
   as read-only "BOT …" lines (no drag, no ×), its fills today and its real past runs (HBDeskClient.botHistory) as
   markers through cell.setExtraMarkers('bots', …), each with a tooltip on hover.
   Every action that changes an order goes through HBTradeUI's confirm policy and send path — this file never
   calls HBDeskClient.send directly. Browser only; the logic (modes, lines, dollars, markers) lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;

/* A primitive that draws nothing: Lightweight Charts calls updateAllViews() before every redraw of the price
   pane (scroll, zoom, autoscale, resize), so the DOM chips follow their lines exactly. */
class Hook {
  constructor(fn) { this.fn = fn; this.raf = 0; }
  updateAllViews() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.fn(); }); }
  paneViews() { return []; }
  detached() { cancelAnimationFrame(this.raf); this.raf = 0; }
}

class Overlay {
  constructor(cell, page) {
    this.cell = cell;
    this.page = page;
    this.root = cell.shown.root;
    this.items = new Map();   // key -> {g, line, chip}
    this.dragging = null;     // the key mid-drag, or null
    this.endDrag = null;      // set by startDrag; cancels a drag in progress (destroy mid-drag)
    this.fillIds = null;      // last JSON.stringify of the fill marker ids sent to setExtraMarkers
    this.dead = false;        // review M2: set in destroy(); render() (and any callback still holding this
                               // overlay, e.g. a cancelled drag's onCancel) becomes a no-op once true, so a
                               // destroyed overlay can never create an orphan price line on the cell's NEW chart

    this.block = document.createElement('div');
    this.block.className = 'lg-trade';
    this.block.hidden = true;
    this.sellBtn = document.createElement('button');
    this.sellBtn.type = 'button'; this.sellBtn.className = 'tr-sell';
    this.sellPx = document.createElement('span'); this.sellPx.className = 'tr-px';
    this.sellBtn.append(this.sellPx, mk('span', 'tr-lbl', 'SELL'));
    this.mid = document.createElement('div'); this.mid.className = 'tr-mid';
    this.qty = document.createElement('input');
    this.qty.type = 'number'; this.qty.min = '1'; this.qty.step = '1'; this.qty.setAttribute('aria-label', 'Quantity');
    this.qty.className = 'tr-qty';
    this.spread = document.createElement('span'); this.spread.className = 'tr-spread';
    this.mid.append(this.qty, this.spread);
    this.buyBtn = document.createElement('button');
    this.buyBtn.type = 'button'; this.buyBtn.className = 'tr-buy';
    this.buyPx = document.createElement('span'); this.buyPx.className = 'tr-px';
    this.buyBtn.append(this.buyPx, mk('span', 'tr-lbl', 'BUY'));
    this.block.append(this.sellBtn, this.mid, this.buyBtn);
    this.sellBtn.onclick = () => this.trade('Sell');
    this.buyBtn.onclick = () => this.trade('Buy');
    this.qty.onchange = () => {
      const n = Math.round(Number(this.qty.value));
      window.HBDeskClient.setPrefs({ qty: Number.isFinite(n) ? n : window.HBDeskClient.prefs.qty });
    };
    cell.el.querySelector('.lg-tradeslot').appendChild(this.block);
    this.accts = mk('span', 'tr-accts');   // the chart's accounts, "…047 DEMO" (shown while its Trading is on)
    this.accts.hidden = true;
    this.acctsKey = null;
    cell.el.querySelector('.lg-tradeslot').appendChild(this.accts);

    this.layer = mk('div', 'tl-layer');
    cell.el.appendChild(this.layer);

    // the chart's algo badge (Task 3): its own legend row under the OHLC values, above the Buy/Sell slot, so the
    // title keeps its width in a small grid cell (fix round 1)
    this.badges = mk('div', 'lg-bots');
    this.badges.hidden = true;
    cell.el.querySelector('.lg-tradeslot').before(this.badges);
    this.bb = {
      ic: mk('span', 'icw bb-ic'), name: mk('span', 'bb-name'), pill: mk('span', 'bb-pill'), pnl: mk('span', 'bb-pnl'),
      kill: document.createElement('button'),
    };
    this.bb.ic.innerHTML = window.HBIcons.bot;   // our own static SVG strings
    this.bb.kill.type = 'button';
    this.bb.kill.className = 'bb-kill';
    this.bb.kill.innerHTML = window.HBIcons.octagonX;
    this.bb.kill.append(mk('span', '', 'Kill'));
    this.bb.kill.onclick = (e) => { e.stopPropagation(); window.HBTradeUI.botKill(this.cell); };
    this.badges.append(this.bb.ic, this.bb.name, this.bb.pill, this.bb.pnl, this.bb.kill);
    this.badgeKey = null;
    this.botItems = new Map();   // key -> {g, line, chip}: the algo's read-only BOT lines
    this.botIds = null;          // last JSON of the bot marker ids sent to setExtraMarkers('bots')
    this.tips = [];              // [{ms, price, position, tip}] of the drawn bot markers, for the hover tooltip

    // the paper (forward-test) algo badge (2026-09-27 paper-forward-test plan, Task 2): its own row, same slot as
    // the bot's -- the two never show together (a chart's algo is either a desk one or a paper one) -- with an
    // event chip and NO Kill (nothing live to stop), plus a stats line under it (paper vs. the backtest).
    this.pbadge = mk('div', 'lg-bots lg-paper');
    this.pbadge.hidden = true;
    cell.el.querySelector('.lg-tradeslot').before(this.pbadge);
    this.pstats = mk('div', 'lg-paper-stats');
    this.pstats.hidden = true;
    cell.el.querySelector('.lg-tradeslot').before(this.pstats);
    this.pb = { ic: mk('span', 'icw bb-ic'), name: mk('span', 'bb-name'), event: mk('span', 'bb-event'), pill: mk('span', 'bb-pill'), pnl: mk('span', 'bb-pnl') };
    this.pb.ic.innerHTML = window.HBIcons.fileText;   // our own static SVG strings
    this.pbadge.append(this.pb.ic, this.pb.name, this.pb.event, this.pb.pill, this.pb.pnl);
    this.paperBadgeKey = null;
    this.paperStatsKey = null;
    this.paperItems = new Map();   // key -> {g, line, chip}: the paper algo's dashed, read-only lines
    this.paperIds = null;          // last JSON of the paper marker ids sent to setExtraMarkers('paper')
    this.ptips = [];               // [{ms, price, position, tip}] of the drawn paper markers, for the hover tooltip

    this.tip = mk('div', 'ev-tip bot-tip');
    this.tip.setAttribute('role', 'tooltip');
    this.tip.hidden = true;
    this.layer.appendChild(this.tip);
    this.onMove = (p) => this.hoverTip(p);
    cell.chart.subscribeCrosshairMove(this.onMove);
    this.unsubPaper = window.HBPaperClient ? window.HBPaperClient.on(() => this.render()) : null;

    this.hook = new Hook(() => this.sync());
    cell.candles.attachPrimitive(this.hook);

    this.unsub = window.HBDeskClient.on(() => this.render());
    this.unsubBusy = window.HBTradeUI.onBusyChange(() => this.render());
    this.unsubTrade = window.HBTradeUI.onTradeChange(() => this.render());   // this (or any) chart's trade config / a LIVE arm
    this.render();
  }

  /* ---- the Buy/Sell block ---- */
  trade(side) {
    if (window.HBTradeUI.busy()) return;
    window.HBTradeUI.placeOrder({ cell: this.cell, root: this.root, side, type: 'Market', qty: window.HBDeskClient.prefs.qty });
  }

  paintBlock(mode) {
    const on = mode.mode === 'on';
    this.block.hidden = !on;
    if (!on) return;
    const Dc = window.HBDeskClient, view = T.quoteView(Dc.quotes[this.root], this.cell.tick, this.page.clockMs());
    this.block.classList.toggle('stale', view.stale);
    this.sellPx.textContent = view.bid;
    this.buyPx.textContent = view.ask;
    this.spread.textContent = view.spread ? `${view.spread}t` : '';
    let title = 'Bid / ask as of the last trade';
    if (view.stale) title += view.age != null ? ` — no trade for ${Math.round(view.age / 1000)} s` : ' — no trade yet';
    this.block.title = title;
    if (document.activeElement !== this.qty) this.qty.value = String(Dc.prefs.qty);
    const busy = window.HBTradeUI.busy();
    this.buyBtn.disabled = this.sellBtn.disabled = busy;
  }

  /* The chart's accounts next to the block while its Trading is on; one not in the chart's effective set right
     now (unarmed LIVE, not tradable, unknown) is dimmed. Rebuilt only when the chips change. */
  paintAccts(mode) {
    const t = window.HBTradeUI.tradeOf(this.cell);
    this.accts.hidden = !t.on || !t.accounts.length;
    if (this.accts.hidden) return;
    const chips = T.accountChips(window.HBDeskClient.state, t.accounts, mode.mode === 'on' ? mode.accounts : []);
    const key = JSON.stringify(chips);
    if (key === this.acctsKey) return;
    this.acctsKey = key;
    this.accts.replaceChildren(...chips.map((c) => {
      const el = mk('span', 'tr-acct' + (c.active ? '' : ' off'), c.who);
      if (c.env) el.append(mk('span', 'env' + (c.live ? ' live' : ''), c.env));
      el.title = c.active ? `Orders from this chart go to ${c.id}` : `${c.id} — not trading from this chart right now`;
      return el;
    }));
  }

  /* ---- lines: positions, working orders and SL/TP legs, merged per HBTrade.linesFor (ruling S8) ---- */
  paintLines(mode) {
    const Dc = window.HBDeskClient, root = this.root;
    // every account's lines; only this chart's effective accounts' are editable (none while it cannot trade)
    const groups = T.linesFor(Dc.state, root, mode.mode === 'on' ? mode.accounts : []);
    const busy = window.HBTradeUI.busy();
    const seen = new Set();
    for (const g of groups) {
      seen.add(g.key);
      if (this.dragging === g.key) continue;   // the key being dragged is skipped
      let it = this.items.get(g.key);
      if (!it) {
        const line = this.cell.candles.createPriceLine({ price: g.price, color: T.lineColor(g, this.cell.P),
          lineWidth: 1, lineStyle: g.kind === 'position' ? 0 : 2, axisLabelVisible: true, title: '' });
        const chip = this.buildChip();
        it = { g, line, chip };
        this.items.set(g.key, it);
        this.layer.appendChild(chip);
      } else {
        it.g = g;
        it.line.applyOptions({ price: g.price, color: T.lineColor(g, this.cell.P) });
      }
      this.wireChip(it, !g.editable, busy);
      this.paint(it);
    }
    for (const [key, it] of [...this.items]) {
      if (seen.has(key) || this.dragging === key) continue;
      this.cell.candles.removePriceLine(it.line);
      it.chip.remove();
      this.items.delete(key);
    }
    this.sync();
  }

  buildChip() {
    const chip = document.createElement('div');
    chip.className = 'tl-chip';
    chip.text = document.createElement('span');
    chip.text.className = 'tl-text';
    chip.btn = document.createElement('button');
    chip.btn.type = 'button';
    chip.btn.className = 'tl-x';
    chip.btn.setAttribute('aria-label', 'Close');
    chip.btn.textContent = '×';
    chip.append(chip.text, chip.btn);
    return chip;
  }

  wireChip(it, readonly, busy) {
    const { chip, g } = it;
    const draggable = !readonly && !busy && T.canDrag(g);   // positions and Stop Limits never drag
    chip.classList.toggle('drag', draggable);
    chip.classList.toggle('view', readonly);
    chip.text.onpointerdown = draggable ? (e) => this.startDrag(e, g.key) : null;
    chip.btn.hidden = readonly;
    chip.btn.disabled = busy;   // review item 3: never clickable while a send is already in flight
    chip.btn.onclick = readonly || busy ? null : () => window.HBTradeUI.closeLine(this.cell, it.g, this.root, this.cell.tick);
  }

  paint(it) {
    const Dc = window.HBDeskClient, q = Dc.quotes[this.root];
    it.chip.text.textContent = T.lineText(it.g, q ? q.last : null);
    it.chip.style.setProperty('--c', T.lineColor(it.g, this.cell.P));
  }

  /* ---- execution markers (ruling S22); re-set only when the fill ids change ---- */
  paintMarkers() {
    const Dc = window.HBDeskClient;
    const list = T.fillMarkers(Dc.state, this.root, window.HBTradeUI.fillIds(this.cell), this.cell.P);
    const ids = JSON.stringify(list.map((m) => m.id));
    if (ids === this.fillIds) return;
    this.fillIds = ids;
    this.cell.setExtraMarkers('fills', list);
  }

  /* ---- the chart's algo (Task 3): badge, BOT lines, today's + past markers ---- */
  paintAlgo() {
    const Dc = window.HBDeskClient, c = this.cell, q = Dc.quotes[this.root];
    const o = T.algoOverlay(Dc.state, c.cfg.algo, this.root, c.tick, c.P, q ? q.last : null, c.pv ?? null);
    this.paintBadge(o);
    this.paintBotLines(o ? o.lines : []);
    let list = [];
    if (o && c.bars.length) {   // only what falls inside the loaded bars (placeMarkers' own range), so a tip never
                                 // belongs to a marker that is not drawn
      const hist = Dc.botHistory(o.key), s = Dc.state.bot.strategies[o.key], bars = c.bars, barMs = c.barMs();
      const from = bars[0].ms, to = barMs > 0 ? bars[bars.length - 1].ms + barMs : Infinity;
      // fix round 1, M3: today by the ET clock (the desk's own date), never the last bot view's `date`, which stays
      // on yesterday after midnight until the timer publishes again
      const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
      list = o.markers.filter((m) => m.ms >= from && m.ms < to);
      if (hist) {
        list = [...T.pastRunMarkers(hist.runs, { key: o.key, s, state: Dc.state, tick: c.tick, pv: c.pv ?? null, P: c.P, from, to, today,
          liveAccounts: o.liveAccounts }), ...list];
      }
    }
    this.tips = list.map((m) => ({ ms: m.ms, price: m.price, position: m.position, tip: m.tip }));
    const ids = JSON.stringify(list.map((m) => [m.id, m.color, m.text]));
    if (ids === this.botIds) return;
    this.botIds = ids;
    this.cell.setExtraMarkers('bots', list.map(({ tip, account, ...m }) => m));   // the tip stays ours (this.tips)
  }

  paintBadge(o) {
    this.badges.hidden = !o;
    if (!o) { this.badgeKey = null; return; }
    const busy = window.HBTradeUI.busy(), pnl = o.pnl == null ? '' : T.usd(o.pnl);
    const key = JSON.stringify([o.label, o.pill, o.gate, pnl, busy]);
    if (key === this.badgeKey) return;
    this.badgeKey = key;
    this.bb.name.textContent = o.name;
    this.bb.name.title = o.label;
    this.bb.pill.textContent = o.pill.text;
    this.bb.pill.className = `bb-pill ${o.pill.tone}`;
    const tip = o.pill.tip || '';
    this.bb.pill.title = o.gate && !tip.includes(o.gate) ? [tip, o.gate].filter(Boolean).join(' · ') : tip;
    this.bb.pnl.textContent = pnl;
    this.bb.pnl.hidden = !pnl;
    this.bb.pnl.className = 'bb-pnl' + (o.pnl > 0 ? ' up' : o.pnl < 0 ? ' down' : '');
    this.bb.pnl.title = "Today's P&L";
    this.bb.kill.disabled = busy;
    this.bb.kill.title = `Kill ${o.name}: cancel its orders and flatten its position on its own accounts`;
    this.bb.kill.setAttribute('aria-label', `Kill ${o.name}`);
  }

  /* read-only: no drag, no × -- the bot owns them (the desk also refuses a change to a bot's order) */
  paintBotLines(lines) {
    const seen = new Set();
    for (const g of lines) {
      seen.add(g.key);
      let it = this.botItems.get(g.key);
      if (!it) {
        const line = this.cell.candles.createPriceLine({ price: g.price, color: g.color, lineWidth: 1, lineStyle: 2,
          axisLabelVisible: true, title: '' });
        const chip = this.buildChip();
        chip.classList.add('bot', 'view');
        chip.btn.hidden = true;
        chip.title = 'The algo\'s order — it cannot be moved or cancelled from the chart (Kill the algo instead)';
        it = { g, line, chip };
        this.botItems.set(g.key, it);
        this.layer.appendChild(chip);
      } else {
        it.g = g;
        it.line.applyOptions({ price: g.price, color: g.color });
      }
      it.chip.text.textContent = g.text;
      it.chip.style.setProperty('--c', g.color);
    }
    for (const [key, it] of [...this.botItems]) {
      if (seen.has(key)) continue;
      this.cell.candles.removePriceLine(it.line);
      it.chip.remove();
      this.botItems.delete(key);
    }
  }

  /* ---- the chart's paper (forward-test) algo (2026-09-27 paper-forward-test plan, Task 2): badge, dashed lines,
     today's + past markers -- the same shape as paintAlgo/paintBadge/paintBotLines, but from HBPaperClient's own
     state (never the desk's), with no Kill and no accounts. */
  paintPaper() {
    const Pc = window.HBPaperClient, c = this.cell;
    const o = Pc ? T.paperOverlay(Pc.state(), c.cfg.algo, this.root, c.tick, c.P) : null;
    this.paintPaperBadge(o);
    this.paintPaperLines(o ? o.lines : []);
    let list = [];
    if (o && c.bars.length) {   // only what falls inside the loaded bars, so a tip never belongs to an undrawn marker
      const hist = Pc.history(o.id), bars = c.bars, barMs = c.barMs();
      const from = bars[0].ms, to = barMs > 0 ? bars[bars.length - 1].ms + barMs : Infinity;
      const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
      list = o.markers.filter((m) => m.ms >= from && m.ms < to);
      if (hist && Array.isArray(hist.runs)) list = [...T.paperRunMarkers(hist.runs, { tick: c.tick, P: c.P, from, to, today }), ...list];
      this.paintPaperStats(o, hist ? hist.stats : null);
    } else {
      this.paintPaperStats(o, null);
    }
    this.ptips = list.map((m) => ({ ms: m.ms, price: m.price, position: m.position, tip: m.tip }));
    const ids = JSON.stringify(list.map((m) => [m.id, m.color, m.text]));
    if (ids === this.paperIds) return;
    this.paperIds = ids;
    this.cell.setExtraMarkers('paper', list.map(({ tip, ...m }) => m));   // the tip stays ours (this.ptips)
  }

  paintPaperBadge(o) {
    this.pbadge.hidden = !o;
    if (!o) { this.paperBadgeKey = null; return; }
    const key = JSON.stringify([o.label, o.event, o.pill, o.pnl]);
    if (key === this.paperBadgeKey) return;
    this.paperBadgeKey = key;
    this.pb.name.textContent = o.name;
    this.pb.name.title = o.label;
    this.pb.event.textContent = o.event || '';
    this.pb.event.hidden = !o.event;
    this.pb.pill.textContent = o.pill.text;
    this.pb.pill.className = `bb-pill ${o.pill.tone}`;
    this.pb.pill.title = o.pill.tip || '';
    const pnl = o.pnl == null ? '' : T.usd(o.pnl);
    this.pb.pnl.textContent = pnl;
    this.pb.pnl.hidden = !pnl;
    this.pb.pnl.className = 'bb-pnl' + (o.pnl > 0 ? ' up' : o.pnl < 0 ? ' down' : '');
    this.pb.pnl.title = "Today's paper P&L";
  }

  /* The stats line under the badge: "Paper 3 · WR 67% · avg +$203 | Backtest 21–24: 76 · WR 68% · avg +$296". */
  paintPaperStats(o, stats) {
    const text = o ? T.paperStatsText(stats) : '';
    this.pstats.hidden = !text;
    if (text === this.paperStatsKey) return;
    this.paperStatsKey = text;
    this.pstats.textContent = text;
  }

  /* dashed, read-only: no drag, no × -- nothing here is a real order (never sent, never cancellable) */
  paintPaperLines(lines) {
    const seen = new Set();
    for (const g of lines) {
      seen.add(g.key);
      let it = this.paperItems.get(g.key);
      if (!it) {
        const line = this.cell.candles.createPriceLine({ price: g.price, color: g.color, lineWidth: 1, lineStyle: 2,
          axisLabelVisible: true, title: '' });
        const chip = this.buildChip();
        chip.classList.add('bot', 'view', 'paper');
        chip.btn.hidden = true;
        chip.title = 'A simulated paper order — it was never sent';
        it = { g, line, chip };
        this.paperItems.set(g.key, it);
        this.layer.appendChild(chip);
      } else {
        it.g = g;
        it.line.applyOptions({ price: g.price, color: g.color });
      }
      it.chip.text.textContent = g.text;
      it.chip.style.setProperty('--c', g.color);
    }
    for (const [key, it] of [...this.paperItems]) {
      if (seen.has(key)) continue;
      this.cell.candles.removePriceLine(it.line);
      it.chip.remove();
      this.paperItems.delete(key);
    }
  }

  /* The tooltip of the bot or paper marker under the mouse (HBTrade.nearestTip within 10 px). */
  hoverTip(p) {
    const c = this.cell, all = this.tips.length || this.ptips.length ? [...this.tips, ...this.ptips] : this.tips;
    if (this.dead || !c.chart || !p || !p.point || !all.length || !c.bars.length) { this.tip.hidden = true; return; }
    const D = window.HBDrawings, ts = c.chart.timeScale(), pts = [];
    for (const m of all) {
      const i = D.barIndexAt(c.bars, m.ms);
      if (i < 0) continue;
      const b = c.bars[i], x = ts.timeToCoordinate(b.tt);
      let y = m.position === 'aboveBar' ? c.candles.priceToCoordinate(b.h) : c.candles.priceToCoordinate(m.price);
      if (x == null || y == null) continue;
      if (m.position === 'aboveBar') y -= 12; else if (m.position === 'atPriceBottom') y += 8; else if (m.position === 'atPriceTop') y -= 8;
      pts.push({ x, y, tip: m.tip });
    }
    const text = T.nearestTip(pts, p.point.x, p.point.y, 10);
    if (!text) { this.tip.hidden = true; return; }
    this.tip.textContent = text;
    this.tip.hidden = false;
    const w = this.layer.clientWidth, tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(4, Math.min(w - tw - 4, p.point.x + 12))}px`;
    this.tip.style.top = `${Math.max(4, p.point.y - 30)}px`;
  }

  render() {
    if (this.dead || !this.cell.chart) return;
    const mode = window.HBTradeUI.effectiveMode(this.cell);   // review M3: LIVE-arm-aware; Task 2: THIS chart's
    this.paintBlock(mode);
    this.paintAccts(mode);
    this.paintLines(mode);
    this.paintAlgo();
    this.paintPaper();
    this.sync();
    this.paintMarkers();
  }

  onBars() { this.render(); }

  /* every chip at its line's y, right-aligned left of the price axis; hidden outside the price pane */
  sync() {
    const c = this.cell;
    if (!c.chart) return;
    const paneH = c.chart.panes()[0].getHeight(), right = c.chart.priceScale('right').width() + 6;
    for (const it of [...this.items.values(), ...this.botItems.values(), ...this.paperItems.values()]) {
      const y = c.candles.priceToCoordinate(it.g.price);
      const off = y == null || y < 0 || y > paneH;
      it.chip.hidden = off;
      if (!off) { it.chip.style.right = `${right}px`; it.chip.style.transform = `translateY(${Math.round(y) - 11}px)`; }
    }
  }

  /* on .tl-text; the pointer is captured by the chip, so the chart never pans */
  startDrag(e, key) {
    if (e.button !== 0) return;
    // Minor 2 (re-review): a stray drag stuck mid-flight (capture survived with no up/cancel reaching us) must
    // not silently swallow the next press -- cancel it properly (restoring its line, clearing this.dragging)
    // instead of just returning, so THIS press can still start a fresh, correct drag.
    if (this.dragging && this.endDrag) this.endDrag();
    e.preventDefault(); e.stopPropagation();
    const c = this.cell, it = this.items.get(key), grip = e.currentTarget, from = it.g.price;
    const top = c.box.getBoundingClientRect().top;
    let price = from, outside = false;   // I1: released outside the price pane must not send
    grip.setPointerCapture(e.pointerId);
    this.dragging = key;
    const move = (ev) => {
      if (ev.buttons === 0) { lost(); return; }   // I2: the button was released without a pointerup/cancel reaching us
      const paneH = c.chart ? c.chart.panes()[0].getHeight() : 0, y = ev.clientY - top;
      outside = y < 0 || y > paneH;
      if (outside) { this.sync(); return; }   // freeze the line at its last in-pane price; do not extrapolate
      const raw = c.candles.coordinateToPrice(y);
      if (raw == null) return;
      price = window.HBDrawings.roundToTick(raw, c.tick);
      it.g = window.HBTrade.withPrice(it.g, price);
      it.line.applyOptions({ price });
      this.paint(it);            // the chip's text with the new SL/TP dollars
      this.sync();
    };
    const end = (commit) => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', lost);
      grip.removeEventListener('lostpointercapture', lost);
      window.removeEventListener('keydown', esc, true);
      window.removeEventListener('blur', lost);
      this.dragging = null;
      this.endDrag = null;
      // M8: compare tick-rounded to tick-rounded (a zero-tick drag can otherwise differ only in float noise)
      const changed = window.HBDrawings.roundToTick(price, c.tick) !== window.HBDrawings.roundToTick(from, c.tick);
      if (commit && !outside && changed) {
        window.HBTradeUI.moveLine(c, { ...it.g, price: from }, price, c.shown.root, c.tick, { onCancel: () => this.render() });
      } else this.render();      // back to the desk's price (also covers a release outside the pane: I1)
    };
    const up = () => end(true), lost = () => end(false);
    const esc = (ev) => { if (ev.key === 'Escape') { ev.stopPropagation(); ev.preventDefault(); end(false); } };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', lost);
    grip.addEventListener('lostpointercapture', lost);   // I2: capture lost with no up/cancel (a system gesture, e.g.)
    window.addEventListener('keydown', esc, true);
    window.addEventListener('blur', lost);
    this.endDrag = () => end(false);
  }

  destroy() {
    this.dead = true;   // review M2: any callback still holding this overlay (e.g. a cancelled drag's onCancel) becomes a no-op
    if (this.dragging && this.endDrag) this.endDrag();
    this.unsub();
    this.unsubBusy();
    this.unsubTrade();
    if (this.unsubPaper) this.unsubPaper();
    for (const it of [...this.items.values(), ...this.botItems.values(), ...this.paperItems.values()]) this.cell.candles.removePriceLine(it.line);
    this.items.clear();
    this.botItems.clear();
    this.paperItems.clear();
    if (this.cell.chart) this.cell.chart.unsubscribeCrosshairMove(this.onMove);
    this.block.remove();
    this.accts.remove();
    this.layer.remove();
    this.badges.remove();
    this.pbadge.remove();
    this.pstats.remove();
    if (this.cell.chart) this.cell.candles.detachPrimitive(this.hook);
    this.cell.setExtraMarkers('fills', []);
    this.cell.setExtraMarkers('bots', []);
    this.cell.setExtraMarkers('paper', []);
  }
}

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

window.HBTradeLines = { overlay: (cell, page) => new Overlay(cell, page) };
})();
