import pandas as pd
from datetime import datetime
from macd_data import _build_initial_macd_state

def calculate_top_movers_report(kline_history, macd_state, cache_lock):
    movers_list = []

    with cache_lock:
        for symbol, klines in kline_history.items():
            if not klines or len(klines) < 30:
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
                current_macd = float(macd_line.iloc[-1])
            except (IndexError, ValueError):
                continue

            up_init = st.get("macd_initial_up_price")
            down_init = st.get("macd_initial_down_price")
            up_time = st.get("macd_initial_up_time")
            down_time = st.get("macd_initial_down_time")
            
            current_trend = st.get("trend", "None")

            # Зөвхөн state дээрх trend-ийн дагуу анхны үнэ болон цагийг сонгоно
            if current_trend == "UP":
                active_init = up_init
                active_timestamp = up_time
            elif current_trend == "DOWN":
                active_init = down_init
                active_timestamp = down_time
            else:
                active_init = None
                active_timestamp = None

            # Хэрэв active_init олдохгүй эсвэл 0-ээс бага байвал хамгийн сүүлийн лааны нээгдсэн үнийг авна
            if not active_init or active_init <= 0:
                active_init = float(klines[-1][1])
                active_timestamp = klines[-1][0]

            change_percent = ((close_price - active_init) / active_init) * 100

            # ХАТУУ ШАЛГУУР: 
            # 1. Өсөлттэй (change_percent > 0) байгаа зоосны MACD шугам хэзээ ч 0-ээс доошоо байж болохгүй.
            if change_percent > 0 and current_macd < 0:
                continue
            
            # 2. Уналттай (change_percent < 0) байгаа зоосны MACD шугам хэзээ ч 0-ээс дээш байж болохгүй.
            if change_percent < 0 and current_macd > 0:
                continue

            # Timestamp-г уншигдахуйц цагийн формат болгох
            formatted_time = ""
            if active_timestamp:
                try:
                    ts = int(active_timestamp)
                    if ts > 10000000000:
                        ts = ts / 1000
                    formatted_time = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    formatted_time = str(active_timestamp)

            movers_list.append({
                "symbol": symbol,
                "initial_price": round(active_init, 8),
                "close_price": round(close_price, 8),
                "change_percent": round(change_percent, 2),
                "start_time": formatted_time
            })

    if not movers_list:
        return {"error": "No valid data calculated yet"}

    sorted_by_gain = sorted(movers_list, key=lambda x: x["change_percent"], reverse=True)

    return {
        "top_gainers": sorted_by_gain[:10],
        "top_losers": sorted_by_gain[-10:][::-1]
    }
