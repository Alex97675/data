import pandas as pd
from datetime import datetime

def calculate_top_movers_report(kline_history, cache_lock):
    movers_list = []

    with cache_lock:
        for symbol, klines in kline_history.items():
            if not klines or len(klines) < 30:
                continue
            
            closes = [float(x[4]) for x in klines]
            closes_series = pd.Series(closes)

            # MACD болон Signal тооцоолох
            ema12 = closes_series.ewm(span=12, adjust=False).mean()
            ema26 = closes_series.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            macd_signal = macd_line.ewm(span=9, adjust=False).mean()

            try:
                close_price = float(klines[-1][4])
                current_macd = float(macd_line.iloc[-1])
                current_signal = float(macd_signal.iloc[-1])
            except (IndexError, ValueError):
                continue

            # Бие дааж хамгийн сүүлийн кросс (тренд эхэлсэн цэг)-ийг олох
            crossover_idx = 0
            for i in range(len(klines) - 1, 0, -1):
                prev_up = macd_line.iloc[i-1] >= macd_signal.iloc[i-1]
                curr_up = macd_line.iloc[i] >= macd_signal.iloc[i]
                if prev_up != curr_up:
                    crossover_idx = i
                    break

            # Кросс хийсэн лааны нээгдсэн үнэ болон цагийг суурь болгон авна
            active_init = float(klines[crossover_idx][1])
            active_timestamp = klines[crossover_idx][0]

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
