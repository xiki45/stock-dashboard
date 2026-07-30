"""GET /api/stock?ticker=AAPL&period=3d"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
import json
from _shared import fetch_chart, fetch_yf_data, build_info, calc_capital_flow


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or ["AAPL"])[0].upper()
        period = (params.get("period") or ["3d"])[0]

        period_map = {"3d": {"daily": "7d", "intraday": "3d"}, "7d": {"daily": "14d", "intraday": "7d"}}
        cfg = period_map.get(period, period_map["3d"])

        price_data = fetch_chart(ticker, cfg["daily"], "1d")
        yf_data = fetch_yf_data(ticker)
        intraday_interval = "30m" if period == "3d" else "1h"
        intraday = fetch_chart(ticker, cfg["intraday"], intraday_interval)
        flow = calc_capital_flow(intraday.get("bars", []), intraday_interval)

        daily_all = price_data.get("bars", [])
        keep = 3 if period == "3d" else 7
        daily = daily_all[-keep:] if len(daily_all) >= keep else daily_all
        info = build_info(yf_data, price_data.get("meta", {}))

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
