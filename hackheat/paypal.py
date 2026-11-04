"""PayPal REST client for the bounty jar, sandbox only, stdlib urllib.

Why not paypal-agent-toolkit: version 1.11.0 hard-pins langchain, crewai-tools and
openai-agents. This app runs with no pip install, so the three calls it needs
(OAuth token, Orders v2 create and capture, Payouts) go straight to the REST API.

Credentials come from the environment only: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET,
PAYPAL_ENV=sandbox. Nothing here logs or returns the secret.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

SANDBOX_API = "https://api-m.sandbox.paypal.com"
ORDER_ID = re.compile(r"^[A-Z0-9]{8,32}$")


class PayPalError(Exception):
    pass


class NotConfigured(PayPalError):
    pass


def configured() -> bool:
    return bool(client_id()) and bool(os.environ.get("PAYPAL_CLIENT_SECRET")) and _env_ok()


def client_id() -> str:
    """The public client id. Safe to put in the page for the JS SDK."""
    return os.environ.get("PAYPAL_CLIENT_ID", "").strip()


def _env_ok() -> bool:
    # v0 is sandbox only. Any other value is treated as not configured, so a live
    # key pasted by mistake never moves real money.
    return os.environ.get("PAYPAL_ENV", "sandbox").strip().lower() == "sandbox"


_token: dict = {}
_token_lock = threading.Lock()


def _access_token() -> str:
    if not configured():
        raise NotConfigured("Sandbox keys not configured. Set PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and PAYPAL_ENV=sandbox.")
    with _token_lock:
        if _token.get("value") and _token.get("expires", 0) > time.time() + 60:
            return _token["value"]
        basic = base64.b64encode(f"{client_id()}:{os.environ['PAYPAL_CLIENT_SECRET']}".encode()).decode()
        payload = _send(
            "POST",
            "/v1/oauth2/token",
            urlencode({"grant_type": "client_credentials"}).encode(),
            {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        _token["value"] = payload["access_token"]
        _token["expires"] = time.time() + int(payload.get("expires_in", 300))
        return _token["value"]


def _api(method: str, path: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"}
    return _send(method, path, json.dumps(body or {}).encode(), headers)


def _send(method: str, path: str, data: bytes, headers: dict) -> dict:
    request = urllib.request.Request(SANDBOX_API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:500]
        raise PayPalError(f"PayPal {method} {path} returned {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise PayPalError(f"PayPal unreachable: {exc.reason}") from None


def create_order(opportunity_id: str, amount_usd: int, description: str) -> dict:
    """Orders v2 create, intent CAPTURE. reference_id carries the board row id."""
    order = _api(
        "POST",
        "/v2/checkout/orders",
        {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": opportunity_id,
                    "custom_id": opportunity_id,
                    "description": description[:127],
                    "amount": {"currency_code": "USD", "value": f"{amount_usd:.2f}"},
                }
            ],
        },
    )
    approve = next((link["href"] for link in order.get("links", []) if link.get("rel") in {"approve", "payer-action"}), None)
    return {"id": order["id"], "status": order.get("status"), "approveUrl": approve}


def capture_order(order_id: str) -> dict:
    if not ORDER_ID.match(order_id):
        raise PayPalError("orderID is not a PayPal order id.")
    return _api("POST", f"/v2/checkout/orders/{order_id}/capture")


def payout(receiver_email: str, amount_usd: float, note: str, batch_id: str) -> dict:
    """Payouts API, one EMAIL item. Sandbox only, like everything else here."""
    return _api(
        "POST",
        "/v1/payments/payouts",
        {
            "sender_batch_header": {"sender_batch_id": batch_id, "email_subject": "Hack Heat bounty payout"},
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": receiver_email,
                    "amount": {"value": f"{amount_usd:.2f}", "currency": "USD"},
                    "note": note[:4000],
                    "sender_item_id": batch_id,
                }
            ],
        },
    )
