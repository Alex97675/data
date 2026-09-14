import pandas as pd
from ta.momentum import RSIIndicator


def calculate_rsi_cross(klines, window=7):
    """Return the latest closed-candle RSI cross states."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(
        close=pd.Series(closes),
        window=window,
    ).rsi().dropna()

    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    # rsi0 is the live candle; use only rsi2 and rsi1.
    rsi1 = float(rsi_series.iloc[-2])
    rsi2 = float(rsi_series.iloc[-3])

    return {
        "30_up": "UP" if (rsi2 <= 30 and rsi1 > 30) else "--",
        "70_up": "UP" if (rsi2 <= 70 and rsi1 > 70) else "--",
        "30_down": "DOWN" if (rsi2 >= 30 and rsi1 < 30) else "--",
        "70_down": "DOWN" if (rsi2 >= 70 and rsi1 < 70) else "--",
    }
