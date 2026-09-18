"""
technical.py
------------
Scores the primary-timeframe indicators into a bullish/bearish contribution.
This is one of four layers combined in advisor_engine.py (the others being
multi-timeframe, order book, and market structure).
"""

from dataclasses import dataclass, field
from src.indicators import detect_trend, support_resistance


@dataclass
class TechnicalReading:
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    notes: list = field(default_factory=list)
    trend_strength: float = 0.0   # ADX value -- how strong the current trend is


def analyze(df, indicator_cfg: dict) -> TechnicalReading:
    if len(df) < 2:
        return TechnicalReading(notes=["Not enough data yet"])

    last = df.iloc[-1]
    prev = df.iloc[-2]
    bullish = 0.0
    bearish = 0.0
    notes = []

    # EMA cross + macro trend
    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
    if crossed_up:
        bullish += 25
        notes.append("EMA fast crossed above slow")
    elif last["ema_fast"] > last["ema_slow"]:
        bullish += 12
        notes.append("EMA fast above slow")
    if crossed_down:
        bearish += 25
        notes.append("EMA fast crossed below slow")
    elif last["ema_fast"] < last["ema_slow"]:
        bearish += 12
        notes.append("EMA fast below slow")

    trend = detect_trend(df, "ema_fast", "ema_slow", "ema_macro")
    if trend == "up":
        bullish += 10
        notes.append("Macro EMA trend up")
    elif trend == "down":
        bearish += 10
        notes.append("Macro EMA trend down")

    # RSI
    r = last["rsi"]
    if r >= indicator_cfg["rsi_bull_level"]:
        bullish += 15
        notes.append(f"RSI {r:.1f} bullish")
    elif r <= indicator_cfg["rsi_bear_level"]:
        bearish += 15
        notes.append(f"RSI {r:.1f} bearish")
    if r >= 75:
        notes.append("RSI overbought -- caution on fresh longs")
    elif r <= 25:
        notes.append("RSI oversold -- caution on fresh shorts")

    # MACD
    if last["macd"] > 0 and last["macd"] > last["macd_signal"]:
        bullish += 20
        notes.append("MACD positive and above signal")
    elif last["macd"] < 0 and last["macd"] < last["macd_signal"]:
        bearish += 20
        notes.append("MACD negative and below signal")

    # Bollinger Band position
    if last["close"] >= last["bb_upper"]:
        notes.append("Price at/above upper Bollinger Band -- extended")
    elif last["close"] <= last["bb_lower"]:
        notes.append("Price at/below lower Bollinger Band -- extended")

    # Volume confirmation
    if last["volume"] > last["volume_ma"]:
        if last["close"] >= prev["close"]:
            bullish += 15
            notes.append("Above-average volume on up move")
        else:
            bearish += 15
            notes.append("Above-average volume on down move")

    # Support / resistance proximity
    support, resistance = support_resistance(df, indicator_cfg["sr_lookback"])
    price = last["close"]
    band = (resistance - support) * 0.05 if resistance > support else 0
    if price >= resistance - band:
        bearish += 5
        notes.append(f"Price near resistance ({resistance:.4f})")
    if price <= support + band:
        bullish += 5
        notes.append(f"Price near support ({support:.4f})")

    adx_val = float(last.get("adx", 0))
    if adx_val < 20:
        notes.append(f"ADX {adx_val:.1f} -- weak/choppy trend, signals less reliable here")

    return TechnicalReading(
        bullish_score=min(bullish, 100),
        bearish_score=min(bearish, 100),
        notes=notes,
        trend_strength=adx_val,
    )
