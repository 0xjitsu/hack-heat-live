"""Small HTTP API and homepage for Hack Heat Live.

Binds to 0.0.0.0 and $PORT so the same process can run on Cloud Run.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from hackheat import __version__
from hackheat.board import HACKATHON_FORMATS, load_board
from hackheat.mcp_server import handle_message
from hackheat.query import Intent, answer_intent, answer_question, answer_to_dict
from hackheat.timeutil import format_sgt, now

HOST = "0.0.0.0"


def bind_host() -> str:
    return os.environ.get("HACKHEAT_HOST", HOST)


def bind_port() -> int:
    return int(os.environ.get("PORT", "8080"))


def make_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    chosen_host = bind_host() if host is None else host
    chosen_port = bind_port() if port is None else port
    return ThreadingHTTPServer((chosen_host, chosen_port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "HackHeatLive/" + __version__

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/":
            question = _first(query, "q") or "what hackathons close this week?"
            self._html(200, render_page(answer_question(question)))
            return
        if path == "/api/health":
            self._json(200, health_payload())
            return
        if path == "/api/freshness":
            self._json(200, freshness_payload())
            return
        if path == "/api/query":
            question = _first(query, "q") or _first(query, "question")
            if not question:
                self._json(400, {"error": "Pass q or question."})
                return
            self._json(200, answer_to_dict(answer_question(question)))
            return
        if path == "/api/opportunities":
            self._json(200, answer_to_dict(_from_params(query)))
            return
        if path.startswith("/api/opportunities/"):
            item_id = path.split("/", 3)[3]
            payload = _one(item_id)
            self._json(200 if "error" not in payload else 404, payload)
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if path == "/api/query":
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "Body must be JSON."})
                return
            question = str(body.get("question") or body.get("q") or "").strip()
            if not question:
                self._json(400, {"error": "question is required."})
                return
            self._json(200, answer_to_dict(answer_question(question)))
            return
        if path == "/mcp":
            if not raw.strip():
                self._json(400, {"error": "JSON-RPC body required."})
                return
            try:
                message = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                return
            if isinstance(message, list):
                responses = [item for item in (handle_message(entry) for entry in message) if item is not None]
                self._json(200, responses)
                return
            response = handle_message(message)
            if response is None:
                self.send_response(202)
                self.end_headers()
                return
            self._json(200, response)
            return
        self._json(404, {"error": "Not found"})

    def log_message(self, fmt: str, *args) -> None:
        # Stdlib logging goes to stderr. Keep stdout free for containers that scrape it.
        super().log_message(fmt, *args)

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def health_payload() -> dict:
    board = load_board()
    moment = now()
    return {
        "ok": True,
        "service": "hack-heat-live",
        "version": __version__,
        "rows": len(board.items),
        "open": sum(1 for item in board.items if item.is_open(moment)),
        "updatedAt": board.updated_at,
        "asOfSgt": format_sgt(moment),
    }


def freshness_payload() -> dict:
    board = load_board()
    moment = now()
    open_items = [item for item in board.items if item.is_open(moment)]
    upcoming = []
    for item in open_items:
        gate = item.next_gate(moment)
        if gate is None:
            continue
        upcoming.append({"id": item.id, "closesAt": gate.at.isoformat(), "countdownSeconds": int((gate.at - moment).total_seconds())})
    upcoming.sort(key=lambda row: row["closesAt"])
    return {
        "ok": bool(board.items),
        "updatedAt": board.updated_at,
        "rows": len(board.items),
        "open": len(open_items),
        "next": upcoming[0] if upcoming else None,
        "asOfSgt": format_sgt(moment),
    }


def _from_params(query: dict[str, list[str]]):
    window = _first(query, "window")
    if window == "this_week":
        window = "next_7_days"
    regions = ()
    region = (_first(query, "region") or "").upper().replace(" ", "")
    if region in {"PH/SG", "PH,SG", "SG,PH"}:
        regions = ("PH", "SG")
    min_prize = _first(query, "min_prize")
    formats = ()
    fmt = _first(query, "format")
    if fmt == "hackathon":
        formats = tuple(sorted(HACKATHON_FORMATS))
    elif fmt:
        formats = (fmt,)
    intent = Intent(
        status=_first(query, "status") or "open",
        window=window or None,
        regions=regions,
        min_prize_usd=float(min_prize) if min_prize else None,
        prize_inclusive=(_first(query, "prize_op") or "gte") != "gt",
        formats=formats,
        lane=_first(query, "lane"),
        text="parameter query",
    )
    return answer_intent(intent)


def _one(item_id: str) -> dict:
    board = load_board()
    item = board.get(item_id)
    if item is None:
        return {"error": f"No row {item_id}"}
    from hackheat.query import _hit, hit_to_dict

    moment = now()
    hit = _hit(item, item.next_gate(moment), moment, item.is_open(moment))
    return hit_to_dict(hit)


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def render_page(answer) -> str:
    from html import escape

    rows = []
    for index, hit in enumerate(answer.hits, start=1):
        item = hit.item
        prize = "Prize not listed as USD" if item.prize_usd is None else f"${int(item.prize_usd):,}" if float(item.prize_usd).is_integer() else f"${item.prize_usd:,.2f}"
        geo = item.eligibility.status
        geo_label = {"yes": "PH/SG open", "no": "PH/SG not open", "check": "Check PH/SG rules"}.get(geo, geo)
        when = hit.countdown
        rows.append(
            "<article class='card'>"
            f"<p class='count'>{escape(when)}</p>"
            f"<h2>{index}. {escape(item.name)}</h2>"
            f"<p class='meta'>{escape(prize)} · {escape(item.lane or 'lane n/a')} · {escape(geo_label)}</p>"
            f"<p>{escape(item.fit)}</p>"
            f"<p><a href='{escape(item.apply_url)}'>{escape(item.apply_url)}</a></p>"
            "</article>"
        )
    if not rows:
        rows.append("<p class='empty'>Nothing on the board matches that question.</p>")
    checks = ""
    if answer.checks:
        names = ", ".join(escape(hit.item.name) for hit in answer.checks)
        checks = f"<p class='check'>Confirm the rules first: {names}.</p>"
    question = escape(answer.question)
    summary = escape(answer.summary.split("\n", 2)[1] if "\n" in answer.summary else answer.summary)
    examples = [
        ("what hackathons close this week?", "Closing this week"),
        ("which ones are open to PH/SG?", "Open to PH/SG"),
        ("which have prizes over $10k?", "Prizes over $10k"),
    ]
    links = " ".join(
        f"<a class='chip' href='/?q={quote(q)}'>{escape(label)}</a>" for q, label in examples
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hack Heat Live</title>
<style>
  :root {{ color-scheme: light; --ink:#1c1915; --paper:#f3ecdf; --heat:#9a3412; --line:#d9cbb8; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:18px/1.45 "Iowan Old Style", Palatino, Georgia, serif; color:var(--ink); background:var(--paper); }}
  main {{ max-width:46rem; margin:0 auto; padding:2.5rem 1.25rem 4rem; }}
  header p {{ letter-spacing:.14em; text-transform:uppercase; font:600 .72rem/1.2 ui-sans-serif, system-ui, sans-serif; color:var(--heat); }}
  h1 {{ font-size:3rem; line-height:.95; margin:.2rem 0 0; }}
  form {{ display:flex; flex-wrap:wrap; gap:.5rem; margin:1.5rem 0 .75rem; }}
  form label {{ flex-basis:100%; }}
  input {{ flex:1; font:inherit; padding:.7rem .8rem; border:1px solid var(--ink); background:#fffdf8; }}
  button, .chip {{ font:600 .85rem/1 ui-sans-serif, system-ui, sans-serif; background:var(--ink); color:var(--paper); border:0; padding:.8rem 1rem; text-decoration:none; }}
  .chip {{ background:transparent; color:var(--ink); border:1px solid var(--line); padding:.45rem .6rem; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:1.5rem; }}
  .asof {{ font: .95rem/1.4 ui-sans-serif, system-ui, sans-serif; }}
  .card {{ border-top:1px solid var(--line); padding:1rem 0 1.2rem; }}
  .count {{ font:600 .95rem/1 ui-monospace, monospace; color:var(--heat); margin:0 0 .3rem; }}
  h2 {{ font-size:1.45rem; margin:0 0 .3rem; }}
  .meta, .check {{ font: .95rem/1.4 ui-sans-serif, system-ui, sans-serif; }}
  a {{ color:var(--heat); }}
  footer {{ margin-top:2rem; font: .85rem/1.4 ui-sans-serif, system-ui, sans-serif; }}
</style>
</head>
<body>
<main>
  <header>
    <p>Weekly SEA hackathon and bounty radar</p>
    <h1>Hack Heat Live</h1>
  </header>
  <form action="/" method="get">
    <label class="asof" for="q">Ask the board</label>
    <input id="q" name="q" value="{question}" autocomplete="off">
    <button type="submit">Ask</button>
  </form>
  <div class="chips">{links}</div>
  <p class="asof">{summary}</p>
  {checks}
  {''.join(rows)}
  <footer>
    Path A · Supervised autonomy · MCP at <code>POST /mcp</code> · stdio via <code>python3 -m hackheat.mcp_server</code>.
    “This week” means the next 7 days. Set <code>HACKHEAT_NOW</code> to freeze the clock for a demo.
  </footer>
</main>
</body>
</html>
"""


def main() -> None:
    port = bind_port()
    server = ThreadingHTTPServer((bind_host(), port), Handler)
    print(f"Hack Heat Live listening on http://{bind_host()}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
