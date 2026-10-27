if (typeof HBClock !== "undefined") {
  HBClock.on(() => { FEED_SIG = null; if (ST) render(); });      // every time on the page is printed again
  if (!DEMO) HBClock.load(CHART);                                 // preview mode never asks :8852
}
refresh(); setInterval(refresh, 2500);
// a Lab strategy's state moves with the day: asked every 5 s, and only while this page is on screen
loadDeskLab(); loadDeskRes(); loadDeskGroups();
window.addEventListener("hashchange", () => {      // a link to a Lab strategy opened while the Desk is already open
  const n = labHashName();
  if (n) { clearLabHash(); setView("lab", n); }
});
if (!DEMO) {
  setInterval(() => { if (!document.hidden) loadDeskLab(); }, 5000);
  setInterval(loadDeskRes, 60000);      // a new saved run shows within a minute
  setInterval(loadDeskGroups, 30000);   // a group changed from another window shows within half a minute
  setInterval(loadDeskGroupRes, 60000); // (asked only while a group's page is open)
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadDeskLab(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadDeskRes(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadDeskGroups(); });
}
