/* Homebase Next in a browser: the same skin the Mac app injects, for a page opened at localhost:8850 / :8852.
   The app sets window.HB_NATIVE before any page script runs; then this file does nothing. In a browser it does what the app's
   start script does -- the hb-apple class, then the manifest's css (shared + the tab's) and js (shared + the tab's, at
   document end) -- with the system's own defaults for what only a window can measure (toolbar 52, window buttons 12).
   Each page names its tab: <script src="/static/apple/web.js" data-tab="desk|charts|lab">. */
(function () {
  'use strict';
  if (window.HB_NATIVE || window.HBApple) return;
  var me = document.currentScript, tab = (me && me.getAttribute('data-tab')) || 'desk';
  var H = document.documentElement, manifest = null;
  try {
    var x = new XMLHttpRequest();
    x.open('GET', '/static/apple/manifest.json?t=' + Date.now(), false);   // never a cached copy: its version names the files' own
    x.send();
    if (x.status === 200) manifest = JSON.parse(x.responseText);
  } catch (e) { manifest = null; }
  var t = manifest && manifest.tabs && manifest.tabs[tab];
  if (!t) return;                                                    // no skin to give: the page stays as it is
  var shared = manifest.shared || {};
  H.classList.add('hb-apple');
  H.setAttribute('data-hb-tab', tab);
  // the manifest's version rides on every file's address, so a browser never keeps an old skin after a change
  // (the pages send no cache headers; the Mac app reads its files past the cache by itself)
  var v = '?v=' + encodeURIComponent(manifest.version || 1), withV = function (u) { return u + v; };
  var css = (shared.css || []).concat(t.css || []).map(withV), js = (shared.js || []).concat(t.js || []).map(withV);
  css.forEach(function (href) { document.write('<link rel="stylesheet" href="' + href + '">'); });
  document.addEventListener('DOMContentLoaded', function () {
    js.forEach(function (src) {
      var s = document.createElement('script');
      s.src = src;
      s.async = false;                                               // in the manifest's order
      document.body.appendChild(s);
    });
  });
}());
