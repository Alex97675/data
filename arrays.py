import pandas as pd
from ta.momentum import RSIIndicator


def calculate_rsi_array(klines, window=7):
    """Return the complete RSI array for frontend/chart use."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(
        close=pd.Series(closes),
        window=window,
    ).rsi().dropna()

    return [float(value) for value in rsi_series.tolist()]


def calculate_macd_arrays(klines, fast=12, slow=26, signal=9):
    """Return the complete MACD, signal, and histogram arrays."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = pd.Series([float(kline[4]) for kline in klines])
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_series = ema_fast - ema_slow
    signal_series = macd_series.ewm(span=signal, adjust=False).mean()
    histogram_series = macd_series - signal_series

    return {
        "macd_line_array": [float(value) for value in macd_series.tolist()],
        "macd_signal_array": [float(value) for value in signal_series.tolist()],
        "macd_histogram_array": [float(value) for value in histogram_series.tolist()],
    }

__all__ = [
    "calculate_rsi_array",
    "calculate_macd_arrays",
]
