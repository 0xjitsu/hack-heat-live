"""Validate a candidate board row and refuse to write it until a human approves.

This is the deterministic half of the supervised radar-curator flow. GitLab Duo
runs the same commands from the flow. The human approval flag is required on
purpose: the agent may prepare the update, and a person accepts the outcome.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from hackheat.board import load_board, load_payload
from hackheat.eligibility import assess
from hackheat.timeutil import format_sgt, now, parse_instant

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LANES = {"code", "creative", "marine", "film"}
REQUIRED_URL_FIELDS = ("applyUrl",)


def validate_candidate(candidate: dict, *, board_ids: set[str], as_of: datetime | None = None) -> dict:
    moment = as_of or now()
    errors: list[str] = []
    warnings: list[str] = []

    item_id = str(candidate.get("id") or "").strip()
    if not item_id or not SLUG.match(item_id):
        errors.append("id must be a lowercase slug, such as sample-sea-agents-2026.")
    elif item_id in board_ids and not candidate.get("updateExisting"):
        errors.append(f"id {item_id} is already on the board. Set updateExisting true to propose a replacement.")

    name = str(candidate.get("name") or "").strip()
    if not name:
        errors.append("name is required.")
    elif len(name) > 200:
        errors.append("name must be 200 characters or fewer.")

    lane = candidate.get("lane")
    if lane not in LANES:
        errors.append(f"lane must be one of {', '.join(sorted(LANES))}.")

    for field in REQUIRED_URL_FIELDS:
        if not _http_url(candidate.get(field)):
            errors.append(f"{field} must be an http(s) URL.")

    if "remote" not in candidate:
        errors.append("remote is required so PH/SG eligibility can be judged.")

    deadline = _parse_optional(candidate.get("deadline"), "deadline", errors)
    registration_closes = _parse_optional(candidate.get("registrationCloses"), "registrationCloses", errors)
    if deadline is None and registration_closes is None:
        errors.append("A deadline or registrationCloses timestamp is required. Rolling calls must say so in notes.")

    future_gates = [instant for instant in (deadline, registration_closes) if instant and instant > moment]
    past_gates = [instant for instant in (deadline, registration_closes) if instant and instant <= moment]
    if not future_gates and (deadline or registration_closes) and not candidate.get("allowClosed"):
        errors.append("Every supplied deadline is already past. Refusing a closed call unless allowClosed is true.")
    elif past_gates and future_gates:
        warnings.append("One gate is already past. The review keeps the row only because a later gate is still open.")

    prize = candidate.get("prizeAmountUsd")
    if prize is not None and prize != "":
        if isinstance(prize, bool) or not isinstance(prize, (int, float)):
            errors.append("prizeAmountUsd must be a number or null.")
        elif prize < 0:
            errors.append("prizeAmountUsd cannot be negative.")

    tags = candidate.get("tags")
    if tags is not None and (not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)):
        errors.append("tags must be a list of strings.")

    if not str(candidate.get("residencyRisk") or "").strip() and not str(candidate.get("notes") or "").strip():
        warnings.append("Add residencyRisk or notes so a reviewer can see who the call excludes.")
    if not str(candidate.get("format") or "").strip():
        warnings.append("format is empty. Use hackathon, open-call, film-festival, challenge, or another board format.")
    if not str(candidate.get("fit") or "").strip():
        warnings.append("fit is empty. One line on why this row belongs on the weekly board helps the reviewer.")

    eligibility = assess(candidate)
    if errors:
        verdict = "reject"
    elif warnings:
        verdict = "needs_changes"
    else:
        verdict = "approve"

    next_gate = min(future_gates) if future_gates else None
    return {
        "id": item_id,
        "verdict": verdict,
        "needsHumanApproval": verdict == "approve",
        "errors": errors,
        "warnings": warnings,
        "eligibility": eligibility.to_dict(),
        "nextGate": next_gate.isoformat() if next_gate else None,
        "nextGateSgt": format_sgt(next_gate) if next_gate else None,
        "normalized": _normalized(candidate) if verdict != "reject" else None,
        "instruction": _instruction(verdict),
    }


def _instruction(verdict: str) -> str:
    if verdict == "approve":
        return (
            "The row is valid. Do not edit the board until a person approves this outcome. "
            "After approval, run curator apply with --approved-by."
        )
    if verdict == "needs_changes":
        return "Fix the warnings, then ask for review again. Do not write the board yet."
    return "Do not add this row. Report the errors on the merge request and stop."


def _normalized(candidate: dict) -> dict:
    kept = {
        "id": str(candidate.get("id") or "").strip(),
        "name": str(candidate.get("name") or "").strip(),
        "lane": candidate.get("lane"),
        "tags": list(candidate.get("tags") or []),
        "deadline": candidate.get("deadline"),
        "deadlineLabel": candidate.get("deadlineLabel"),
        "prize": candidate.get("prize"),
        "remote": candidate.get("remote"),
        "residencyRisk": candidate.get("residencyRisk"),
        "applyUrl": candidate.get("applyUrl"),
        "infoUrl": candidate.get("infoUrl") or candidate.get("applyUrl"),
        "fit": candidate.get("fit"),
        "format": candidate.get("format"),
        "mode": candidate.get("mode"),
        "prizeLabel": candidate.get("prizeLabel") or candidate.get("prize"),
        "prizeAmountUsd": candidate.get("prizeAmountUsd"),
        "prizeAmountNote": candidate.get("prizeAmountNote"),
        "registrationOpens": candidate.get("registrationOpens"),
        "registrationCloses": candidate.get("registrationCloses"),
        "registrationLabel": candidate.get("registrationLabel"),
        "notes": candidate.get("notes"),
        "org": candidate.get("org"),
    }
    return {key: value for key, value in kept.items() if value not in (None, "", []) or key in {"remote", "prizeAmountUsd", "tags"}}


def _parse_optional(value, field: str, errors: list[str]):
    if value in (None, ""):
        return None
    try:
        return parse_instant(str(value))
    except ValueError:
        errors.append(f"{field} is not a parseable ISO timestamp.")
        return None


def _http_url(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def apply_candidate(candidate: dict, *, board_file: Path, approved_by: str, as_of: datetime | None = None) -> dict:
    who = approved_by.strip()
    if len(who) < 2:
        raise SystemExit("Refusing to write the board without --approved-by set to a person's name.")
    payload = load_payload(board_file)
    ids = {str(item.get("id")) for item in payload.get("items") or []}
    review = validate_candidate(candidate, board_ids=ids, as_of=as_of)
    if review["verdict"] != "approve":
        raise SystemExit(f"Refusing to apply a row whose verdict is {review['verdict']}.")
    normalized = review["normalized"]
    items = list(payload.get("items") or [])
    if candidate.get("updateExisting"):
        items = [normalized if item.get("id") == normalized["id"] else item for item in items]
    else:
        items.append(normalized)
    payload["items"] = items
    payload["updatedAt"] = (as_of or now()).isoformat()
    payload["lastCuratorApproval"] = {"id": normalized["id"], "approvedBy": who}
    board_file.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    review["applied"] = True
    review["approvedBy"] = who
    review["board"] = str(board_file)
    return review


def _print(review: dict) -> None:
    json.dump(review, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review a Hack Heat candidate row.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Review a candidate JSON file and print the verdict.")
    validate.add_argument("path", type=Path)
    validate.add_argument("--board", type=Path, default=None)

    apply_cmd = sub.add_parser("apply", help="Write an approved row onto a board file.")
    apply_cmd.add_argument("path", type=Path)
    apply_cmd.add_argument("--board", type=Path, required=True)
    apply_cmd.add_argument("--approved-by", required=True)

    args = parser.parse_args(argv)
    candidate = json.loads(args.path.read_text(encoding="utf-8"))
    if args.command == "validate":
        board = load_board(args.board)
        review = validate_candidate(candidate, board_ids={item.id for item in board.items})
        _print(review)
        return 0 if review["verdict"] == "approve" else 1
    review = apply_candidate(candidate, board_file=args.board, approved_by=args.approved_by)
    _print(review)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
