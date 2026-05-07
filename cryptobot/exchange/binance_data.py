"""
Binance data layer. Uses the public REST API for klines and 24h tickers.
No keys required for paper-mode data. Live mode wraps the same client with auth.
"""
from __future__ import annotations
import time
import logging
from typing import List, Dict, Optional
import requests
import pandas as pd

from config import CONFIG

log = logging.getLogger(__name__)

BINANCE_BASE = "https://api.binance.com"


class BinanceData:
    """Pull public market data. Paper mode uses this exclusively."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    # ---------- public endpoints ----------

    def get_24h_tickers(self) -> List[Dict]:
        """All symbols' 24h stats. ~1500 symbols, single call."""
        r = self.session.get(f"{BINANCE_BASE}/api/v3/ticker/24hr", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 200) -> pd.DataFrame:
        """OHLCV candles as a DataFrame."""
        r = self.session.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json()
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "tb_base", "tb_quote", "ignore",
        ])
        for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[c] = df[c].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        return df

    def get_price(self, symbol: str) -> float:
        r = self.session.get(
            f"{BINANCE_BASE}/api/v3/ticker/price",
            params={"symbol": symbol}, timeout=5,
        )
        r.raise_for_status()
        return float(r.json()["price"])

    # ---------- symbol selection ----------

    def pick_top_gainers(self) -> List[Dict]:
        """
        Find top USDT gainers in last 24h that have ALSO pulled back >= 2% from high.
        This avoids buying the absolute peak — the user's chosen filter.
        Returns up to TOP_GAINERS_TO_CONSIDER candidates with metadata.
        """
        try:
            tickers = self.get_24h_tickers()
        except Exception as e:
            log.error("ticker fetch failed: %s", e)
            return []

        candidates = []
        for t in tickers:
            sym = t["symbol"]
            if not sym.endswith(CONFIG.QUOTE_ASSET):
                continue
            if sym in CONFIG.EXCLUDED_SYMBOLS:
                continue
            # exclude leveraged tokens
            if any(sym.startswith(p) or p in sym for p in ("UP", "DOWN", "BULL", "BEAR")):
                # crude but effective: e.g. BTCUPUSDT, ETHDOWNUSDT
                base = sym.replace("USDT", "")
                if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
                    continue

            try:
                pct = float(t["priceChangePercent"])
                quote_vol = float(t["quoteVolume"])
                last = float(t["lastPrice"])
                high = float(t["highPrice"])
            except (KeyError, ValueError):
                continue

            if pct <= 0:
                continue
            if quote_vol < CONFIG.MIN_24H_VOLUME_USDT:
                continue
            if high <= 0:
                continue

            pullback = (high - last) / high
            if pullback < CONFIG.PULLBACK_FROM_HIGH_MIN_PCT:
                continue  # too close to top

            candidates.append({
                "symbol": sym,
                "change_pct_24h": pct,
                "quote_volume": quote_vol,
                "last_price": last,
                "pullback_pct": pullback * 100,
            })

        # rank by 24h gain, tiebreak on volume
        candidates.sort(key=lambda x: (x["change_pct_24h"], x["quote_volume"]), reverse=True)
        return candidates[: CONFIG.TOP_GAINERS_TO_CONSIDER]
