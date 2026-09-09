import os
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import websocket
from binance.um_futures import UMFutures
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import requests
import pandas as pd
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from ohlc_data import calculate_ohlc_tracker_report
from rsi_data import calculate_rsi_report
from ema_data import calculate_ema_report
from macd_data import calculate_macd_report, _build_initial_macd_state, macd_state

# ==================== CONFIG ====================
MAX_KLINES = 300  # Лааны түүхэн датаны хязгаар
REST_WORKERS = 10
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 10
WS_URL = "wss://fstream.binance.com/market/stream"

# ==================== STATE ====================
kline_history = {}
cache_lock = threading.Lock()
closed_kline_count = 0
last_kline_time = 0

# Бот болон Daemon удирдах флагууд
daemon_is_running = False
daemon_thread = None
daemon_lock = threading.Lock()
ws_app = None  # WebSocket-г гаднаас нь зогсооход зориулав

selected_symbols = set()
selected_lock = threading.Lock()

# ==================== FASTAPI APP ====================
app = FastAPI(title="Binance Controlled Candle Data Daemon")

@app.get("/")
def root():
    with cache_lock:
        data = {
            "status": "running" if daemon_is_running else "stopped",
            "symbols_loaded": len(kline_history),
            "closed_candles_count": closed_kline_count,
            "last_closed_time": last_kline_time
        }
        return JSONResponse(content=jsonable_encoder(data))

@app.get("/railway-ip")
def get_railway_public_ip():
    """Railway серверийн гадагшаа гарч буй Public IP-г шалгах"""
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=5)
        return JSONResponse(content=jsonable_encoder(response.json()))
    except Exception as e:
        return JSONResponse(content=jsonable_encoder({"error": str(e)}))

# ==================== START / STOP CONTROL ====================
@app.get("/start")
def start_daemon():
    global daemon_is_running, daemon_thread
    with daemon_lock:
        if daemon_is_running:
            return {"status": "already running"}
        daemon_is_running = True
        daemon_thread = threading.Thread(target=start_background_daemon, daemon=True)
        daemon_thread.start()
    return {"status": "daemon started successfully"}

@app.get("/stop")
def stop_daemon():
    global daemon_is_running, ws_app
    with daemon_lock:
        if not daemon_is_running:
            return {"status": "already stopped"}
        daemon_is_running = False
        
        # WebSocket ажиллаж байгаа бол шууд хаах
        if ws_app:
            try:
                ws_app.close()
            except Exception:
                pass
                
    return {"status": "stop signal sent"}

@app.get("/status")
def daemon_status():
    with cache_lock:
        return {
            "is_running": daemon_is_running,
            "symbols_loaded": len(kline_history),
            "closed_candles_count": closed_kline_count
        }

# ==================== SELECTED SYMBOLS STATE ====================

@app.get("/choose/{symbol}")
def choose_symbol(symbol: str):
    symbol = symbol.upper()
    with selected_lock:
        selected_symbols.add(symbol)
    return {"status": "success", "message": f"{symbol} added to selected list", "selected_symbols": list(selected_symbols)}

@app.get("/delete/{symbol}")
def delete_symbol(symbol: str):
    symbol = symbol.upper()
    with selected_lock:
        if symbol in selected_symbols:
            selected_symbols.remove(symbol)
    return {"status": "success", "message": f"{symbol} removed from selected list", "selected_symbols": list(selected_symbols)}

@app.get("/selected-symbols")
def get_selected_symbols():
    with selected_lock:
        return {"selected_symbols": list(selected_symbols)}
    
# ==================== CANDLE & INDICATOR ENDPOINTS ====================
@app.get("/candles")
def get_all_candles():
    with cache_lock:
        return kline_history

