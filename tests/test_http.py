import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request

from hackheat.http_api import bind_host, make_server


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HACKHEAT_NOW"] = "2026-10-25T03:34:00+00:00"
        cls.server = make_server("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        deadline = time.time() + 5
        while True:
            try:
                with urllib.request.urlopen(cls.base + "/api/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                if time.time() > deadline:
                    raise
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        os.environ.pop("HACKHEAT_NOW", None)

    def test_bind_default_is_all_interfaces(self):
        self.assertEqual(bind_host(), "0.0.0.0")

    def test_homepage_and_closing_query(self):
        with urllib.request.urlopen(self.base + "/") as response:
            html = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Hack Heat Live", html)
        self.assertIn("Life After Code", html)
        self.assertIn("/?q=what%20hackathons%20close%20this%20week%3F", html)
        self.assertIn("/?q=which%20have%20prizes%20over%20%2410k%3F", html)
        with urllib.request.urlopen(
            self.base + "/api/query?q=what+hackathons+close+this+week%3F"
        ) as response:
            payload = json.load(response)
        ids = [row["id"] for row in payload["results"]]
        self.assertIn("gitlab-life-after-code", ids)
        self.assertTrue(any("closes in" in row["countdown"] for row in payload["results"]))

    def test_post_query_and_health(self):
        request = urllib.request.Request(
            self.base + "/api/query",
            data=json.dumps({"question": "which have prizes over $10k?"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        self.assertGreater(payload["count"], 0)
        self.assertTrue(all(row["prizeAmountUsd"] > 10000 for row in payload["results"]))
        with urllib.request.urlopen(self.base + "/api/opportunities?min_prize=10000") as response:
            listed = json.load(response)
        self.assertTrue(all(row["prizeAmountUsd"] >= 10000 for row in listed["results"]))
        self.assertTrue(any(row["id"] == "telegraph-season-2-2026" for row in listed["results"]))
        with urllib.request.urlopen(self.base + "/api/health") as response:
            health = json.load(response)
        self.assertTrue(health["ok"])
        self.assertEqual(health["rows"], 64)

    def test_mcp_over_http(self):
        request = urllib.request.Request(
            self.base + "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "query_board",
                        "arguments": {"question": "what hackathons close this week?"},
                    },
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        self.assertIn("gitlab-life-after-code", payload["result"]["content"][0]["text"])
