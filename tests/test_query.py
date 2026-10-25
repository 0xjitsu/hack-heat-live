import os
import unittest
from datetime import datetime

from hackheat.query import answer_question
from hackheat.timeutil import parse_instant

FROZEN = "2026-10-25T03:34:00+00:00"


class QueryTests(unittest.TestCase):
    def setUp(self):
        os.environ["HACKHEAT_NOW"] = FROZEN
        self.now = parse_instant(FROZEN)

    def tearDown(self):
        os.environ.pop("HACKHEAT_NOW", None)

    def test_hackathons_closing_this_week_have_live_countdowns(self):
        answer = answer_question("what hackathons close this week?", as_of=self.now)
        ids = [hit.item.id for hit in answer.hits]
        self.assertIn("gitlab-life-after-code", ids)
        self.assertIn("opencv-ai-competition-2026", ids)
        self.assertIn("nebius-nvidia-global-ai", ids)
        self.assertNotIn("aifj-2026", ids)
        self.assertNotIn("glasgow-sff-2027", ids)
        self.assertNotIn("pixlight-2026", ids)
        for hit in answer.hits:
            self.assertIn(hit.item.format, {"hackathon", "challenge"})
            self.assertTrue(hit.open_now)
            self.assertTrue(hit.countdown.startswith("registration closes in") or hit.countdown.startswith("submission closes in"))
            self.assertGreater(hit.countdown_seconds, 0)
        self.assertLess(
            ids.index("gitlab-life-after-code"),
            ids.index("nebius-nvidia-global-ai"),
        )
        self.assertIn("closes in", answer.summary)
        self.assertIn("gitlab-life-after-code", answer.summary)

    def test_prizes_over_10k_are_strict_and_open(self):
        answer = answer_question("which have prizes over $10k?", as_of=self.now)
        ids = {hit.item.id for hit in answer.hits}
        self.assertIn("gitlab-life-after-code", ids)
        self.assertIn("opencv-ai-competition-2026", ids)
        self.assertIn("pixlight-2026", ids)
        self.assertNotIn("telegraph-season-2-2026", ids)
        self.assertNotIn("build-with-ai-basics-2026", ids)
        self.assertNotIn("ann-arbor-film-fest-65", ids)
        for hit in answer.hits:
            self.assertGreater(hit.item.prize_usd, 10000)
            self.assertTrue(hit.open_now)

    def test_open_to_ph_sg(self):
        answer = answer_question("which ones are open to PH/SG?", as_of=self.now)
        ids = {hit.item.id for hit in answer.hits}
        checks = {hit.item.id for hit in answer.checks}
        self.assertIn("gitlab-life-after-code", ids)
        self.assertIn("meta-global-ai-hackathon-2026", ids)
        self.assertIn("ugreen-ai-nas-2026", ids)
        self.assertNotIn("sounds-of-metaverse-2026", ids)
        self.assertNotIn("eulsukdo-ecoart-2026", ids)
        self.assertNotIn("meta-vr-start-2026", ids)
        self.assertIn("meta-vr-start-2026", checks)
        self.assertIn("kling-see-the-glimmer-2026", checks)
        for hit in answer.hits:
            self.assertTrue(hit.item.eligibility.open_to_ph_sg)

    def test_calendar_week_on_sunday_is_shorter_than_seven_days(self):
        week = answer_question("what closes this calendar week?", as_of=self.now)
        rolling = answer_question("what closes this week?", as_of=self.now)
        self.assertLess(len(week.hits), len(rolling.hits))
        self.assertIn("ieee-climatechain-2026", [hit.item.id for hit in week.hits])


class BoardTests(unittest.TestCase):
    def test_seed_board_has_64_unique_rows(self):
        from hackheat.board import load_board

        board = load_board()
        self.assertEqual(len(board.items), 64)
        self.assertEqual(len({item.id for item in board.items}), 64)
        self.assertIsNotNone(board.get("gitlab-life-after-code"))


class ClockTests(unittest.TestCase):
    def test_parse_date_only_is_end_of_utc_day(self):
        parsed = parse_instant("2026-12-01")
        self.assertEqual(parsed, datetime.fromisoformat("2026-12-01T23:59:59+00:00"))
