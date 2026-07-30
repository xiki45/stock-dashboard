"""GET /api/compare?ticker=AAPL"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from _shared import fetch_yf_data, sf


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or ["AAPL"])[0].upper()

        yf_data = fetch_yf_data(ticker)
        if yf_data:
            result = {
                "ticker": ticker,
                "shortRatio": round(sf(yf_data.get("shortRatio")), 2),
                "shortPercentOfFloat": round(sf(yf_data.get("shortPercentOfFloat")) * 100, 2),
                "heldPercentInsiders": round(sf(yf_data.get("heldPercentInsiders")) * 100, 2),
                "heldPercentInstitutions": round(sf(yf_data.get("heldPercentInstitutions")) * 100, 2),
                "shortToWeek": None,
                "holders": yf_data.get("holders", {"institutional": [], "mutualfund": []}),
                "sources": {
                    "shortRatio": "yfinance → Yahoo Finance Quote API",
                    "shortPercentOfFloat": "yfinance → Yahoo Finance Quote API",
                    "heldPercentInstitutions": "yfinance → Yahoo Finance Quote API",
                }
            }
        else:
            result = {
                "ticker": ticker,
                "shortRatio": 0, "shortPercentOfFloat": 0,
                "heldPercentInsiders": 0, "heldPercentInstitutions": 0,
                "shortToWeek": None,
                "holders": {"institutional": [], "mutualfund": []},
                "sources": {"error": "yfinance 不可用"},
            }

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
