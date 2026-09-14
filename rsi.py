import pandas as pd
from ta.momentum import RSIIndicator

def calculate_rsi_values(klines, window=7):
    """Return the latest four RSI values from kline data."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(
        close=pd.Series(closes),
        window=window,
    ).rsi().dropna()

    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    rsi0 = float(rsi_series.iloc[-1])
    rsi1 = float(rsi_series.iloc[-2])
    rsi2 = float(rsi_series.iloc[-3])
    rsi3 = float(rsi_series.iloc[-4])

    return {
        "rsi0": rsi0,
        "rsi1": rsi1,
        "rsi2": rsi2,
        "rsi3": rsi3,
    }

if __name__ == "__main__":
    sample_klines = [[0, 0, 0, 0, close] for close in range(1, 31)]
    print(calculate_rsi_values(sample_klines))
