"""GET /api/news?ticker=AAPL"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
import json, urllib.request
from _shared import HEADERS, YAHOO


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or ["AAPL"])[0].upper()

        url = f"{YAHOO}/v1/finance/search?q={ticker}&newsCount=10&quotesCount=0"
        news_list = []
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read())
            for item in raw.get("news", []):
                ts = item.get("providerPublishTime", 0)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                news_list.append({
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "link": item.get("link", ""),
                    "time": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                    "ts": ts, "type": item.get("type", "STORY"),
                })
        except Exception:
            pass

        result = {"ticker": ticker, "news": news_list, "source": "Yahoo Finance v1 Search API"}
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
