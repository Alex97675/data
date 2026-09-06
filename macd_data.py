# macd_data.py

import datetime
import pandas as pd

macd_state = {}

# ==================== ADVANCED MACD CALCULATION ====================
def _build_initial_macd_state(klines, macd_line, macd_signal):
    initial_st = {
        "uplimit": None, "downlimit": None,
        "uplimit_cross_line": None, "downlimit_cross_line": None,
        "trend": "None",
        "macd_initial_up_price": None, "macd_initial_up_time": None,
        "macd_average_lineup": None,
        "macd_initial_down_price": None, "macd_initial_down_time": None,
        "macd_average_linedown": None,
        "signal_initial_up_price": None, "signal_initial_up_time": None,
        "signal_initial_down_price": None, "signal_initial_down_time": None
    }
    
    last_cross_up_idx = -1
    last_cross_down_idx = -1

    for i in range(len(macd_line) - 2, 2, -1):
        if macd_line.iloc[i] > macd_signal.iloc[i] and macd_line.iloc[i-1] < macd_signal.iloc[i-1]:
            if initial_st["uplimit"] is None:
                last_cross_up_idx = i
                window_klines = macd_line.iloc[i-3:i+1]
                initial_st["uplimit"] = min(window_klines)
                initial_st["uplimit_cross_line"] = macd_line.iloc[i]

        if macd_line.iloc[i] < macd_signal.iloc[i] and macd_line.iloc[i-1] > macd_signal.iloc[i-1]:
            if initial_st["downlimit"] is None:
                last_cross_down_idx = i
                window_klines = macd_line.iloc[i-3:i+1]
                initial_st["downlimit"] = max(window_klines)
                initial_st["downlimit_cross_line"] = macd_line.iloc[i]

        if initial_st["uplimit"] is not None and initial_st["downlimit"] is not None:
            break

    if last_cross_up_idx > last_cross_down_idx:
        initial_st["trend"] = "UP"
    elif last_cross_down_idx > last_cross_up_idx:
        initial_st["trend"] = "DOWN"

    offset = len(klines) - len(macd_line)
    mongolia_tz = datetime.timezone(datetime.timedelta(hours=8))

    found_macd_up = False
    found_macd_down = False
    up_start_idx = -1
    down_start_idx = -1

    for i in range(len(macd_line) - 1, 0, -1):
        curr_line = macd_line.iloc[i]
        prev_line = macd_line.iloc[i-1]
        
        if not found_macd_up and prev_line < 0 and curr_line > 0:
            kline_idx = i + offset
            if 0 <= kline_idx < len(klines):
                initial_st["macd_initial_up_price"] = float(klines[kline_idx][1])
                ts_ms = int(klines[kline_idx][0])
                initial_st["macd_initial_up_time"] = datetime.datetime.fromtimestamp(ts_ms / 1000.0, mongolia_tz).strftime('%Y-%m-%d %H:%M:%S')
                up_start_idx = i
                found_macd_up = True

        if not found_macd_down and prev_line > 0 and curr_line < 0:
            kline_idx = i + offset
            if 0 <= kline_idx < len(klines):
                initial_st["macd_initial_down_price"] = float(klines[kline_idx][1])
                ts_ms = int(klines[kline_idx][0])
                initial_st["macd_initial_down_time"] = datetime.datetime.fromtimestamp(ts_ms / 1000.0, mongolia_tz).strftime('%Y-%m-%d %H:%M:%S')
                down_start_idx = i
                found_macd_down = True

        if found_macd_up and found_macd_down:
            break

    if up_start_idx != -1:
        up_vals = [float(macd_line.iloc[j]) for j in range(up_start_idx, len(macd_line))]
        if up_vals:
            max_up_peak = max(up_vals)
            initial_st["macd_average_lineup"] = max_up_peak / 2.0

    if down_start_idx != -1:
        down_vals = [float(macd_line.iloc[j]) for j in range(down_start_idx, len(macd_line))]
        if down_vals:
            min_down_trough = min(down_vals)
            initial_st["macd_average_linedown"] = min_down_trough / 2.0

    found_signal_up = False
    found_signal_down = False

    for i in range(len(macd_signal) - 1, 0, -1):
        curr_sig = macd_signal.iloc[i]
        prev_sig = macd_signal.iloc[i-1]
        
        if not found_signal_up and prev_sig < 0 and curr_sig > 0:
            kline_idx = i + offset
            if 0 <= kline_idx < len(klines):
                initial_st["signal_initial_up_price"] = float(klines[kline_idx][1])
                ts_ms = int(klines[kline_idx][0])
                initial_st["signal_initial_up_time"] = datetime.datetime.fromtimestamp(ts_ms / 1000.0, mongolia_tz).strftime('%Y-%m-%d %H:%M:%S')
                found_signal_up = True

        if not found_signal_down and prev_sig > 0 and curr_sig < 0:
            kline_idx = i + offset
            if 0 <= kline_idx < len(klines):
                initial_st["signal_initial_down_price"] = float(klines[kline_idx][1])
                ts_ms = int(klines[kline_idx][0])
                initial_st["signal_initial_down_time"] = datetime.datetime.fromtimestamp(ts_ms / 1000.0, mongolia_tz).strftime('%Y-%m-%d %H:%M:%S')
                found_signal_down = True

        if found_signal_up and found_signal_down:
            break

    return initial_st

