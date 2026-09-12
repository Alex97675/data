import pandas as pd
from datetime import datetime, timezone, timedelta

def calculate_new_movers_report(kline_history, cache_lock):
    movers_list = []
    ub_timezone = timezone(timedelta(hours=8))

    with cache_lock:
        for symbol, klines in kline_history.items():
            if not klines or len(klines) < 30:
                continue
            
            closes = [float(x[4]) for x in klines]
            closes_series = pd.Series(closes)

            # MACD тооцоолол (12, 26, 9)
            ema12 = closes_series.ewm(span=12, adjust=False).mean()
            ema26 = closes_series.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26

            try:
                # Зөвхөн бүрэн хаагдсан хамгийн сүүлийн лааны утгыг авна (-2)
                close_price = float(klines[-2][4])
                current_macd = float(macd_line.iloc[-2])
            except (IndexError, ValueError):
                continue

            # MACD 0-ийн шугамыг гаталсан цэгийг олох (prevprev болон prev утгаар)
            crossover_idx = None
            for i in range(len(klines) - 2, 0, -1):
                prev_prev_val = macd_line.iloc[i-1] # prevprev
                prev_val = macd_line.iloc[i]       # prev
                
                # Zero-line crossover шалгуур
                if (prev_prev_val < 0 and prev_val >= 0) or (prev_prev_val > 0 and prev_val <= 0):
                    crossover_idx = i
                    break

            if crossover_idx is None:
                continue

            active_init = float(klines[crossover_idx][1])
            active_timestamp = klines[crossover_idx][0]

            if not active_init or active_init <= 0:
                continue

            change_percent = ((close_price - active_init) / active_init) * 100

            # Хатуу шүүлтүүр
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
        return {"error": "No valid zero-crossover data found"}

    sorted_by_gain = sorted(movers_list, key=lambda x: x["change_percent"], reverse=True)

    return {
        "top_gainers": sorted_by_gain[:50],
        "top_losers": sorted_by_gain[-50:][::-1]
    }
