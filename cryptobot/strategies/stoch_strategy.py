"""
Strategy A — User's spec:
  Stoch(7,3,10): %K crosses above %D while %K < 20 (oversold).
  Confirmed by a bullish candle on the signal bar.
  Long-only (Binance spot).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from .indicators import stochastic, is_bullish_candle
from config import CONFIG


@dataclass
class Signal:
    action: str            # "buy" | "exit" | "hold"
    reason: str
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None


class StochStrategy:
    name = "Stoch(7,3,10) + Bullish Candle"

    def evaluate(self, df: pd.DataFrame, in_position: bool) -> Signal:
        if len(df) < CONFIG.STOCH_K_PERIOD + CONFIG.STOCH_D_PERIOD + 5:
            return Signal("hold", "warming up")

        d = stochastic(df, CONFIG.STOCH_K_PERIOD, CONFIG.STOCH_K_SMOOTH, CONFIG.STOCH_D_PERIOD)
        # Use the LAST CLOSED bar (-2). -1 is forming, can repaint.
        prev = d.iloc[-3]
        cur = d.iloc[-2]

        if pd.isna(cur["stoch_k"]) or pd.isna(cur["stoch_d"]):
            return Signal("hold", "indicator NaN")

        # ----- exit logic (collapse) -----
        if in_position and CONFIG.SETUP_COLLAPSE_EXIT:
            crossed_down = prev["stoch_k"] >= prev["stoch_d"] and cur["stoch_k"] < cur["stoch_d"]
            if crossed_down:
                return Signal(
                    "exit", "stoch %K crossed below %D — setup collapsed",
                    cur["stoch_k"], cur["stoch_d"],
                )
            return Signal("hold", "in position", cur["stoch_k"], cur["stoch_d"])

        # ----- entry logic -----
        if in_position:
            return Signal("hold", "already in position")

        crossed_up = prev["stoch_k"] <= prev["stoch_d"] and cur["stoch_k"] > cur["stoch_d"]
        oversold = cur["stoch_k"] < CONFIG.STOCH_OVERSOLD
        bullish = is_bullish_candle(cur)

        if crossed_up and oversold and bullish:
            return Signal(
                "buy",
                f"K({cur['stoch_k']:.1f})>D({cur['stoch_d']:.1f}), oversold, bullish candle",
                cur["stoch_k"], cur["stoch_d"],
            )

        # Diagnostic message helps debugging in the dashboard
        bits = []
        bits.append("cross↑" if crossed_up else "no cross")
        bits.append("OS" if oversold else f"K={cur['stoch_k']:.0f}")
        bits.append("bull" if bullish else "bear")
        return Signal("hold", " / ".join(bits), cur["stoch_k"], cur["stoch_d"])
