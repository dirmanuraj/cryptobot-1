"""
Portfolio-level state and risk.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime

from config import CONFIG
from risk.position import Position


@dataclass
class Portfolio:
    cash_usdt: float
    positions: Dict[str, Position] = field(default_factory=dict)
    peak_equity: float = field(init=False)
    starting_equity: float = field(init=False)
    halted: bool = False
    halt_reason: str = ""
    realized_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    equity_history: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        self.peak_equity = self.cash_usdt
        self.starting_equity = self.cash_usdt

    def total_equity(self, prices: Dict[str, float]) -> float:
        eq = self.cash_usdt
        for pos in self.positions.values():
            px = prices.get(pos.symbol, pos.entry_price)
            eq += pos.quantity * px
        return eq

    def can_open_new(self) -> bool:
        if self.halted:
            return False
        return len(self.positions) < CONFIG.MAX_CONCURRENT_POSITIONS

    def position_size_usdt(self, prices: Dict[str, float]) -> float:
        equity = self.total_equity(prices)
        return equity * CONFIG.POSITION_SIZE_PCT

    def update_drawdown(self, prices: Dict[str, float]) -> None:
        equity = self.total_equity(prices)
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        if dd >= CONFIG.MAX_DRAWDOWN_PCT and not self.halted:
            self.halted = True
            self.halt_reason = (
                f"Max drawdown breached: {dd*100:.1f}% from peak ${self.peak_equity:.2f}. "
                "Trading halted. Restart bot to resume."
            )
        # snapshot for the equity-curve chart
        self.equity_history.append({
            "ts": datetime.utcnow().isoformat(),
            "equity": equity,
            "peak": self.peak_equity,
        })
        # cap memory: keep last 5000 points
        if len(self.equity_history) > 5000:
            self.equity_history = self.equity_history[-5000:]

    def open_position(self, symbol: str, price: float, usdt: float, strategy: str) -> Position:
        if usdt > self.cash_usdt:
            usdt = self.cash_usdt  # safety clamp
        pos = Position.open(symbol, price, usdt, strategy)
        self.positions[symbol] = pos
        self.cash_usdt -= usdt
        return pos

    def close_position(self, symbol: str, exit_price: float, reason: str) -> Dict:
        pos = self.positions.pop(symbol)
        proceeds = pos.quantity * exit_price
        pnl = proceeds - pos.usdt_invested
        self.cash_usdt += proceeds
        self.realized_pnl += pnl
        self.trade_count += 1
        if pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        return {
            "symbol": symbol,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "pnl_usdt": pnl,
            "pnl_pct": (exit_price - pos.entry_price) / pos.entry_price * 100,
            "reason": reason,
            "strategy": pos.strategy,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": datetime.utcnow().isoformat(),
            "duration_sec": (datetime.utcnow() - pos.opened_at).total_seconds(),
        }
