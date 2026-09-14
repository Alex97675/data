import pandas as pd
from ta.momentum import RSIIndicator


def calculate_last_status(klines, window=7):
    """Return only the latest closed-candle RSI crossing status."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(
        close=pd.Series(closes),
        window=window,
    ).rsi().dropna()

    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    rsi1 = float(rsi_series.iloc[-2])
    rsi2 = float(rsi_series.iloc[-3])

    if rsi2 <= 30 and rsi1 > 30:
        return "30U"
    if rsi2 >= 30 and rsi1 < 30:
        return "30D"
    if rsi2 <= 70 and rsi1 > 70:
        return "70U"
    if rsi2 >= 70 and rsi1 < 70:
        return "70D"

    return "None"
