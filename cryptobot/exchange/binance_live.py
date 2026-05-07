"""
Live trading wrapper around python-binance Client.
Only imported/instantiated when CONFIG.MODE == 'live' AND LIVE_TRADING_CONFIRMED.

You should run paper mode for at least 2-4 weeks before flipping this on,
and start with way less than 100% of your capital.
"""
from __future__ import annotations
import logging
from typing import Optional
from decimal import Decimal, ROUND_DOWN

from config import CONFIG

log = logging.getLogger(__name__)


class LiveBinance:
    def __init__(self):
        from binance.client import Client  # lazy import - only needed in live mode
        self.client = Client(
            CONFIG.BINANCE_API_KEY,
            CONFIG.BINANCE_API_SECRET,
            testnet=CONFIG.BINANCE_TESTNET,
        )
        self._symbol_info_cache: dict = {}

    def get_balance(self, asset: str = "USDT") -> float:
        bal = self.client.get_asset_balance(asset=asset)
        return float(bal["free"]) if bal else 0.0

    def _symbol_info(self, symbol: str) -> dict:
        if symbol not in self._symbol_info_cache:
            self._symbol_info_cache[symbol] = self.client.get_symbol_info(symbol)
        return self._symbol_info_cache[symbol]

    def _round_qty(self, symbol: str, qty: float) -> float:
        """Binance requires step-size compliant quantities."""
        info = self._symbol_info(symbol)
        step = None
        for f in info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                step = Decimal(f["stepSize"])
                break
        if step is None:
            return qty
        q = Decimal(str(qty)).quantize(step, rounding=ROUND_DOWN)
        return float(q)

    def market_buy(self, symbol: str, usdt_amount: float) -> Optional[dict]:
        """Buy `usdt_amount` worth of `symbol` at market."""
        price = float(self.client.get_symbol_ticker(symbol=symbol)["price"])
        qty = self._round_qty(symbol, usdt_amount / price)
        if qty <= 0:
            log.error("qty rounded to zero for %s", symbol)
            return None
        log.info("LIVE BUY %s qty=%s (~$%.2f)", symbol, qty, usdt_amount)
        return self.client.order_market_buy(symbol=symbol, quantity=qty)

    def market_sell(self, symbol: str, qty: float) -> Optional[dict]:
        qty = self._round_qty(symbol, qty)
        if qty <= 0:
            return None
        log.info("LIVE SELL %s qty=%s", symbol, qty)
        return self.client.order_market_sell(symbol=symbol, quantity=qty)
