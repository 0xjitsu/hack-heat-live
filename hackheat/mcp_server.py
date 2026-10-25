"""Model Context Protocol server for Hack Heat Live.

Stdio transport uses newline-delimited JSON-RPC, which is what current MCP
clients read. POST /mcp on the HTTP API uses the same handler.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from hackheat import __version__
from hackheat.board import load_board
from hackheat.query import answer_question, answer_to_dict
from hackheat.timeutil import format_sgt, now

SERVER_INFO = {"name": "hack-heat-live", "version": __version__}
PROTOCOL_VERSION = "2025-06-18"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_board",
        "description": (
            "Answer a plain-language question about the Hack Heat board. "
            "Examples: 'what hackathons close this week?', "
            "'which ones are open to PH/SG?', 'which have prizes over $10k?'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to answer."}
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_closing",
        "description": "List calls whose next gate closes inside a window. 'this_week' means the next 7 days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "enum": ["this_week", "calendar_week", "today"],
                    "description": "Closing window. Defaults to this_week.",
                },
                "hackathons_only": {
                    "type": "boolean",
                    "description": "When true, keep hackathons and challenges only.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_eligible",
        "description": "List open calls a person in the Philippines or Singapore can enter remotely.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "regions": {
                    "type": "string",
                    "description": "Region pair. Only PH/SG is supported.",
                    "enum": ["PH/SG"],
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_by_prize",
        "description": "List open calls whose cash prize is over a USD amount.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_usd": {"type": "number", "description": "Exclusive minimum prize in USD."}
            },
            "required": ["min_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_opportunity",
        "description": "Fetch one board row by id, including its live countdown.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "board_status",
        "description": "Report how many rows are open right now and when the board file was updated.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def handle_message(message: dict) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")
    if msg_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return None
    try:
        result = _dispatch(method, message.get("params") or {})
    except _RpcError as exc:
        if msg_id is None:
            return None
        return _error(msg_id, exc.code, str(exc))
    except Exception as exc:  # noqa: BLE001 — surface a JSON-RPC error to the client
        if msg_id is None:
            return None
        return _error(msg_id, -32603, str(exc))
    if msg_id is None:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _dispatch(method: str | None, params: dict) -> Any:
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            return _call_tool(name, arguments)
        except _ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    raise _RpcError(f"Method not found: {method}", code=-32601)


def _call_tool(name: str, arguments: dict) -> dict:
    if name == "query_board":
        question = str(arguments.get("question") or "").strip()
        if not question:
            raise _ToolError("question is required")
        answer = answer_question(question)
        return _tool_result(answer.summary, answer_to_dict(answer))
    if name == "list_closing":
        window = arguments.get("window") or "this_week"
        hackathons_only = bool(arguments.get("hackathons_only"))
        question = _closing_question(window, hackathons_only)
        answer = answer_question(question)
        return _tool_result(answer.summary, answer_to_dict(answer))
    if name == "list_eligible":
        regions = arguments.get("regions") or "PH/SG"
        if regions != "PH/SG":
            raise _ToolError("Only PH/SG is supported.")
        answer = answer_question("which ones are open to PH/SG?")
        return _tool_result(answer.summary, answer_to_dict(answer))
    if name == "list_by_prize":
        if "min_usd" not in arguments:
            raise _ToolError("min_usd is required")
        amount = float(arguments["min_usd"])
        answer = answer_question(f"which have prizes over ${amount:g}?")
        return _tool_result(answer.summary, answer_to_dict(answer))
    if name == "get_opportunity":
        item_id = str(arguments.get("id") or "").strip()
        if not item_id:
            raise _ToolError("id is required")
        board = load_board()
        item = board.get(item_id)
        if item is None:
            raise _ToolError(f"No board row with id {item_id}")
        from hackheat.query import _hit, hit_to_dict

        moment = now()
        hit = _hit(item, item.next_gate(moment), moment, item.is_open(moment))

        payload = hit_to_dict(hit)
        text = f"{item.name}\n{hit.countdown}\n{item.apply_url}\n"
        return _tool_result(text, payload)
    if name == "board_status":
        board = load_board()
        moment = now()
        open_count = sum(1 for item in board.items if item.is_open(moment))
        payload = {
            "updatedAt": board.updated_at,
            "timezone": board.timezone_name,
            "rows": len(board.items),
            "open": open_count,
            "asOfSgt": format_sgt(moment),
        }
        text = (
            f"Hack Heat board updated {board.updated_at}. "
            f"{payload['open']} of {payload['rows']} calls are still open as of {payload['asOfSgt']}.\n"
        )
        return _tool_result(text, payload)
    raise _ToolError(f"Unknown tool: {name}")


def _closing_question(window: str, hackathons_only: bool) -> str:
    subject = "hackathons" if hackathons_only else "calls"
    if window == "calendar_week":
        return f"what {subject} close this calendar week?"
    if window == "today":
        return f"what {subject} close today?"
    if window == "this_week":
        return f"what {subject} close this week?"
    raise _ToolError("window must be this_week, calendar_week, or today")


def _tool_result(text: str, payload: dict) -> dict:
    return {
        "content": [
            {"type": "text", "text": text},
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
        ],
        "isError": False,
    }


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


class _RpcError(Exception):
    def __init__(self, message: str, code: int = -32603):
        super().__init__(message)
        self.code = code


class _ToolError(Exception):
    pass


def serve_stdio() -> None:
    print("hack-heat-live mcp ready", file=sys.stderr, flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_error(None, -32700, f"Parse error: {exc}")) + "\n")
            sys.stdout.flush()
            continue
        response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main() -> None:
    serve_stdio()


if __name__ == "__main__":
    main()
