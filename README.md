# Signal Advisor

A **read-only** market advisor: it watches the market and gives you a
BUY / SELL / WAIT signal with a confidence score and full reasoning. It
**never places an order** -- there is no exchange API call anywhere in
this project that can send a trade. It records every signal it issues and
later checks its own accuracy, so the confidence numbers are backed by a
real track record instead of being trusted blindly.

## How a signal is built

Four independent layers are combined into one composite score, each
weighted (weights are configurable in `config.yaml`):

1. **Technical (40%)** -- EMA cross + macro trend, RSI, MACD, Bollinger
   Band position, volume confirmation, support/resistance proximity, and
   ADX (flags weak/choppy markets where signals are less trustworthy).
2. **Multi-timeframe confirmation (20%)** -- checks whether the higher
   timeframes (default 1h and 4h) agree with the primary-timeframe
   (default 15m) trend. A signal fighting the higher-timeframe trend
   scores lower.
3. **Order book (20%)** -- live bid/ask volume imbalance, spread
   tightness, and detection of unusually large resting orders ("walls")
   that can act as short-term support/resistance.
4. **Market structure (20%)** -- perpetual futures funding rate (crowded
   long/short positioning) and open interest trend (is a move backed by
   new money or just position unwinding). This is the closest available
   proxy to "fundamentals" for crypto without a paid news/sentiment API --
   see the doc comment at the top of `src/market_structure.py` for the
   exact interpretation used.

A BUY or SELL is only issued when one side's composite score clears
`min_score_to_signal` (default 70) AND beats the other side by at least
`min_score_gap` (default 15). Otherwise the advisor reports WAIT. This is
deliberately conservative -- it would rather say nothing than guess.

## The journal (self-tracked accuracy)

Every BUY/SELL signal is written to `data/signal_journal.db` with its
full reasoning. A fixed number of candles later (`journal.evaluation_candles`,
default 8), the advisor checks what price actually did and marks the
signal `correct` or `incorrect` based on whether price moved at least
`journal.success_move_pct` (default 0.5%) in the predicted direction. The
dashboard's **Accuracy** card and **Signal Journal** table show this
running record, so you can see over time how reliable the signals
actually are for your chosen market -- and adjust the scoring weights or
thresholds in `config.yaml` accordingly.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# API keys are OPTIONAL here (read-only system). Only set
# DASHBOARD_ADMIN_TOKEN if you want to protect the config-reload endpoint.
```

`config.yaml` defaults to `mexc` via ccxt, same as the trading bot -- change
`exchange.id` for a different exchange. Note: order book, funding rate, and
open interest features work best on exchanges/symbols where those
endpoints are available (funding rate and open interest are futures-only
concepts; if your exchange/symbol doesn't support them, those notes will
simply say "unavailable" and the composite score falls back to the other
three layers).

## Running

```bash
python main.py
```

Then open `http://localhost:5050`. The dashboard shows:
- **Current signal** with a live buy/sell score bar and full breakdown
- **Accuracy** card (correct / incorrect / pending / accuracy %)
- **Technical / Multi-timeframe / Order book / Market structure** panels
  explaining exactly why the current reading is what it is
- **Signal Journal** table of every past signal and its outcome
- **Price & EMA chart** and **Activity Log**

## Tuning

Everything is in `config.yaml`:
- `scoring.weights` -- how much each of the four layers counts
- `scoring.min_score_to_signal` / `min_score_gap` -- how strict the advisor is
- `journal.evaluation_candles` / `success_move_pct` -- how a signal is graded
- `market.confirm_timeframes` -- which higher timeframes to check
- `orderbook.*` -- depth, wall sensitivity, imbalance window

## What this is not

This does not read news, social sentiment, or on-chain data -- "fundamental"
here means exchange-level positioning data (funding/open interest), not a
news feed. It is a decision-support tool, not financial advice, and its
own tracked accuracy is the best evidence of how much to trust it for your
market and timeframe -- let it run and build up a track record before
relying on it.
