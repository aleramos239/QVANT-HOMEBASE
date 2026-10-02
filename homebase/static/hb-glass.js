/* Homebase glass -- the one clear-glass material, for every page.
   An element with class "hb-lens" is rendered as a real lens: a flat top with a rounded lip. From that shape this
   file computes (a) how far the picture behind bends at each pixel (Snell's law, glass at 1.5) -- a displacement
   map used as the element's backdrop filter -- and (b) how much light the lip catches there -- a highlight map
   painted over it. Where the browser cannot run a filter behind an element (WebKit, so the Mac app), the bend is
   skipped and everything else stays: the highlights, the shadow, a light blur. Presentation only: it never reads
   or changes what an element does.
   The pure half (surface / maps) runs headless: tests/js/hbglass.test.mjs. */
(function () {
'use strict';
const IOR = 1.5, LIGHT = [-0.62, -0.78];       // light from the upper left

/* Distance in from the edge of a rounded rectangle (negative outside) and the outward normal there. */
function edge(px, py, w, h, rad) {
  const cx = px - w / 2, cy = py - h / 2, qx = Math.abs(cx) - (w / 2 - rad), qy = Math.abs(cy) - (h / 2 - rad);
  const d = -(Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - rad);
  let nx, ny;
  if (qx > 0 && qy > 0) { const l = Math.hypot(qx, qy) || 1; nx = qx / l * Math.sign(cx); ny = qy / l * Math.sign(cy); }
  else if (qx > qy) { nx = Math.sign(cx) || 1; ny = 0; } else { nx = 0; ny = Math.sign(cy) || 1; }
  return { d, nx, ny, cx, cy };
}
/* The lip, d pixels in from the edge: its height (0..1) and slope. A squircle profile: steep at the rim, flat inside. */
function lip(d, bezel, lift) {
  const t = Math.min(1, Math.max(0.035, d / bezel)), u = 1 - t;
  return { h: Math.pow(1 - u ** 4, 0.25), slope: (u ** 3) / Math.pow(1 - u ** 4, 0.75) * lift / bezel };
}
/* How the lens is proportioned for an element of this size. */
function shape(w, h) {
  const small = Math.min(w, h) < 60;
  return { bezel: Math.min(small ? 13 : 20, Math.min(w, h) * 0.46), lift: small ? 9 : 14, depth: small ? 9 : 15, mag: small ? 0.05 : 0.035 };
}
/* Where the backdrop pixel under (px, py) is taken from, as an offset in pixels. */
function bend(px, py, w, h, rad, S = shape(w, h)) {
  const e = edge(px, py, w, h, rad);
  let ox = -e.cx * S.mag, oy = -e.cy * S.mag;                       // the flat middle magnifies a little
  if (e.d >= 0 && e.d < S.bezel) {
    const L = lip(e.d, S.bezel, S.lift), t1 = Math.atan(L.slope), t2 = Math.asin(Math.sin(t1) / IOR), m = (S.depth + S.lift * L.h) * Math.tan(t1 - t2);
    ox -= e.nx * m; oy -= e.ny * m;
  }
  return [ox, oy];
}
/* The light the lip catches at a point: [white, black] in 0..1. */
function glint(d, nx, ny, bezel, dark) {
  if (d < 0 || d > bezel) return [0, 0];
  const u = 1 - d / bezel, f = nx * LIGHT[0] + ny * LIGHT[1], line = Math.exp(-(d - 0.7) * (d - 0.7) / 1.1), gain = dark ? 0.8 : 1;
  const hi = gain * (line * (0.20 + 0.80 * Math.pow(Math.abs(f), 1.5)) + 0.16 * Math.pow(u, 2.2) * Math.pow(Math.max(0, f), 1.6) + 0.06 * Math.pow(u, 3));
  const lo = (dark ? 0.34 : 0.20) * Math.pow(u, 1.6) * Math.pow(Math.max(0, -f), 1.4) * (1 - line);
  return [hi, lo];
}
const pure = { edge, lip, shape, bend, glint, IOR };
if (typeof module !== 'undefined' && module.exports) module.exports = pure;
if (typeof window === 'undefined' || typeof document === 'undefined') return;

/* ---- the browser half ---- */
const CAN_BEND = !!(window.CSS && CSS.supports && (CSS.supports('backdrop-filter', 'url(#a)') || CSS.supports('-webkit-backdrop-filter', 'url(#a)'))) && !/^((?!chrome|android).)*safari/i.test(navigator.userAgent);
const reduce = () => window.matchMedia && (matchMedia('(prefers-reduced-transparency: reduce)').matches || matchMedia('(prefers-contrast: more)').matches);
let defs = null, seq = 0;
const built = new WeakMap();            // element -> {key, id}
function holder() {
  if (defs && defs.isConnected) return defs;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '0'); svg.setAttribute('height', '0'); svg.setAttribute('aria-hidden', 'true'); svg.style.position = 'absolute';
  defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); svg.appendChild(defs); document.body.appendChild(svg);
  return defs;
}
function build(el) {
  const w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
  if (w < 8 || h < 8 || w * h > 700000) return;
  const rad = Math.min(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0, w / 2, h / 2), dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const key = `${w}x${h}r${Math.round(rad)}${dark ? 'd' : 'l'}`, was = built.get(el);
  if (was && was.key === key) return;
  const S = shape(w, h);
  // highlights, at twice the resolution so the line stays crisp
  const sc = document.createElement('canvas'); sc.width = w * 2; sc.height = h * 2;
  const sx = sc.getContext('2d'), simg = sx.createImageData(w * 2, h * 2), P = simg.data;
  for (let py = 0; py < h * 2; py++) for (let px = 0; px < w * 2; px++) {
    const e = edge(px + 0.5, py + 0.5, w * 2, h * 2, rad * 2), [hi, lo] = glint(e.d / 2, e.nx, e.ny, S.bezel, dark);
    if (!hi && !lo) continue;
    const k = (py * w * 2 + px) * 4, a = Math.min(1, hi + lo);
    P[k] = P[k + 1] = P[k + 2] = 255 * hi / (hi + lo); P[k + 3] = 255 * a;
  }
  sx.putImageData(simg, 0, 0);
  el.style.setProperty('--hb-spec', `url(${sc.toDataURL()})`);
  let id = '';
  if (CAN_BEND && !reduce()) {
    const dc = document.createElement('canvas'); dc.width = w; dc.height = h;
    const dx = dc.getContext('2d'), dimg = dx.createImageData(w, h), D = dimg.data, off = new Float32Array(w * h * 2); let max = 1;
    for (let py = 0; py < h; py++) for (let px = 0; px < w; px++) { const [ox, oy] = bend(px + 0.5, py + 0.5, w, h, rad, S), k = (py * w + px) * 2; off[k] = ox; off[k + 1] = oy; max = Math.max(max, Math.abs(ox), Math.abs(oy)); }
    const sc2 = max * 2;
    for (let i = 0; i < w * h; i++) { D[i * 4] = 127.5 + off[i * 2] / sc2 * 255; D[i * 4 + 1] = 127.5 + off[i * 2 + 1] / sc2 * 255; D[i * 4 + 2] = 128; D[i * 4 + 3] = 255; }
    dx.putImageData(dimg, 0, 0);
    id = `hbLens${++seq}`;
    const ch = (n, s, m) => `<feDisplacementMap in="SourceGraphic" in2="m" scale="${s}" xChannelSelector="R" yChannelSelector="G" result="d${n}"/><feColorMatrix in="d${n}" type="matrix" values="${m}" result="c${n}"/>`;
    holder().insertAdjacentHTML('beforeend', `<filter id="${id}" x="0" y="0" width="${w}" height="${h}" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feImage href="${dc.toDataURL()}" x="0" y="0" width="${w}" height="${h}" result="m"/>
      ${ch('r', sc2 * 1.035, '1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0')}${ch('g', sc2, '0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0')}${ch('b', sc2 * 0.965, '0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0')}
      <feBlend in="cr" in2="cg" mode="screen" result="rg"/><feBlend in="rg" in2="cb" mode="screen" result="rgb"/>
      <feGaussianBlur in="rgb" stdDeviation=".55" result="bl"/><feColorMatrix in="bl" type="saturate" values="1.3"/></filter>`);
    el.style.setProperty('--hb-lens', `url(#${id})`);
    el.classList.add('hb-lens-on');
  }
  if (was && was.id) { const old = document.getElementById(was.id); if (old) old.remove(); }
  built.set(el, { key, id });
}
let queued = false;
function scan() { queued = false; for (const el of document.querySelectorAll('.hb-lens')) build(el); }
function refresh() { if (!queued) { queued = true; requestAnimationFrame(scan); } }
const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(refresh) : null;
function watch() { if (ro) for (const el of document.querySelectorAll('.hb-lens')) ro.observe(el); refresh(); }
function start() {
  for (const el of document.querySelectorAll('.pgsw')) el.classList.add('hb-lens');   // the page switcher is glass on every page
  watch();
  new MutationObserver((ms) => { for (const m of ms) if (m.type === 'attributes' || m.addedNodes.length) { watch(); return; } })
    .observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-theme'] });
  // the sheen follows the pointer across every piece of glass
  window.addEventListener('pointermove', (e) => {
    for (const el of document.querySelectorAll('.hb-lens')) { const r = el.getBoundingClientRect(); if (e.clientX < r.left - 200 || e.clientX > r.right + 200 || e.clientY < r.top - 200 || e.clientY > r.bottom + 200) continue;
      el.style.setProperty('--hb-mx', `${e.clientX - r.left}px`); el.style.setProperty('--hb-my', `${e.clientY - r.top}px`); }
  }, { passive: true });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
window.HBGlass = { ...pure, refresh, canBend: CAN_BEND };
})();
