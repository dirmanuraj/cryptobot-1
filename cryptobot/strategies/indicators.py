"""
Pure-numeric indicator calculations. No I/O, no state.
"""
import numpy as np
import pandas as pd


def stochastic(df: pd.DataFrame, k_period: int = 7, k_smooth: int = 3,
               d_period: int = 10) -> pd.DataFrame:
    """
    Stochastic oscillator with the user's chosen (7, 3, 10) parameters.

    %K_raw   = 100 * (close - lowest_low) / (highest_high - lowest_low)
    %K       = SMA(%K_raw, k_smooth)
    %D       = SMA(%K, d_period)

    Returns DataFrame with two new columns: 'stoch_k', 'stoch_d'.
    """
    out = df.copy()
    low_min = out["low"].rolling(k_period).min()
    high_max = out["high"].rolling(k_period).max()
    rng = (high_max - low_min).replace(0, np.nan)
    k_raw = 100 * (out["close"] - low_min) / rng
    out["stoch_k"] = k_raw.rolling(k_smooth).mean()
    out["stoch_d"] = out["stoch_k"].rolling(d_period).mean()
    return out


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def is_bullish_candle(row: pd.Series) -> bool:
    """Close above open. Simplest definition; we keep it clean."""
    return float(row["close"]) > float(row["open"])
