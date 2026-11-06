"""Alert gate: only an evidenced live-risk cause may message the user.

The failure it was built from: an hourly audit flagged "Claude session log is stale" as critical
whenever the user had been quiet for 24h, and critical meant a phone notification. Five went out in
one evening (18:05 through 22:08). Staleness of another tool's log is metadata, not a risk.

The rule: a finding reaches the user only if it names a cause, carries evidence, and the cause is not
on the metadata list. A bare `critical=True` is not enough.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    cause: str
    evidence: str


@dataclass(frozen=True)
class AuditResult:
    findings: tuple[Finding, ...] = ()
    critical: bool = False  # legacy flag; never sufficient on its own
    metadata: tuple[str, ...] = field(default_factory=tuple)  # facts worth logging, never alerts


def sendable(result: AuditResult, metadata_causes: frozenset[str]) -> list[Finding]:
    """Findings allowed to notify: named, evidenced, not a metadata cause."""
    return [
        f for f in result.findings
        if f.cause and f.cause not in metadata_causes and f.evidence.strip()
    ]


def alert_text(findings: list[Finding]) -> str:
    """Built from the sendable findings only, so metadata can't ride along in the message."""
    return "Critical: " + " ".join(f"{f.cause}: {f.evidence}" for f in findings)
