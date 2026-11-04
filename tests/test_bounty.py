import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from hackheat import bounty, paypal, payouts
from hackheat.http_api import make_server, render_page
from hackheat.mcp_server import handle_message
from hackheat.query import answer_question

ROW = "gitlab-life-after-code"  # closes inside the frozen week below
NOW = "2026-10-25T03:34:00+00:00"
# Placeholders only. Nothing here reaches PayPal: _send is mocked.
FAKE_KEYS = {"PAYPAL_CLIENT_ID": "test-client-id", "PAYPAL_CLIENT_SECRET": "test-secret", "PAYPAL_ENV": "sandbox"}


class FakePayPal:
    """Stands in for paypal._send. Records calls, answers like the sandbox REST API."""

    def __init__(self, reference_id=ROW, amount="5.00", status="COMPLETED"):
        self.calls = []
        self.reference_id = reference_id
        self.amount = amount
        self.status = status

    def __call__(self, method, path, data, headers):
        self.calls.append((method, path, data))
        if path == "/v1/oauth2/token":
            return {"access_token": "fake-token", "expires_in": 3600}
        if path == "/v2/checkout/orders":
            body = json.loads(data)
            self.amount = body["purchase_units"][0]["amount"]["value"]
            return {
                "id": "5O190127TN364715T",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T"}],
            }
        if path.endswith("/capture"):
            return {
                "id": path.split("/")[4],
                "status": self.status,
                "purchase_units": [
                    {
                        "reference_id": self.reference_id,
                        "payments": {"captures": [{"id": "3C679366HH908993F", "status": self.status, "amount": {"currency_code": "USD", "value": self.amount}}]},
                    }
                ],
            }
        if path == "/v1/payments/payouts":
            return {"batch_header": {"payout_batch_id": "FAKEBATCH", "batch_status": "PENDING"}}
        raise AssertionError(f"unexpected PayPal call {method} {path}")


class BountyTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {k: v for k, v in os.environ.items() if not k.startswith("PAYPAL_") and k != "VERCEL"}
        env.update({"HACKHEAT_BOUNTY_STORE": str(Path(self.tmp.name) / "bounties.json"), "HACKHEAT_NOW": NOW})
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        paypal._token.clear()
        self.addCleanup(paypal._token.clear)

    def configure(self, fake=None):
        os.environ.update(FAKE_KEYS)
        self.fake = fake or FakePayPal()
        patcher = mock.patch.object(paypal, "_send", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)


