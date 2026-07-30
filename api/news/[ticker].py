"""GET /api/news/[ticker]
数据源：Yahoo Finance v1 Search API
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone
import json, urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
YAHOO = "https://query1.finance.yahoo.com"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        parts = parsed.path.split("/")
        ticker = parts[3].upper() if len(parts) > 3 and parts[3] else "AAPL"

        url = f"{YAHOO}/v1/finance/search?q={ticker}&newsCount=10&quotesCount=0"
        req = urllib.request.Request(url, headers=HEADERS)
        news_list = []
        try:
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
                    "ts": ts,
                    "type": item.get("type", "STORY"),
                })
        except Exception:
            pass

        result = {"ticker": ticker, "news": news_list, "source": "Yahoo Finance v1 Search API"}
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
