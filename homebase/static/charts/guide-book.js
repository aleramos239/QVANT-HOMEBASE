/* HBGuide entries: the book (Level 2) and tape order-flow indicators, in plain words.
   bkimb, bkdepth, bkmicro, bkquote read the book; tspeed, pressure, ddiv read the tape (the executed trades). */
(function () {
'use strict';
const G = (typeof window !== 'undefined' && window.HBGuide) || require('./guide.js');
G.add({
  bkimb: {
    what: 'Shows whether more size waits on the buy side or on the sell side of the book.',
    see: [
      'A histogram in its own pane: green bars above zero, red bars below.',
      'Dashed lines at +0.3 and -0.3. The scale runs from -1 to +1.',
      'One bar for each chart bar: the average over that bar.',
    ],
    read: [
      'The book (Level 2) is the list of orders waiting: buyers below the price, sellers above.',
      'Above zero: more buyers waiting than sellers. Below zero: more sellers waiting.',
      'Past +0.3 or -0.3 the book is clearly lopsided. +1 means only buyers wait, -1 only sellers.',
      'It is (bid minus ask) over (bid plus ask), counted in contracts over the top levels.',
      'Setting "Book levels": top 1, 5 or 10 price levels. The default is 10.',
    ],
    use: [
      'Buyers waiting can mean support under the price. Sellers waiting can mean a lid above it.',
      'It is a hint to read with price, not a signal by itself.',
      'Top 1 jumps around a lot. Top 10 is steadier.',
    ],
    watch: 'Waiting orders can be pulled in a blink. Book data exists only for NQ and ES, from late September 2026.',
  },

  bkdepth: {
    what: 'The total size waiting on the bid side and on the ask side of the book, as two lines.',
    see: [
      'Two lines in their own pane: green for the bid size, red for the ask size.',
      'Size is in contracts, added over the top 10 price levels, then averaged per bar.',
    ],
    read: [
      'Bid = buyers waiting to buy. Ask = sellers waiting to sell. The book is all those waiting orders.',
      'Green above red: more buyers waiting. Red above green: more sellers waiting.',
      'The gap between the lines shows how lopsided the book is.',
      'Both lines falling: the book is thinning out. Both rising: it is filling up.',
    ],
    use: [
      'A thin book can move fast on a few orders. A thick book is harder to push.',
      'This shows how much is waiting. Book imbalance boils it down to one number.',
    ],
    watch: 'Big waiting orders are often pulled before they trade. Book data exists only for NQ and ES, from late September 2026.',
  },

  bkmicro: {
    what: 'A price line that is pulled toward the thinner side of the book, a finer view of fair price.',
    see: [
      'One violet line drawn on the price chart, next to the candles.',
      'One point for each bar: the average over that bar.',
    ],
    read: [
      'Best bid = highest price a buyer waits at. Best ask = lowest price a seller waits at.',
      'The microprice sits between them. It counts the size waiting at each of the two prices.',
      'More size on the bid pulls it up toward the ask. More size on the ask pulls it down.',
      'Line above the price: buyers are heavier at the top of the book. Below: sellers are.',
    ],
    use: [
      'Heavy buyers waiting at the top can mean the next tick is more likely up.',
      'It is a fast, short-term hint. On big timeframes it hugs the price and says little.',
    ],
    watch: 'It reads only the best price on each side, which changes in moments. A bar shows just its average.',
  },

  bkquote: {
    what: 'The best bid and the best ask price over time. The gap between them is the spread.',
    see: [
      'Two lines on the price chart: green for the best bid, red for the best ask.',
      'Each point is the average over one bar.',
    ],
    read: [
      'Best bid = highest price a buyer waits at. Best ask = lowest price a seller waits at.',
      'Buyers in a hurry pay the ask. Sellers in a hurry hit the bid.',
      'The gap is the spread: the cost of getting in and out right away.',
      'Lines tight together: easy trading. A wide gap can mean a thin, nervous market.',
    ],
    use: [
      'Check the gap before you trade. A wide spread means worse fills.',
      'A gap that suddenly widens can come with news or a book that has gone thin.',
    ],
    watch: 'On liquid contracts the gap is often one tick, so the lines sit almost on top of each other.',
  },

  tspeed: {
    what: 'How many trades print each second, and when the pace jumps well above its normal level.',
    see: [
      'A histogram in its own pane. Grey bars: prints per second in that bar.',
      'A bar turns orange when the pace is a burst.',
      'A dashed orange line: the burst line. Orange bars reach above it.',
    ],
    read: [
      'A print is one trade on the tape. The tape is the stream of executed trades.',
      'Tall bar: many trades per second. Short bar: a quiet market.',
      'Orange means at least 3 times the usual pace: 3 x the median of the last 200 bars.',
      'Speed has no direction. Look at the candle to see who won.',
    ],
    use: [
      'A burst can come with news, a level breaking or a stop run. It says look now.',
      'A fast tape can mean wider moves and more slip on your stop.',
      'Setting "Bars for the burst line": how many past bars set the usual pace.',
    ],
    watch: 'It counts prints, not contracts. The burst line needs 10 closed bars of history before it shows.',
  },

  pressure: {
    what: 'Which side pushes harder, buyers or sellers, as one number from -100 to +100.',
    see: [
      'A histogram in its own pane: green bars above zero, red below. Dashed lines at +25 and -25.',
      'A thick orange line: buy against sell volume for the whole session so far.',
      'Thin dotted lines for the parts: Volume grey, Orders cyan, Big prints violet, Sweeps green.',
    ],
    read: [
      'An aggressive buyer hits the ask and wants in now. An aggressive seller hits the bid.',
      'Above zero: buyers push harder. Below zero: sellers do. +100 is all buyers.',
      'Past +25 or -25 is a clear lean. Near zero the two sides are even.',
      'Parts: volume, number of aggressive orders, big prints (10+ contracts), sweeps (one order eating levels).',
      'The bars are the average of the parts, over the last 5 bars by default.',
    ],
    use: [
      'Bars and orange line both on one side: a steady push. Bars turning against the line: the push may fade.',
      'Several dotted parts agreeing is stronger than one part alone.',
      'Price rising while pressure is below zero can be a warning. It is evidence, not a signal.',
    ],
    watch: 'It counts trades that already happened, so it is late. A part with no data is left out of the average.',
  },

  ddiv: {
    what: 'Marks swing highs and lows where price and the buy-minus-sell volume disagree.',
    see: [
      'A small arrow with a delta sign on the candles. It has no pane of its own.',
      'Red arrow above a bar: a swing high with weaker buying behind it.',
      'Green arrow below a bar: a swing low with weaker selling behind it.',
      'The arrow sits on the swing bar but shows up only 5 bars later, once it is confirmed.',
    ],
    read: [
      'Delta = buy volume minus sell volume. Cumulative delta is its running total for the session.',
      'Red: price made a higher high, but the running delta is lower than at the last high.',
      'Green: price made a lower low, but the running delta is higher than at the last low.',
      'A swing is a bar higher (or lower) than the 5 bars on each side. That number is a setting.',
    ],
    use: [
      'It can warn that a push is running out of fuel, near a high or a low.',
      'It carries more weight at a level you already watch than in the middle of nowhere.',
      'Wait for price to react. Price can keep going despite the disagreement.',
    ],
    watch: 'It appears late, 5 bars after the swing, and the running delta restarts at every session start.',
  },
});
})();
