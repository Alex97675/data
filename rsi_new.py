from collections import deque
from datetime import datetime, timedelta, timezone

import pandas as pd
from ta.momentum import RSIIndicator


def _format_time_gmt8(timestamp):
    """Convert a millisecond timestamp to a readable GMT+8 time."""
    if timestamp is None:
        return None

    gmt8 = timezone(timedelta(hours=8))
    return datetime.fromtimestamp(float(timestamp) / 1000.0, tz=gmt8).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

# ==================== RSI VALUES ====================
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

# ==================== RSI CROSS ====================
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

# ==================== RSI STATES ====================
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

    offset = len(klines) - len(rsi_series)
    price_history = {
        "rsi_30_up": [],
        "rsi_30_down": [],
        "rsi_70_up": [],
        "rsi_70_down": [],
    }
    time_history = {
        "rsi_30_up": [],
        "rsi_30_down": [],
        "rsi_70_up": [],
        "rsi_70_down": [],
    }

    # Use the same four-candle open window as rsi_data.py/ohlc_data.py.
    for index in range(len(rsi_series) - 2, 2, -1):
        previous_rsi = float(rsi_series.iloc[index - 1])
        current_rsi = float(rsi_series.iloc[index])
        window_klines = klines[index + offset - 3 : index + offset + 1]
        opens = [float(kline[1]) for kline in window_klines]
        if len(opens) < 4:
            continue

        matched_time = _format_time_gmt8(klines[index + offset][0])
        if previous_rsi <= 30 and current_rsi > 30:
            price_history["rsi_30_up"].append(min(opens))
            time_history["rsi_30_up"].append(matched_time)
        elif previous_rsi >= 30 and current_rsi < 30:
            price_history["rsi_30_down"].append(max(opens))
            time_history["rsi_30_down"].append(matched_time)
        elif previous_rsi <= 70 and current_rsi > 70:
            price_history["rsi_70_up"].append(min(opens))
            time_history["rsi_70_up"].append(matched_time)
        elif previous_rsi >= 70 and current_rsi < 70:
            price_history["rsi_70_down"].append(max(opens))
            time_history["rsi_70_down"].append(matched_time)

    cross_history = {
        "s30u": price_history["rsi_30_up"][0] if price_history["rsi_30_up"] else None,
        "s30u_time": time_history["rsi_30_up"][0] if time_history["rsi_30_up"] else None,
        "s30u_prev": price_history["rsi_30_up"][1] if len(price_history["rsi_30_up"]) > 1 else None,
        "s30u_prev_time": time_history["rsi_30_up"][1] if len(time_history["rsi_30_up"]) > 1 else None,
        "s30d": price_history["rsi_30_down"][0] if price_history["rsi_30_down"] else None,
        "s30d_time": time_history["rsi_30_down"][0] if time_history["rsi_30_down"] else None,
        "s30d_prev": price_history["rsi_30_down"][1] if len(price_history["rsi_30_down"]) > 1 else None,
        "s30d_prev_time": time_history["rsi_30_down"][1] if len(time_history["rsi_30_down"]) > 1 else None,
        "s70u": price_history["rsi_70_up"][0] if price_history["rsi_70_up"] else None,
        "s70u_time": time_history["rsi_70_up"][0] if time_history["rsi_70_up"] else None,
        "s70u_prev": price_history["rsi_70_up"][1] if len(price_history["rsi_70_up"]) > 1 else None,
        "s70u_prev_time": time_history["rsi_70_up"][1] if len(time_history["rsi_70_up"]) > 1 else None,
        "s70d": price_history["rsi_70_down"][0] if price_history["rsi_70_down"] else None,
        "s70d_time": time_history["rsi_70_down"][0] if time_history["rsi_70_down"] else None,
        "s70d_prev": price_history["rsi_70_down"][1] if len(price_history["rsi_70_down"]) > 1 else None,
        "s70d_prev_time": time_history["rsi_70_down"][1] if len(time_history["rsi_70_down"]) > 1 else None,
    }

    return {"cross_history": cross_history}

