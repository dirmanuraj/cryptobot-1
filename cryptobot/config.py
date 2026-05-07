"""
Central configuration. Edit values here, NOT in the bot code.
All secrets come from environment variables (.env file or Railway vars).
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # ----- MODE -----
    # "paper" = no real orders, simulated fills against live prices
    # "live"  = real Binance orders. REQUIRES API keys + you flipping LIVE_TRADING=true
    MODE: str = os.getenv("MODE", "paper")
    LIVE_TRADING_CONFIRMED: bool = os.getenv("LIVE_TRADING", "false").lower() == "true"

    # ----- CAPITAL -----
    PAPER_STARTING_BALANCE_USDT: float = float(os.getenv("PAPER_BALANCE", "100"))
    POSITION_SIZE_PCT: float = 0.25       # 25% of equity per trade
    MAX_CONCURRENT_POSITIONS: int = 3
    MAX_DRAWDOWN_PCT: float = 0.25        # kill switch at -25% from peak equity

    # ----- STRATEGY: Stoch (7,3,10) + bullish candle -----
    STOCH_K_PERIOD: int = 7
    STOCH_K_SMOOTH: int = 3
    STOCH_D_PERIOD: int = 10
    STOCH_OVERSOLD: float = 20.0
    STOCH_OVERBOUGHT: float = 80.0        # used by exit / collapse logic

    # ----- TRADE MANAGEMENT -----
    TAKE_PROFIT_PCT: float = 0.010        # +1.0%
    STOP_LOSS_PCT: float = 0.010          # -1.0%
    BREAKEVEN_TRIGGER_PCT: float = 0.005  # move SL to entry after +0.5%
    SETUP_COLLAPSE_EXIT: bool = True      # exit if Stoch %K crosses back below %D before TP/SL

    # ----- SYMBOL SELECTION -----
    QUOTE_ASSET: str = "USDT"
    TOP_GAINERS_TO_CONSIDER: int = 3
    PULLBACK_FROM_HIGH_MIN_PCT: float = 0.02   # must be >=2% off 24h high
    MIN_24H_VOLUME_USDT: float = 5_000_000     # liquidity floor
    SYMBOL_REFRESH_SECONDS: int = 300           # rescan top gainers every 5 min
    EXCLUDED_SYMBOLS: List[str] = field(default_factory=lambda: [
        # Stablecoins & wrapped — exclude from gainers list
        "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "FDUSDUSDT", "DAIUSDT",
        "USDPUSDT", "PYUSDUSDT", "EURUSDT", "GBPUSDT",
    ])

    # ----- TIMING -----
    KLINE_INTERVAL: str = "1m"
    KLINE_HISTORY_LIMIT: int = 200        # bars pulled on warmup

    # ----- BINANCE -----
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    # ----- DASHBOARD -----
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = int(os.getenv("PORT", "8080"))   # Railway sets PORT
    DASHBOARD_AUTH_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")  # optional gate

    # ----- LOGGING -----
    DB_PATH: str = os.getenv("DB_PATH", "trades.db")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


CONFIG = Config()


def safety_check() -> None:
    """Loud guardrails before bot starts."""
    if CONFIG.MODE == "live":
        if not CONFIG.LIVE_TRADING_CONFIRMED:
            raise SystemExit(
                "REFUSED: MODE=live but LIVE_TRADING env var is not 'true'. "
                "Set LIVE_TRADING=true to confirm you understand real money is at risk."
            )
        if not CONFIG.BINANCE_API_KEY or not CONFIG.BINANCE_API_SECRET:
            raise SystemExit("REFUSED: live mode requires BINANCE_API_KEY and BINANCE_API_SECRET.")
        print("=" * 60)
        print(" LIVE TRADING MODE ENABLED — REAL MONEY AT RISK")
        print("=" * 60)
    else:
        print(f"[paper] starting balance: ${CONFIG.PAPER_STARTING_BALANCE_USDT}")
