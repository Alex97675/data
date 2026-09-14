import pandas as pd
from ta.momentum import RSIIndicator


def calculate_rsi_states(klines, window=7):
    """Return cross states and min/max open values for the latest RSI crosses."""
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

    offset = len(klines) - len(rsi_series)
    price_history = {
        "rsi_30_up": [],
        "rsi_30_down": [],
        "rsi_70_up": [],
        "rsi_70_down": [],
    }
    last_status_time = None

    # Use the same four-candle open window as rsi_data.py/ohlc_data.py.
    for index in range(len(rsi_series) - 2, 2, -1):
        previous_rsi = float(rsi_series.iloc[index - 1])
        current_rsi = float(rsi_series.iloc[index])
        window_klines = klines[index + offset - 3 : index + offset + 1]
        opens = [float(kline[1]) for kline in window_klines]
        if len(opens) < 4:
            continue

        matched_time = klines[index + offset][0]
        if previous_rsi <= 30 and current_rsi > 30:
            price_history["rsi_30_up"].append(min(opens))
            if last_status_time is None:
                last_status_time = matched_time
        elif previous_rsi >= 30 and current_rsi < 30:
            price_history["rsi_30_down"].append(max(opens))
            if last_status_time is None:
                last_status_time = matched_time
        elif previous_rsi <= 70 and current_rsi > 70:
            price_history["rsi_70_up"].append(min(opens))
            if last_status_time is None:
                last_status_time = matched_time
        elif previous_rsi >= 70 and current_rsi < 70:
            price_history["rsi_70_down"].append(max(opens))
            if last_status_time is None:
                last_status_time = matched_time

    cross_history = {
        "last_status_time": last_status_time,
        "s30u": price_history["rsi_30_up"][0] if price_history["rsi_30_up"] else None,
        "s30u_prev": price_history["rsi_30_up"][1] if len(price_history["rsi_30_up"]) > 1 else None,
        "s30d": price_history["rsi_30_down"][0] if price_history["rsi_30_down"] else None,
        "s30d_prev": price_history["rsi_30_down"][1] if len(price_history["rsi_30_down"]) > 1 else None,
        "s70u": price_history["rsi_70_up"][0] if price_history["rsi_70_up"] else None,
        "s70u_prev": price_history["rsi_70_up"][1] if len(price_history["rsi_70_up"]) > 1 else None,
        "s70d": price_history["rsi_70_down"][0] if price_history["rsi_70_down"] else None,
        "s70d_prev": price_history["rsi_70_down"][1] if len(price_history["rsi_70_down"]) > 1 else None,
    }

    return {
        "cross_now": cross_now,
        "cross_history": cross_history,
    }
