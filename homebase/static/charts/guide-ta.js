/* Homebase Charts -- the indicator guide, part: volume, VWAP, moving averages, trend, momentum and volatility
   indicators. Plain words; the registry and the shape of an entry are in guide.js. */
(function () {
'use strict';
const G = (typeof window !== 'undefined' && window.HBGuide) || require('./guide.js');
G.add({
  volume: {
    what: 'How many contracts traded in each bar. A tall bar means a busy bar.',
    see: [
      'Bars along the bottom of the price pane, one under each candle.',
      'Green bar: buyers were the more aggressive side in that candle. Red bar: sellers were.',
      'The colour follows who pushed harder, not whether the candle closed up or down.',
    ],
    read: [
      'A tall bar means many contracts changed hands. More traders cared.',
      'Judge a bar against its neighbours, not against a fixed number.',
      'A move on big volume is more convincing than the same move on thin volume.',
    ],
    use: [
      'Check that a breakout (price leaving a range) arrives with a big bar.',
      'A huge bar after a long run can mark exhaustion, as many traders exit at once.',
      'Very small bars say price is drifting. Few traders are involved.',
    ],
    watch: 'Volume counts trades. It does not say which side is right, only that people showed up.',
  },

  vwap: {
    what: 'Volume-weighted average price: the average price paid since a start time, busy bars counting more.',
    see: [
      'One purple line on the price pane, 2 pixels thick.',
      'It restarts at its anchor. The default anchor, Session, is the 18:00 New York open.',
      'Optional bands, off by default: dashed lines above and below, in the same colour.',
      'Band 1, 2 and 3 sit 1, 2 and 3 standard deviations away (the usual spread of price around the line).',
    ],
    read: [
      'Price above the line: the average trade so far was cheaper than now. Below: dearer.',
      'Price hugging the line is a balanced day. A long run away from it is a trend day.',
      'A band is a measure of stretch. Price at band 2 or 3 is far from the average.',
    ],
    use: [
      'Many traders treat it as fair price: favour buys above it, sells below it.',
      'Bands show how stretched price is. Far out, price may drift back to the line.',
      'RTH (regular trading hours, from the 09:30 open) starts it at the stock-market open. Week and Month go longer.',
    ],
    watch: 'It is a running average, so late in a session it barely moves. Early on it is jumpy.',
  },

  ema: {
    what: 'Exponential moving average: the average of recent closes, with newer bars counting more.',
    see: [
      'One line on the price pane. A new one is blue and 1 pixel thick; length 20 by default.',
      'Length is how many bars it looks back. Source is the price it uses; close is the price at the end of a bar.',
      'Add several with different lengths. Each new copy takes another colour.',
      'The Timeframe box lets it follow longer bars, such as 1h, while you watch a 1m chart.',
    ],
    read: [
      'Price above a rising line: up trend. Price below a falling line: down trend.',
      'The slope shows speed. A flat line means no clear trend.',
      'A short length hugs price. A long length is smooth and slow.',
    ],
    use: [
      'Trend filter: only look for buys while price is above the line.',
      'Pullback marker: in a trend, price often dips back to the line and may turn there.',
      'Two lengths, such as 20 and 50: the fast one above the slow one means up trend.',
    ],
    watch: 'It lags, so it tells you what already happened. In a sideways market price crosses it again and again.',
  },

  sma: {
    what: 'Simple moving average: the plain average of the last N closes, every bar counting the same.',
    see: [
      'One line on the price pane. A new one is blue and 1 pixel thick; length 50 by default.',
      'Length is how many bars it averages. Source is the price used; close is the default.',
      'It is smoother and slower than an EMA of the same length.',
    ],
    read: [
      'Price above a rising line: up trend. Below a falling line: down trend.',
      'A bar leaving the window can make the line step, since every bar counts the same.',
      'Longer lengths, such as 50 or 200, show the bigger picture.',
    ],
    use: [
      'Trend filter on a higher length: take only trades in the direction of the line.',
      'Many traders watch the same round lengths, so price often reacts near them.',
      'Compare with a short average: fast above slow means price is rising.',
    ],
    watch: 'It lags more than an EMA. In a flat market it gives many false crossings.',
  },

  vwma: {
    what: 'Volume-weighted moving average: the average close of N bars where busy bars count more.',
    see: [
      'One line on the price pane. A new one is blue and 1 pixel thick; length 20 by default.',
      'It uses the close of each bar, weighted by that bar volume.',
      'It sits close to a plain average, then bends toward the busy bars.',
    ],
    read: [
      'VWMA above the plain average of the same length: heavier trading happened at higher prices.',
      'VWMA below it: heavier trading happened at lower prices.',
      'A gap between the two lines shows where the volume really sat.',
    ],
    use: [
      'Use it as a trend line that gives more weight to moves that had real volume.',
      'Place it next to an EMA or SMA of the same length and watch the gap.',
    ],
    watch: 'One huge bar drags it for the next N bars. On thin overnight volume it is no better than a plain average.',
  },

  tema: {
    what: 'Triple exponential moving average: a moving average built to cut the lag of a normal one.',
    see: [
      'One orange line on the price pane, 1 pixel thick; length 20 by default.',
      'It starts once N bars have printed.',
      'It turns sooner than an EMA of the same length.',
    ],
    read: [
      'Same idea as an EMA: price above a rising line is up trend, below a falling line is down trend.',
      'Its turns come earlier, so a turn is a first hint, not proof.',
      'Price far from the line has run a long way from its recent average.',
    ],
    use: [
      'A quicker trend line when an EMA feels too slow.',
      'A trailing guide: in a trend, a close back through it warns that the move is tiring.',
    ],
    watch: 'Less lag means more false turns. It overshoots when price snaps back, and chops in a range.',
  },

  adx: {
    what: 'Average directional index: trend strength from 0 to 100, with two lines showing which side leads.',
    see: [
      'Its own pane under the chart. The ADX line is thicker; by default it is blue.',
      '+DI is a thin green line: the upward push. -DI is a thin red line: the downward push.',
      'Length is 14 by default. No reading shows until about 28 bars have printed.',
    ],
    read: [
      'ADX says how strong the trend is, not which way. Low (under about 20): no trend.',
      'ADX above about 25: a real trend is under way. Rising ADX: the trend is gaining strength.',
      '+DI above -DI: buyers lead. -DI above +DI: sellers lead.',
    ],
    use: [
      'Sort days: with ADX high, use trend rules. With ADX low, use range rules or stay out.',
      'Take trend entries only when ADX is rising and the matching DI line is on top.',
    ],
    watch: 'It lags. A high ADX often arrives late in the move, and a falling ADX only means the trend is slowing.',
  },

  er: {
    what: 'Efficiency ratio: the net move divided by the distance price travelled, from 0 to 1.',
    see: [
      'Its own pane under the chart: one blue line, length 14 by default.',
      'Dashed reference lines at 0.5 and 0.25.',
      'Based on Kaufman: net move over the last N bars, divided by the sum of every bar-to-bar step.',
    ],
    read: [
      'Near 1: price walked in a straight line. Every step went the same way.',
      'Near 0: price went back and forth and ended near where it began. That is chop.',
      'Above 0.5: clean trend. Below 0.25: choppy and hard to trade by trend rules.',
    ],
    use: [
      'A filter: skip trend setups when it sits under 0.25.',
      'Pick the style: high values favour following, low values favour fading moves.',
    ],
    watch: 'It has no direction and no forecast. It only describes how smooth the last N bars were.',
  },

  rsi: {
    what: 'Relative strength index: how strongly price rose versus fell over the last N bars, 0 to 100.',
    see: [
      'Its own pane under the chart: one violet line, length 14 by default.',
      'Dashed reference lines at 70 and 30. The middle is 50.',
      'It uses closes, smoothed the way its inventor Wilder did.',
    ],
    read: [
      'Above 70: price rose hard and may be stretched up. Below 30: stretched down.',
      'Above 50: gains outweigh losses lately. Below 50: losses outweigh gains.',
      'In a strong trend it can sit above 70 or below 30 for a long time.',
    ],
    use: [
      'A stretch warning: do not chase a buy above 70 or a sell below 30.',
      'In an up trend, a dip toward 40 or 50 that turns up can be a pullback entry.',
      'Divergence: price makes a new high but RSI does not. Momentum is fading.',
    ],
    watch: 'Over 70 is not a sell signal. In a strong trend price keeps going while RSI stays high.',
  },

  macd: {
    what: 'MACD: the gap between a fast and a slow moving average, with a smoothed copy of that gap.',
    see: [
      'Its own pane under the chart. Lengths are 12, 26 and 9 by default.',
      'MACD line in blue: fast EMA minus slow EMA. Signal line in orange: a smoothed MACD line.',
      'Histogram bars: MACD minus signal. Green above zero, red below.',
    ],
    read: [
      'MACD above zero: the fast average is above the slow one, which is up trend. Below zero: down.',
      'MACD crossing above the signal line: momentum turning up. Crossing below: turning down.',
      'Taller histogram bars: momentum is growing. Shorter bars: it is fading.',
    ],
    use: [
      'Shrinking bars while price still climbs are an early warning that the push is tiring.',
      'A cross of the signal line is a momentum turn hint, best in the direction of the bigger trend.',
      'Divergence: price makes a new high but MACD does not.',
    ],
    watch: 'It is built from averages, so it lags and whipsaws in a sideways market.',
  },

  stoch: {
    what: 'Stochastic: where the close sits inside the last N bars high-to-low range, 0 to 100.',
    see: [
      'Its own pane under the chart. K length 14, K smoothing 3, D smoothing 3 by default.',
      '%K in blue is the main line. %D in orange is a slower average of %K.',
      'Dashed reference lines at 80 and 20.',
    ],
    read: [
      'Near 100: the close is at the top of its recent range. Near 0: at the bottom.',
      'Above 80: stretched up. Below 20: stretched down.',
      '%K crossing above %D: momentum turning up. Crossing below: turning down.',
    ],
    use: [
      'In a range: look for sells when it turns down from above 80, buys when it turns up from below 20.',
      'In a trend: a dip under 20 that turns up can time an entry with the trend.',
    ],
    watch: 'It is jumpy. In a strong trend it sits above 80 or below 20 for a long time, so fading it loses.',
  },

  mfi: {
    what: 'Money flow index: like RSI, but each move is weighted by volume. 0 to 100.',
    see: [
      'Its own pane under the chart: one violet line, length 14 by default.',
      'Dashed reference lines at 80 and 20.',
      'It uses the typical price of each bar: high, low and close averaged, times volume.',
    ],
    read: [
      'Above 80: money has flowed in heavily on up moves. Below 20: heavily out.',
      'Around 50: buying and selling are balanced.',
      'A move with big volume pushes it more than a move on thin volume.',
    ],
    use: [
      'A second opinion next to RSI: the same stretch on both is a stronger warning.',
      'Divergence: price makes a new high but MFI does not. Volume is not backing the move.',
    ],
    watch: 'Like RSI it can stay stretched in a strong trend. Thin overnight volume makes it noisy.',
  },

  atr: {
    what: 'Average true range: how many points a typical bar moves, counting gaps between bars.',
    see: [
      'Its own pane under the chart: one red line, length 14 by default.',
      'The value is in price points, not dollars.',
      'The red colour does not mean down. ATR has no direction.',
    ],
    read: [
      'True range of a bar is its high minus low, or more if price gapped from the last close.',
      'Rising ATR: price is moving more. Falling ATR: it is quieter.',
      'Compare it with its own past, since a normal level differs for each market and time.',
    ],
    use: [
      'Stop distance: a stop of 1.5 to 2 ATR is outside normal bar noise.',
      'Size: with a wide ATR, take fewer contracts for the same dollar risk.',
      'Target: how far a move can normally go in N bars.',
    ],
    watch: 'It lags: one huge bar lifts it for N bars. It says how much, never which way.',
  },

  bb: {
    what: 'Bollinger bands: the average close of N bars, with bands set by how widely closes have spread.',
    see: [
      'Three lines on the price pane. Length 20 and 2 deviations by default.',
      'Blue upper and lower bands, solid. An orange dashed line between them is the average.',
      'A deviation is the usual spread of closes around the average. The bands sit 2 of them away.',
    ],
    read: [
      'Bands widen when price is wild and narrow when it is quiet.',
      'Price at the upper band: stretched up for these N bars. At the lower band: stretched down.',
      'Narrow bands (a squeeze) often come before a bigger move. The direction is not given.',
    ],
    use: [
      'In a range: price at an outer band tends to return toward the middle line.',
      'In a trend: price rides along the outer band, so a touch is not a turn.',
      'A squeeze tells you to expect a move and to wait for a break.',
    ],
    watch: 'A touch of a band is not a reversal signal. Trends keep price on the band for a long time.',
  },

  keltner: {
    what: 'Keltner channel: an EMA with bands set by average bar size, a smoother channel than Bollinger.',
    see: [
      'Three lines on the price pane. Length 20, range length 20, multiplier 1.5 by default.',
      'Violet upper and lower bands, solid. A grey dashed line between them is the EMA.',
      'Band width is the average true range (the typical bar size, gaps counted) times the multiplier.',
    ],
    read: [
      'Close above the upper band: a strong push up. Below the lower band: a strong push down.',
      'Price inside the channel: normal movement for the recent bar size.',
      'The width follows bar size, so it changes smoothly and does not jump on one bar.',
    ],
    use: [
      'Trend following: in a trend, price tends to hold on one side of the middle line.',
      'Squeeze: when Bollinger bands pull inside this channel, the market is very quiet.',
      'A break outside the channel with volume is a sign of a real move starting.',
    ],
    watch: 'A close outside the band is not a reversal. The multiplier is a choice, not a law.',
  },

  donchian: {
    what: 'Donchian channel: the highest high and lowest low of the last N bars, with the middle.',
    see: [
      'Three lines on the price pane. Length 20 by default.',
      'Blue upper line: the highest high. Blue lower line: the lowest low. Grey dashed: the middle.',
      'The lines step, as old highs and lows drop out of the window.',
    ],
    read: [
      'Price at the upper line: it is at a new N-bar high. At the lower line: a new low.',
      'Width is the size of the recent range. Wide means big swings. Narrow means tight.',
      'Above the middle: the upper half of the range. Below it: the lower half.',
    ],
    use: [
      'Breakouts: a close above the old upper line is a classic trend entry.',
      'Stops: the lower line is a natural trailing stop for a long.',
      'Range play: the lines mark the edges of the box price has been in.',
    ],
    watch: 'Breakouts in a range often fail. The line includes the current bar, so a new high just touches it.',
  },

  supertrend: {
    what: 'Supertrend: a line that trails price and flips side when the trend changes.',
    see: [
      'A thick line on the price pane. Length 10 and multiplier 3 by default.',
      'Green line under price: up trend. Red line over price: down trend.',
      'The line sits at a distance from price based on ATR (the typical bar size).',
    ],
    read: [
      'Green under price: buyers hold. Price stays above it as long as the up trend lasts.',
      'A close through the line flips it to red above price, and the trend turns down.',
      'Distance from price to line shows how much room the trend has been given.',
    ],
    use: [
      'A simple trend filter: take only longs while green, only shorts while red.',
      'A trailing stop: the line only moves in the trend direction.',
      'A flip is an exit or a reverse signal for trend followers.',
    ],
    watch: 'In a sideways market it flips again and again and each flip costs money.',
  },

  rvol: {
    what: 'Relative volume: this bar volume against the usual volume at the same time of day.',
    see: [
      'Its own pane under the chart: bars, green by default.',
      'Dashed reference lines at 1 and 2. It compares with 14 earlier days.',
      'Nothing shows until 10 earlier days have a bar at the same time.',
    ],
    read: [
      '1 means a normal amount for this time. 2 means twice the normal amount, a spike.',
      'Under 1: quieter than usual. Few traders are active.',
      'The base is the median: the middle value of the same bar on earlier days.',
    ],
    use: [
      'Confirm that a breakout has real participation, such as 1.5 or 2 or more.',
      'Spot unusual activity: a news or an unusual open stands out right away.',
      'Stay careful when it sits under 1: moves are less reliable and fills can be worse.',
    ],
    watch: 'It only compares with the same clock time. A bar needs 10 earlier days of data to show.',
  },
});
})();