def calculate_macd_report(klines, symbol="UNKNOWN"):
    global macd_state
    try:
        if not klines or len(klines) < 50:
            return {"error": "Not enough kline data for MACD"}

        closes = [float(x[4]) for x in klines]
        closes_series = pd.Series(closes)

        ema12 = closes_series.ewm(span=12, adjust=False).mean()
        ema26 = closes_series.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal

        if len(macd_line.dropna()) < 4:
            return {"error": "Insufficient MACD data"}

        macd_state[symbol] = _build_initial_macd_state(klines, macd_line, macd_signal)

        if symbol not in macd_state:
            macd_state[symbol]["line_direction"] = "None"
            macd_state[symbol]["macd_lineup_limit"] = None
            macd_state[symbol]["macd_linedown_limit"] = None

        macd_up = macd_line.iloc[-2] > macd_signal.iloc[-2] and macd_line.iloc[-3] < macd_signal.iloc[-3]
        macd_down = macd_line.iloc[-2] < macd_signal.iloc[-2] and macd_line.iloc[-3] > macd_signal.iloc[-3]

        line_minus_1 = macd_line.iloc[-2]
        line_minus_2 = macd_line.iloc[-3]

        current_line_direction = "UP" if line_minus_1 > line_minus_2 else "DOWN"
        previous_line_direction = macd_state[symbol].get("line_direction", "None")

        if current_line_direction != previous_line_direction:
            if current_line_direction == "DOWN":
                macd_state[symbol]["macd_lineup_limit"] = line_minus_2
            elif current_line_direction == "UP":
                macd_state[symbol]["macd_linedown_limit"] = line_minus_2
        
        macd_state[symbol]["line_direction"] = current_line_direction

        last_4_lines = [macd_line.iloc[-1], macd_line.iloc[-2], macd_line.iloc[-3], macd_line.iloc[-4]]
        macd_min = min(last_4_lines)
        macd_max = max(last_4_lines)

        if macd_up:
            macd_state[symbol]["trend"] = "UP"
            macd_state[symbol]["uplimit"] = macd_min
            macd_state[symbol]["uplimit_cross_line"] = macd_line.iloc[-2]
        if macd_down:
            macd_state[symbol]["trend"] = "DOWN"
            macd_state[symbol]["downlimit"] = macd_max
            macd_state[symbol]["downlimit_cross_line"] = macd_line.iloc[-2]

        current_trend = macd_state[symbol].get("trend", "None")

        # --- ШИНЭЭР НЭМЭХ ТООЦООЛОЛ ---
        current_macd_line = float(macd_line.iloc[-1])
        macd_line_up_0 = current_macd_line > 0
        macd_line_down_0 = current_macd_line < 0
        # -----------------------------

        return {
            "symbol": symbol,
            "line": {
                "0": f"{macd_line.iloc[-1]:.8f}",
                "-1": f"{macd_line.iloc[-2]:.8f}",
                "-2": f"{macd_line.iloc[-3]:.8f}",
                "-3": f"{macd_line.iloc[-4]:.8f}"
            },
            "signal": {
                "0": f"{macd_signal.iloc[-1]:.8f}",
                "-1": f"{macd_signal.iloc[-2]:.8f}",
                "-2": f"{macd_signal.iloc[-3]:.8f}",
                "-3": f"{macd_signal.iloc[-4]:.8f}"
            },
            "hist": {
                "0": f"{macd_hist.iloc[-1]:.8f}",
                "-1": f"{macd_hist.iloc[-2]:.8f}",
                "-2": f"{macd_hist.iloc[-3]:.8f}",
                "-3": f"{macd_hist.iloc[-4]:.8f}"
            },
            # --- ШИНЭ ТӨЛӨВҮҮДҮҮДИЙГ ЭНД ОРУУЛАВ ---
            "macd_lineUp0": macd_line_up_0,
            "macd_linedown0": macd_line_down_0,
            # --------------------------------------
            "macd_up": current_trend == "UP",
            "macd_down": current_trend == "DOWN",
            "macd_min": f"{macd_min:.8f}",
            "macd_max": f"{macd_max:.8f}",
            "macd_uplimit": f"{macd_state[symbol]['uplimit']:.8f}" if macd_state[symbol]['uplimit'] is not None else None,
            "macd_downlimit": f"{macd_state[symbol]['downlimit']:.8f}" if macd_state[symbol]['downlimit'] is not None else None,
            "macd_lineup_limit": f"{macd_state[symbol].get('macd_lineup_limit'):.8f}" if macd_state[symbol].get('macd_lineup_limit') is not None else None,
            "macd_linedown_limit": f"{macd_state[symbol].get('macd_linedown_limit'):.8f}" if macd_state[symbol].get('macd_linedown_limit') is not None else None,
            "uplimit_cross_line": f"{macd_state[symbol]['uplimit_cross_line']:.8f}" if macd_state[symbol]['uplimit_cross_line'] is not None else None,
            "downlimit_cross_line": f"{macd_state[symbol]['downlimit_cross_line']:.8f}" if macd_state[symbol]['downlimit_cross_line'] is not None else None,
            "macd_initial_up_price": f"{macd_state[symbol].get('macd_initial_up_price'):.8f}" if macd_state[symbol].get('macd_initial_up_price') is not None else None,
            "macd_initial_up_time": macd_state[symbol].get('macd_initial_up_time'),
            "macd_average_lineup": f"{macd_state[symbol].get('macd_average_lineup'):.8f}" if macd_state[symbol].get('macd_average_lineup') is not None else None,
            "macd_initial_down_price": f"{macd_state[symbol].get('macd_initial_down_price'):.8f}" if macd_state[symbol].get('macd_initial_down_price') is not None else None,
            "macd_initial_down_time": macd_state[symbol].get('macd_initial_down_time'),
            "macd_average_linedown": f"{macd_state[symbol].get('macd_average_linedown'):.8f}" if macd_state[symbol].get('macd_average_linedown') is not None else None,
            "signal_initial_up_price": f"{macd_state[symbol].get('signal_initial_up_price'):.8f}" if macd_state[symbol].get('signal_initial_up_price') is not None else None,
            "signal_initial_up_time": macd_state[symbol].get('signal_initial_up_time'),
            "signal_initial_down_price": f"{macd_state[symbol].get('signal_initial_down_price'):.8f}" if macd_state[symbol].get('signal_initial_down_price') is not None else None,
            "signal_initial_down_time": macd_state[symbol].get('signal_initial_down_time')
        }
    except Exception as e:
        return {"error": str(e)}
