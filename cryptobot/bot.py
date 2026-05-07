"""
Main bot loop. Polls 1-min klines for selected symbols, runs strategies,
manages positions in paper or live mode.

Architecture choice: REST polling once per ~10s rather than WebSocket,
because (a) we only act on closed bars (1-min candles), (b) much simpler
to debug and deploy on Railway, (c) avoids reconnect/state-sync issues.
WebSocket would only matter for sub-second reaction, which isn't this strategy.
"""
from __future__ import annotations
import time
import logging
import threading
from typing import Dict, List, Optional
from datetime import datetime

from config import CONFIG, safety_check
from exchange.binance_data import BinanceData
from strategies.stoch_strategy import StochStrategy
from strategies.ema_rsi_shadow import EMARsiShadowStrategy
from risk.portfolio import Portfolio
from risk.position import Position
import storage

log = logging.getLogger(__name__)


class TradingBot:
    """Singleton-ish bot. The dashboard reads its `state` dict for live UI."""

    def __init__(self):
        self.data = BinanceData()
        self.live_client = None  # initialized lazily if MODE=live
        self.strategy = StochStrategy()
        self.shadow = EMARsiShadowStrategy()
        self.portfolio = Portfolio(cash_usdt=CONFIG.PAPER_STARTING_BALANCE_USDT)

        # Shadow strategy keeps its own pretend positions; never touches real cash.
        self.shadow_positions: Dict[str, Dict] = {}

        # Symbols currently being scanned. Updated periodically.
        self.active_symbols: List[Dict] = []
        self.last_symbol_refresh: float = 0.0

        # Live state for dashboard (read-only by Flask)
        self.state = {
            "started_at": datetime.utcnow().isoformat(),
            "mode": CONFIG.MODE,
            "running": False,
            "last_tick": None,
            "last_signals": {},      # symbol -> latest signal
            "current_prices": {},    # symbol -> last price
        }
        self._stop = threading.Event()

    # ----------------------- lifecycle -----------------------

    def start(self) -> None:
        safety_check()
        storage.init_db()
        storage.log_event("INFO", f"Bot started in {CONFIG.MODE} mode",
                          {"balance": CONFIG.PAPER_STARTING_BALANCE_USDT})
        if CONFIG.MODE == "live":
            from exchange.binance_live import LiveBinance
            self.live_client = LiveBinance()
            real_balance = self.live_client.get_balance("USDT")
            log.info("Live USDT balance: %.2f", real_balance)
            self.portfolio = Portfolio(cash_usdt=real_balance)

        self.state["running"] = True
        threading.Thread(target=self._run_loop, daemon=True, name="bot-loop").start()

    def stop(self) -> None:
        self._stop.set()
        self.state["running"] = False

    # ----------------------- main loop -----------------------

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                log.exception("tick error: %s", e)
                storage.log_event("ERROR", f"Tick failed: {e}")
            time.sleep(10)  # ~6 ticks per minute; new 1-min bar checked every tick

        log.info("loop stopped")

    def _tick(self) -> None:
        if self.portfolio.halted:
            self.state["last_tick"] = datetime.utcnow().isoformat()
            return

        # 1) refresh symbol list periodically
        if time.time() - self.last_symbol_refresh > CONFIG.SYMBOL_REFRESH_SECONDS:
            self._refresh_symbols()

        if not self.active_symbols:
            self.state["last_tick"] = datetime.utcnow().isoformat()
            return

        # 2) for each symbol: get klines, evaluate, manage
        prices: Dict[str, float] = {}
        for s in self.active_symbols:
            sym = s["symbol"]
            try:
                df = self.data.get_klines(sym, CONFIG.KLINE_INTERVAL, CONFIG.KLINE_HISTORY_LIMIT)
            except Exception as e:
                log.warning("klines failed for %s: %s", sym, e)
                continue

            current_price = float(df.iloc[-1]["close"])
            prices[sym] = current_price
            self.state["current_prices"][sym] = current_price

            # main strategy
            self._handle_strategy(sym, df, current_price)
            # shadow strategy (paper-only comparison)
            self._handle_shadow(sym, df, current_price)

        # 3) also keep prices fresh for any open position whose symbol fell off the gainer list
        for sym in list(self.portfolio.positions.keys()):
            if sym not in prices:
                try:
                    prices[sym] = self.data.get_price(sym)
                    self.state["current_prices"][sym] = prices[sym]
                    pos = self.portfolio.positions[sym]
                    self._manage_open_position(sym, pos, prices[sym], df=None)
                except Exception as e:
                    log.warning("price refresh failed for %s: %s", sym, e)

        # 4) drawdown / kill switch
        self.portfolio.update_drawdown(prices)
        if self.portfolio.halted:
            storage.log_event("CRITICAL", self.portfolio.halt_reason)
            log.critical(self.portfolio.halt_reason)

        self.state["last_tick"] = datetime.utcnow().isoformat()

    # ----------------------- symbol selection -----------------------

    def _refresh_symbols(self) -> None:
        picks = self.data.pick_top_gainers()
        self.active_symbols = picks
        self.last_symbol_refresh = time.time()
        msg = "Top gainers: " + ", ".join(f"{p['symbol']} (+{p['change_pct_24h']:.1f}%, "
                                          f"-{p['pullback_pct']:.1f}% from high)" for p in picks)
        log.info(msg)
        storage.log_event("INFO", msg)

    # ----------------------- main strategy handling -----------------------

    def _handle_strategy(self, symbol: str, df, current_price: float) -> None:
        in_pos = symbol in self.portfolio.positions
        sig = self.strategy.evaluate(df, in_pos)
        self.state["last_signals"][symbol] = {
            "action": sig.action, "reason": sig.reason,
            "stoch_k": sig.stoch_k, "stoch_d": sig.stoch_d,
            "ts": datetime.utcnow().isoformat(),
        }

        if in_pos:
            pos = self.portfolio.positions[symbol]
            # collapse exit comes from strategy; TP/SL from position itself
            self._manage_open_position(symbol, pos, current_price, df, collapse_signal=(sig.action == "exit"))
        else:
            if sig.action == "buy" and self.portfolio.can_open_new():
                self._enter_position(symbol, current_price)

    def _enter_position(self, symbol: str, price: float) -> None:
        prices = dict(self.state["current_prices"])
        prices[symbol] = price
        size = self.portfolio.position_size_usdt(prices)
        if size < 5:  # Binance min notional ~5 USDT
            return
        if size > self.portfolio.cash_usdt:
            size = self.portfolio.cash_usdt
        if size < 5:
            return

        # Live mode: actually place the order
        if CONFIG.MODE == "live" and self.live_client:
            order = self.live_client.market_buy(symbol, size)
            if not order:
                return
            # use the avg fill price if available
            fills = order.get("fills") or []
            if fills:
                price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / \
                        sum(float(f["qty"]) for f in fills)

        pos = self.portfolio.open_position(symbol, price, size, self.strategy.name)
        msg = f"OPEN {symbol} @ {price:.6f} size=${size:.2f} SL={pos.initial_sl:.6f} TP={pos.take_profit:.6f}"
        log.info(msg)
        storage.log_event("TRADE", msg)

    def _manage_open_position(self, symbol: str, pos: Position, price: float,
                              df=None, collapse_signal: bool = False) -> None:
        pos.update_trailing(price)
        exit_reason = pos.check_exit(price)
        if not exit_reason and collapse_signal:
            exit_reason = "setup_collapse"
        if not exit_reason:
            return

        # Live: actually sell
        if CONFIG.MODE == "live" and self.live_client:
            self.live_client.market_sell(symbol, pos.quantity)

        trade = self.portfolio.close_position(symbol, price, exit_reason)
        storage.log_trade(trade, CONFIG.MODE)
        msg = (f"CLOSE {symbol} @ {price:.6f} reason={exit_reason} "
               f"pnl=${trade['pnl_usdt']:+.3f} ({trade['pnl_pct']:+.2f}%)")
        log.info(msg)
        storage.log_event("TRADE", msg)

    # ----------------------- shadow strategy handling -----------------------

    def _handle_shadow(self, symbol: str, df, current_price: float) -> None:
        in_pos = symbol in self.shadow_positions
        sig = self.shadow.evaluate(df, in_pos)

        if in_pos:
            pos = self.shadow_positions[symbol]
            # use same TP/SL rules for fair comparison
            entry = pos["entry_price"]
            move = (current_price - entry) / entry
            should_exit = (
                move >= CONFIG.TAKE_PROFIT_PCT or
                move <= -CONFIG.STOP_LOSS_PCT or
                sig.action == "exit"
            )
            if should_exit:
                trade = {
                    "symbol": symbol, "strategy": self.shadow.name,
                    "entry_price": entry, "exit_price": current_price,
                    "pnl_pct": move * 100,
                    "opened_at": pos["opened_at"],
                    "closed_at": datetime.utcnow().isoformat(),
                }
                storage.log_shadow(trade)
                self.shadow_positions.pop(symbol)
        else:
            if sig.action == "buy":
                self.shadow_positions[symbol] = {
                    "entry_price": current_price,
                    "opened_at": datetime.utcnow().isoformat(),
                }


# global handle for the Flask app
BOT = TradingBot()
