/* Homebase Charts -- the indicator guide, part: Pine scripts run in the page. Plain words; the registry and the shape
   of an entry are in guide.js. */
(function () {
'use strict';
const G = (typeof window !== 'undefined' && window.HBGuide) || require('./guide.js');
G.add({
  pine: {
    what: "Runs a Pine script from the server's script list on this chart's bars and draws what it plots.",
    see: ['Its plot lines on the price pane, or in a pane of its own when the script says overlay is off.',
      'Marks the script places (arrows, dots, letters) sit on the bars; its boxes, lines, labels and tables draw on the chart.',
      'Under Settings, Script picks the file and Script inputs are that script\'s own inputs.'],
    read: ['The numbers by the name are the script\'s plots on the bar under the crosshair.',
      'A note by the name says why it shows nothing: no script picked, a script that does not compile, or no Pine runtime.'],
    use: ['Pick a script, then change its inputs: the chart runs it again as you type.',
      'It needs a time chart (minutes, hours, days); a tick or range chart shows a note instead.',
      'Max bars is how many of the newest bars it runs on; fewer bars run faster.'],
    watch: 'Runs in your browser; a Pine function the runtime lacks shows as a note, not as a wrong line.',
  },
});
})();
