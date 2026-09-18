"""
advisor_engine.py
------------------
The core loop. On every tick it:

  1. Pulls primary-timeframe candles -> runs indicators -> technical.analyze()
  2. Pulls higher-timeframe candles -> multi_timeframe.analyze()
  3. Pulls the live order book -> orderbook.analyze()
  4. Pulls funding rate / open interest (if available) -> market_structure.analyze()
  5. Combines all four into a weighted composite BUY/SELL/WAIT signal
  6. Records the signal in the journal
  7. Checks any previously-pending signals to see if enough time has passed
     to score them correct/incorrect

This module NEVER calls an order-placing endpoint. It only reads data and
writes to its own journal.
"""

import logging
import pandas as pd

from src.indicators import compute_all
from src import technical, multi_timeframe, orderbook, market_structure

logger = logging.getLogger("advisor_engine")


class Advisor:
    def __init__(self, config: dict, exchange_client, journal):
        self.cfg = config
        self.exchange = exchange_client
        self.journal = journal
        self.symbol = config["market"]["symbol"]
        self.timeframe = config["market"]["primary_timeframe"]
        self._prev_open_interest = None
        self.last_reading = None   # most recent full AdvisorReading, for the dashboard
        try:
            self._timeframe_ms = self.exchange.exchange.parse_timeframe(self.timeframe) * 1000
        except Exception:
            self._timeframe_ms = 15 * 60 * 1000  # fallback: assume 15m

    def tick(self):
        raw = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, self.cfg["market"]["candles_lookback"])
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        data = compute_all(df, self.cfg["indicators"])
        current_timestamp = int(data.iloc[-1]["timestamp"])
        price = float(data.iloc[-1]["close"])
        prev_price = float(data.iloc[-2]["close"]) if len(data) > 1 else price
        price_change_pct = (price - prev_price) / prev_price * 100 if prev_price else 0

        # --- resolve any pending signals whose evaluation window has arrived ---
        self._resolve_pending(current_timestamp, price)

        # --- layer 1: technical ---
        tech = technical.analyze(data, self.cfg["indicators"])

        # --- layer 2: multi-timeframe ---
        mtf = multi_timeframe.analyze(
            self.exchange, self.symbol, self.cfg["market"]["confirm_timeframes"],
            self.cfg["indicators"],
        )

        # --- layer 3: order book ---
        ob_reading = None
        if self.cfg["orderbook"]["enabled"]:
            try:
                raw_book = self.exchange.fetch_order_book(self.symbol, self.cfg["orderbook"]["depth"])
                ob_reading = orderbook.analyze(raw_book, self.cfg["orderbook"])
            except Exception as e:
                self.journal.log(f"Order book unavailable this cycle: {e}", "warn")

        # --- layer 4: market structure (funding / open interest) ---
        ms_reading = None
        if self.cfg["market_structure"]["enabled"]:
            futures_symbol = self.cfg["market_structure"].get("futures_symbol", self.symbol)
            funding = self.exchange.fetch_funding_rate(futures_symbol)
            oi = self.exchange.fetch_open_interest(futures_symbol)
            oi_value = None
            if oi:
                oi_value = oi.get("openInterestAmount") or oi.get("openInterestValue")
            ms_reading = market_structure.analyze(funding, oi, self._prev_open_interest, price_change_pct)
            if oi_value is not None:
                self._prev_open_interest = oi_value

        # --- combine into composite score ---
        weights = self.cfg["scoring"]["weights"]
        buy_score = 0.0
        sell_score = 0.0

        buy_score += tech.bullish_score * (weights["technical"] / 100)
        sell_score += tech.bearish_score * (weights["technical"] / 100)

        if mtf.readings:
            buy_score += mtf.agreement_bullish * (weights["multi_timeframe"] / 100)
            sell_score += mtf.agreement_bearish * (weights["multi_timeframe"] / 100)

        if ob_reading:
            ob_bull = max(ob_reading.imbalance, 0) * 100
            ob_bear = max(-ob_reading.imbalance, 0) * 100
            buy_score += ob_bull * (weights["orderbook"] / 100)
            sell_score += ob_bear * (weights["orderbook"] / 100)

        if ms_reading and ms_reading.available:
            buy_score += ms_reading.bullish_score * (weights["market_structure"] / 100)
            sell_score += ms_reading.bearish_score * (weights["market_structure"] / 100)

        buy_score = round(min(buy_score, 100), 1)
        sell_score = round(min(sell_score, 100), 1)

        action = "WAIT"
        confidence = max(buy_score, sell_score)
        min_score = self.cfg["scoring"]["min_score_to_signal"]
        gap = self.cfg["scoring"]["min_score_gap"]

        if buy_score >= min_score and (buy_score - sell_score) >= gap:
            action = "BUY"
            confidence = buy_score
        elif sell_score >= min_score and (sell_score - buy_score) >= gap:
            action = "SELL"
            confidence = sell_score

        ob_notes = self._orderbook_notes(ob_reading)
        ms_notes = ms_reading.notes if ms_reading else []

        reading = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": price,
            "action": action,
            "confidence": confidence,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "technical_notes": tech.notes,
            "trend_strength_adx": round(tech.trend_strength, 1),
            "mtf_notes": mtf.notes,
            "orderbook_notes": ob_notes,
            "market_structure_notes": ms_notes,
        }
        self.last_reading = reading

        if action in ("BUY", "SELL"):
            eval_at_timestamp = current_timestamp + self.cfg["journal"]["evaluation_candles"] * self._timeframe_ms
            self.journal.record_signal(
                symbol=self.symbol, timeframe=self.timeframe, action=action, confidence=confidence,
                price=price, buy_score=buy_score, sell_score=sell_score,
                technical_notes=tech.notes, mtf_notes=mtf.notes,
                orderbook_notes=ob_notes, market_structure_notes=ms_notes,
                eval_candle_index=eval_at_timestamp,
            )
            self.journal.log(f"Signal recorded: {action} {self.symbol} @ {price} (confidence {confidence}%)", "info")
        else:
            self.journal.log(f"WAIT -- buy {buy_score}, sell {sell_score} (threshold {min_score})", "info")

        return reading

    def _orderbook_notes(self, ob_reading):
        if not ob_reading:
            return ["Order book unavailable"]
        notes = [
            f"Bid/ask imbalance: {ob_reading.imbalance:+.2f} (bid_vol={ob_reading.bid_volume}, ask_vol={ob_reading.ask_volume})",
            f"Spread: {ob_reading.spread_pct:.4f}%",
        ]
        if ob_reading.bid_walls:
            notes.append(f"Bid wall(s) at: {', '.join(f'{p:.4f}' for p, s in ob_reading.bid_walls[:3])}")
        if ob_reading.ask_walls:
            notes.append(f"Ask wall(s) at: {', '.join(f'{p:.4f}' for p, s in ob_reading.ask_walls[:3])}")
        return notes

    def _resolve_pending(self, current_timestamp, current_price):
        """eval_at_candle stores a target timestamp (ms), despite the name --
        kept for schema simplicity. A signal is resolved once the latest
        candle's timestamp reaches or passes that target."""
        pending = self.journal.get_pending_signals(self.symbol)
        for sig in pending:
            if current_timestamp >= sig["eval_at_candle"]:
                self.journal.resolve_signal(sig["id"], current_price, self.cfg["journal"]["success_move_pct"])
                self.journal.log(
                    f"Signal #{sig['id']} ({sig['action']} @ {sig['price_at_signal']}) evaluated at {current_price}",
                    "info",
                )
