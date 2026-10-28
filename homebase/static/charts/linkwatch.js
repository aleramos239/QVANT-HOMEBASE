/* Homebase Charts — HBLinkWatch (D11, 2026-10-27): a toast, and an optional alarm, when the chart service, the Desk
   link or the prices stop. The toast is always there and stays until the link is back; the alarm is a sound picked in
   Settings > Sounds ("Connection lost", "Connection lost, position open": both Off until picked), repeated every 15 s
   until nothing is down, the stronger one if a position was open when it dropped. Display and sound only: it sends
   nothing. Fed by app.js (service, feed) and HBDeskClient (desk). Browser only. */
(() => {
'use strict';
const REPEAT_MS = 15000;

function make({ toast, dismiss, sound, positionOpen, every, cancel }) {
  const open = new Map();   // problem -> its toast
  let timer = null, strong = false, deskSeenUp = false;
  const ring = () => sound(strong ? 'linkpos' : 'link');
  function start(key, text) {
    if (open.has(key)) return;
    const pos = positionOpen();
    strong = strong || pos;
    open.set(key, toast('warn', text(pos)));
    ring();
    if (!timer) timer = every(ring, REPEAT_MS);
  }
  function end(key, text) {
    if (!open.has(key)) return;
    dismiss(open.get(key));
    open.delete(key);
    toast('ok', text);
    if (!open.size && timer) { cancel(timer); timer = null; strong = false; }
  }
  const held = (pos) => (pos ? ' A position was open: check it another way.' : '');
  return {
    service: (up) => (up ? end('service', 'The chart service is back.')
      : start('service', (pos) => `Lost the chart service. The charts are not live.${held(pos)}`)),
    // `down`: HBDeskClient.down -- null while the Desk link is up, else why not. A page that never saw it up stays quiet.
    desk: (down) => {
      if (down == null) { deskSeenUp = true; end('desk', 'The Desk link is back.'); }
      else if (deskSeenUp) start('desk', (pos) => `Lost the link to the Desk (${down}). Orders cannot be sent from here.${held(pos)}`);
    },
    // `stale`: the markets on this page's charts that are open and silent too long (catalog feedSummary's `stale`)
    feed: (stale) => (stale.length ? start('feed', (pos) => `No new prices for ${stale.join(', ')}.${held(pos)}`) : end('feed', 'Prices are back.')),
  };
}

function mount() {
  const D = window.HBDeskClient, S = window.HBSounds;
  if (!D) return;
  const w = make({
    toast: D.toast, dismiss: D.dismiss, sound: (k) => S && S.event(k),
    positionOpen: () => { const st = D.state || D.heldState; return !!st && (st.accounts || []).some((a) => (a.positions || []).some((p) => p.net)); },
    every: (fn, ms) => setInterval(fn, ms), cancel: clearInterval,
  });
  D.on((why) => { if (why.has('state')) w.desk(D.down); });
  w.desk(D.down);
  // cj-6: sounds are on but the page has not been pressed yet, so the browser keeps them silent: say so until it is
  if (S && S.locked()) {
    const el = D.toast('warn', 'Sounds are on, but stay silent until you click once on this page.');
    document.addEventListener('pointerdown', () => D.dismiss(el), { once: true, capture: true });
  }
  window.HBLinkWatch.service = w.service;
  window.HBLinkWatch.feed = w.feed;
}
window.HBLinkWatch = { make };
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
