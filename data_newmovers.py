import pandas as pd
from datetime import datetime, timezone, timedelta

def calculate_new_movers_report(kline_history, cache_lock, macd_state):
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
                close_price = float(klines[-2][4])
                current_macd = float(macd_line.iloc[-2])
                prev_macd = float(macd_line.iloc[-3])
            except (IndexError, ValueError):
                continue

            # Коин бүрийн хувьд state санах ойг шалгах, байхгүй бол үүсгэх
            if symbol not in macd_state:
                macd_state[symbol] = {
                    "crossover_time": None,
                    "initial_price": None,
                    "active_sign": 0
                }

            state = macd_state[symbol]
            
            if "active_sign" not in state:
                state["active_sign"] = 0
            if "crossover_time" not in state:
                state["crossover_time"] = None
            if "initial_price" not in state:
                state["initial_price"] = None

            current_sign = 1 if current_macd > 0 else -1

            # ЗӨВХӨН ЯГ ОДОО ЦОО ШИНЭЭР 0-ИЙГ ГАТЛАСАН ЭСЭХИЙГ ШАЛГАХ (Cross эхэлсэн мөч)
            if state["active_sign"] == 0 or state["active_sign"] != current_sign:
                if (prev_macd < 0 and current_macd >= 0) or (prev_macd > 0 and current_macd <= 0):
                    state["active_sign"] = current_sign
                    state["crossover_time"] = klines[-2][0]
                    state["initial_price"] = float(klines[-2][1]) # Кросс болсон лааны нээгдсэн үнэ

            # Хэрэв кросс хийгээгүй эсвэл мэдээлэл байхгүй бол алгасна
            if not state["crossover_time"] or not state["initial_price"]:
                continue

            active_init = state["initial_price"]
            active_timestamp = state["crossover_time"]

            if active_init <= 0:
                continue

            change_percent = ((close_price - active_init) / active_init) * 100

            # Хатуу шүүлтүүр (Эерэг бол MACD > 0, Сөрөг бол MACD < 0 байх)
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
        return {"error": "No new zero-crossover movers found yet"}

    # Супер uraldaan: Gainers болон Losers тус бүрээрээ 0-ээс эхэлж uralдаад хамгийн top 10-т шалгарсан нь үлдэх
    gainers_filtered = [m for m in movers_list if m["change_percent"] > 0]
    sorted_by_gain = sorted(gainers_filtered, key=lambda x: x["change_percent"], reverse=True)

    losers_filtered = [m for m in movers_list if m["change_percent"] < 0]
    sorted_by_loss = sorted(losers_filtered, key=lambda x: x["change_percent"], reverse=False)

    return {
        "new_gainers": sorted_by_gain[:10],
        "new_losers": sorted_by_loss[:10]
    }
