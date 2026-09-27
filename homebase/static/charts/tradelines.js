/* Homebase Charts — HBTradeLines: trading on the chart itself, one overlay per chart (rebuilt with it,
   like every host.overlays() entry):
     - the Buy/Sell block under the legend, bid/ask "as of last trade" (ruling S10);
     - position / order / SL / TP lines (native price lines) with DOM chips that carry their text and a ×
       (ruling S8), draggable by the chip's text (order/SL/TP only — positions are not draggable: ruling S11);
     - the execution markers, through cell.setExtraMarkers('fills', …) (ruling S22).
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
    cell.el.querySelector('.legend').appendChild(this.block);

    this.layer = mk('div', 'tl-layer');
    cell.el.appendChild(this.layer);

    this.badges = mk('span', 'lg-bots');   // filled in Task 7 (the bot overlay's badges)
    cell.el.querySelector('.lg-title').appendChild(this.badges);

    this.hook = new Hook(() => this.sync());
    cell.candles.attachPrimitive(this.hook);

    this.unsub = window.HBDeskClient.on(() => this.render());
    this.unsubBusy = window.HBTradeUI.onBusyChange(() => this.render());
    this.render();
  }

  /* HBDeskClient.prefs with `ticked` narrowed to the armed accounts (review item 5: an unarmed LIVE account
     never draws a line or a fill marker, only the raw ticked checkbox in the Trade menu). */
  armedPrefs() {
    const Dc = window.HBDeskClient;
    return { ...Dc.prefs, ticked: window.HBTradeUI.armedIds() };
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

  /* ---- lines: positions, working orders and SL/TP legs, merged per HBTrade.linesFor (ruling S8) ---- */
  paintLines(mode) {
    const Dc = window.HBDeskClient, root = this.root;
    const groups = T.linesFor(Dc.state, root, this.armedPrefs());
    const readonly = mode.mode !== 'on';
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
      this.wireChip(it, readonly, busy);
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
    const draggable = !readonly && !busy && g.kind !== 'position';
    chip.classList.toggle('drag', draggable);
    chip.text.onpointerdown = draggable ? (e) => this.startDrag(e, g.key) : null;
    chip.btn.hidden = readonly;
    chip.btn.disabled = busy;   // review item 3: never clickable while a send is already in flight
    chip.btn.onclick = readonly || busy ? null : () => window.HBTradeUI.closeLine(it.g, this.root, this.cell.tick);
  }

  paint(it) {
    const Dc = window.HBDeskClient, q = Dc.quotes[this.root];
    it.chip.text.textContent = T.lineText(it.g, q ? q.last : null);
    it.chip.style.setProperty('--c', T.lineColor(it.g, this.cell.P));
  }

  /* ---- execution markers (ruling S22); re-set only when the fill ids change ---- */
  paintMarkers() {
    const Dc = window.HBDeskClient;
    const list = T.fillMarkers(Dc.state, this.root, this.armedPrefs(), this.cell.P);
    const ids = JSON.stringify(list.map((m) => m.id));
    if (ids === this.fillIds) return;
    this.fillIds = ids;
    this.cell.setExtraMarkers('fills', list);
  }

  render() {
    if (this.dead || !this.cell.chart) return;
    const mode = window.HBTradeUI.effectiveMode();   // review M3: LIVE-arm-aware, not the raw desk mode
    this.paintBlock(mode);
    this.paintLines(mode);
    this.paintMarkers();
  }

  onBars() { this.render(); }

  /* every chip at its line's y, right-aligned left of the price axis; hidden outside the price pane */
  sync() {
    const c = this.cell;
    if (!c.chart) return;
    const paneH = c.chart.panes()[0].getHeight(), right = c.chart.priceScale('right').width() + 6;
    for (const it of this.items.values()) {
      const y = c.candles.priceToCoordinate(it.g.price);
      const off = y == null || y < 0 || y > paneH;
      it.chip.hidden = off;
      if (!off) { it.chip.style.right = `${right}px`; it.chip.style.transform = `translateY(${Math.round(y) - 11}px)`; }
    }
  }

  /* on .tl-text; the pointer is captured by the chip, so the chart never pans */
  startDrag(e, key) {
    if (e.button !== 0 || this.dragging) return;
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
        window.HBTradeUI.moveLine({ ...it.g, price: from }, price, c.shown.root, c.tick, { onCancel: () => this.render() });
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
    for (const it of this.items.values()) this.cell.candles.removePriceLine(it.line);
    this.items.clear();
    this.block.remove();
    this.layer.remove();
    this.badges.remove();
    if (this.cell.chart) this.cell.candles.detachPrimitive(this.hook);
    this.cell.setExtraMarkers('fills', []);
    this.cell.setExtraMarkers('bots', []);
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
