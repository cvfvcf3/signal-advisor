"""
orderbook.py
------------
Turns a raw ccxt order book (bids/asks) into a small set of signals:

  - imbalance: is there more resting buy-side or sell-side volume near the
    current price? (a simple proxy for short-term buying/selling pressure)
  - spread_pct: how tight the market currently is (wide spread = thin/risky
    liquidity, signals should be trusted less)
  - walls: unusually large orders sitting at a specific price -- often act
    as short-term support/resistance because they must be absorbed before
    price can move through them
"""

from dataclasses import dataclass, field


@dataclass
class OrderBookReading:
    mid_price: float
    spread_pct: float
    bid_volume: float
    ask_volume: float
    imbalance: float          # -1 (all sell pressure) .. +1 (all buy pressure)
    bid_walls: list = field(default_factory=list)   # [(price, size), ...]
    ask_walls: list = field(default_factory=list)


def analyze(order_book: dict, cfg: dict) -> OrderBookReading:
    bids = order_book.get("bids", [])[: cfg["imbalance_levels"]]
    asks = order_book.get("asks", [])[: cfg["imbalance_levels"]]

    if not bids or not asks:
        return OrderBookReading(0, 0, 0, 0, 0)

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread_pct = (best_ask - best_bid) / mid * 100 if mid else 0

    bid_volume = sum(size for _, size in bids)
    ask_volume = sum(size for _, size in asks)
    total = bid_volume + ask_volume
    imbalance = (bid_volume - ask_volume) / total if total > 0 else 0

    # wall detection over a wider window than the imbalance calc, since walls
    # further from best price still matter as future support/resistance
    wide_bids = order_book.get("bids", [])[: cfg["depth"]]
    wide_asks = order_book.get("asks", [])[: cfg["depth"]]
    bid_walls = _find_walls(wide_bids, cfg["wall_size_multiplier"])
    ask_walls = _find_walls(wide_asks, cfg["wall_size_multiplier"])

    return OrderBookReading(
        mid_price=mid,
        spread_pct=round(spread_pct, 4),
        bid_volume=round(bid_volume, 4),
        ask_volume=round(ask_volume, 4),
        imbalance=round(imbalance, 3),
        bid_walls=bid_walls,
        ask_walls=ask_walls,
    )


def _find_walls(levels: list, multiplier: float):
    if not levels:
        return []
    sizes = [size for _, size in levels]
    avg = sum(sizes) / len(sizes)
    threshold = avg * multiplier
    return [(price, size) for price, size in levels if size >= threshold and threshold > 0]