class JarTests(BountyTestCase):
    def test_unconfigured_is_a_demo_state_not_a_crash(self):
        self.assertFalse(paypal.configured())
        with self.assertRaises(bounty.BountyError) as ctx:
            bounty.create_order(ROW, 5)
        self.assertEqual(ctx.exception.status, 503)
        html = render_page(answer_question("what hackathons close this week?"))
        self.assertIn("class='jar'", html)
        self.assertIn("Sandbox keys not configured", html)
        self.assertIn("data-amount='5' disabled", html)
        self.assertNotIn("paypal.com/sdk/js", html)

    def test_live_env_is_refused(self):
        os.environ.update(FAKE_KEYS, PAYPAL_ENV="live")
        self.assertFalse(paypal.configured())

    def test_create_validates_amount_and_row(self):
        self.configure()
        with self.assertRaises(bounty.BountyError) as ctx:
            bounty.create_order(ROW, 7)
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(bounty.BountyError) as ctx:
            bounty.create_order(ROW, 5.5)
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(bounty.BountyError) as ctx:
            bounty.create_order("no-such-row", 5)
        self.assertEqual(ctx.exception.status, 404)

    def test_create_capture_persists_once(self):
        self.configure()
        order = bounty.create_order(ROW, 5)
        self.assertEqual(order["id"], "5O190127TN364715T")
        self.assertIn("sandbox.paypal.com", order["approveUrl"])
        sent = json.loads(self.fake.calls[1][2])
        self.assertEqual(sent["purchase_units"][0]["reference_id"], ROW)
        self.assertEqual(sent["purchase_units"][0]["amount"], {"currency_code": "USD", "value": "5.00"})
        self.assertEqual(self.fake.calls[0][1], "/v1/oauth2/token")

        result = bounty.capture_order(ROW, order["id"])
        self.assertEqual(result["jar"]["totalUsd"], 5.0)
        again = bounty.capture_order(ROW, order["id"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(bounty.jar(ROW)["totalUsd"], 5.0)
        stored = json.loads(Path(os.environ["HACKHEAT_BOUNTY_STORE"]).read_text())
        self.assertEqual(len(stored["pledges"]), 1)
        self.assertEqual(sum(1 for c in self.fake.calls if c[1] == "/v1/oauth2/token"), 1, "token is cached")

    def test_capture_for_another_row_is_rejected(self):
        self.configure(FakePayPal(reference_id="some-other-row"))
        with self.assertRaises(bounty.BountyError) as ctx:
            bounty.capture_order(ROW, "5O190127TN364715T")
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(bounty.jar(ROW)["totalUsd"], 0)

    def test_bad_order_id_never_reaches_paypal(self):
        self.configure()
        with self.assertRaises(bounty.BountyError):
            bounty.capture_order(ROW, "../../v1/oauth2/token")
        self.assertFalse(any("capture" in c[1] for c in self.fake.calls))

    def test_vercel_uses_memory(self):
        os.environ["VERCEL"] = "1"
        self.addCleanup(bounty._memory.clear)
        self.configure()
        bounty.capture_order(ROW, "5O190127TN364715T")
        self.assertEqual(bounty.jar(ROW)["totalUsd"], 5.0)
        self.assertTrue(bounty.jar(ROW)["ephemeral"])
        self.assertFalse(Path(os.environ["HACKHEAT_BOUNTY_STORE"]).exists())


class McpBountyTests(BountyTestCase):
    def call(self, name, arguments):
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        return response["result"]

    def test_tools_are_listed(self):
        tools = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertLessEqual({"jar_status", "create_bounty_order", "capture_bounty_order"}, names)

    def test_biggest_jars_closing_this_week(self):
        self.configure()
        self.call("capture_bounty_order", {"opportunity_id": ROW, "order_id": "5O190127TN364715T"})
        result = self.call("jar_status", {})
        self.assertFalse(result["isError"])
        jars = json.loads(result["content"][1]["text"])["jars"]
        self.assertGreater(len(jars), 1)
        self.assertEqual(jars[0]["opportunityId"], ROW)
        self.assertEqual(jars[0]["totalUsd"], 5.0)
        self.assertIn("biggest first", result["content"][0]["text"])

    def test_create_order_tool(self):
        self.configure()
        result = self.call("create_bounty_order", {"opportunity_id": ROW, "amount_usd": 10})
        self.assertFalse(result["isError"])
        self.assertIn("checkoutnow", result["content"][0]["text"])

    def test_create_order_tool_unconfigured_is_tool_error(self):
        result = self.call("create_bounty_order", {"opportunity_id": ROW, "amount_usd": 10})
        self.assertTrue(result["isError"])
        self.assertIn("not configured", result["content"][0]["text"])


class PayoutTests(BountyTestCase):
    def test_near_intents_is_a_stub(self):
        with self.assertRaises(NotImplementedError):
            payouts.PROVIDERS["near-intents"].pay(ROW, 10, "alice.near")

    def test_paypal_payout(self):
        self.configure()
        result = payouts.PROVIDERS["paypal"].pay(ROW, 15, "winner@example.com")
        self.assertEqual(result["batch_header"]["payout_batch_id"], "FAKEBATCH")
        body = json.loads(self.fake.calls[-1][2])
        self.assertEqual(body["items"][0]["receiver"], "winner@example.com")
        self.assertEqual(body["items"][0]["amount"], {"value": "15.00", "currency": "USD"})


class HttpBountyTests(BountyTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server("127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_page_has_jar_favicon_and_og(self):
        status, body, _ = self.request("/")
        html = body.decode()
        self.assertEqual(status, 200)
        self.assertIn("class='jar'", html)
        self.assertIn('rel="icon" href="/static/favicon.svg"', html)
        self.assertIn('property="og:video" content="http://127.0.0.1', html)
        self.assertIn('property="og:image"', html)
        self.assertIn('name="twitter:card"', html)

    def test_static_files_and_traversal(self):
        for name, kind in (("favicon.svg", "image/svg+xml"), ("og.png", "image/png"), ("og.mp4", "video/mp4")):
            status, body, headers = self.request("/static/" + name)
            self.assertEqual(status, 200, name)
            self.assertEqual(headers["Content-Type"], kind)
        self.assertLess(len(self.request("/static/og.mp4")[1]), 2 * 1024 * 1024)
        self.assertEqual(self.request("/static/../LICENSE")[0], 404)
        self.assertEqual(self.request("/static/%2e%2e/LICENSE")[0], 404)

    def test_jar_endpoints(self):
        status, body, _ = self.request(f"/api/bounty/{ROW}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["totalUsd"], 0)
        self.assertEqual(self.request("/api/bounty/nope")[0], 404)
        self.assertEqual(self.request(f"/api/bounty/{ROW}/order", {"amount": 5})[0], 503)
        self.assertEqual(self.request("/api/bounty/order", {"amount": 5})[0], 404)

        self.configure()
        status, body, _ = self.request(f"/api/bounty/{ROW}/order", {"amount": 5})
        self.assertEqual(status, 200)
        order_id = json.loads(body)["id"]
        status, body, _ = self.request(f"/api/bounty/{ROW}/capture", {"orderID": order_id})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["jar"]["totalUsd"], 5.0)
        html = self.request("/")[1].decode()
        self.assertIn("paypal.com/sdk/js?client-id=test-client-id", html)
        self.assertNotIn("test-secret", html)
        self.assertIn("<strong>$5.00</strong>", html)


if __name__ == "__main__":
    unittest.main()
