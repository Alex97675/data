import datetime

import pandas as pd

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9


def _format_time_gmt8(timestamp):
    gmt8 = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.fromtimestamp(
        float(timestamp) / 1000.0,
        gmt8,
    ).strftime("%Y-%m-%d %H:%M:%S")


def _calculate_macd_series(klines, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    if not klines:
        raise ValueError("Kline data is empty")
    closes = pd.Series([float(kline[4]) for kline in klines])
    fast_ema = closes.ewm(span=fast, adjust=False).mean()
    slow_ema = closes.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal, macd_line - macd_signal


# ==================== MACD VALUES ====================
def calculate_macd_values(klines):
    macd_line, macd_signal, macd_histogram = _calculate_macd_series(klines)
    if len(macd_line) < 5:
        raise ValueError("At least five MACD values are required")
    return {
        "latest_macd_line": f"{macd_line.iloc[-1]:.8f}",
        "previous_macd_line": f"{macd_line.iloc[-2]:.8f}",
        "previous_2_macd_line": f"{macd_line.iloc[-3]:.8f}",
        "previous_3_macd_line": f"{macd_line.iloc[-4]:.8f}",
        "previous_4_macd_line": f"{macd_line.iloc[-5]:.8f}",
        "latest_macd_signal": f"{macd_signal.iloc[-1]:.8f}",
        "previous_macd_signal": f"{macd_signal.iloc[-2]:.8f}",
        "previous_2_macd_signal": f"{macd_signal.iloc[-3]:.8f}",
        "previous_3_macd_signal": f"{macd_signal.iloc[-4]:.8f}",
        "previous_4_macd_signal": f"{macd_signal.iloc[-5]:.8f}",
        "latest_macd_histogram": f"{macd_histogram.iloc[-1]:.8f}",
        "previous_macd_histogram": f"{macd_histogram.iloc[-2]:.8f}",
        "previous_2_macd_histogram": f"{macd_histogram.iloc[-3]:.8f}",
        "previous_3_macd_histogram": f"{macd_histogram.iloc[-4]:.8f}",
        "previous_4_macd_histogram": f"{macd_histogram.iloc[-5]:.8f}",
    }


# ==================== MACD ARRAYS ====================
def calculate_macd_arrays(klines):
    macd_line, macd_signal, macd_histogram = _calculate_macd_series(klines)
    return {
        "macd_line_array": [float(value) for value in macd_line.tolist()],
        "macd_signal_array": [float(value) for value in macd_signal.tolist()],
        "macd_histogram_array": [float(value) for value in macd_histogram.tolist()],
    }


# ==================== MACD CROSS ====================
def calculate_macd_cross(klines):
    macd_line, macd_signal, _ = _calculate_macd_series(klines)
    if len(macd_line) < 3:
        raise ValueError("At least three MACD values are required")
    previous_macd_line = macd_line.iloc[-2]
    previous_2_macd_line = macd_line.iloc[-3]
    previous_macd_signal = macd_signal.iloc[-2]
    previous_2_macd_signal = macd_signal.iloc[-3]
    return {
        "macd_upcross": bool(
            previous_2_macd_line <= previous_2_macd_signal
            and previous_macd_line > previous_macd_signal
        ),
        "macd_downcross": bool(
            previous_2_macd_line >= previous_2_macd_signal
            and previous_macd_line < previous_macd_signal
        ),
    }


# ==================== MACD STATE ====================
def calculate_macd_state(klines):
    macd_line, macd_signal, _ = _calculate_macd_series(klines)
    previous_macd_line = macd_line.iloc[-2]
    previous_macd_signal = macd_signal.iloc[-2]
    return {
        "macd_line_up": bool(previous_macd_line > 0),
        "macd_line_down": bool(previous_macd_line < 0),
        "macd_up": bool(previous_macd_line > previous_macd_signal),
        "macd_down": bool(previous_macd_line < previous_macd_signal),
    }


# ==================== MACD TREND ====================
def calculate_macd_trend(klines):
    macd_line, macd_signal, _ = _calculate_macd_series(klines)
    if len(macd_line) < 3:
        raise ValueError("At least three MACD values are required")
    trend = "None"
    for index in range(len(macd_line) - 2, 0, -1):
        if macd_line.iloc[index - 1] <= macd_signal.iloc[index - 1] and macd_line.iloc[index] > macd_signal.iloc[index]:
            trend = "UP"
            break
        if macd_line.iloc[index - 1] >= macd_signal.iloc[index - 1] and macd_line.iloc[index] < macd_signal.iloc[index]:
            trend = "DOWN"
            break
    return {"macd_trend": trend}


# ==================== MACD AVERAGE ====================
def calculate_macd_average(klines):
    macd_line, _, _ = _calculate_macd_series(klines)
    if len(macd_line) < 4:
        raise ValueError("At least four MACD values are required")
    values = [float(value) for value in macd_line.iloc[-5:-1]]
    peaks = calculate_macd_peaks(klines)
    peak_value = peaks["macd_peak"]["macd_value"]
    trough_value = peaks["macd_trough"]["macd_value"]
    return {
        "macd_min": f"{min(values):.8f}",
        "macd_max": f"{max(values):.8f}",
        "macd_average": f"{(peak_value + trough_value) / 2.0:.8f}",
    }


# ==================== MACD LIMITS ====================
def calculate_macd_limits(klines):
    """Return the latest MACD/signal cross limits from closed candles."""
    macd_line, macd_signal, _ = _calculate_macd_series(klines)
    if len(macd_line) < 5:
        raise ValueError("At least five MACD values are required")

    up_limit = None
    down_limit = None
    up_cross_line = None
    down_cross_line = None
    for index in range(len(macd_line) - 2, 2, -1):
        previous_macd_line = macd_line.iloc[index]
        previous_2_macd_line = macd_line.iloc[index - 1]
        previous_macd_signal = macd_signal.iloc[index]
        previous_2_macd_signal = macd_signal.iloc[index - 1]
        window = macd_line.iloc[index - 3 : index + 1]

        if up_limit is None and previous_macd_line > previous_macd_signal and previous_2_macd_line < previous_2_macd_signal:
            up_limit = float(min(window))
            up_cross_line = float(previous_macd_line)
        if down_limit is None and previous_macd_line < previous_macd_signal and previous_2_macd_line > previous_2_macd_signal:
            down_limit = float(max(window))
            down_cross_line = float(previous_macd_line)
        if up_limit is not None and down_limit is not None:
            break

    return {
        "macd_uplimit": up_limit,
        "macd_downlimit": down_limit,
        "uplimit_cross_line": up_cross_line,
        "downlimit_cross_line": down_cross_line,
    }


# ==================== MACD INITIAL CROSSES ====================
def calculate_macd_initial_crosses(klines):
    """Return first zero-line cross price/time values in GMT+8."""
    macd_line, _, _ = _calculate_macd_series(klines)
    offset = len(klines) - len(macd_line)
    initial_up = None
    initial_down = None

    for index in range(len(macd_line) - 2, 0, -1):
        previous_2_macd_line = macd_line.iloc[index - 1]
        previous_macd_line = macd_line.iloc[index]
        kline_index = index + offset
        if not 0 <= kline_index < len(klines):
            continue

        item = {
            "price": float(klines[kline_index][1]),
            "time": _format_time_gmt8(klines[kline_index][0]),
        }
        if initial_up is None and previous_2_macd_line < 0 and previous_macd_line > 0:
            initial_up = item
        if initial_down is None and previous_2_macd_line > 0 and previous_macd_line < 0:
            initial_down = item
        if initial_up is not None and initial_down is not None:
            break

    return {
        "macd_initial_up": initial_up,
        "macd_initial_down": initial_down,
    }


# ==================== MACD PEAKS ====================
def calculate_macd_peaks(klines):
    """Return the latest positive peak and negative trough prices."""
    macd_line, _, _ = _calculate_macd_series(klines)
    offset = len(klines) - len(macd_line)
    up_crossings = []
    down_crossings = []

    for index in range(1, len(macd_line) - 1):
        previous_2_macd_line = macd_line.iloc[index - 1]
        previous_macd_line = macd_line.iloc[index]
        if previous_2_macd_line <= 0 < previous_macd_line:
            up_crossings.append(index)
        elif previous_2_macd_line >= 0 > previous_macd_line:
            down_crossings.append(index)

    def find_peak(start_index, positive):
        if start_index is None:
            return {"macd_value": 0.0, "price": 0.0}
        values = macd_line.iloc[start_index : len(macd_line) - 1]
        value = max(values) if positive else min(values)
        index = values.tolist().index(value) + start_index
        kline_index = index + offset
        return {
            "macd_value": float(value),
            "price": float(klines[kline_index][1]) if 0 <= kline_index < len(klines) else 0.0,
        }

    return {
        "macd_peak": find_peak(up_crossings[-1] if up_crossings else None, True),
        "macd_trough": find_peak(down_crossings[-1] if down_crossings else None, False),
    }


__all__ = [
    "calculate_macd_cross",
    "calculate_macd_state",
    "calculate_macd_trend",
    "calculate_macd_average",
    "calculate_macd_limits",
    "calculate_macd_initial_crosses",
    "calculate_macd_peaks",
]
