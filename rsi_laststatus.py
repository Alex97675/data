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

    # Skip rsi0, then search backward for the latest closed-candle crossing.
    for index in range(len(rsi_series) - 2, 0, -1):
        previous_rsi = rsi_series.iloc[index - 1]
        current_rsi = rsi_series.iloc[index]

        if previous_rsi <= 30 and current_rsi > 30:
            return "30U"
        if previous_rsi >= 30 and current_rsi < 30:
            return "30D"
        if previous_rsi <= 70 and current_rsi > 70:
            return "70U"
        if previous_rsi >= 70 and current_rsi < 70:
            return "70D"

    return "None"
