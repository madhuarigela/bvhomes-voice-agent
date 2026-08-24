"""Dependency-free local dashboard and JSON API for saved BVHomes calls.

Run separately from the LiveKit worker with:
    python -m agent.dashboard
Then open http://127.0.0.1:8080 in a browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from agent.config import load_config
from agent.storage import LeadStore

logger = logging.getLogger("bvhomes-agent.dashboard")

_PAGE = """<!doctype html><html><head><meta charset=utf-8><title>BVHomes Call Dashboard</title>
<style>body{font:15px system-ui;margin:2rem;background:#f7f5f0;color:#222}input,button{padding:.55rem;margin:.2rem}table{width:100%;border-collapse:collapse;background:white;margin-top:1rem}td,th{padding:.65rem;border-bottom:1px solid #ddd;text-align:left}tr{cursor:pointer}#detail{white-space:pre-wrap;background:#fff;padding:1rem;margin-top:1rem;border-radius:6px}small{color:#666}</style></head><body>
<h1>BVHomes Customer Conversations</h1><small>Calls are stored locally in SQLite.</small><div>
<input id=customer placeholder="Customer / phone"><input id=date type=date><input id=product placeholder="Product"><input id=status placeholder="Lead status"><button onclick=load()>Search</button></div>
<table><thead><tr><th>When</th><th>Customer</th><th>Products</th><th>Status</th><th>Summary</th></tr></thead><tbody id=rows></tbody></table><section id=detail>Select a call to view its details and transcript.</section>
<script>const q=id=>document.getElementById(id);async function load(){let p=new URLSearchParams();['customer','date','product','status'].forEach(k=>{if(q(k).value)p.set(k==='status'?'lead_status':k,q(k).value)});let d=await fetch('/api/conversations?'+p).then(r=>r.json());q('rows').innerHTML=d.map(x=>`<tr onclick="show(${x.id})"><td>${x.created_at}</td><td>${x.customer_name||x.customer_phone||'Unknown'}</td><td>${x.products_discussed}</td><td>${x.lead_status}</td><td>${x.ai_summary}</td></tr>`).join('')}async function show(id){let x=await fetch('/api/conversations/'+id).then(r=>r.json());q('detail').textContent=`Customer: ${x.customer_name||'Unknown'} (${x.customer_phone||'No phone'})\nStatus: ${x.lead_status}\nFollow-up: ${x.follow_up_action}\nTopics: ${x.topics_discussed}\nProducts: ${x.products_discussed}\nBudget: ${x.budget}\nRequirements: ${x.requirements}\n\nSummary\n${x.ai_summary}\n\nTranscript\n${x.transcript}`}load()</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    store: LeadStore
    loop: asyncio.AbstractEventLoop

    def log_message(self, format: str, *args: object) -> None:
        logger.info("dashboard: " + format, *args)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @classmethod
    def _await(cls, coroutine):
        """Run storage work on the dashboard's single event loop.

        asyncpg pools are bound to an event loop; a single-loop HTTP server
        keeps PostgreSQL and SQLite behavior identical here.
        """
        return cls.loop.run_until_complete(coroutine)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = _PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        query = parse_qs(parsed.query)
        if parsed.path == "/api/conversations":
            try:
                rows = self._await(
                    self.store.list_conversations(
                        customer=query.get("customer", [""])[0],
                        date=query.get("date", [""])[0],
                        product=query.get("product", [""])[0],
                        lead_status=query.get("lead_status", [""])[0],
                        limit=int(query.get("limit", ["100"])[0]),
                    )
                )
                self._send_json(rows)
            except (ValueError, OverflowError):
                self._send_json({"error": "limit must be a number"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/conversations/"):
            try:
                conversation_id = int(parsed.path.rsplit("/", 1)[1])
                row = self._await(self.store.get_conversation(conversation_id))
            except ValueError:
                self._send_json({"error": "conversation id must be an integer"}, HTTPStatus.BAD_REQUEST)
                return
            if row is None:
                self._send_json({"error": "conversation not found"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(row)
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    config = load_config()
    DashboardHandler.store = LeadStore(config.database_url or config.db_path)
    DashboardHandler.loop = asyncio.new_event_loop()
    DashboardHandler._await(DashboardHandler.store.init())
    server = HTTPServer((host, port), DashboardHandler)
    logger.info("Dashboard listening at http://%s:%s", host, port)
    try:
        server.serve_forever()
    finally:
        DashboardHandler._await(DashboardHandler.store.close())
        DashboardHandler.loop.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
