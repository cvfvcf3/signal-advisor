"""
exchange_client.py
-------------------
Read-only ccxt wrapper. This project never calls create_order -- it only
ever fetches data. Kept deliberately minimal for that reason.
"""

import os
import time
import logging

import ccxt

logger = logging.getLogger("exchange_client")


class ExchangeClient:
    def __init__(self, exchange_cfg: dict):
        self.exchange_id = exchange_cfg["id"]
        exchange_class = getattr(ccxt, self.exchange_id)
        params = {"enableRateLimit": True}
        api_key = os.getenv("EXCHANGE_API_KEY", "")
        api_secret = os.getenv("EXCHANGE_API_SECRET", "")
        if api_key and api_secret:
            params["apiKey"] = api_key
            params["secret"] = api_secret
        self.exchange = exchange_class(params)
        if exchange_cfg.get("sandbox") and hasattr(self.exchange, "set_sandbox_mode"):
            self.exchange.set_sandbox_mode(True)

    def _retry(self, fn, *args, attempts=3, delay=2, **kwargs):
        last_err = None
        for i in range(attempts):
            try:
                return fn(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                last_err = e
                logger.warning("Retryable error (%d/%d): %s", i + 1, attempts, type(e).__name__)
                time.sleep(delay)
            except ccxt.ExchangeError as e:
                # not retryable (e.g. unsupported endpoint) -- surface immediately
                raise
        raise last_err

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300):
        return self._retry(self.exchange.fetch_ohlcv, symbol, timeframe=timeframe, limit=limit)

    def fetch_order_book(self, symbol: str, depth: int = 50):
        return self._retry(self.exchange.fetch_order_book, symbol, limit=depth)

    def fetch_funding_rate(self, symbol: str):
        """Only meaningful for perpetual futures markets. Returns None if unsupported."""
        if not self.exchange.has.get("fetchFundingRate"):
            return None
        try:
            return self._retry(self.exchange.fetch_funding_rate, symbol, attempts=1)
        except Exception as e:
            logger.info("Funding rate unavailable for %s: %s", symbol, e)
            return None

    def fetch_open_interest(self, symbol: str):
        if not self.exchange.has.get("fetchOpenInterest"):
            return None
        try:
            return self._retry(self.exchange.fetch_open_interest, symbol, attempts=1)
        except Exception as e:
            logger.info("Open interest unavailable for %s: %s", symbol, e)
            return None
