import json
import tempfile
import unittest
from pathlib import Path

from hackheat.curator import apply_candidate, main, validate_candidate


GOOD = json.loads(Path("candidates/example-good.json").read_text(encoding="utf-8"))
STALE = json.loads(Path("candidates/example-stale.json").read_text(encoding="utf-8"))


class CuratorTests(unittest.TestCase):
    def test_good_candidate_needs_a_human(self):
        review = validate_candidate(GOOD, board_ids=set())
        self.assertEqual(review["verdict"], "approve")
        self.assertTrue(review["needsHumanApproval"])
        self.assertTrue(review["eligibility"]["openToPhSg"])
        self.assertIn("approved-by", review["instruction"])

    def test_past_deadline_is_rejected(self):
        review = validate_candidate(STALE, board_ids=set())
        self.assertEqual(review["verdict"], "reject")
        self.assertFalse(review["needsHumanApproval"])
        self.assertIsNone(review["normalized"])

    def test_duplicate_id_is_rejected(self):
        review = validate_candidate(GOOD, board_ids={GOOD["id"]})
        self.assertEqual(review["verdict"], "reject")
        self.assertTrue(any("already on the board" in error for error in review["errors"]))

    def test_apply_refuses_without_approval_and_with_a_bad_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.json"
            board.write_text(json.dumps({"updatedAt": "x", "items": []}), encoding="utf-8")
            before = board.read_text(encoding="utf-8")
            with self.assertRaises(SystemExit):
                apply_candidate(GOOD, board_file=board, approved_by=" ")
            self.assertEqual(board.read_text(encoding="utf-8"), before)
            with self.assertRaises(SystemExit):
                apply_candidate(STALE, board_file=board, approved_by="Berna")
            self.assertEqual(board.read_text(encoding="utf-8"), before)

    def test_apply_writes_only_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.json"
            board.write_text(
                json.dumps({"updatedAt": "2026-10-23T09:10:00+08:00", "timezone": "Asia/Singapore", "items": []}),
                encoding="utf-8",
            )
            review = apply_candidate(GOOD, board_file=board, approved_by="Berna")
            self.assertTrue(review["applied"])
            saved = json.loads(board.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["id"], GOOD["id"])
            self.assertEqual(saved["lastCuratorApproval"]["approvedBy"], "Berna")

    def test_cli_validate_good_candidate(self):
        from io import StringIO
        from contextlib import redirect_stdout

        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(["validate", "candidates/example-good.json"])
        self.assertEqual(code, 0)
        self.assertIn('"verdict": "approve"', buffer.getvalue())


class SecretPatternTests(unittest.TestCase):
    def test_scanner_pattern_flags_a_constructed_key(self):
        from hackheat.ci import SECRET_PATTERNS

        sample = "AKIA" + ("A" * 16)
        self.assertTrue(any(pattern.search(sample) for pattern in SECRET_PATTERNS))
        example = Path(".env.example").read_text(encoding="utf-8")
        self.assertFalse(any(pattern.search(example) for pattern in SECRET_PATTERNS))
