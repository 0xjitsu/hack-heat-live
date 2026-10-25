"""Load the seeded Hack Heat board and resolve the next deadline gate."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hackheat.eligibility import Eligibility, assess
from hackheat.timeutil import SGT, UTC, parse_instant

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "data" / "opportunities.json"

HACKATHON_FORMATS = frozenset({"hackathon", "challenge"})


@dataclass(frozen=True)
class Gate:
    kind: str  # deadline, registrationCloses
    at: datetime

    @property
    def label(self) -> str:
        if self.kind == "registrationCloses":
            return "registration"
        return "submission"


@dataclass(frozen=True)
class Opportunity:
    raw: dict
    eligibility: Eligibility
    gates: tuple[Gate, ...]

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or "")

    @property
    def lane(self) -> str:
        return str(self.raw.get("lane") or "")

    @property
    def format(self) -> str:
        return str(self.raw.get("format") or "")

    @property
    def prize_usd(self) -> float | None:
        value = self.raw.get("prizeAmountUsd")
        if value is None or value == "":
            return None
        return float(value)

    @property
    def apply_url(self) -> str:
        return str(self.raw.get("applyUrl") or "")

    @property
    def fit(self) -> str:
        return str(self.raw.get("fit") or "")

    @property
    def prize_label(self) -> str:
        return str(self.raw.get("prizeLabel") or self.raw.get("prize") or "")

    def next_gate(self, as_of: datetime) -> Gate | None:
        future = [gate for gate in self.gates if gate.at > as_of]
        if future:
            return min(future, key=lambda gate: gate.at)
        if not self.gates:
            return None
        return max(self.gates, key=lambda gate: gate.at)

    def is_open(self, as_of: datetime) -> bool:
        if not self.gates:
            return True
        return any(gate.at > as_of for gate in self.gates)


@dataclass(frozen=True)
class Board:
    updated_at: str
    timezone_name: str
    items: tuple[Opportunity, ...]

    def get(self, item_id: str) -> Opportunity | None:
        for item in self.items:
            if item.id == item_id:
                return item
        return None


def board_path() -> Path:
    override = os.environ.get("HACKHEAT_BOARD", "").strip()
    if override:
        return Path(override)
    return DEFAULT_BOARD


def load_board(path: Path | None = None) -> Board:
    source = path or board_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    items = tuple(_build(raw) for raw in payload.get("items") or [])
    return Board(
        updated_at=str(payload.get("updatedAt") or ""),
        timezone_name=str(payload.get("timezone") or "Asia/Singapore"),
        items=items,
    )


def load_payload(path: Path | None = None) -> dict:
    source = path or board_path()
    return json.loads(source.read_text(encoding="utf-8"))


def _build(raw: dict) -> Opportunity:
    gates: list[Gate] = []
    for kind in ("registrationCloses", "deadline"):
        value = raw.get(kind)
        if not value:
            continue
        try:
            gates.append(Gate(kind=kind, at=parse_instant(str(value))))
        except ValueError:
            continue
    return Opportunity(raw=raw, eligibility=assess(raw), gates=tuple(gates))


def window_bounds(kind: str, as_of: datetime) -> tuple[datetime, datetime]:
    """Return an inclusive ``(start, end)`` window.

    ``next_7_days`` is what "this week" means on a weekly radar: the next
    seven days from the moment the question is asked. ``calendar_week`` is
    Monday 00:00 through Sunday 23:59 Asia/Singapore. ``today`` ends at
    23:59 SGT.
    """
    if kind == "next_7_days":
        return as_of, as_of + timedelta(days=7)
    local = as_of.astimezone(SGT)
    if kind == "today":
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
    elif kind == "calendar_week":
        start = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=7) - timedelta(seconds=1)
    else:
        raise ValueError(f"unknown window {kind}")
    return max(as_of, start.astimezone(UTC)), end.astimezone(UTC)
