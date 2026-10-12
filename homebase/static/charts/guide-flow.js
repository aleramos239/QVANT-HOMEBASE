/* Homebase Charts — guide text for the order-flow indicators (footprint, profile, delta, big prints, the Level 2 book
   ones, stop runs, exhaustion). Plain words; see guide.js for the entry shape. Every colour and number here is what
   the code draws: footprint / profile in primitives.js, big orders + gauge in l2layer.js, book marks in
   bookevents.js, stop runs + exhaustion + sweeps + bubbles in flowlayer.js / flowmath.js, rules in bookflow.py. */
(function () {
'use strict';
const G = (typeof window !== 'undefined' && window.HBGuide) || require('./guide.js');
G.add({
  footprint: {
    what: 'Shows, at every price inside each candle, how many contracts were sold and how many were bought.',
    see: [
      'At each price in a candle: sold contracts on the left, bought contracts on the right.',
      'A grey bar behind each row grows with the total traded there. The busiest row gets an orange box.',
      'A red left number or a green right number is an imbalance: one side is 3 times the other or more.',
      'A red or green line beside 3 or more imbalances in a row. Red sits on the left, green on the right.',
      'A small grey triangle on a top or bottom row, and the candle\'s delta (buys minus sells) printed under it.',
    ],
    read: [
      'A buy is a buyer paying the ask. A sell is a seller hitting the bid. Left = sellers, right = buyers.',
      'Green right number: buys here are 3x the sells one row below. Red left number is the mirror.',
      'Orange box: the price with the most volume in that candle (the point of control).',
      'A stacked line means several rows in a row were won by one side: a strong, one-way push.',
      'Triangle on the top row: both sides still traded there, so the move was not finished.',
    ],
    use: [
      'Find where the volume sat. A big orange-box row near a low can be a price buyers defended.',
      'Green lines stacked near a low can mean buyers took control. Red lines near a high, sellers.',
      'Compare the delta under the candle with its colour. A green candle with red delta looks weak.',
      'Use it on the few candles at a level you care about, not to scan the whole chart.',
    ],
    watch: 'Drawn only when you zoom in until candles are wide and price rows are tall. Zoomed out you see plain candles.',
  },
  profile: {
    what: 'Shows how much volume traded at each price this session, as a sideways histogram on the right edge.',
    see: [
      'Horizontal bars grow from the right edge. A longer bar means more contracts traded at that price.',
      'One orange row is the POC (point of control): the single price with the most volume.',
      'Darker blue rows are the value area: the prices holding 70% of the volume. Lighter blue is outside.',
      'Left of it, a faint ghost of the prior session. Optional lines mark its VAH, VAL and POC.',
      'The session restarts at 6 pm New York time, so the profile starts fresh each evening.',
    ],
    read: [
      'Long bar: price spent time and traded a lot there. Short bar: price moved through quickly.',
      'The POC is the most traded price of the session. Many traders treat it as a magnet.',
      'VAH is the value area high and VAL the value area low. Between them is where most trading happened.',
      'A thin zone between two thick ones is a low-volume gap. Price can cross it fast.',
      'A dashed prior-POC line means price has not traded back to that level yet today.',
    ],
    use: [
      'Treat VAH, VAL and POC as places where price may stall or react. Watch the candles there.',
      'Price holding above the value area shows buyers in control. Holding below it, sellers.',
      'Price that falls back into the value area from outside can drift across to the other side.',
      'Thin zones outside the area are where a move can run quickly if price gets there.',
    ],
    watch: 'It shows where volume was, not who won. A tall bar could be mostly buyers or mostly sellers.',
  },
  delta: {
    what: 'Buy volume minus sell volume in each candle: which side was hitting the market harder.',
    see: [
      'A histogram in its own pane, one bar per candle.',
      'Green bar above zero: more contracts were bought than sold. Red bar below zero: more were sold.',
      'The bar\'s height is the difference in contracts. The latest value is in the legend.',
    ],
    read: [
      'A buy is a buyer paying the ask. A sell is a seller hitting the bid. Delta = buys minus sells.',
      'Tall green: buyers were in a hurry. Tall red: sellers were. A short bar: the two were close.',
      'Compare with the candle. Up candle and green delta: buyers drove it. Up candle and red delta: weak.',
    ],
    use: [
      'Check that a breakout candle has strong delta in its own direction. A break on tiny delta is weaker.',
      'A huge one-sided bar at a high or low that price does not follow is effort without result.',
      'Add Cumulative delta to see how this builds up over the session.',
    ],
    watch: 'Busier candles have bigger delta, so compare like with like. It describes the past candle; it is no forecast.',
  },
  cumdelta: {
    what: 'The running total of every candle\'s delta since the session began: is the push building up or down?',
    see: [
      'One orange line in its own pane. It starts again at zero when each session opens (6 pm New York).',
      'The line climbs when buyers hit harder than sellers, and falls when sellers do. Value is in the legend.',
    ],
    read: [
      'Rising line: buyers have been the more aggressive side. Falling line: sellers have been.',
      'A steeper line means a stronger one-sided push in that stretch.',
      'Compare it with price. Both rising together: the move has buying behind it.',
      'Divergence: price makes a new high but the line does not. Buyers are doing less of the work.',
    ],
    use: [
      'In a trend, a line that moves with price supports staying with the move.',
      'Price at a new high while the line sits lower than before: take care chasing it there.',
      'A sudden change of slope at a key level can show the other side stepping in.',
    ],
    watch: 'The level itself means little: read the slope and compare with price. It resets to zero every session.',
  },
  bigprints: {
    what: 'Marks single trades of 25 or more contracts: one order big enough to stand out.',
    see: [
      'A circle on the candle with its contract count. Green below the candle is a buy; red above is a sell.',
      'A bigger circle is a bigger trade. Turn off "Marker size follows the print size" for equal circles.',
      'Optional "Mark sweeps": a vertical line with an arrow, pointing up for buyers and down for sellers.',
    ],
    read: [
      'Green: a buyer paid the ask in one go. Red: a seller hit the bid in one go.',
      'A contract is one futures contract. Most trades are small, so a big print is a large player acting.',
      'A sweep is one order that ate several prices inside one millisecond. It shows more urgency.',
      'Count the circles. Many green ones on one candle means repeated big buying.',
    ],
    use: [
      'Big red prints at a low where price then stops falling: sellers may be spent, or buyers absorbed them.',
      'Big green prints on a breakout candle show real size behind the move.',
      'Raise the minimum if the chart is crowded. Lower it on quiet days.',
    ],
    watch: 'Trades under 10 contracts are never kept, so a minimum below 10 acts like 10. It shows who hit, not why.',
  },
  bigorders: {
    what: 'Draws big resting orders waiting in the Level 2 book: walls of buyers or sellers sitting at a price.',
    see: [
      'Level 2 is the book: the orders waiting to trade at each price. Big ones are drawn as horizontal lines.',
      'Blue line: a big bid (buyers waiting below price). Red line: a big offer (sellers waiting above).',
      'The price axis label gives its size and price. Up to 8 lines a side, fading out 5 seconds after it goes.',
      'Orders that have ended stay as a thick short segment with a mark at its end.',
    ],
    read: [
      'Big means 5 times the usual order size (the median of the last minute), not a fixed number.',
      'The longer the segment, the longer the order stood. A longer stand shows more commitment.',
      'End mark: filled square = traded through and used up. Hollow circle = the owner pulled it. None = faded.',
      'A big blue line below price is a possible floor. A big red line above is a possible ceiling.',
    ],
    use: [
      'Price stalling at a big line that stays: that order is soaking up the flow, a possible turning point.',
      'A line that disappears as price nears it was never a real wall (see Pulled liquidity).',
      'One that keeps refilling after being hit can be a hidden order (see Icebergs).',
      'Raise Multiple, for example to 8, to see only the largest.',
    ],
    watch: 'Orders can be cancelled any moment, so a wall is no promise. Level 2 exists for NQ and ES, from late September.',
  },
  imbalance: {
    what: 'A gauge in the legend: is more size waiting on the bid (buyers) or on the ask (sellers) right now?',
    see: [
      'A small bar and a percent in the indicator\'s legend row, not on the chart.',
      'Blue bar and a plus number: more size on the bid side. Red bar and a minus number: more on the ask.',
      'The bar fills up to 100% and moves live as the book changes.',
    ],
    read: [
      'It adds up the 10 best price levels on each side, then shows bid minus ask over the total.',
      'About 0%: balanced. +50%: bids hold 3 times the contracts of asks. -50%: the reverse.',
      'Heavy bids can act as support and heavy asks as a lid. Both can be cancelled.',
    ],
    use: [
      'Use it as a quick read of who is waiting. It is a live snapshot, so watch how it moves.',
      'A heavy imbalance that price ignores, or that flips quickly, is weak. A steady one at a key level counts.',
      'For the same thing over time, add Book imbalance (over time).',
    ],
    watch: 'Live only: it shows nothing on old days or in Bar Replay. The book is a snapshot with no memory.',
  },
  heatmap: {
    what: 'Paints how much size rested at each price over time, behind the candles: the book as a picture.',
    see: [
      'Coloured blocks behind the candles. Time runs left to right, price up and down.',
      'Faint blue: little size waiting. Orange: more. Strong red: the most on the screen.',
      'A long horizontal streak is an order that sat at one price for a long time.',
      'Optional trade bubbles: green for buyers, red for sellers. A bigger circle is more contracts in one second.',
    ],
    read: [
      'Colour is relative to the biggest size now on screen, so it rescales as you zoom and scroll.',
      'A bright streak under price is a wall of buyers. A bright streak above price is a wall of sellers.',
      'A streak that ends as price arrives was used up or pulled. One that holds while price bounces held.',
      'A bubble is trading that really happened. Big bubbles on a streak mean the wall is being hit.',
    ],
    use: [
      'Look at where price runs into a bright streak. It can stall, bounce or break there.',
      'Watch whether the streak shrinks as price touches it (being eaten) or just vanishes (pulled).',
      'Turn bubbles on to see the fight: who is hitting the wall and how hard.',
    ],
    watch: 'NQ and ES only, on days the book was recorded. Nothing draws zoomed out past 3 days. Walls can be cancelled.',
  },
  absorb: {
    what: 'Marks a big resting order that took heavy trading and still held: it absorbed the flow.',
    see: [
      'A filled triangle at the price and moment it was flagged.',
      'Green pointing up: a bid (buyers waiting) absorbed sellers. Red pointing down: an offer absorbed buyers.',
    ],
    read: [
      'The level was big (at least 4 times the usual) and stood 5 seconds or more.',
      'It was traded into by at least its own opening size, still showed half of it, and price did not break it.',
      'Green: sellers pushed hard and could not move price down. Red: buyers pushed and could not go up.',
      'Someone big is on the other side and taking everything thrown at them.',
    ],
    use: [
      'Green triangle at a low and price lifts away: buyers defended it. Red at a high then a drop: sellers did.',
      'If the level absorbs and then breaks anyway, the big player ran out. Do not stay with it.',
      'Use it as a clue at a level you already watch. Do not trade a single triangle on its own.',
    ],
    watch: 'A first-guess rule: dozens of marks a day can show on NQ. Needs the recorded Level 2 book (NQ, ES).',
  },
  pulled: {
    what: 'Marks a big resting order that was cancelled just as price came close to it.',
    see: [
      'A small X at the price and moment the order vanished.',
      'Blue X: a big bid was pulled (buyers left). Red X: a big offer was pulled (sellers left).',
    ],
    read: [
      'Pulled means removed, not traded: 80% of its size gone within 2 seconds with little trading at it.',
      'Price had to be within 4 ticks (the smallest price steps) of it, and the order had to be big.',
      'A pulled bid takes support away. A pulled offer takes a lid away.',
      'Some call these fake walls: size shown to be seen, taken back before it is tested.',
    ],
    use: [
      'A bid pulled under price, then price falls through: the floor was never real.',
      'An offer pulled above price, then price rises through: the lid was never real.',
      'Do not trust a wall until it has been tested. The X shows which walls were not.',
    ],
    watch: 'A pulled order does not prove a trick: a trader may simply change their mind. Needs recorded Level 2 (NQ, ES).',
  },
  iceberg: {
    what: 'Marks a price hit again and again that keeps reloading: it can be a large hidden order.',
    see: [
      'A diamond where it starts, then a thick line running right while it stays alive.',
      'Green: a bid (a hidden buyer). Red: an offer (a hidden seller).',
      'The label reads x and a number, then the contracts traded: x4 means 4 times the size it showed.',
      'The line is fainter once it has ended.',
    ],
    read: [
      'An iceberg is a big order shown in small pieces. Each time a piece is hit, it fills up again.',
      'At the defaults it traded at least 3 times the biggest size it showed, 30 contracts or more, and reloaded twice.',
      'A higher x number means more hidden size. x6 hides far more than x3.',
      'It ends when the level goes, sits idle for 20 seconds, or price trades through it.',
    ],
    use: [
      'A green iceberg under price that holds: a big buyer is soaking up the selling. It can act as support.',
      'A red iceberg above price that holds: a big seller is capping the move.',
      'If price trades through it, the hidden order is spent. Do not lean on it after that.',
    ],
    watch: 'The hidden size is a guess from trades and the book, not a fact. Needs recorded Level 2 (NQ, ES).',
  },
  stoprun: {
    what: 'Marks a burst of aggressive trades that pushes price through a recent swing high or low.',
    see: [
      'A dashed line at the swing level: the highest high or lowest low of the last 50 candles.',
      'A triangle just past the line pointing the way price ran, with the burst size in contracts beside it.',
      'Green: a run up through a high. Red: a run down through a low.',
      'Filled triangle: the candle closed beyond the level. Hollow with a cross: it closed back inside.',
    ],
    read: [
      'A sweep is one order eating several price levels inside one millisecond. The burst adds up sweeps past the level.',
      'The default is 100 contracts or more. Traders park stop orders just beyond obvious highs and lows.',
      'Filled: price accepted the new area for that candle. Hollow: pushed straight back, a possible trap.',
    ],
    use: [
      'A hollow marker at a high is a failed break. Some traders look for a fade, once price confirms it.',
      'A filled marker followed by more candles beyond the line: the break may be real.',
      'A bigger number means more force behind the break.',
    ],
    watch: 'About 21 a day on NQ 1m at defaults. A burst through a level is a fact; what follows is not.',
  },
  exhaust: {
    what: 'Marks a big one-sided push to a new extreme that went nowhere and was then given back.',
    see: [
      'A short thick horizontal cap at the extreme of the push candle.',
      'A filled arrow on the confirming candle, labelled Ex, pointing the way price turned.',
      'Red arrow down after a buying push to a high. Green arrow up after a selling push to a low.',
    ],
    read: [
      'The push candle makes a new 20-candle extreme with delta (buys minus sells) 4 times the usual or more.',
      'The next 3 candles make no new extreme, and the last closes back past the push candle\'s midpoint.',
      'The aggressive side spent its effort and price would not follow: that side looks exhausted.',
      'The mark appears on that third candle after the push, so it never repaints earlier.',
    ],
    use: [
      'Red arrow near a rally high: the buyers ran out. The idea fails if price trades back above the cap.',
      'Green arrow near a selloff low: the sellers ran out. The idea fails below the cap.',
      'It is best at a level you already watch. Alone it is a weak clue.',
    ],
    watch: 'It confirms 3 candles late, so part of the turn has already happened. About 4 a day on NQ 1m at defaults.',
  },
});
})();