@app.get("/candles/{symbol}")
def get_symbol_candles(symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol in kline_history:
            return {"symbol": symbol, "candles": kline_history[symbol]}
    raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")

@app.get("/ohlc/{symbol}")
def get_symbol_ohlc(symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol not in kline_history:
            raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")
        klines = kline_history[symbol]

    result = calculate_ohlc_tracker_report(klines, symbol)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return JSONResponse(content=jsonable_encoder(result))

@app.get("/rsi/{symbol}")
def get_symbol_rsi(symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol not in kline_history:
            raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")
        klines = kline_history[symbol]

    result = calculate_rsi_report(klines, symbol)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return JSONResponse(content=jsonable_encoder(result))

@app.get("/ema/{span}/{symbol}")
def get_symbol_ema(span: int, symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol not in kline_history:
            raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")
        klines = kline_history[symbol]

    result = calculate_ema_report(klines, symbol, span=span)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return JSONResponse(content=jsonable_encoder(result))

@app.get("/macd/{symbol}")
def get_symbol_macd(symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol not in kline_history:
            raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")
        klines = kline_history[symbol]

    result = calculate_macd_report(klines, symbol)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/top-movers")
def calculate_gain_lose_report():
    global kline_history, macd_state
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

            active_init = up_init if st.get("trend") == "UP" else down_init
            if not active_init or active_init <= 0:
                active_init = float(klines[-1][1])

            change_percent = ((close_price - active_init) / active_init) * 100

            movers_list.append({
                "symbol": symbol,
                "initial_price": round(active_init, 8),
                "close_price": round(close_price, 8),
                "change_percent": round(change_percent, 2),
                "trend": st.get("trend", "None")
            })

    if not movers_list:
        return {"error": "No valid data calculated yet"}

    sorted_by_gain = sorted(movers_list, key=lambda x: x["change_percent"], reverse=True)

    return {
        "top_gainers": sorted_by_gain[:10],
        "top_losers": sorted_by_gain[-10:][::-1]
    }

@app.get("/all/{symbol}")
def get_symbol_all_data(symbol: str):
    symbol = symbol.upper()
    with cache_lock:
        if symbol not in kline_history:
            raise HTTPException(status_code=404, detail="Symbol not found or not loaded yet")
        klines = kline_history[symbol]

    rsi_res = calculate_rsi_report(klines, symbol)
    macd_res = calculate_macd_report(klines, symbol)
    ema13_res = calculate_ema_report(klines, symbol, span=13)
    ema50_res = calculate_ema_report(klines, symbol, span=50)
    ema200_res = calculate_ema_report(klines, symbol, span=200)
    ohlc_res = calculate_ohlc_tracker_report(klines, symbol)

    tops_res = None
    try:
        if symbol in macd_state:
            init_price = macd_state[symbol].get("macd_initial_up_price")
            if init_price and init_price > 0:
                close_price = float(klines[-1][4])
                change_percent = ((close_price - init_price) / init_price) * 100
                tops_res = {
                    "symbol": symbol,
                    "initial_price": round(init_price, 8),
                    "close_price": round(close_price, 8),
                    "change_percent": round(change_percent, 2)
                }
    except Exception:
        pass

    return JSONResponse(content=jsonable_encoder({
        "symbol": symbol,
        "rsi": rsi_res if "error" not in rsi_res else None,
        "macd": macd_res if "error" not in macd_res else None,
        "ema13": ema13_res if "error" not in ema13_res else None,
        "ema50": ema50_res if "error" not in ema50_res else None,
        "ema200": ema200_res if "error" not in ema200_res else None,
        "ohlc": ohlc_res if "error" not in ohlc_res else None,
        "tops": tops_res
    }))
    
@app.get("/binchart", response_class=HTMLResponse)
def get_binchart():
    try:
        with open("binchart.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="binchart.html файл олдсонгүй!")
        
# ==================== API / DATA ====================
def get_active_symbols():
    try:
        client = UMFutures()
        client.session.requests_params = {"timeout": 10}
        info = client.exchange_info()
        return [s["symbol"] for s in info["symbols"] if s["quoteAsset"] == "USDT" and s["status"] == "TRADING" and s["contractType"] == "PERPETUAL"]
    except Exception as e:
        print(f"[ERROR] Failed to fetch symbols: {e}")
        return []

def fetch_historical_klines(client, symbol):
    for attempt in range(3):
        try:
            klines = client.klines(symbol=symbol, interval="1m", limit=MAX_KLINES)
            if not klines:
                return symbol, None
            return symbol, [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), int(x[6])] for x in klines]
        except Exception as e:
            if attempt == 2:
                print(f"[ERROR] {symbol} failed: {e}")
            time.sleep(1)
    return symbol, None

def process_closed_kline(symbol, k):
    global closed_kline_count, last_kline_time
    new_kline = [int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"]), int(k["T"])]
    
    with cache_lock:
        if symbol not in kline_history:
            kline_history[symbol] = []
        history = kline_history[symbol]
        
        if history and history[-1][0] == new_kline[0]:
            history[-1] = new_kline
        else:
            history.append(new_kline)
            
        if len(history) > MAX_KLINES:
            del history[:len(history) - MAX_KLINES]
            
        closed_kline_count += 1
        last_kline_time = time.time()
        
# ==================== WEBSOCKET ====================
def start_websocket(symbols):
    global ws_app, daemon_is_running
    print("\n" + "="*60 + "\nSTARTING REALTIME WEBSOCKET\n" + "="*60)
    print(f"[WS] Symbols: {len(symbols)} | URL: {WS_URL}")

    def on_open(ws):
        print("[WS] Connection opened successfully.")
        streams = [f"{s.lower()}@kline_1m" for s in symbols]
        print(f"[WS] Subscribing to {len(streams)} kline streams...")
        ws.send(json.dumps({"method": "SUBSCRIBE", "params": streams, "id": 1}))

    def on_message(ws, message):
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)
            
            if "result" in data:
                return
            if "data" in data:
                data = data["data"]
            if data.get("e") != "kline":
                return
                
            symbol, kline = data.get("s"), data.get("k")
            if symbol and kline:
                process_closed_kline(symbol, kline)
        except Exception as e:
            print(f"[WS MESSAGE ERROR] {e}")

    def on_error(ws, error):
        print(f"[WS ERROR] {error}")

    def on_close(ws, code, message):
        print(f"[WS CLOSED] code={code}, message={message}")

    while daemon_is_running:
        try:
            print("[WS] Connecting...")
            ws_app = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
            ws_app.run_forever(ping_interval=WS_PING_INTERVAL, ping_timeout=WS_PING_TIMEOUT)
        except Exception as e:
            print(f"[WS EXCEPTION] {e}")
        
        if daemon_is_running:
            print("[WS] Reconnecting in 5 seconds...")
            time.sleep(5)

# ==================== MONITOR ====================
def status_monitor():
    global closed_kline_count, last_kline_time, daemon_is_running
    while daemon_is_running:
        time.sleep(10)
        with cache_lock:
            count, symbols_loaded = closed_kline_count, len(kline_history)
            total_candles = sum(len(x) for x in kline_history.values())
        age = "NO CANDLES YET" if last_kline_time == 0 else f"{time.time() - last_kline_time:.1f}s ago"
        print(f"[STATUS] Symbols: {symbols_loaded} | Candles in RAM: {total_candles:,} | Updates: {count} | Last: {age}")

# ==================== BACKGROUND DAEMON INIT ====================
def start_background_daemon():
    global kline_history, daemon_is_running
    print("="*60 + "\nBINANCE 1M CANDLE BASE DATA DAEMON\n" + "="*60)
    
    print("[INFO] Fetching active USDT perpetual symbols...")
    symbols = get_active_symbols()
    if not symbols or not daemon_is_running:
        print("[ERROR] No active symbols found or daemon stopped.")
        daemon_is_running = False
        return

    print(f"[SUCCESS] Found {len(symbols)} active symbols.")
    print("\n" + "="*60 + "\nONE-TIME HISTORICAL DOWNLOAD (TURBO MODE)\n" + "="*60)

    client = UMFutures()
    client.session.requests_params = {"timeout": 10}
    loaded_count = 0
    failed_symbols = []
    progress_lock = threading.Lock()

    def worker(symbol):
        nonlocal loaded_count
        if not daemon_is_running:
            return symbol, None
        
        # Лимитийн 50% орчимд ажиллахаар хугацааг багасгав (~20-30 сек)
        time.sleep(0.05) 
        
        res_sym, hist = fetch_historical_klines(client, symbol)
        with progress_lock:
            loaded_count += 1
            print(f"\r[LOADING] {loaded_count}/{len(symbols)} - {symbol}", end="", flush=True)
        return res_sym, hist

    start_time = time.time()
    
    # Урсгалын тоог 10 болгож өсгөв (Турбо горим)
    TURBO_WORKERS = 10 
    with ThreadPoolExecutor(max_workers=TURBO_WORKERS) as executor:
        futures = [executor.submit(worker, s) for s in symbols]
        for f in as_completed(futures):
            if not daemon_is_running:
                break
            sym, hist = f.result()
            if hist:
                with cache_lock:
                    kline_history[sym] = hist
            else:
                failed_symbols.append(sym)

    if not daemon_is_running:
        print("\n🛑 [STOP] Daemon was stopped during download.")
        return

    print(f"\n[SUCCESS] Download finished in {time.time() - start_time:.1f}s. Loaded: {len(kline_history)}/{len(symbols)}")
    
    threading.Thread(target=status_monitor, daemon=True).start()
    start_websocket(symbols)
    
# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)



# ==================== VIRTUAL TRADER BOT (FULL LOGIC) ====================
JSON_FILE = "trade_data.json"
MARGIN = 0.6
LEVERAGE = 10
POSITION_SIZE = MARGIN * LEVERAGE

trade_is_running = False
trade_thread = None
trade_lock = threading.Lock()

def load_trade_data():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "condition_data": {}, "summary": {}, "counters": {},
        "open_positions": {}, "trade_history": [], "first_flags": {}
    }

def save_trade_data(data):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [FILE ERROR] {e}")

def background_virtual_trader():
    global trade_is_running
    print("🤖 [SERVER VIRTUAL TRADER] Виртуал арилжааны бот бүрэн логикоор эхэллээ...")
    
    while trade_is_running:
        try:
            with selected_lock:
                symbols = list(selected_symbols)
            
            if not symbols:
                time.sleep(5)
                continue

            db = load_trade_data()
            all_open_positions = db.get("open_positions", {})
            trade_history = db.get("trade_history", {})
            if isinstance(trade_history, dict):
                trade_history = list(trade_history.values())
            first_flags = db.get("first_flags", {})
            
            updated = False
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            condition_data = {}
            total_live_pnl = 0.0

            # 1. Нээлттэй позицуудын PnL болон хаах нөхцөлийг шалгах
            for pos_key in list(all_open_positions.keys()):
                symbol = pos_key.split("_")[0]
                pos_type = pos_key.split("_")[1]
                
                with cache_lock:
                    if symbol not in kline_history or not kline_history[symbol]:
                        continue
                    klines = kline_history[symbol]
                    try:
                        open0 = float(klines[-1][4])
                    except (IndexError, ValueError):
                        continue

                macd_res = calculate_macd_report(klines, symbol)
                if "error" in macd_res:
                    continue

                line_dict = macd_res.get("line", {})
                macd_line1 = float(line_dict.get("-1", 0))
                macd_line2 = float(line_dict.get("-2", 0))
                macd_average = float(macd_res.get("macd_average") or 0)

                if open0 > 0:
                    entry = all_open_positions[pos_key]["entry"]
                    if pos_type == "LONG":
                        price_change_percent = ((open0 - entry) / entry) * 100
                    else:
                        price_change_percent = ((entry - open0) / entry) * 100
                    live_pnl_percent = price_change_percent * LEVERAGE
                    live_pnl_usdt = (POSITION_SIZE * price_change_percent) / 100
                    all_open_positions[pos_key]["current_price"] = open0
                    all_open_positions[pos_key]["live_pnl_percent"] = round(live_pnl_percent, 2)
                    all_open_positions[pos_key]["live_pnl_usdt"] = round(live_pnl_usdt, 2)
                    total_live_pnl += live_pnl_usdt
                    updated = True

                long_opened = f"{symbol}_LONG" in all_open_positions
                short_opened = f"{symbol}_SHORT" in all_open_positions

                # LONG CLOSE
                if long_opened and pos_type == "LONG" and (macd_line1 <= macd_average and macd_line2 >= macd_average):
                    pos_info = all_open_positions.pop(f"{symbol}_LONG")
                    entry_price = pos_info["entry"]
                    price_change_percent = ((open0 - entry_price) / entry_price) * 100
                    pnl_percent = price_change_percent * LEVERAGE
                    pnl_usdt = (POSITION_SIZE * price_change_percent) / 100
                    print(f"✅ [LONG CLOSE] {symbol} @ {open0} | PnL: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)")
                    trade_history.append({
                        "symbol": symbol, "type": "LONG", "entry": entry_price, "exit": open0,
                        "margin": MARGIN, "leverage": LEVERAGE, "pnl_percent": round(pnl_percent, 2),
                        "pnl_usdt": round(pnl_usdt, 2), "open_time": pos_info.get("open_time"),
                        "close_time": current_time, "status": "CLOSED"
                    })
                    updated = True

                # SHORT CLOSE
                if short_opened and pos_type == "SHORT" and (macd_line1 >= macd_average and macd_line2 <= macd_average):
                    pos_info = all_open_positions.pop(f"{symbol}_SHORT")
                    entry_price = pos_info["entry"]
                    price_change_percent = ((entry_price - open0) / entry_price) * 100
                    pnl_percent = price_change_percent * LEVERAGE
                    pnl_usdt = (POSITION_SIZE * price_change_percent) / 100
                    print(f"✅ [SHORT CLOSE] {symbol} @ {open0} | PnL: {pnl_percent:.2f}% ({pnl_usdt:.2f} USDT)")
                    trade_history.append({
                        "symbol": symbol, "type": "SHORT", "entry": entry_price, "exit": open0,
                        "margin": MARGIN, "leverage": LEVERAGE, "pnl_percent": round(pnl_percent, 2),
                        "pnl_usdt": round(pnl_usdt, 2), "open_time": pos_info.get("open_time"),
                        "close_time": current_time, "status": "CLOSED"
                    })
                    updated = True

            total_closed_pnl = sum(item.get("pnl_usdt", 0) for item in trade_history)
            grand_total_pnl = total_live_pnl + total_closed_pnl

            # 2. Шинэ позиц нээх болон нөхцөл шалгах
            for symbol in symbols:
                with cache_lock:
                    if symbol not in kline_history or len(kline_history[symbol]) < 50:
                        continue
                    klines = kline_history[symbol]
                    try:
                        open0 = float(klines[-1][4])
                        open1 = float(klines[-2][4])
                    except (IndexError, ValueError):
                        continue

                macd_res = calculate_macd_report(klines, symbol)
                rsi_res = calculate_rsi_report(klines, symbol)
                if "error" in macd_res or "error" in rsi_res:
                    continue

                last_status = rsi_res.get("last_status", "None")
                macd_average = float(macd_res.get("macd_average") or 0)
                line_dict = macd_res.get("line", {})
                macd_line1 = float(line_dict.get("-1", 0))
                macd_line2 = float(line_dict.get("-2", 0))

                condition_data[symbol] = {
                    "open0": f"{open0:.8f}", "open1": f"{open1:.8f}",
                    "macd_line1": f"{macd_line1:.8f}", "macd_line2": f"{macd_line2:.8f}",
                    "macd_average": f"{macd_average:.8f}", "last_status": last_status
                }

                long_opened = f"{symbol}_LONG" in all_open_positions
                short_opened = f"{symbol}_SHORT" in all_open_positions
                qty = POSITION_SIZE / open0

                long_condition = (
                    macd_line1 > macd_average 
                    and macd_line2 <= macd_average 
                    and (last_status == "30U" or last_status == "70U")
                )
                if not long_opened and long_condition:
                    all_open_positions[f"{symbol}_LONG"] = {
                        "entry": open0, "qty": round(qty, 6), "margin": MARGIN,
                        "leverage": LEVERAGE, "current_price": open0, "live_pnl_percent": 0.0,
                        "live_pnl_usdt": 0.0, "open_time": current_time
                    }
                    print(f"🟢 [LONG OPEN] {symbol} @ {open0} (Qty: {qty:.4f})")
                    updated = True

                short_condition = (
                    macd_line1 < macd_average 
                    and macd_line2 >= macd_average 
                    and (last_status == "70D" or last_status == "30D")
                )
                if not short_opened and short_condition:
                    all_open_positions[f"{symbol}_SHORT"] = {
                        "entry": open0, "qty": round(qty, 6), "margin": MARGIN,
                        "leverage": LEVERAGE, "current_price": open0, "live_pnl_percent": 0.0,
                        "live_pnl_usdt": 0.0, "open_time": current_time
                    }
                    print(f"🔴 [SHORT OPEN] {symbol} @ {open0} (Qty: {qty:.4f})")
                    updated = True

            counters = {}
            for pos_key in all_open_positions.keys():
                sym = pos_key.split("_")[0]
                ptype = pos_key.split("_")[1]
                if sym not in counters:
                    counters[sym] = []
                counters[sym].append(ptype)

            formatted_counters = {}
            for sym, types in counters.items():
                if len(types) > 1:
                    formatted_counters[sym] = "HEDGE"
                else:
                    formatted_counters[sym] = types[0]

            save_trade_data({
                "condition_data": condition_data,
                "summary": {
                    "total_live_pnl_usdt": round(total_live_pnl, 2),
                    "total_closed_pnl_usdt": round(total_closed_pnl, 2),
                    "grand_total_pnl_usdt": round(grand_total_pnl, 2)
                },
                "counters": formatted_counters,
                "open_positions": all_open_positions,
                "trade_history": trade_history,
                "first_flags": first_flags
            })

        except Exception as e:
            print(f"⚠️ [TRADER ERROR] {e}")

        time.sleep(5)
    print("🛑 [SERVER VIRTUAL TRADER] Бот зогслоо.")

@app.get("/start-trade")
def start_trade_bot():
    global trade_is_running, trade_thread
    with trade_lock:
        if trade_is_running:
            return {"status": "trade bot already running"}
        trade_is_running = True
        trade_thread = threading.Thread(target=background_virtual_trader, daemon=True)
        trade_thread.start()
    return {"status": "trade bot started successfully"}

@app.get("/stop-trade")
def stop_trade_bot():
    global trade_is_running
    with trade_lock:
        if not trade_is_running:
            return {"status": "trade bot already stopped"}
        trade_is_running = False
    return {"status": "trade bot stop signal sent"}
