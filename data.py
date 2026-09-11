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
from data_topmovers import calculate_top_movers_report

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
def get_top_movers():
    global kline_history, macd_state
    result = calculate_top_movers_report(kline_history, macd_state, cache_lock)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return JSONResponse(content=jsonable_encoder(result))

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
        
        # Завсарлагыг 0.3 секунд болгож сунгав (Бинансын weight limit-д хэт ачаалал өгөхгүй)
        time.sleep(0.3) 
        
        res_sym, hist = fetch_historical_klines(client, symbol)
        with progress_lock:
            loaded_count += 1
            print(f"\r[LOADING] {loaded_count}/{len(symbols)} - {symbol}", end="", flush=True)
        return res_sym, hist

    start_time = time.time()
    
    # Урсгалын тоог 5 болгон багасгаж илүү тогтвортой болгов
    TURBO_WORKERS = 5
    
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



# ==================== REAL TRADING BACKGROUND WORKER (MACD & RSI LOGIC) ====================
from client import (get_client, get_open_positions, get_symbol_rules,
                    open_long_position, open_short_position,
                    close_long_position, close_short_position)

trade_is_running = False
trade_thread = None
trade_lock = threading.Lock()

def background_real_trader():
    global trade_is_running
    print("🤖 [SERVER REAL TRADER] Бодит MACD/RSI арилжааны бот эхэллээ...")

    client = get_client()
    if not client:
        print("🔥 Client үүсгэж чадсангүй. Бот зогслоо.")
        trade_is_running = False
        return

    position_counts = {}

    while trade_is_running:
        try:
            with selected_lock:
                symbols = list(selected_symbols)
            
            if not symbols:
                time.sleep(5)
                continue

            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            for symbol in symbols:
                with cache_lock:
                    if symbol not in kline_history or len(kline_history[symbol]) < 50:
                        continue
                    klines = kline_history[symbol]
                    try:
                        open0 = float(klines[-1][4])
                        open1 = float(klines[-2][4])
                    except (IndexError, TypeError):
                        continue

                # Сервер дээрх индикаторуудыг шууд ашиглах
                macd_res = calculate_macd_report(klines, symbol)
                rsi_res = calculate_rsi_report(klines, symbol)

                if "error" in macd_res or "error" in rsi_res:
                    continue

                last_status = rsi_res.get("last_status", "None")
                line_dict = macd_res.get("line", {})
                macd_line1 = float(line_dict.get("-1", 0))
                macd_line2 = float(line_dict.get("-2", 0))
                macd_average = float(macd_res.get("macd_average") or 0)

                open_positions = get_open_positions(client)

                long_opened = False
                short_opened = False
                long_total_qty = 0.0
                short_total_qty = 0.0

                for pos in open_positions.values():
                    if pos.get('symbol') != symbol:
                        continue

                    if pos.get('positionSide') == 'LONG' and abs(float(pos.get('positionAmt', 0))) > 0:
                        long_opened = True
                        long_total_qty = abs(float(pos.get('positionAmt', 0)))
                    elif pos.get('positionSide') == 'SHORT' and abs(float(pos.get('positionAmt', 0))) > 0:
                        short_opened = True
                        short_total_qty = abs(float(pos.get('positionAmt', 0)))

                total_pnl = 0.0
                pnl_details = []
                for pos in open_positions.values():
                    if pos.get('symbol') != symbol:
                        continue
                    try:
                        pnl = float(pos.get('unRealizedProfit', 0.0))
                        total_pnl += pnl
                        pnl_details.append(f"{pos['symbol']} {pos['positionSide']}: {pnl:+.2f} USDT")
                    except (ValueError, TypeError):
                        continue

                if symbol not in position_counts:
                    position_counts[symbol] = {"long": 0, "short": 0}
                
                if not long_opened and not short_opened:
                    position_counts[symbol] = {"long": 0, "short": 0}

                print(f"\n--- [{current_time}] ---")
                print(f"SYMBOL: {symbol} | open0: {open0} | open1: {open1} | RSI Status: {last_status}")
                print(f"MACD Line1: {macd_line1:.6f} | Line2: {macd_line2:.6f} | Avg: {macd_average:.6f}")
                print(f"POSITIONS: Long Open? {long_opened} | Short Open? {short_opened}")

                if pnl_details:
                    print(f"PNL: {' | '.join(pnl_details)}")
                print(f"TOTAL PNL: {total_pnl:+.2f} USDT")

                rules = get_symbol_rules(client, symbol)
                if not rules:
                    print(f"⚠️ {symbol}-н арилжааны дүрмийг авч чадсангүй. Түр алгасаж байна.")
                    continue

                # --- 1. LONG ХААХ НӨХЦӨЛ (MACD Cross Down) ---
                if long_opened and (macd_line1 <= macd_average and macd_line2 >= macd_average):
                    print(f"✅ [LONG CLOSE] {symbol} @ {open0}")
                    pos_info = open_positions.get(f"{symbol}_LONG")
                    if pos_info:
                        qty_to_close = abs(float(pos_info['positionAmt']))
                        if qty_to_close > 0:
                            close_long_position(client, symbol, qty_to_close, info=rules)

                # --- 2. SHORT ХААХ НӨХЦӨЛ (MACD Cross Up) ---
                if short_opened and (macd_line1 >= macd_average and macd_line2 <= macd_average):
                    print(f"✅ [SHORT CLOSE] {symbol} @ {open0}")
                    pos_info = open_positions.get(f"{symbol}_SHORT")
                    if pos_info:
                        qty_to_close = abs(float(pos_info['positionAmt']))
                        if qty_to_close > 0:
                            close_short_position(client, symbol, qty_to_close, info=rules)

                # --- 3. LONG НЭЭХ НӨХЦӨЛ ---
                long_condition = (
                    macd_line1 > macd_average 
                    and macd_line2 <= macd_average 
                    and (last_status == "30U" or last_status == "70U")
                )
                if not long_opened and long_condition:
                    print(f"🟢 [LONG OPEN] {symbol} @ {open0}")
                    result = open_long_position(client, symbol, info=rules)
                    if result and not result.get("error"):
                        position_counts[symbol]["long"] += 1
                        time.sleep(3)

                # --- 4. SHORT НЭЭХ НӨХЦӨЛ ---
                short_condition = (
                    macd_line1 < macd_average 
                    and macd_line2 >= macd_average 
                    and (last_status == "70D" or last_status == "30D")
                )
                if not short_opened and short_condition:
                    print(f"🔴 [SHORT OPEN] {symbol} @ {open0}")
                    result = open_short_position(client, symbol, info=rules)
                    if result and not result.get("error"):
                        position_counts[symbol]["short"] += 1
                        time.sleep(3)

        except Exception as e:
            print(f"🔥 REAL TRADER ERROR: {e}")

        time.sleep(5)
    print("🛑 [SERVER REAL TRADER] Бодит арилжааны бот зогслоо.")

@app.get("/start-trade")
def start_trade_bot():
    global trade_is_running, trade_thread
    with trade_lock:
        if trade_is_running:
            return {"status": "real trade bot already running"}
        trade_is_running = True
        trade_thread = threading.Thread(target=background_real_trader, daemon=True)
        trade_thread.start()
    return {"status": "real trade bot started successfully"}

@app.get("/stop-trade")
def stop_trade_bot():
    global trade_is_running
    with trade_lock:
        if not trade_is_running:
            return {"status": "real trade bot already stopped"}
        trade_is_running = False
    return {"status": "real trade bot stop signal sent"}
