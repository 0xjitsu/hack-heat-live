"""Bounty jar: micro-pledges on a board row, paid through PayPal Checkout (sandbox).

Pledges are counted only after a capture comes back COMPLETED for the same board
row. Storage is one JSON file locally. On Vercel the filesystem is ephemeral, so
the jar lives in memory there.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from hackheat import paypal
from hackheat.board import ROOT, load_board
from hackheat.query import closing_this_week

PRESET_AMOUNTS_USD = (1, 5, 10)

_lock = threading.Lock()
_memory: list[dict] = []


class BountyError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ephemeral() -> bool:
    # TODO(bounty-jar): pick a free durable store before judging (e.g. a JSON
    # blob or KV). Vercel and Cloud Run both lose this list on a cold start.
    return bool(os.environ.get("VERCEL")) or os.environ.get("HACKHEAT_BOUNTY_STORE") == ":memory:"


def store_path() -> Path:
    return Path(os.environ.get("HACKHEAT_BOUNTY_STORE") or ROOT / "var" / "bounties.json")


def _load() -> list[dict]:
    if ephemeral():
        return _memory
    path = store_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("pledges", [])


def _save(pledges: list[dict]) -> None:
    if ephemeral():
        return
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pledges": pledges}, indent=2), encoding="utf-8")
    tmp.replace(path)


def totals() -> dict[str, float]:
    out: dict[str, float] = {}
    for p in _load():
        out[p["opportunityId"]] = round(out.get(p["opportunityId"], 0) + p["amountUsd"], 2)
    return out


def jar(opportunity_id: str) -> dict:
    pledges = [p for p in _load() if p["opportunityId"] == opportunity_id]
    return {
        "opportunityId": opportunity_id,
        "totalUsd": round(sum(p["amountUsd"] for p in pledges), 2),
        "pledges": len(pledges),
        "currency": "USD",
        "environment": "sandbox",
        "configured": paypal.configured(),
        "ephemeral": ephemeral(),
    }


def jars_closing_this_week() -> list[dict]:
    """Closing-this-week hackathons with their jar, biggest jar first."""
    rows = []
    for hit in closing_this_week(hackathons_only=True).hits:
        row = jar(hit.item.id)
        row.update({"name": hit.item.name, "countdown": hit.countdown})
        rows.append(row)
    rows.sort(key=lambda row: -row["totalUsd"])  # stable: ties stay soonest-first
    return rows


def _require_row(opportunity_id: str):
    item = load_board().get(opportunity_id)
    if item is None:
        raise BountyError(f"No board row with id {opportunity_id}", 404)
    return item


def create_order(opportunity_id: str, amount_usd) -> dict:
    item = _require_row(opportunity_id)
    try:
        amount = int(amount_usd)
    except (TypeError, ValueError):
        amount = None
    if amount not in PRESET_AMOUNTS_USD or float(amount_usd) != amount:
        raise BountyError(f"amount must be one of {list(PRESET_AMOUNTS_USD)} USD")
    if not paypal.configured():
        raise BountyError("Sandbox keys not configured.", 503)
    try:
        order = paypal.create_order(item.id, amount, f"Hack Heat bounty: {item.name}")
    except paypal.PayPalError as exc:
        raise BountyError(str(exc), 502) from None
    order.update({"opportunityId": item.id, "amountUsd": amount, "environment": "sandbox"})
    return order


def capture_order(opportunity_id: str, order_id: str) -> dict:
    _require_row(opportunity_id)
    if not paypal.configured():
        raise BountyError("Sandbox keys not configured.", 503)
    order_id = str(order_id or "").strip()
    with _lock:
        pledges = _load()
        if any(p["orderId"] == order_id for p in pledges):
            return {"status": "COMPLETED", "duplicate": True, "jar": jar(opportunity_id)}
        try:
            result = paypal.capture_order(order_id)
        except paypal.PayPalError as exc:
            raise BountyError(str(exc), 502) from None
        unit = (result.get("purchase_units") or [{}])[0]
        capture = ((unit.get("payments") or {}).get("captures") or [{}])[0]
        if result.get("status") != "COMPLETED" or capture.get("status") != "COMPLETED":
            raise BountyError(f"Capture not completed: {result.get('status')}", 409)
        if unit.get("reference_id") != opportunity_id:
            raise BountyError("Order belongs to a different board row.", 409)
        pledges.append(
            {
                "opportunityId": opportunity_id,
                "orderId": order_id,
                "captureId": capture.get("id"),
                "amountUsd": float(capture["amount"]["value"]),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save(pledges)
    return {"status": "COMPLETED", "captureId": capture.get("id"), "jar": jar(opportunity_id)}
