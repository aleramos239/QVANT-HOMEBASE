if (typeof HBClock !== "undefined") {
  HBClock.on(() => { FEED_SIG = null; if (ST) render(); });      // every time on the page is printed again
  HBClock.load(CHART);
}
refresh(); setInterval(refresh, 2500);
// a Lab strategy's state moves with the day: asked every 5 s, and only while this page is on screen
loadDeskLab(); loadDeskRes();
window.addEventListener("hashchange", () => {      // a link to a Lab strategy opened while the Desk is already open
  const n = labHashName();
  if (n) { clearLabHash(); setView("lab", n); }
});
setInterval(() => { if (!document.hidden) loadDeskLab(); }, 5000);
setInterval(loadDeskRes, 60000);      // a new saved run shows within a minute
loadPreopen(false); setInterval(preopenTick, 60000);   // the pre-open check's last result, then a fresh run in the 07:45-09:00 ET window
setInterval(loadDeskGroupRes, 60000); // (asked only while a group's page is open)
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadDeskLab(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadDeskRes(); });
