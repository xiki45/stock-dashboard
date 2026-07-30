"""GET /api/compare/[ticker]
数据源：yfinance（子进程）→ Yahoo Finance Quote API
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
import json, subprocess, sys

def sf(v, default=0):
    try: return float(v) if v is not None else default
    except: return default

def fetch_yf(ticker):
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
    "shortRatio": info.get("shortRatio",0),
    "shortPercentOfFloat": info.get("shortPercentOfFloat",0),
    "heldPercentInsiders": info.get("heldPercentInsiders",0),
    "heldPercentInstitutions": info.get("heldPercentInstitutions",0),
    "holders": holders,
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        parts = parsed.path.split("/")
        ticker = parts[3].upper() if len(parts) > 3 and parts[3] else "AAPL"

        yf_data = fetch_yf(ticker)

        if yf_data:
            short_pct = sf(yf_data.get("shortPercentOfFloat"))
            insiders = sf(yf_data.get("heldPercentInsiders"))
            institutions = sf(yf_data.get("heldPercentInstitutions"))
            result = {
                "ticker": ticker,
                "shortRatio": round(sf(yf_data.get("shortRatio")), 2),
                "shortPercentOfFloat": round(short_pct * 100, 2),
                "heldPercentInsiders": round(insiders * 100, 2),
                "heldPercentInstitutions": round(institutions * 100, 2),
                "shortToWeek": None,
                "holders": yf_data.get("holders", {"institutional": [], "mutualfund": []}),
                "sources": {
                    "shortRatio": "yfinance → Yahoo Finance Quote API",
                    "shortPercentOfFloat": "yfinance → Yahoo Finance Quote API",
                    "heldPercentInstitutions": "yfinance → Yahoo Finance Quote API",
                    "institutionalHolders": "yfinance → Yahoo Finance institution-ownership API",
                }
            }
        else:
            result = {
                "ticker": ticker,
                "shortRatio": 0, "shortPercentOfFloat": 0,
                "heldPercentInsiders": 0, "heldPercentInstitutions": 0,
                "shortToWeek": None,
                "holders": {"institutional": [], "mutualfund": []},
                "sources": {"error": "yfinance 不可用，多空数据暂不可用"},
            }

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
