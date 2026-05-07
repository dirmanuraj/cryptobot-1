"""
Flask dashboard. Two purposes:
  1) Serve a single HTML page (templates/index.html) that polls /api/state.
  2) Serve the JSON state itself.

Separate from bot.py — Flask runs in main thread, bot in a daemon thread.
"""
from __future__ import annotations
import os
from functools import wraps
from flask import Flask, jsonify, render_template, request, abort

from config import CONFIG
from bot import BOT
import storage


app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"))


def auth(view):
    """Optional shared-token gate. Set DASHBOARD_TOKEN env var to enable."""
    @wraps(view)
    def wrapped(*a, **kw):
        token = CONFIG.DASHBOARD_AUTH_TOKEN
        if token:
            provided = request.args.get("token") or request.headers.get("X-Token")
            if provided != token:
                abort(401)
        return view(*a, **kw)
    return wrapped


@app.route("/")
@auth
def index():
    return render_template("index.html",
                           mode=CONFIG.MODE,
                           starting_balance=CONFIG.PAPER_STARTING_BALANCE_USDT)


@app.route("/api/state")
@auth
def api_state():
    p = BOT.portfolio
    prices = BOT.state["current_prices"]

    open_positions = []
    for sym, pos in p.positions.items():
        px = prices.get(sym, pos.entry_price)
        open_positions.append({
            "symbol": sym,
            "entry": pos.entry_price,
            "current": px,
            "qty": pos.quantity,
            "invested": pos.usdt_invested,
            "pnl_usdt": pos.pnl_usdt(px),
            "pnl_pct": pos.pnl_pct(px),
            "sl": pos.current_sl,
            "tp": pos.take_profit,
            "moved_be": pos.moved_to_breakeven,
            "opened_at": pos.opened_at.isoformat(),
            "strategy": pos.strategy,
        })

    equity = p.total_equity(prices)
    return jsonify({
        "mode": CONFIG.MODE,
        "running": BOT.state["running"],
        "halted": p.halted,
        "halt_reason": p.halt_reason,
        "started_at": BOT.state["started_at"],
        "last_tick": BOT.state["last_tick"],
        "starting_equity": p.starting_equity,
        "cash": p.cash_usdt,
        "equity": equity,
        "peak_equity": p.peak_equity,
        "drawdown_pct": (p.peak_equity - equity) / p.peak_equity * 100 if p.peak_equity > 0 else 0,
        "realized_pnl": p.realized_pnl,
        "trade_count": p.trade_count,
        "wins": p.win_count,
        "losses": p.loss_count,
        "win_rate": (p.win_count / p.trade_count * 100) if p.trade_count else 0,
        "active_symbols": BOT.active_symbols,
        "last_signals": BOT.state["last_signals"],
        "open_positions": open_positions,
        "equity_history": p.equity_history[-300:],
        "recent_trades": storage.recent_trades(25),
        "recent_events": storage.recent_events(40),
        "stats": storage.strategy_stats(),
        "shadow_open": len(BOT.shadow_positions),
        "config": {
            "stoch": [CONFIG.STOCH_K_PERIOD, CONFIG.STOCH_K_SMOOTH, CONFIG.STOCH_D_PERIOD],
            "tp": CONFIG.TAKE_PROFIT_PCT * 100,
            "sl": CONFIG.STOP_LOSS_PCT * 100,
            "be": CONFIG.BREAKEVEN_TRIGGER_PCT * 100,
            "max_dd": CONFIG.MAX_DRAWDOWN_PCT * 100,
            "pos_size": CONFIG.POSITION_SIZE_PCT * 100,
            "max_concurrent": CONFIG.MAX_CONCURRENT_POSITIONS,
        },
    })


@app.route("/healthz")
def health():
    return "ok", 200


def run() -> None:
    BOT.start()
    app.run(host=CONFIG.DASHBOARD_HOST, port=CONFIG.DASHBOARD_PORT,
            debug=False, use_reloader=False)
