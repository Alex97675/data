import pandas as pd
from macd_data import _build_initial_macd_state

def calculate_top_movers_report(kline_history, macd_state, cache_lock):
    movers_list = []

    with cache_lock:
        for symbol, klines in kline_history.items():
            if not klines or len(klines) < 50:
                continue
            
            closes = [float(x[4]) for x in klines]
            closes_series = pd.Series(closes)

            ema12 = closes_series.ewm(span=12, adjust=False).mean()
            ema26 = closes_series.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            macd_signal = macd_line.ewm(span=9, adjust=False).mean()

            macd_state[symbol] = _build_initial_macd_state(klines, macd_line, macd_signal)
            st = macd_state[symbol]

            try:
                close_price = float(klines[-1][4])
            except (IndexError, ValueError):
                continue

            up_init = st.get("macd_initial_up_price")
            down_init = st.get("macd_initial_down_price")

            current_macd = macd_line.iloc[-1]
            current_signal = macd_signal.iloc[-1]
            stored_trend = st.get("trend", "None")

            if stored_trend == "UP" and current_macd < current_signal:
                active_init = down_init if down_init and down_init > 0 else float(klines[-1][1])
            elif stored_trend == "DOWN" and current_macd > current_signal:
                active_init = up_init if up_init and up_init > 0 else float(klines[-1][1])
            else:
                active_init = up_init if stored_trend == "UP" else down_init

            if not active_init or active_init <= 0:
                active_init = float(klines[-1][1])

            change_percent = ((close_price - active_init) / active_init) * 100

            movers_list.append({
                "symbol": symbol,
                "initial_price": round(active_init, 8),
                "close_price": round(close_price, 8),
                "change_percent": round(change_percent, 2)
            })

    if not movers_list:
        return {"error": "No valid data calculated yet"}

    sorted_by_gain = sorted(movers_list, key=lambda x: x["change_percent"], reverse=True)

    return {
        "top_gainers": sorted_by_gain[:10],
        "top_losers": sorted_by_gain[-10:][::-1]
    }
