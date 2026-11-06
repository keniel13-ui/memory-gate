"""Topic filter: keep a retired topic out of what the model sees for one kind of request.

The failure it was built from: an agent's memory still held months of notes about a project the owner
had shut down, so its self-audits kept narrating that project as live. Deleting the memory would erase
history; this filters the request instead. Stored memory is never changed.

Lexical and section rule, not a semantic filter:
- a token match is a whole token from your list, any case ("BTC-USDT" matches btc; "ABTCX" does not);
- plain text: a matching line is dropped; a markdown heading that matches drops its whole section,
  lines without the token included, until the next heading of the same or higher level;
- history items: a matching message is replaced whole by a placeholder (keeps role order).
It is an input filter, not an output guarantee: the model can still mention the topic from its weights.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

def token_pattern(*tokens: str) -> re.Pattern[str]:
    """Whole-token, case-insensitive. Example: token_pattern("btc", "bitcoin")."""
    alternatives = "|".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", re.IGNORECASE)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
OMITTED_MESSAGE = "[message omitted from this view]"


@dataclass
class OmissionReceipt:
    lines: int = 0
    sections: int = 0
    messages: int = 0
    rules: list[str] = field(default_factory=list)

    def total(self) -> int:
        return self.lines + self.sections + self.messages


def project_text(text: str, pattern: re.Pattern[str], receipt: OmissionReceipt) -> str:
    out: list[str] = []
    skip_level: int | None = None
    for line in text.splitlines(keepends=True):
        heading = _HEADING_RE.match(line.rstrip("\r\n"))
        if heading:
            level = len(heading.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and pattern.search(heading.group(2)):
                skip_level = level
                receipt.sections += 1
                receipt.rules.append("section")
                continue
        if skip_level is not None:
            receipt.lines += 1
            continue
        if pattern.search(line):
            receipt.lines += 1
            receipt.rules.append("line")
            continue
        out.append(line)
    return "".join(out)


def _message_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return str(content)


def project_messages(messages: list[dict], pattern: re.Pattern[str], receipt: OmissionReceipt) -> list[dict]:
    out = []
    for message in messages:
        if pattern.search(_message_text(message.get("content", ""))):
            receipt.messages += 1
            receipt.rules.append("message")
            out.append({**message, "content": OMITTED_MESSAGE})
        else:
            out.append(message)
    return out