# ==================== RSI LAST STATUS ====================
def calculate_rsi_laststatus(klines, window=7):
    """Return the latest closed-candle RSI status and its timestamp."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(close=pd.Series(closes), window=window).rsi().dropna()
    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    offset = len(klines) - len(rsi_series)
    for index in range(len(rsi_series) - 2, 0, -1):
        previous_rsi = rsi_series.iloc[index - 1]
        current_rsi = rsi_series.iloc[index]
        status_time = _format_time_gmt8(klines[index + offset][0])

        if previous_rsi <= 30 and current_rsi > 30:
            return {"last_status": "30U", "last_status_time": status_time}
        if previous_rsi >= 30 and current_rsi < 30:
            return {"last_status": "30D", "last_status_time": status_time}
        if previous_rsi <= 70 and current_rsi > 70:
            return {"last_status": "70U", "last_status_time": status_time}
        if previous_rsi >= 70 and current_rsi < 70:
            return {"last_status": "70D", "last_status_time": status_time}

    return {"last_status": "None", "last_status_time": None}

# ==================== RSI TREND ====================
def calculate_rsi_trend(klines, window=7):
    """Return the RSI trend independently from the other RSI calculations."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(close=pd.Series(closes), window=window).rsi().dropna()
    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    trend_status_history = deque(maxlen=10)
    for index in range(len(rsi_series) - 1, 0, -1):
        previous_rsi = rsi_series.iloc[index - 1]
        current_rsi = rsi_series.iloc[index]
        status = None

        if previous_rsi <= 30 and current_rsi > 30:
            status = "30U"
        elif previous_rsi >= 30 and current_rsi < 30:
            status = "30D"
        elif previous_rsi <= 50 and current_rsi > 50:
            status = "50U"
        elif previous_rsi >= 50 and current_rsi < 50:
            status = "50D"
        elif previous_rsi <= 70 and current_rsi > 70:
            status = "70U"
        elif previous_rsi >= 70 and current_rsi < 70:
            status = "70D"

        if status and (not trend_status_history or trend_status_history[0] != status):
            trend_status_history.appendleft(status)

    trend = "None"
    for index in range(len(trend_status_history) - 1, 0, -1):
        current_status = trend_status_history[index]
        previous_status = trend_status_history[index - 1]
        if previous_status == "30U" and current_status == "50U":
            trend = "uptrand1"
            break
        if previous_status == "50U" and current_status == "70U":
            trend = "uptrand2"
            break
        if previous_status == "70D" and current_status == "50D":
            trend = "downtrand1"
            break
        if previous_status == "50D" and current_status == "30D":
            trend = "downtrand2"
            break

    return {"trend": trend}

# ==================== RSI AVERAGE ====================
def calculate_rsi_average(klines, window=7):
    """Return average_status, MAXU, and MIND independently."""
    if not klines:
        raise ValueError("Kline data is empty")

    closes = [float(kline[4]) for kline in klines]
    rsi_series = RSIIndicator(close=pd.Series(closes), window=window).rsi().dropna()
    if len(rsi_series) < 4:
        raise ValueError("At least four RSI values are required")

    offset = len(klines) - len(rsi_series)
    price_history = {
        "rsi_30_up": [],
        "rsi_30_down": [],
        "rsi_70_up": [],
        "rsi_70_down": [],
    }

    for index in range(len(rsi_series) - 2, 2, -1):
        previous_rsi = rsi_series.iloc[index - 1]
        current_rsi = rsi_series.iloc[index]
        window_klines = klines[index + offset - 3 : index + offset + 1]
        opens = [float(kline[1]) for kline in window_klines]

        if previous_rsi <= 30 and current_rsi > 30:
            price_history["rsi_30_up"].append(min(opens))
        if previous_rsi >= 30 and current_rsi < 30:
            price_history["rsi_30_down"].append(max(opens))
        if previous_rsi <= 70 and current_rsi > 70:
            price_history["rsi_70_up"].append(min(opens))
        if previous_rsi >= 70 and current_rsi < 70:
            price_history["rsi_70_down"].append(max(opens))

    s30u = price_history["rsi_30_up"][0] if price_history["rsi_30_up"] else None
    s70d = price_history["rsi_70_down"][0] if price_history["rsi_70_down"] else None
    s70u = price_history["rsi_70_up"][0] if price_history["rsi_70_up"] else None
    s30d = price_history["rsi_30_down"][0] if price_history["rsi_30_down"] else None

    return {
        "average_status": (s30u + s70d) / 2.0 if s30u and s70d else None,
    }

__all__ = [
    "calculate_rsi_values",
    "calculate_rsi_cross",
    "calculate_rsi_states",
    "calculate_rsi_laststatus",
    "calculate_rsi_trend",
    "calculate_rsi_average",
]
