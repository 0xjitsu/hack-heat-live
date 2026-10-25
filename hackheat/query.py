"""Natural-language questions over the Hack Heat board."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from hackheat.board import HACKATHON_FORMATS, Board, Opportunity, load_board, window_bounds
from hackheat.timeutil import countdown, format_sgt, now

WINDOW_LABELS = {
    "next_7_days": "the next 7 days",
    "calendar_week": "this calendar week (Mon–Sun, Asia/Singapore)",
    "today": "today (Asia/Singapore)",
}


@dataclass
class Intent:
    status: str = "open"  # open, closed, all
    window: str | None = None
    regions: tuple[str, ...] = ()
    min_prize_usd: float | None = None
    prize_inclusive: bool = False
    formats: tuple[str, ...] = ()
    lane: str | None = None
    text: str = ""


@dataclass
class Hit:
    item: Opportunity
    gate_kind: str | None
    gate_at: datetime | None
    countdown: str
    countdown_seconds: int | None
    open_now: bool


@dataclass
class Answer:
    question: str
    as_of: datetime
    intent: Intent
    window_start: datetime | None = None
    window_end: datetime | None = None
    hits: list[Hit] = field(default_factory=list)
    checks: list[Hit] = field(default_factory=list)
    board_updated_at: str = ""

    @property
    def summary(self) -> str:
        return render_text(self)


def parse_question(question: str) -> Intent:
    text = " ".join(question.strip().split())
    low = text.lower()
    intent = Intent(text=text)

    if "including closed" in low or "include closed" in low:
        intent.status = "all"
    elif re.search(r"\bclosed\b", low) and "close" not in low.replace("closed", ""):
        intent.status = "closed"

    prize = re.search(
        r"(?:over|above|greater than|more than|>|at least|>=)\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(k\b)?",
        low,
    )
    if prize:
        amount = float(prize.group(1).replace(",", ""))
        if prize.group(2):
            amount *= 1000
        # "at least" and ">=" are inclusive. "over" / "more than" / ">" are strict,
        # so store the exclusive floor by nudging comparisons in the filter.
        intent.prize_inclusive = bool(re.search(r"at least|>=", prize.group(0)))
        intent.min_prize_usd = amount
        intent.text = text

    if re.search(r"ph\s*/\s*sg|philippines|singapore", low) or (
        re.search(r"\bph\b", low) and re.search(r"\bsg\b", low)
    ):
        intent.regions = ("PH", "SG")

    if "calendar week" in low:
        intent.window = "calendar_week"
    elif any(phrase in low for phrase in ("this week", "next 7 days", "next seven days")):
        intent.window = "next_7_days"
    elif re.search(r"\b(today|tonight)\b", low):
        intent.window = "today"

    if "hackathon" in low:
        intent.formats = tuple(sorted(HACKATHON_FORMATS))
    elif re.search(r"\bfilms?\b", low):
        intent.formats = ("film-festival",)
    elif "open call" in low or "open-call" in low:
        intent.formats = ("open-call",)

    if re.search(r"\bcode lane\b|\blane[:= ]+code\b", low):
        intent.lane = "code"
    elif re.search(r"\bcreative lane\b|\blane[:= ]+creative\b", low):
        intent.lane = "creative"
    return intent


def prize_is_inclusive(intent: Intent) -> bool:
    return intent.prize_inclusive or intent.min_prize_usd is None


def answer_question(question: str, *, board: Board | None = None, as_of: datetime | None = None) -> Answer:
    source = board or load_board()
    moment = as_of or now()
    intent = parse_question(question)
    return _collect(question, intent, source, moment)


def answer_intent(intent: Intent, *, board: Board | None = None, as_of: datetime | None = None) -> Answer:
    source = board or load_board()
    moment = as_of or now()
    return _collect(intent.text or "filtered board", intent, source, moment)


def closing_this_week(*, board: Board | None = None, as_of: datetime | None = None, hackathons_only: bool = False) -> Answer:
    question = "what hackathons close this week?" if hackathons_only else "what closes this week?"
    return answer_question(question, board=board, as_of=as_of)


def _collect(question: str, intent: Intent, board: Board, as_of: datetime) -> Answer:
    start = end = None
    if intent.window:
        start, end = window_bounds(intent.window, as_of)
    hits: list[Hit] = []
    checks: list[Hit] = []
    inclusive = prize_is_inclusive(intent)
    for item in board.items:
        gate = item.next_gate(as_of)
        open_now = item.is_open(as_of)
        if intent.status == "open" and not open_now:
            continue
        if intent.status == "closed" and open_now:
            continue
        if intent.lane and item.lane != intent.lane:
            continue
        if intent.formats and item.format not in intent.formats:
            continue
        if intent.min_prize_usd is not None:
            if item.prize_usd is None:
                continue
            if inclusive and item.prize_usd < intent.min_prize_usd:
                continue
            if not inclusive and item.prize_usd <= intent.min_prize_usd:
                continue
        if intent.window:
            if gate is None or not open_now:
                continue
            if gate.at < start or gate.at > end:
                continue
        hit = _hit(item, gate, as_of, open_now)
        if intent.regions == ("PH", "SG"):
            if item.eligibility.status == "check":
                checks.append(hit)
                continue
            if not item.eligibility.open_to_ph_sg:
                continue
        hits.append(hit)
    hits.sort(key=_sort_key)
    checks.sort(key=_sort_key)
    return Answer(
        question=question,
        as_of=as_of,
        intent=intent,
        window_start=start,
        window_end=end,
        hits=hits,
        checks=checks,
        board_updated_at=board.updated_at,
    )


def _hit(item: Opportunity, gate, as_of: datetime, open_now: bool) -> Hit:
    if gate is None:
        return Hit(item, None, None, "no fixed deadline", None, open_now)
    phrase, seconds = countdown(gate.at, as_of=as_of)
    if open_now and gate.at > as_of:
        phrase = phrase.replace("closes in", f"{gate.label} closes in", 1)
    return Hit(item, gate.kind, gate.at, phrase, seconds, open_now)


def _sort_key(hit: Hit):
    when = hit.gate_at.isoformat() if hit.gate_at is not None else "9999"
    return (0 if hit.open_now else 1, when, hit.item.name)


def render_text(answer: Answer) -> str:
    intent = answer.intent
    bits = []
    if intent.formats == tuple(sorted(HACKATHON_FORMATS)):
        bits.append("hackathons")
    elif intent.formats:
        bits.append(intent.formats[0].replace("-", " ") + "s")
    else:
        bits.append("calls")
    if intent.regions == ("PH", "SG"):
        bits.append("open to PH/SG")
    if intent.min_prize_usd is not None:
        op = "at least" if prize_is_inclusive(intent) else "over"
        amount = int(intent.min_prize_usd) if intent.min_prize_usd.is_integer() else intent.min_prize_usd
        bits.append(f"with prizes {op} ${amount:,}")
    if intent.window:
        bits.append("closing in " + WINDOW_LABELS[intent.window])
    elif intent.status == "open":
        bits.append("still open")
    elif intent.status == "closed":
        bits.append("already closed")
    headline = " ".join(bits)
    as_of = format_sgt(answer.as_of)
    lines = [
        f"Hack Heat Live — {headline}",
        f"As of {as_of}. Board updated {answer.board_updated_at}. {len(answer.hits)} match.",
        "",
    ]
    if not answer.hits:
        lines.append("Nothing on the board matches.")
    for index, hit in enumerate(answer.hits, start=1):
        lines.append(_format_hit(index, hit))
    if answer.checks:
        lines.append("")
        lines.append(f"{len(answer.checks)} more need a PH/SG rules check before you treat them as open:")
        for hit in answer.checks:
            lines.append(f"- {hit.item.name} ({hit.item.id})")
    return "\n".join(lines).rstrip() + "\n"


def _format_hit(index: int, hit: Hit) -> str:
    item = hit.item
    prize = "prize n/a" if item.prize_usd is None else _money(item.prize_usd)
    where = "remote" if item.eligibility.remote_ok else "not remote"
    geo = {
        "yes": "PH/SG open",
        "no": "PH/SG not open",
        "check": "PH/SG check the rules",
    }[item.eligibility.status if item.eligibility.status in {"yes", "no", "check"} else "check"]
    when = "no fixed deadline" if hit.gate_at is None else format_sgt(hit.gate_at)
    flags = f" · flags: {', '.join(item.eligibility.flags)}" if item.eligibility.flags else ""
    fit = item.fit.strip()
    if len(fit) > 180:
        fit = fit[:177] + "..."
    return (
        f"{index}. {item.name}\n"
        f"   {hit.countdown} · {when} · {prize} · {where} · {geo}{flags}\n"
        f"   {item.id} · {item.apply_url}\n"
        f"   {fit}\n"
    )


def _money(amount: float) -> str:
    if amount.is_integer():
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def hit_to_dict(hit: Hit) -> dict:
    item = hit.item
    return {
        "id": item.id,
        "name": item.name,
        "lane": item.lane,
        "format": item.format or None,
        "closesAt": hit.gate_at.isoformat() if hit.gate_at else None,
        "closesAtSgt": format_sgt(hit.gate_at) if hit.gate_at else None,
        "gate": hit.gate_kind,
        "countdown": hit.countdown,
        "countdownSeconds": hit.countdown_seconds,
        "open": hit.open_now,
        "prizeAmountUsd": item.prize_usd,
        "prizeLabel": item.prize_label,
        "applyUrl": item.apply_url,
        "infoUrl": item.raw.get("infoUrl"),
        "fit": item.fit,
        "remote": item.raw.get("remote"),
        "eligibility": item.eligibility.to_dict(),
        "tags": list(item.raw.get("tags") or []),
        "mode": item.raw.get("mode"),
        "deadlineLabel": item.raw.get("deadlineLabel"),
    }


def answer_to_dict(answer: Answer) -> dict:
    intent = answer.intent
    return {
        "question": answer.question,
        "asOf": answer.as_of.isoformat(),
        "asOfSgt": format_sgt(answer.as_of),
        "timezone": "Asia/Singapore",
        "boardUpdatedAt": answer.board_updated_at,
        "summary": answer.summary,
        "count": len(answer.hits),
        "filters": {
            "status": intent.status,
            "window": intent.window,
            "windowStart": answer.window_start.isoformat() if answer.window_start else None,
            "windowEnd": answer.window_end.isoformat() if answer.window_end else None,
            "regions": list(intent.regions),
            "minPrizeUsd": intent.min_prize_usd,
            "minPrizeInclusive": prize_is_inclusive(intent),
            "formats": list(intent.formats),
            "lane": intent.lane,
        },
        "results": [hit_to_dict(hit) for hit in answer.hits],
        "confirmFirst": [hit_to_dict(hit) for hit in answer.checks],
    }
