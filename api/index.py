"""Vercel Python Serverless Function - 单一入口 /api
请求方式: GET /api?route=stock&ticker=AAPL&period=3d
          GET /api?route=news&ticker=AAPL
          GET /api?route=compare&ticker=AAPL
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from collections import defaultdict
import json, urllib.request, subprocess, sys

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
YAHOO = "https://query1.finance.yahoo.com"


def sf(v, default=0):
    try: return float(v) if v is not None else default
    except: return default


def fetch_chart(ticker, range_str, interval):
    url = f"{YAHOO}/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
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
        if o == 0 and h == 0 and l == 0 and c == 0 and v == 0: continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        bars.append({"time": dt.strftime("%Y-%m-%d %H:%M"), "ts": ts,
                      "open": round(o,2), "high": round(h,2), "low": round(l,2),
                      "close": round(c,2), "volume": v})
    return {
        "meta": {"currency": meta.get("currency","USD"), "regularPrice": sf(meta.get("regularMarketPrice")),
                  "previousClose": sf(meta.get("chartPreviousClose")), "exchange": meta.get("exchangeName",""),
                  "marketState": meta.get("marketState","")},
        "bars": bars,
    }


def fetch_yf_data(ticker):
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
    "longName": info.get("longName",""), "sector": info.get("sector",""), "industry": info.get("industry",""),
    "marketCap": info.get("marketCap",0), "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh",0),
    "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow",0), "trailingPE": info.get("trailingPE",0),
    "forwardPE": info.get("forwardPE",0), "dividendYield": info.get("dividendYield",0),
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
    if not bars: return {"total": {"inflow": 0, "outflow": 0, "net": 0}, "daily": []}
    by_day = defaultdict(list)
    for b in bars: by_day[b["time"][:10]].append(b)
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
            if move > 0: in_sum += flow_val * ratio; in_vol += vol
            else: out_sum += flow_val * ratio; out_vol += vol
        daily_flow.append({"date": day_key, "inflow": round(in_sum), "outflow": round(out_sum),
                           "net": round(in_sum - out_sum)})
        total_in += in_sum; total_out += out_sum
    return {"total": {"inflow": round(total_in), "outflow": round(total_out), "net": round(total_in - total_out)},
            "daily": daily_flow,
            "method": f"基于{interval}K线 OHLCV 估算。仅供参考。",
            "source": f"Yahoo Finance v8 Chart API ({interval})"}


def handle_stock(ticker, period):
    pm = {"3d": {"d": "7d", "i": "3d"}, "7d": {"d": "14d", "i": "7d"}}
    cfg = pm.get(period, pm["3d"])
    price = fetch_chart(ticker, cfg["d"], "1d")
    yf = fetch_yf_data(ticker)
    ii = "30m" if period == "3d" else "1h"
    flow = calc_capital_flow(fetch_chart(ticker, cfg["i"], ii).get("bars", []), ii)
    daily = price.get("bars", [])
    keep = 3 if period == "3d" else 7
    return {
        "ticker": ticker, "meta": price.get("meta", {}),
        "daily": daily[-keep:] if len(daily) >= keep else daily,
        "info": (lambda yf, cm: {"longName": yf.get("longName",""), "sector": yf.get("sector",""),
            "shortRatio": sf(yf.get("shortRatio")), "shortPercentOfFloat": sf(yf.get("shortPercentOfFloat")),
            "heldPercentInstitutions": sf(yf.get("heldPercentInstitutions")), "marketCap": yf.get("marketCap",0),
            "source": "yfinance"})(yf, price.get("meta",{})) if yf else {"source": "yfinance 不可用"},
        "flow": flow,
        "updated": int(datetime.now(timezone.utc).timestamp()),
    }


def handle_news(ticker):
    url = f"{YAHOO}/v1/finance/search?q={ticker}&newsCount=10&quotesCount=0"
    news = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        for item in raw.get("news", []):
            ts = item.get("providerPublishTime", 0)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            news.append({"title": item.get("title",""), "publisher": item.get("publisher",""),
                          "link": item.get("link",""), "time": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "", "ts": ts})
    except: pass
    return {"ticker": ticker, "news": news, "source": "Yahoo Finance v1 Search API"}


def handle_compare(ticker):
    yf = fetch_yf_data(ticker)
    if yf:
        return {"ticker": ticker, "shortRatio": round(sf(yf.get("shortRatio")),2),
                "shortPercentOfFloat": round(sf(yf.get("shortPercentOfFloat"))*100,2),
                "heldPercentInstitutions": round(sf(yf.get("heldPercentInstitutions"))*100,2),
                "holders": yf.get("holders",{}), "sources": {"data": "yfinance"}}
    return {"ticker": ticker, "shortRatio": 0, "shortPercentOfFloat": 0,
            "heldPercentInstitutions": 0, "holders": {}, "sources": {"error": "yfinance 不可用"}}


ROUTES = {"stock": handle_stock, "news": handle_news, "compare": handle_compare}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        route = (params.get("route") or [""])[0]
        ticker = (params.get("ticker") or ["AAPL"])[0].upper()
        period = (params.get("period") or ["3d"])[0]

        fn = ROUTES.get(route)
        if not fn:
            # 根路径 /api 无 route 参数 → 返回可用路由列表
            self._json(200, {"routes": list(ROUTES.keys()), "example": "/api?route=stock&ticker=AAPL&period=3d"})
            return

        try:
            if route == "stock":
                result = fn(ticker, period)
            else:
                result = fn(ticker)
            self._json(200, result)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
