/* HBGuide entries: levels, ranges and structure, in plain words.
   levels, wk, mo, topen, vaprev, dhl are price levels; orb, sess, noise are ranges of a time window or of the day's open;
   swing, equal, rmove, rswing, fvg are structure (turning points, gaps, ranges). events and headlines are the news
   (calendar flags and headline dots). Times are New York (ET). */
(function () {
'use strict';
const G = (typeof window !== 'undefined' && window.HBGuide) || require('./guide.js');
G.add({
  events: {
    what: 'Marks scheduled news (jobs, inflation, rate decisions) on the chart: a flag for each, a line for the big ones.',
    see: [
      'A small coloured flag along the time axis for each calendar event. Hover a flag for the names, times and numbers.',
      'Red = high impact, orange = medium, yellow = low, grey = a holiday. These are the calendar\'s folders.',
      'A vertical line in the flag colour at every red and orange event. The line can be switched off or restyled.',
    ],
    read: [
      'The flag sits at the minute the number comes out. Several events at one minute share one flag.',
      'Red folders are the ones that move price most: jobs report, CPI, rate decisions.',
      'Pick the folders in the indicator settings. Only red = a clean chart. Add orange for more.',
      'The currency list (USD by default) is in Settings > Events.',
    ],
    use: [
      'Be flat or small before a red event. Price can jump several points in one second.',
      'Look at what price did at the last few red events on this market: that is its usual reaction.',
      'Turn the indicator off (the eye) for a clean chart. It comes back as it was.',
    ],
    watch: 'Times are the scheduled ones. A number can be late, and the first move often reverses.',
  },
  headlines: {
    what: 'Marks news headlines on the chart, and a bolt where price made a big move that had news behind it.',
    see: [
      'Small dots at the bar where a headline came out (only in "Every headline" mode).',
      'A bolt above or below a bar: a fast move, 4 times the usual in 30 seconds, with a headline close to it.',
      'Hover a dot or bolt to read the headline, its source and the time.',
    ],
    read: [
      'Green bolt: the move was up. Red bolt: down. The move is measured on this chart\'s own market.',
      '"Big moves that had news" shows only the bolts with a headline behind them. It is the quiet setting.',
      '"Every headline" adds a dot for each one, so a busy day gets crowded.',
    ],
    use: [
      'Use the bolt to ask "what was that move?" without opening the news list.',
      'A bolt with no news on a quiet tape is a move from order flow, not from news.',
      'Turn it off (the eye) when you want only price.',
    ],
    watch: 'A headline near a move does not prove it caused it. Many headlines arrive after price has moved.',
  },
  levels: {
    what: "Six price lines: yesterday's high, low and close, the overnight high and low, and today's open.",
    see: [
      'Six grey dashed lines across the chart. Each has a tag on the price axis: PDH, PDL, PDC, ONH, ONL, Open.',
      "The lines show today's numbers. They stay put as you scroll back.",
    ],
    read: [
      'PDH, PDL, PDC: the prior day high, low and close. A day here runs from 18:00 ET to the next afternoon.',
      'ONH, ONL: the overnight high and low, from 18:00 ET to 09:30 ET. They stretch until 09:30, then freeze.',
      'Open: the price at 09:30 ET, when the regular stock-market hours (RTH) begin. It is missing before 09:30.',
    ],
    use: [
      'Many traders watch these prices. Price may stall or turn there, or run through them fast.',
      'Use them as targets for a trade, or as places to take care.',
      'Open is a dividing line: above it buyers lead the day so far, below it sellers. A quick read, not a rule.',
      'Many traders wait for a break of the overnight high or low after 09:30.',
    ],
    watch: 'Lines always show the latest numbers, even over older days on the chart.',
  },

  orb: {
    what: 'The high, low and middle of the first minutes after a start time. Default: 15 minutes from 09:30 ET.',
    see: [
      'Three flat lines across the day: High in green, Middle in grey dashed, Low in red.',
      'While the window is open the lines grow with each new high or low. After it they freeze.',
      'The legend reads "Opening range 15m", or "Candle 03:00 15m" for another start time.',
    ],
    read: [
      'The opening range is the high and low of the first minutes after the 09:30 ET open.',
      'Change the start time and it is the same idea for that time: one candle of that many minutes.',
      'Price above the green line has broken up out of the range. Below the red line, it broke down.',
      'Middle is the halfway price between the high and the low.',
    ],
    use: [
      'Breakout: some traders buy a break above the high and sell a break below the low.',
      'Or they fade it: wait for a break to fail, then trade back toward the middle.',
      'The other side of the range, or the middle, is a common place for the stop.',
      'Wait for the window to end before you trade it. Until then the range is still changing.',
    ],
    watch: 'A bar counts if it starts inside the window. Use bars shorter than the minutes you pick.',
  },

  sess: {
    what: 'The high and low of time windows you choose, each in its own colour. Four are set up for you.',
    see: [
      'For each window that is on: a solid line at its high and a dashed line at its low, in one colour.',
      'Set up: London 02:00-05:00 blue, Asia 20:00-00:00 orange, NY AM 09:30-11:00 green, NY PM 13:30-16:00 pink.',
      'While a window is open its lines move. After it ends they stay flat for the rest of the session.',
    ],
    read: [
      'A session is a block of the day when one group of traders is active, such as London or New York morning.',
      'Its high and low show how far price went during that block.',
      "Price above a window's high has taken out that block's high. Below its low, the low.",
      'You can have up to 8 windows. Each has a name, a start, an end and an on / off switch.',
    ],
    use: [
      "An earlier window's high and low are targets, and places where price may stall.",
      'Traders watch for a break of one, or a sweep: a quick poke past it, then back.',
      'Make a window for the hours you trade, then read its range as your own yardstick.',
    ],
    watch: 'A bar counts if it starts inside the window. On long bars the window edges are rough.',
  },

  noise: {
    what: 'Two lines above and below the open. A move past them is bigger than the usual wobble.',
    see: [
      'Two flat lines for the day: Upper in green, Lower in red. Nothing shows before the open time.',
      'The legend reads "Noise band 0.3". The 0.3 is the multiplier.',
    ],
    read: [
      'They start from the open: the 09:30 ET price, or 01:00 ET if you pick Globex (the overnight market).',
      'The distance is the multiplier times the daily ATR, the typical size of a day range over 14 days.',
      'Example: ATR 300 points and 0.3 puts the lines 90 points above and below the open.',
      'Price inside the lines is ordinary movement. Outside them the move is bigger than usual.',
      'The lines wait until 15 finished sessions are on the chart.',
    ],
    use: [
      'Some traders only take trades after price leaves the band, in that direction.',
      'Others stay out while price sits inside it: nothing has happened yet.',
      'A smaller multiplier puts the lines closer, so price leaves them more often.',
    ],
    watch: 'The lines are fixed by the open and past ranges. They do not widen when the day gets wild.',
  },

  swing: {
    what: 'The latest swing high and swing low that price has not traded beyond yet.',
    see: [
      'Two flat dashed lines: Swing high in red, Swing low in green.',
      'The legend reads "Swings 50". The 50 is the bars each side.',
      'A line appears 50 bars after the turn, and it can jump to another swing.',
    ],
    read: [
      'A swing high is a bar whose high is above the 50 bars before it and the 50 bars after it.',
      'A swing low is the mirror image: its low is under the 50 bars on each side.',
      'This is the same swing the strategy tester uses. It is known only 50 bars late.',
      'A line stays until a bar trades past it. Then it drops to the next older swing still standing, or goes.',
    ],
    use: [
      'Swing highs are where price turned down, swing lows where it turned up.',
      'Many traders aim for the swing on the far side, and put stops just beyond the near one.',
      'More bars each side gives fewer, bigger swings. Fewer bars gives more, smaller ones.',
    ],
    watch: '50 bars is 50 minutes on a 1-minute chart and 250 minutes on a 5-minute chart.',
  },

  equal: {
    what: 'A level where two swing highs, or two swing lows, sit at almost the same price.',
    see: [
      'Two flat dotted lines: Equal highs in red, Equal lows in green.',
      'The legend reads "Equal H/L 50 10": the bars each side, then the tolerance in points.',
      'A line shows only while such a pair exists. It goes when price trades past it.',
    ],
    read: [
      'Swings are found as in Swing high / low: 50 bars each side.',
      'Two highs are equal when the second is at or just under the first, within 10 points.',
      'Price must not have gone above the first one in between. Lows work the same, upside down.',
      'The line sits at the first swing, the more extreme price of the two.',
    ],
    use: [
      'Many stop orders sit just beyond such levels. Traders call this liquidity.',
      'Price is often pulled toward it. Some trade the poke-through and snap-back, others wait for a real break.',
      'Use it as a target, or as a place to be careful with stops.',
    ],
    watch: 'Tolerance is in points. The same number means something different on NQ, ES or gold.',
  },

  rmove: {
    what: 'The size of the current up or down move, with its middle and the 62% to 79% pullback zone.',
    see: [
      'Five flat lines: High and Low in grey, Middle in grey dashed, OTE 62% and OTE 79% in blue dotted.',
      'The legend reads "Move range 200". The 200 is the reversal size in points.',
      'The lines step when the move makes a new extreme or turns the other way.',
    ],
    read: [
      'A move runs from the last turning point to the furthest price since. It turns after a 200-point pullback.',
      'Middle is the halfway price of that move.',
      'The blue zone is where price has given back 62% to 79% of the move. OTE means optimal trade entry.',
      'After an up move the zone sits below the high. After a down move it sits above the low.',
    ],
    use: [
      'Some traders wait for a pullback into the blue zone, then trade back in the direction of the move.',
      'Many read a shallow pullback as strength and a deep one as weakness.',
      'Set the points to the size of move you care about.',
    ],
    watch: 'Nothing shows until price has moved the full reversal size. The zone is a guide, not a promise.',
  },

  rswing: {
    what: 'The range from the latest untouched swing high to swing low, with its middle and 62% to 79% zone.',
    see: [
      'The same five lines as Range of the current move: High, Low, Middle, OTE 62% and OTE 79%.',
      'The legend reads "Swing range 50". The 50 is the bars each side.',
    ],
    read: [
      'The top is the latest swing high not yet passed. The bottom is the latest swing low not yet passed.',
      'It needs both. No range shows while one is missing.',
      'If the low came first, price went up: the blue zone sits below the high. Otherwise above the low.',
      'Middle is the halfway price. The blue zone is 62% to 79% of the way back.',
    ],
    use: [
      'It marks the range price is working in. Its ends are targets, its middle a halfway line.',
      'As with the move range, some traders look for a pullback into the blue zone.',
      'When price passes the high or low, that swing is gone and the range changes.',
    ],
    watch: 'Swings are known 50 bars late, so the range lags the market.',
  },

  fvg: {
    what: 'A hole in price left by a fast move: bar 3 sits fully above bar 1, or fully below it.',
    see: [
      'A shaded box for each gap: green for an up gap, red for a down gap. No lines join one gap to the next.',
      'A box starts at the first of the three bars and runs right until price trades through it.',
      'The legend reads "FVG 0.25". The 0.25 is the smallest gap, in times ATR.',
    ],
    read: [
      'Take three bars in a row. If bar 3 low is above bar 1 high, price jumped up and left an up gap.',
      'A down gap is the reverse: bar 3 high is below bar 1 low.',
      'Gaps under 0.25 times the ATR (the typical bar size over 14 bars) are ignored.',
      'Only the newest open gap on each side is drawn. A bar trading all the way through a gap closes it.',
      'All gaps clear at the start of a new session.',
    ],
    use: [
      'Some traders expect price to come back and test a gap, then trade that return.',
      'An up gap can act as support under price, a down gap as resistance over it.',
      'A bigger smallest-gap setting shows fewer gaps, from stronger moves.',
    ],
    watch: 'A gap is known only when bar 3 closes. Not every gap pulls price back: a hint, not a signal.',
  },

  wk: {
    what: "Last week's high, low and close, and this week's open, as four lines.",
    see: [
      'Four flat lines: Prior week high in red, Prior week low in green.',
      'Prior week close in grey dashed, Week open in orange dotted.',
      'On the first bar of a new week the lines jump to the new numbers.',
    ],
    read: [
      "A week runs from the Sunday 18:00 ET open to Friday's close.",
      "Prior week high and low are last week's extremes. Prior close is where last week ended.",
      "Week open is this week's first price. Above it, the week is up so far.",
    ],
    use: [
      'These are bigger levels than daily ones, so more traders watch them.',
      "Price near last week's high or low: watch for a stall or a break.",
      'Week open works as a dividing line: buyers lead above it, sellers below.',
    ],
    watch: 'Shows only after one full week on the chart, so a short chart may show nothing.',
  },

  mo: {
    what: "Last month's high, low and close, and this month's open, as four lines.",
    see: [
      'Four flat lines: Prior month high in red, Prior month low in green.',
      'Prior month close in grey dashed, Month open in orange dotted.',
      'On the first bar of a new month the lines jump to the new numbers.',
    ],
    read: [
      'A month follows the trading date: its first session starts it.',
      "Prior month high and low are last month's extremes. Prior close is where it ended.",
      "Month open is this month's first price. Above it, the month is up so far.",
    ],
    use: [
      'These are the biggest levels here. Many traders mark them as long-range targets and turning points.',
      'Price near last month high or low: watch for a stall or a break.',
      'Month open works as a dividing line: buyers lead above it, sellers below.',
    ],
    watch: 'Shows only after one full month on the chart, so a short chart may show nothing.',
  },

  topen: {
    what: 'The price at one time of the day, such as midnight, drawn as a line to the end of the session.',
    see: [
      'One orange dashed line. The legend reads "Open 00:00", or the time you set.',
      'It starts at that time and stays flat until the session ends. Before that time, nothing.',
    ],
    read: [
      'It is the opening price of the first bar at or just after your time (ET). The default is 00:00, midnight.',
      'Price above the line is higher than at that time. Below it is lower.',
      'A time of 18:00 or later is the evening that starts the session.',
    ],
    use: [
      'Many traders mark a key time, such as the midnight open, the London open or the 09:30 open.',
      'A simple filter: look for longs above the line and shorts below it.',
      'You can add several, one for each time you care about.',
    ],
    watch: 'If no bar starts within 5 minutes after your time, the line does not draw that day.',
  },

  vaprev: {
    what: "Where most of yesterday's trading happened, as three lines: VAH, POC and VAL.",
    see: [
      'Three flat lines: VAH in blue, POC in orange, VAL in blue.',
      'The legend reads "Prior VA". The lines hold for the whole next session.',
    ],
    read: [
      'The value area is the price band that holds 70% of the contracts traded from 09:30 to 16:00 ET.',
      'VAH is its top (value area high). VAL is its bottom (value area low).',
      'POC, the point of control, is the one price where the most contracts traded.',
      'It is built from the footprint price rows of the prior session.',
    ],
    use: [
      "Open inside yesterday's value area: many expect back and forth between VAL and VAH.",
      'A move out of the area that holds outside is read as a sign of a new direction.',
      'POC is a price many traders return to, so it is used as a magnet and a pivot.',
    ],
    watch: "Built from footprint data. If a day's data has gaps, that day's area is off.",
  },

  dhl: {
    what: 'The highest high and lowest low of the last 5 finished days, as two lines.',
    see: [
      'Two flat lines: High in red, Low in green. The legend reads "5-day H/L".',
      'Days is a setting, from 1 to 60. Today is not counted until it ends.',
    ],
    read: [
      'A day here is a whole session: from 18:00 ET the evening before to the close.',
      'Red is the top of the last N days. Green is the bottom.',
      'Price near red is at a multi-day high. Near green, a multi-day low.',
      'The lines move only when a day ends, or when an old day drops out of the window.',
    ],
    use: [
      'Many stop orders sit beyond these highs and lows. Traders call this liquidity.',
      'Some trade a break of the high. Others trade a failed break: price pokes through, then falls back.',
      'Use 1 day for yesterday, 5 for about a week, 20 for about a month.',
    ],
    watch: 'Sessions include the overnight hours, so these are wider than 09:30-16:00 highs and lows.',
  },
});
})();
