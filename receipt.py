"""One clock: "when did the user last send a message that we recorded".

The receipt is the newest valid USER timestamp in conversation history, or an accepted inbound
message seen by this process. File mtimes, assistant turns, diary headings and audit
counters are never receipts. Elapsed = now - receipt. "Unknown" is a real state, not zero.

Naive (legacy) timestamps are read as the machine's local zone. A naive time that is ambiguous
(DST fall-back) or nonexistent (spring-forward) in that zone is rejected as invalid rather than
turned into a precise elapsed figure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class UserReceipt:
    status: str  # "known" | "unknown" | "conflict"
    at: datetime | None = None  # timezone-aware instant when status == "known"
    source: str = ""
    detail: str = ""

    def elapsed_seconds(self, now: datetime) -> float | None:
        if self.status != "known" or self.at is None:
            return None
        return (_aware(now) - self.at).total_seconds()

    def describe(self, now: datetime) -> str:
        """One line for audits and prompts. Never claims the user was absent."""
        now = _aware(now)
        if self.status != "known" or self.at is None:
            return f"{self.status.upper()} ({self.detail or 'no valid recorded user message'})"
        minutes = (now - self.at).total_seconds() / 60
        return (
            f"{self.at.astimezone().strftime('%Y-%m-%d %H:%M %Z')} from {self.source}; "
            f"{minutes:.0f} minutes before {now.astimezone().strftime('%Y-%m-%d %H:%M %Z')}. "
            "This is time since the last RECORDED message, not proof he was away."
        )

    def heading_minutes(self, now: datetime) -> str:
        seconds = self.elapsed_seconds(now)
        return "unknown" if seconds is None else f"{seconds / 60:.0f}min"


def _aware(dt: datetime) -> datetime:
    return dt.astimezone() if dt.tzinfo is None else dt


def _parse_user_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed
    first = parsed.replace(fold=0).astimezone()
    second = parsed.replace(fold=1).astimezone()
    if first.utcoffset() != second.utcoffset():
        return None  # ambiguous local time
    if first.replace(tzinfo=None) != parsed:
        return None  # nonexistent local time (normalised to a different wall clock)
    return first


def resolve_user_receipt(history: Iterable[dict], now: datetime, *, source_name: str) -> UserReceipt:
    now = _aware(now)
    best: tuple[datetime, int] | None = None
    user_rows = invalid = future = 0
    for index, item in enumerate(history):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        user_rows += 1
        at = _parse_user_timestamp(item.get("timestamp"))
        if at is None:
            invalid += 1
            continue
        if at > now:
            future += 1
            continue
        if best is None or at > best[0]:
            best = (at, index)
    if best is not None:
        detail = f"{future} future and {invalid} invalid user timestamps ignored" if (future or invalid) else ""
        return UserReceipt("known", best[0].astimezone(timezone.utc), f"{source_name} row {best[1]} (user)", detail)
    if future:
        return UserReceipt("conflict", detail=f"{future} user timestamp(s) are later than now; {invalid} invalid")
    if invalid:
        return UserReceipt("unknown", detail=f"{invalid} user timestamp(s) could not be read")
    return UserReceipt("unknown", detail=f"no user rows in {source_name}" if not user_rows else "no usable user rows")


def inbound_receipt(at: datetime, message_id: Any) -> UserReceipt:
    return UserReceipt("known", _aware(at).astimezone(timezone.utc), f"inbound message {message_id}")


def newest(*receipts: UserReceipt | None) -> UserReceipt:
    known = [(r.at, r) for r in receipts if r is not None and r.status == "known" and r.at is not None]
    if known:
        return max(known, key=lambda pair: pair[0])[1]
    for r in receipts:
        if r is not None:
            return r
    return UserReceipt("unknown", detail="no receipt")
