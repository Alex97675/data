# ohlc_data.py
import pandas as pd

# ==================== STATE ====================
ohlc_states = {}

# ==================== ADVANCED OHLC TRACKER ====================
def calculate_ohlc_tracker_report(klines, symbol="UNKNOWN"):
    global ohlc_states
    try:
        if not klines or len(klines) < 4:
            return {"error": "Not enough kline data for OHLC tracker"}

        last_4 = klines[-4:]
        index_keys = ["-3", "-2", "-1", "0"]
        ohlc_dict = {}
        ohlc_list_for_df = []

        for i in range(4):
            kline = last_4[i]
            idx_key = index_keys[i]
            candle_data = {
                "open": float(kline[1]),
                "high": float(kline[2]),
                "low": float(kline[3]),
                "close": float(kline[4])
            }
            ohlc_dict[idx_key] = candle_data
            ohlc_list_for_df.append(candle_data)

        df = pd.DataFrame(ohlc_list_for_df)

        min_open = df["open"].min()
        max_open = df["open"].max()
        min_close = df["close"].min()
        max_close = df["close"].max()
        max_high = df["high"].max()
        min_low = df["low"].min()

        open0 = ohlc_list_for_df[-1]["open"]
        open1 = ohlc_list_for_df[-2]["open"]

        openup = open0 > open1
        opendown = open0 < open1

        if symbol not in ohlc_states:
            ohlc_states[symbol] = {
                "last_openup_limit": None,
                "last_opendown_limit": None,
                "prev_openup": False,
                "prev_opendown": False
            }

        st = ohlc_states[symbol]

        if openup and not st["prev_openup"]:
            st["last_openup_limit"] = min_open

        if opendown and not st["prev_opendown"]:
            st["last_opendown_limit"] = max_open

        st["prev_openup"] = openup
        st["prev_opendown"] = opendown

        return {
            "symbol": symbol,
            "candles": ohlc_dict,
            "min_open": min_open,
            "max_open": max_open,
            "min_close": min_close,
            "max_close": max_close,
            "max_high": max_high,
            "min_low": min_low,
            "openup": openup,
            "opendown": opendown,
            "openup_limit": st["last_openup_limit"],
            "opendown_limit": st["last_opendown_limit"]
        }
    except Exception as e:
        return {"error": str(e)}
