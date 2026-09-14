import pandas as pd
from ta.momentum import RSIIndicator


def calculate_rsi_states(klines, window=7):
    """Return current RSI cross states and the latest four closed-candle crosses."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(
        close=pd.Series(closes),
        window=window,
    ).rsi().dropna()

    if len(rsi_series) < 5:
        raise ValueError("At least five RSI values are required")

    # rsi0 is the live candle; use only rsi2 and rsi1 for current states.
    rsi1 = float(rsi_series.iloc[-2])
    rsi2 = float(rsi_series.iloc[-3])

    cross_now = {
        "30_up": "UP" if (rsi2 <= 30 and rsi1 > 30) else "--",
        "70_up": "UP" if (rsi2 <= 70 and rsi1 > 70) else "--",
        "30_down": "DOWN" if (rsi2 >= 30 and rsi1 < 30) else "--",
        "70_down": "DOWN" if (rsi2 >= 70 and rsi1 < 70) else "--",
    }

    last_4_crosses = []
    for index in range(len(rsi_series) - 2, 0, -1):
        previous_rsi = float(rsi_series.iloc[index - 1])
        current_rsi = float(rsi_series.iloc[index])
        status = None

        if previous_rsi <= 30 and current_rsi > 30:
            status = "30U"
        elif previous_rsi >= 30 and current_rsi < 30:
            status = "30D"
        elif previous_rsi <= 70 and current_rsi > 70:
            status = "70U"
        elif previous_rsi >= 70 and current_rsi < 70:
            status = "70D"

        if status:
            last_4_crosses.append({
                "status": status,
                "rsi_value": current_rsi,
                "previous_rsi": previous_rsi,
            })
            if len(last_4_crosses) == 4:
                break

    return {
        "cross_now": cross_now,
        "last_4_crosses": last_4_crosses,
    }
