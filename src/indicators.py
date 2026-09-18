"""
indicators.py
-------------
Pure technical-analysis functions on OHLCV DataFrames. Self-contained --
this project is deliberately separate from the trading bot, so it
duplicates rather than imports its indicator math.
"""

import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(series: pd.Series, period=20, std_mult=2.0):
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    return middle + std_mult * std, middle, middle - std_mult * std


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index -- measures trend STRENGTH (not direction).
    Used to avoid issuing confident signals in a directionless, choppy market.
    """
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume.rolling(period).mean()


def support_resistance(df: pd.DataFrame, lookback: int = 50):
    window = df.tail(lookback)
    return window["low"].min(), window["high"].max()


def detect_trend(df: pd.DataFrame, fast_col: str, slow_col: str, macro_col: str) -> str:
    last = df.iloc[-1]
    fast, slow, macro = last[fast_col], last[slow_col], last[macro_col]
    if fast > slow > macro:
        return "up"
    if fast < slow < macro:
        return "down"
    return "sideways"


def compute_all(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["close"], cfg["ema_fast"])
    out["ema_slow"] = ema(out["close"], cfg["ema_slow"])
    out["ema_trend"] = ema(out["close"], cfg["ema_trend"])
    out["ema_macro"] = ema(out["close"], cfg["ema_macro"])
    out["rsi"] = rsi(out["close"], cfg["rsi_period"])
    macd_line, signal_line, hist = macd(out["close"], cfg["macd_fast"], cfg["macd_slow"], cfg["macd_signal"])
    out["macd"], out["macd_signal"], out["macd_hist"] = macd_line, signal_line, hist
    upper, middle, lower = bollinger_bands(out["close"], cfg["bbands_period"], cfg["bbands_std"])
    out["bb_upper"], out["bb_middle"], out["bb_lower"] = upper, middle, lower
    out["atr"] = atr(out, cfg["atr_period"])
    out["adx"] = adx(out, cfg["adx_period"])
    out["volume_ma"] = volume_ma(out["volume"], cfg["volume_ma_period"])
    return out
