"""
market_structure.py
--------------------
The closest thing to "fundamental" data available programmatically for
crypto: perpetual futures funding rate and open interest. These describe
who is positioned how in the market, as opposed to pure price action.

Interpretation used here (a common, simplified read -- not guaranteed):
  - Funding strongly positive -> longs are paying shorts -> market is
    crowded long -> some risk of a long squeeze (mild bearish tilt).
  - Funding strongly negative -> crowded short -> some risk of a short
    squeeze (mild bullish tilt).
  - Rising open interest WITH rising price -> new money entering longs ->
    trend has real conviction (bullish confirmation).
  - Rising open interest WITH falling price -> new money entering shorts ->
    downtrend has real conviction (bearish confirmation).
  - Falling open interest -> positions being closed, not opened -> any
    move is more likely exhaustion/unwind than a fresh trend.

This module returns a bullish/bearish score contribution, not a verdict on
its own -- it is one input among several in advisor_engine.py.
"""

from dataclasses import dataclass


@dataclass
class MarketStructureReading:
    available: bool
    funding_rate: float = None
    open_interest: float = None
    open_interest_prev: float = None
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    notes: list = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


def analyze(funding_data: dict, oi_now: dict, oi_prev_value: float, price_change_pct: float) -> MarketStructureReading:
    if not funding_data and not oi_now:
        return MarketStructureReading(available=False)

    notes = []
    bullish = 0.0
    bearish = 0.0

    funding_rate = None
    if funding_data:
        funding_rate = funding_data.get("fundingRate")
        if funding_rate is not None:
            # thresholds are illustrative -- typical 8h funding on major pairs
            # sits within +/-0.01%; values beyond +/-0.03% are notably stretched
            if funding_rate > 0.0003:
                bearish += 10
                notes.append(f"Funding rate elevated positive ({funding_rate*100:.4f}%) -- crowded long, squeeze risk")
            elif funding_rate < -0.0003:
                bullish += 10
                notes.append(f"Funding rate elevated negative ({funding_rate*100:.4f}%) -- crowded short, squeeze risk")
            else:
                notes.append(f"Funding rate neutral ({funding_rate*100:.4f}%)")

    open_interest = None
    if oi_now:
        open_interest = oi_now.get("openInterestAmount") or oi_now.get("openInterestValue")
        if open_interest is not None and oi_prev_value:
            oi_change_pct = (open_interest - oi_prev_value) / oi_prev_value * 100 if oi_prev_value else 0
            if oi_change_pct > 1 and price_change_pct > 0:
                bullish += 10
                notes.append(f"Open interest rising (+{oi_change_pct:.1f}%) with price up -- trend has conviction")
            elif oi_change_pct > 1 and price_change_pct < 0:
                bearish += 10
                notes.append(f"Open interest rising (+{oi_change_pct:.1f}%) with price down -- downtrend has conviction")
            elif oi_change_pct < -1:
                notes.append(f"Open interest falling ({oi_change_pct:.1f}%) -- move may be position unwind, not fresh trend")

    return MarketStructureReading(
        available=True,
        funding_rate=funding_rate,
        open_interest=open_interest,
        open_interest_prev=oi_prev_value,
        bullish_score=bullish,
        bearish_score=bearish,
        notes=notes,
    )
