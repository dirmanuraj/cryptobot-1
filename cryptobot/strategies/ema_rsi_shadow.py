"""
Strategy B — Comparison / "shadow" strategy.
Runs in paper mode alongside the main strategy WITHOUT taking real positions.
Logs hypothetical results so you can see which logic actually performs better
on YOUR data over time.

Logic: EMA(9) crossing above EMA(21) + RSI(14) between 50-70.
This is a momentum-continuation setup, philosophically opposite to mean-reversion
Stoch. Useful comparison.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from .indicators import ema, rsi


@dataclass
class ShadowSignal:
    action: str
    reason: str
    indicators: dict


class EMARsiShadowStrategy:
    name = "Shadow: EMA(9/21) + RSI(14)"

    def evaluate(self, df: pd.DataFrame, in_position: bool) -> ShadowSignal:
        if len(df) < 30:
            return ShadowSignal("hold", "warming up", {})

        close = df["close"]
        e9 = ema(close, 9)
        e21 = ema(close, 21)
        r = rsi(close, 14)

        prev_e9, cur_e9 = e9.iloc[-3], e9.iloc[-2]
        prev_e21, cur_e21 = e21.iloc[-3], e21.iloc[-2]
        cur_rsi = r.iloc[-2]

        ind = {"ema9": float(cur_e9), "ema21": float(cur_e21), "rsi": float(cur_rsi)}

        if in_position:
            crossed_down = prev_e9 >= prev_e21 and cur_e9 < cur_e21
            if crossed_down:
                return ShadowSignal("exit", "EMA9 crossed below EMA21", ind)
            return ShadowSignal("hold", "in position", ind)

        crossed_up = prev_e9 <= prev_e21 and cur_e9 > cur_e21
        rsi_ok = 50 <= cur_rsi <= 70  # momentum but not exhausted

        if crossed_up and rsi_ok:
            return ShadowSignal("buy", f"EMA9>EMA21 cross, RSI={cur_rsi:.1f}", ind)
        return ShadowSignal("hold", "no setup", ind)
