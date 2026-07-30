"""GET /api/stock/[ticker]?period=3d|7d
数据源：Yahoo Finance v8 Chart API
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from collections import defaultdict
import json, urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
YAHOO = "https://query1.finance.yahoo.com"


def sf(v, default=0):
    try: return float(v) if v is not None else default
    except: return default


def fetch_chart(ticker, range_str, interval):
    url = f"{YAHOO}/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
    except Exception:
        return {"meta": {}, "bars": []}

    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp", [])
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]

    bars = []
    for i, ts in enumerate(timestamps):
        o = sf(quotes["open"][i]) if i < len(quotes.get("open", [])) else 0
        h = sf(quotes["high"][i]) if i < len(quotes.get("high", [])) else 0
        l = sf(quotes["low"][i]) if i < len(quotes.get("low", [])) else 0
        c = sf(quotes["close"][i]) if i < len(quotes.get("close", [])) else 0
        v = int(sf(quotes["volume"][i])) if i < len(quotes.get("volume", [])) else 0
        if o == 0 and h == 0 and l == 0 and c == 0 and v == 0:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        bars.append({"time": dt.strftime("%Y-%m-%d %H:%M"), "ts": ts,
                      "open": round(o,2), "high": round(h,2), "low": round(l,2),
                      "close": round(c,2), "volume": v})
    return {
        "meta": {
            "currency": meta.get("currency", "USD"),
            "regularPrice": sf(meta.get("regularMarketPrice")),
            "previousClose": sf(meta.get("chartPreviousClose")),
            "exchange": meta.get("exchangeName", ""),
            "marketState": meta.get("marketState", ""),
        },
        "bars": bars,
    }


def fetch_info_raw(ticker):
    """子进程调 yfinance，Vercel Lambda 里每个请求独立进程，无线程池问题"""
    import subprocess, sys
    script = f'''
import json, yfinance as yf
t = yf.Ticker("{ticker}")
info = t.info or {{}}
holders = {{"institutional": [], "mutualfund": []}}
try:
    ih = t.institutional_holders
    if ih is not None:
        for _, row in ih.head(10).iterrows():
            holders["institutional"].append({{"holder": str(row.get("Holder","")), "shares": int(row.get("Shares",0) or 0), "value": int(row.get("Value",0) or 0)}})
except: pass
try:
    mh = t.mutualfund_holders
    if mh is not None:
        for _, row in mh.head(10).iterrows():
            holders["mutualfund"].append({{"holder": str(row.get("Holder","")), "shares": int(row.get("Shares",0) or 0), "value": int(row.get("Value",0) or 0)}})
except: pass
r = {{
    "longName": info.get("longName",""), "sector": info.get("sector",""),
    "industry": info.get("industry",""), "marketCap": info.get("marketCap",0),
    "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh",0), "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow",0),
    "trailingPE": info.get("trailingPE",0), "forwardPE": info.get("forwardPE",0),
    "dividendYield": info.get("dividendYield",0),
    "shortRatio": info.get("shortRatio",0), "shortPercentOfFloat": info.get("shortPercentOfFloat",0),
    "heldPercentInsiders": info.get("heldPercentInsiders",0), "heldPercentInstitutions": info.get("heldPercentInstitutions",0),
    "beta": info.get("beta",0), "averageVolume": info.get("averageVolume",0),
    "marketState": info.get("marketState",""), "holders": holders,
}}
print(json.dumps(r))
'''
    try:
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
    except Exception:
        pass
    return None


def calc_capital_flow(bars, interval="30m"):
    if not bars:
        return {"total": {"inflow": 0, "outflow": 0, "net": 0}, "daily": []}
    by_day = defaultdict(list)
    for b in bars:
        by_day[b["time"][:10]].append(b)
    daily_flow, total_in, total_out = [], 0, 0
    for day_key in sorted(by_day.keys()):
        in_sum = out_sum = in_vol = out_vol = 0
        for b in by_day[day_key]:
            vol = b["volume"]
            if vol == 0: continue
            range_px = max(b["high"] - b["low"], 1)
            move = b["close"] - b["open"]
            ratio = abs(move) / range_px
            flow_val = vol * b["close"] * 0.3
            if move > 0:
                in_sum += flow_val * ratio; in_vol += vol
            else:
                out_sum += flow_val * ratio; out_vol += vol
        daily_flow.append({"date": day_key, "inflow": round(in_sum), "outflow": round(out_sum),
                           "net": round(in_sum - out_sum), "inflowVol": in_vol, "outflowVol": out_vol})
        total_in += in_sum; total_out += out_sum
    return {
        "total": {"inflow": round(total_in), "outflow": round(total_out), "net": round(total_in - total_out)},
        "daily": daily_flow,
        "method": f"基于{interval}K线 OHLCV 估算：上涨区间成交量×价格=流入，下跌区间=流出。仅供参考，非交易所精确数据。",
        "source": f"Yahoo Finance v8 Chart API ({interval} interval) → 自建估算模型",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        parts = parsed.path.split("/")
        ticker = parts[3].upper() if len(parts) > 3 and parts[3] else "AAPL"
        params = parse_qs(parsed.query)
        period = params.get("period", ["3d"])[0]

        period_map = {"3d": {"daily": "7d", "intraday": "3d"}, "7d": {"daily": "14d", "intraday": "7d"}}
        cfg = period_map.get(period, period_map["3d"])

        price_data = fetch_chart(ticker, cfg["daily"], "1d")
        yf_data = fetch_info_raw(ticker)
        intraday_interval = "30m" if period == "3d" else "1h"
        intraday = fetch_chart(ticker, cfg["intraday"], intraday_interval)
        flow = calc_capital_flow(intraday.get("bars", []), intraday_interval)

        daily_all = price_data.get("bars", [])
        keep = 3 if period == "3d" else 7
        daily = daily_all[-keep:] if len(daily_all) >= keep else daily_all

        if yf_data:
            info = {
                "longName": yf_data.get("longName", ""), "sector": yf_data.get("sector", ""),
                "industry": yf_data.get("industry", ""), "marketCap": yf_data.get("marketCap", 0),
                "fiftyTwoWeekHigh": sf(yf_data.get("fiftyTwoWeekHigh")), "fiftyTwoWeekLow": sf(yf_data.get("fiftyTwoWeekLow")),
                "trailingPE": sf(yf_data.get("trailingPE")), "forwardPE": sf(yf_data.get("forwardPE")),
                "dividendYield": sf(yf_data.get("dividendYield")),
                "shortRatio": sf(yf_data.get("shortRatio")), "shortPercentOfFloat": sf(yf_data.get("shortPercentOfFloat")),
                "heldPercentInstitutions": sf(yf_data.get("heldPercentInstitutions")),
                "beta": sf(yf_data.get("beta")), "averageVolume": int(sf(yf_data.get("averageVolume"))),
                "marketState": yf_data.get("marketState", price_data.get("meta", {}).get("marketState", "")),
                "source": "yfinance (子进程) → Yahoo Finance Quote API",
            }
        else:
            info = {"longName": "", "sector": "", "source": "yfinance 不可用，仅返回 Chart API 基础数据"}

        result = {
            "ticker": ticker, "meta": price_data.get("meta", {}),
            "daily": daily, "info": info, "flow": flow,
            "updated": int(datetime.now(timezone.utc).timestamp()),
        }

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
