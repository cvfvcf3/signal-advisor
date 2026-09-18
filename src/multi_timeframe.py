"""
multi_timeframe.py
-------------------
Checks whether higher timeframes agree with the primary-timeframe signal.
A 15-minute BUY that lines up with an uptrend on the 1h and 4h charts is a
much stronger signal than one that fights the higher-timeframe trend.
"""

from dataclasses import dataclass, field
from src.indicators import compute_all, detect_trend


@dataclass
class TimeframeReading:
    timeframe: str
    trend: str   # "up" | "down" | "sideways"


@dataclass
class MultiTimeframeResult:
    readings: list = field(default_factory=list)
    agreement_bullish: float = 0.0   # 0-100
    agreement_bearish: float = 0.0
    notes: list = field(default_factory=list)


def analyze(exchange_client, symbol: str, timeframes: list, indicator_cfg: dict, candles: int = 150) -> MultiTimeframeResult:
    readings = []
    for tf in timeframes:
        try:
            raw = exchange_client.fetch_ohlcv(symbol, tf, candles)
        except Exception:
            continue
        if len(raw) < 60:
            continue
        import pandas as pd
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        data = compute_all(df, indicator_cfg)
        trend = detect_trend(data, "ema_fast", "ema_slow", "ema_macro")
        readings.append(TimeframeReading(timeframe=tf, trend=trend))

    if not readings:
        return MultiTimeframeResult()

    up_count = sum(1 for r in readings if r.trend == "up")
    down_count = sum(1 for r in readings if r.trend == "down")
    total = len(readings)

    bullish = (up_count / total) * 100
    bearish = (down_count / total) * 100

    notes = [f"{r.timeframe} trend: {r.trend}" for r in readings]

    return MultiTimeframeResult(
        readings=readings,
        agreement_bullish=round(bullish, 1),
        agreement_bearish=round(bearish, 1),
        notes=notes,
    )
