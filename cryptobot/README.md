# STOCH/SCALP — Crypto Paper-Trading Bot

A 1-minute crypto scalping bot for Binance, built around a Stochastic(7,3,10) +
bullish-candle entry signal, with a built-in shadow strategy for comparison.

**Default mode is paper trading. No real money moves until you explicitly flip
the switch and add API keys.**

---

## ⚠ Read this first

This is a research / paper-trading tool. Crypto 1-minute scalping with retail
indicators is **extremely difficult** to make profitable because:

1. **Fees eat the edge.** Binance taker fees are 0.1% per side = 0.2% round trip.
   The default TP target is 1.0%, so ~20% of every winning trade goes to fees.
   The bot does not yet model fees in paper mode — assume real-world results
   will be ~0.2% worse per trade.
2. **Top gainers are often local tops.** The pullback filter helps but doesn't
   eliminate this risk.
3. **1-minute candles are noisy.** Indicators that work on 1H/4H frequently
   fail on 1m.

Run paper mode for **at least 2-4 weeks** before considering live trading,
and even then start with money you can fully afford to lose.

---

## What it does

- Picks top 3 USDT gainers in last 24h, filtered to ones that have pulled back
  ≥ 2% from their 24h high and have ≥ $5M daily volume.
- For each, polls 1-minute klines from Binance every ~10 seconds.
- Entry: Stoch(7,3,10) %K crosses above %D while %K < 20, on a bullish candle.
- Exit: 1% TP, 1% SL, SL ratchets to breakeven after +0.5%, OR Stoch %K
  crossing back below %D triggers an immediate "setup collapse" exit.
- Position sizing: 25% of equity each, max 3 concurrent.
- Account-level kill switch at 25% drawdown from peak equity.
- Shadow strategy (EMA 9/21 + RSI) runs in parallel for performance comparison.
- Dashboard at `/` shows live equity curve, open positions, signals,
  trade history, and strategy comparison.

---

## Local setup

```bash
# 1. Clone / unzip
cd cryptobot

# 2. Virtualenv
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# (edit .env if you want — defaults are fine for paper)

# 5. Run
python main.py
```

Open http://localhost:8080. You'll see "Scanning…" while it picks symbols
(takes ~10 seconds), then real-time data and signals.

---

## Deploying to Railway

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app): New Project → Deploy from GitHub repo.
3. Railway auto-detects Python (via `railway.toml` + `requirements.txt`).
4. Set environment variables in **Variables** tab:
   - `MODE=paper`
   - `PAPER_BALANCE=100`
   - `DASHBOARD_TOKEN=<some-random-string>` (optional but recommended)
5. Railway gives you a public URL. Visit `https://yourapp.up.railway.app/?token=<your-token>`.

The bot runs 24/7 there. SQLite persists trades to `trades.db` inside the
container — Railway gives ephemeral storage by default, so for long-term
trade history attach a Railway Volume to `/app`.

---

## Going live (only after paper has run for weeks)

1. Create a Binance API key:
   - **Disable withdrawal permission.** You only need spot trading.
   - Restrict to your server's IP if possible.
2. Set environment variables:
   ```
   MODE=live
   LIVE_TRADING=true
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```
3. The bot will start using your real USDT balance instead of paper $100.
4. Position sizes scale to whatever balance it sees — start with a small wallet,
   not your main one.

To test live-mode plumbing without real money first, set
`BINANCE_TESTNET=true` and use [testnet.binance.vision](https://testnet.binance.vision)
keys.

---

## File map

```
cryptobot/
├── main.py                        # entry point
├── config.py                      # all tunable parameters
├── bot.py                         # main trading loop
├── storage.py                     # SQLite trade log
├── exchange/
│   ├── binance_data.py            # public REST data + symbol picker
│   └── binance_live.py            # live order wrapper (only used in live mode)
├── strategies/
│   ├── indicators.py              # Stoch, EMA, RSI math
│   ├── stoch_strategy.py          # main entry/exit logic
│   └── ema_rsi_shadow.py          # comparison strategy
├── risk/
│   ├── portfolio.py               # equity, drawdown, kill switch
│   └── position.py                # per-position TP/SL/breakeven
├── dashboard/
│   ├── app.py                     # Flask routes
│   └── templates/index.html       # live UI
├── requirements.txt
├── Procfile                       # Railway/Heroku
├── railway.toml                   # Railway-specific
└── .env.example
```

---

## Tuning

All tunables live in `config.py`. Common adjustments:

- `STOCH_OVERSOLD` (default 20) — looser threshold = more trades, lower quality.
- `TAKE_PROFIT_PCT` / `STOP_LOSS_PCT` — current 1:1 R:R. Try 1.5:1 by setting TP=1.5%.
- `POSITION_SIZE_PCT` — lower this if drawdown feels too high.
- `MIN_24H_VOLUME_USDT` — raise to 20M+ for stricter liquidity.
- `KLINE_INTERVAL` — try `"5m"` to reduce noise. You'll need to also bump
  the Stoch periods or accept fewer signals.

---

## Roadmap ideas (not built yet)

- Realistic fee + slippage modeling in paper mode.
- Backtest harness to replay historical klines through the same logic.
- Telegram / Discord alerts on entry/exit.
- Trailing stop instead of fixed TP.
- Multi-timeframe confirmation (1m signal + 5m trend filter).
- Walk-forward optimization of Stoch parameters per symbol.

---

## Disclaimer

Not financial advice. Not investment advice. The code may have bugs.
Past paper-trading performance does not predict future live-trading results
(in fact paper results almost always overstate live performance because of
slippage, partial fills, exchange latency, and the psychological pressure
of real money). Use at your own risk.
