import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class McpClosingThisWeekTests(unittest.TestCase):
    def test_stdio_server_answers_closing_this_week(self):
        env = os.environ.copy()
        env["HACKHEAT_NOW"] = "2026-10-25T03:34:00+00:00"
        proc = subprocess.Popen(
            [sys.executable, "-m", "hackheat.mcp_server"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "hack-heat-test", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_board",
                    "arguments": {"question": "what hackathons close this week?"},
                },
            },
        ]
        payload = "".join(json.dumps(message) + "\n" for message in messages)
        stdout, stderr = proc.communicate(payload, timeout=20)
        self.assertEqual(proc.returncode, 0, stderr)
        responses = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        by_id = {response["id"]: response for response in responses}
        self.assertIn("hack-heat-live", by_id[1]["result"]["serverInfo"]["name"])
        tool_names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
        self.assertIn("query_board", tool_names)
        content = by_id[3]["result"]["content"][0]["text"]
        self.assertIn("gitlab-life-after-code", content)
        self.assertIn("closes in", content)
        self.assertNotIn("aifj-2026", content)
        self.assertFalse(by_id[3]["result"]["isError"])
        self.assertIn("mcp ready", stderr)
