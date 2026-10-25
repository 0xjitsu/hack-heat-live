"""Philippines and Singapore eligibility, read from the board's own notes.

The GitLab Transcend rules exclude a fixed territory list. The Philippines
and Singapore are not on it. This module applies that fact only when a row
says the call uses the standard Devpost exclusion list, and it trusts an
explicit PH/SG note on the row over the default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Eligibility:
    open_to_ph_sg: bool
    status: str  # yes, no, check
    remote_ok: bool
    reasons: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "openToPhSg": self.open_to_ph_sg,
            "status": self.status,
            "remoteOk": self.remote_ok,
            "reasons": list(self.reasons),
            "flags": list(self.flags),
        }


def _remote_ok(value) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "false", "no", "0", "irl", "on-site", "onsite"}:
            return False
        return True
    return False


def assess(raw: dict) -> Eligibility:
    text = " ".join(
        str(raw.get(key) or "")
        for key in ("residencyRisk", "fit", "notes", "deadlineLabel", "registrationLabel")
    ).lower()
    remote_ok = _remote_ok(raw.get("remote"))
    reasons: list[str] = []
    flags: list[str] = []
    status = "yes"

    if not remote_ok:
        status = "no"
        reasons.append("The row is not a remote entry, so it is not an open PH/SG application.")

    explicit_yes = (
        "ph/sg ok" in text
        or "ph/sg not excluded" in text
        or "none for ph/sg" in text
        or "no nationality/residence restriction" in text
        or "no nationality/region limit" in text
        or "all countries/territories, excluding standard" in text
    )
    if explicit_yes and status != "no":
        status = "yes"
        reasons.append("The board notes that PH/SG are not excluded.")

    if "check rules for ph/sg" in text and status != "no":
        status = "check"
        reasons.append("The board says to confirm PH/SG against the official rules.")

    for label, needles in (
        ("the Philippines", ("excluding philippines", "philippines excluded", "excludes the philippines", "not open to ph")),
        ("Singapore", ("excluding singapore", "singapore excluded", "excludes singapore", "not open to sg")),
    ):
        if any(needle in text for needle in needles):
            status = "no"
            reasons.append(f"The board calls out {label} as excluded.")

    standard = (
        "standard devpost" in text
        or "devpost standard" in text
        or "standard exceptions" in text
        or "standard country exclusions" in text
        or "devpost exclusions" in text
    )
    if standard and status == "yes":
        reasons.append(
            "Standard Devpost territory exclusions do not include the Philippines or Singapore."
        )

    if ("china-focused" in text or "zh subtitles" in text) and status == "yes":
        status = "check"
        reasons.append("Described as China-focused. Confirm the rules before applying from PH/SG.")

    if "students only" in text:
        flags.append("students only")
    if "under 35" in text or "under-35" in text:
        flags.append("under 35")
    if "aws partner" in text:
        flags.append("AWS Partner required")
    if "ages 18+" in text or "18+" in text:
        flags.append("18+")

    if not reasons:
        if remote_ok:
            reasons.append("Remote entry, and the board does not exclude PH/SG.")
        else:
            reasons.append("On-site or otherwise not remote.")

    open_to = status == "yes" and remote_ok
    return Eligibility(
        open_to_ph_sg=open_to,
        status="yes" if open_to else status,
        remote_ok=remote_ok,
        reasons=tuple(reasons),
        flags=tuple(flags),
    )
