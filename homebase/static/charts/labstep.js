/* Homebase Lab — a previous / next trade button ON the chart (2026-10-10, owner: "add a button so i can click and go
   to previous or next trade on the chart").

   The stepper itself is lab.js's (#labNav: its two [data-nav] buttons and the "3 of 42" text); the Mac skin keeps it in the
   inspector, which is often closed. This is a small capsule on the chart that mirrors it and clicks its buttons, so the
   stepping logic (selection, the window jump, the interval kept) stays in one place. It hides while the run has no trades,
   and when the stepper itself already sits on the chart. */
(function () {
'use strict';
const nav = document.getElementById('labNav'), chart = document.getElementById('labChart');
if (!nav || !chart) return;
const CHEV = (d) => `<svg viewBox="0 0 10 14" width="10" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;
const box = document.createElement('div');
box.className = 'lab-step';
box.id = 'labStep';
box.setAttribute('role', 'group');
box.setAttribute('aria-label', 'Step through the trades');
box.hidden = true;
box.innerHTML = `<button type="button" class="lab-step-b" data-step="-1" aria-label="Previous trade" title="Previous trade">${CHEV('M7.5 1.5 2 7l5.5 5.5')}</button>`
  + '<span class="lab-step-t" aria-hidden="true"></span>'
  + `<button type="button" class="lab-step-b" data-step="1" aria-label="Next trade" title="Next trade">${CHEV('M2.5 1.5 8 7l-5.5 5.5')}</button>`;
chart.appendChild(box);
const [prev, next] = box.querySelectorAll('.lab-step-b'), txt = box.querySelector('.lab-step-t');
const real = (d) => nav.querySelector(`[data-nav="${d}"]`);

function sync() {
  const full = (document.getElementById('labNavText') || {}).textContent || '';
  const m = /^(\d+) of (\d+)/.exec(full.trim());
  const onChart = chart.contains(nav);                         // the page's own stepper is on the chart: this one is not needed
  box.hidden = nav.hidden || onChart || !(m || /^\d+ trades?$/.test(full.trim()));
  if (box.hidden) return;
  txt.textContent = m ? `${m[1]} / ${m[2]}` : full.trim();
  box.title = (document.getElementById('labNavText') || {}).title || '';
  const a = real(-1), b = real(1);
  prev.disabled = !a || a.disabled;
  next.disabled = !b || b.disabled;
}
box.addEventListener('click', (e) => {
  const b = e.target.closest('[data-step]');
  if (!b || b.disabled) return;
  const r = real(b.dataset.step);
  if (r && !r.disabled) r.click();
});
new MutationObserver(sync).observe(nav, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'hidden', 'title'] });
sync();
// the page moves the stepper between the inspector and the chart after this runs
setTimeout(sync, 500);
setTimeout(sync, 2500);
})();
