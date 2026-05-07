"""
A single open position and its risk state.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import CONFIG


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: float
    usdt_invested: float
    opened_at: datetime
    strategy: str
    initial_sl: float
    take_profit: float
    current_sl: float
    moved_to_breakeven: bool = False
    high_water_price: float = field(init=False)

    def __post_init__(self):
        self.high_water_price = self.entry_price

    @classmethod
    def open(cls, symbol: str, price: float, usdt: float, strategy: str) -> "Position":
        qty = usdt / price
        sl = price * (1 - CONFIG.STOP_LOSS_PCT)
        tp = price * (1 + CONFIG.TAKE_PROFIT_PCT)
        return cls(
            symbol=symbol,
            entry_price=price,
            quantity=qty,
            usdt_invested=usdt,
            opened_at=datetime.utcnow(),
            strategy=strategy,
            initial_sl=sl,
            take_profit=tp,
            current_sl=sl,
        )

    def update_trailing(self, current_price: float) -> None:
        """Track high-water mark and ratchet SL to breakeven once threshold hit."""
        if current_price > self.high_water_price:
            self.high_water_price = current_price
        if not self.moved_to_breakeven:
            gain = (current_price - self.entry_price) / self.entry_price
            if gain >= CONFIG.BREAKEVEN_TRIGGER_PCT:
                self.current_sl = self.entry_price  # lock in breakeven
                self.moved_to_breakeven = True

    def check_exit(self, current_price: float) -> Optional[str]:
        """Return exit reason if TP/SL hit, else None."""
        if current_price <= self.current_sl:
            return "stop_loss" if not self.moved_to_breakeven else "breakeven_stop"
        if current_price >= self.take_profit:
            return "take_profit"
        return None

    def pnl_usdt(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.quantity

    def pnl_pct(self, current_price: float) -> float:
        return (current_price - self.entry_price) / self.entry_price * 100
