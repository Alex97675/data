import pandas as pd
from datetime import datetime, timezone, timedelta

def calculate_top_movers_report(kline_history, cache_lock, macd_state=None):
    movers_list = []
    
    ub_timezone = timezone(timedelta(hours=8))

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

            try:
                close_price = float(klines[-1][4])
                current_macd = float(macd_line.iloc[-1])
            except (IndexError, ValueError):
                continue

            # Шалгуур: Өсөлттэй бол MACD > 0, уналттай бол MACD < 0 байх ёстой
            if current_macd > 0:
                target_sign = 1  # 0-ээс дээш буюу эерэг бүс
            else:
                target_sign = -1 # 0-ээс доош буюу сөрөг бүс

            # Хамгийн сүүлийн лаанаас эхлэн ухраад MACD шугам 0-ийг гаталсан (sign өөрчлөгдсөн) цэгийг олох
            crossover_idx = 0
            for i in range(len(klines) - 1, 0, -1):
                prev_val = macd_line.iloc[i-1]
                curr_val = macd_line.iloc[i]
                
                # Zero-line crossover шалгах (0-ийн шугамыг гаталсан эсэх)
                if (prev_val < 0 and curr_val >= 0) or (prev_val > 0 and curr_val <= 0):
                    crossover_idx = i
                    break

            active_init = float(klines[crossover_idx][1])
            active_timestamp = klines[crossover_idx][0]

            if not active_init or active_init <= 0:
                active_init = float(klines[-1][1])
                active_timestamp = klines[-1][0]

            change_percent = ((close_price - active_init) / active_init) * 100

            # Хатуу шүүлтүүрүүд
            if change_percent > 0 and current_macd < 0:
                continue
            if change_percent < 0 and current_macd > 0:
                continue

            formatted_time = ""
            if active_timestamp:
                try:
                    ts = int(active_timestamp)
                    if ts > 10000000000:
                        ts = ts / 1000
                    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                    dt_ub = dt_utc.astimezone(ub_timezone)
                    formatted_time = dt_ub.strftime('%Y-%m-%d %H:%M:%S')
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
        "top_gainers": sorted_by_gain[:500],
        "top_losers": sorted_by_gain[-500:][::-1]
    }
