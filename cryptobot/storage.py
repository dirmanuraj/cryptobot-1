"""
Persistent trade log. Survives restarts so the dashboard isn't blank
every time Railway redeploys.
"""
from __future__ import annotations
import sqlite3
import json
import threading
from typing import List, Dict
from contextlib import contextmanager

from config import CONFIG


_lock = threading.Lock()


@contextmanager
def _conn():
    c = sqlite3.connect(CONFIG.DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def init_db() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, strategy TEXT,
                entry_price REAL, exit_price REAL, quantity REAL,
                pnl_usdt REAL, pnl_pct REAL, reason TEXT,
                opened_at TEXT, closed_at TEXT, duration_sec REAL,
                mode TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS shadow_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, strategy TEXT,
                entry_price REAL, exit_price REAL,
                pnl_pct REAL, opened_at TEXT, closed_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, level TEXT, message TEXT, meta TEXT
            )
        """)


def log_trade(t: Dict, mode: str) -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO trades (symbol, strategy, entry_price, exit_price, quantity,
                pnl_usdt, pnl_pct, reason, opened_at, closed_at, duration_sec, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (t["symbol"], t["strategy"], t["entry_price"], t["exit_price"], t["quantity"],
              t["pnl_usdt"], t["pnl_pct"], t["reason"], t["opened_at"], t["closed_at"],
              t["duration_sec"], mode))


def log_shadow(t: Dict) -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO shadow_trades (symbol, strategy, entry_price, exit_price,
                pnl_pct, opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (t["symbol"], t["strategy"], t["entry_price"], t["exit_price"],
              t["pnl_pct"], t["opened_at"], t["closed_at"]))


def log_event(level: str, message: str, meta: Dict | None = None) -> None:
    from datetime import datetime
    with _lock, _conn() as c:
        c.execute("INSERT INTO events (ts, level, message, meta) VALUES (?, ?, ?, ?)",
                  (datetime.utcnow().isoformat(), level, message, json.dumps(meta or {})))


def recent_trades(limit: int = 50) -> List[Dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def recent_shadow(limit: int = 50) -> List[Dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM shadow_trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def recent_events(limit: int = 100) -> List[Dict]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def strategy_stats() -> Dict:
    """Aggregate stats: realized PnL, win rate per strategy & shadow."""
    with _lock, _conn() as c:
        live_rows = c.execute("""
            SELECT strategy,
                   COUNT(*) as n,
                   SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                   COALESCE(SUM(pnl_usdt), 0) as total_pnl,
                   COALESCE(AVG(pnl_pct), 0) as avg_pct
            FROM trades GROUP BY strategy
        """).fetchall()
        shadow_rows = c.execute("""
            SELECT strategy,
                   COUNT(*) as n,
                   SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                   COALESCE(AVG(pnl_pct), 0) as avg_pct,
                   COALESCE(SUM(pnl_pct), 0) as total_pct
            FROM shadow_trades GROUP BY strategy
        """).fetchall()
    return {
        "live": [dict(r) for r in live_rows],
        "shadow": [dict(r) for r in shadow_rows],
    }
