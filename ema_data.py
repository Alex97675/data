# ema_data.py

import pandas as pd

# ==================== EMA (13, 50, 200) CALCULATION ====================
def calculate_ema_report(klines, symbol="UNKNOWN", span=50):
    try:
        if not klines or len(klines) < span:
            return {"error": f"Not enough kline data for EMA {span}"}

        closes = [float(x[4]) for x in klines]
        closes_series = pd.Series(closes)

        ema_series = closes_series.ewm(span=span, adjust=False).mean().dropna()
        
        if len(ema_series) < 4:
            return {"error": f"Insufficient EMA {span} data"}

        ema0 = ema_series.iloc[-1]
        ema1 = ema_series.iloc[-2]
        ema2 = ema_series.iloc[-3]
        ema3 = ema_series.iloc[-4]

        current_price = closes[-1]
        trend = "UP" if current_price > ema0 else "DOWN"

        return {
            "symbol": symbol,
            "span": span,
            "values": {
                "0": f"{ema0:.8f}",
                "-1": f"{ema1:.8f}",
                "-2": f"{ema2:.8f}",
                "-3": f"{ema3:.8f}"
            },
            "current_price": f"{current_price:.8f}",
            "trend": trend
        }
    except Exception as e:
        return {"error": str(e)}
