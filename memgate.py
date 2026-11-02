"""memgate: a write gate for agents that keep their own memory.

An agent that reflects on its own conversations and saves what it "learned" can write a false belief
into memory and then act on it every turn after. memgate sits between the agent's reflection and its
memory:

  1. Evidence: every proposed memory must quote the USER's exact words from a recent turn. The code
     checks the quote is really in that turn. The agent's own replies are never evidence.
     This checks that the quote EXISTS, not that the claim FOLLOWS from it. A false claim that cites a
     real user sentence passes this step. That is what step 3 is for.
  2. Holding: items that pass evidence go to a PROPOSED pile, not into live memory.
  3. Owner approval: only an approval line the owner typed (hash-chained, tty-only CLI) moves an item
     live. A model output can never approve anything.
  4. Audit: every dropped item is written to a log with the reason, so the drops can be checked.
  5. Secrets: anything token- or key-shaped is redacted before it is written anywhere.

No dependencies beyond the Python standard library.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROPOSED = "PROPOSED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

_SECRET_PATTERNS = (
    re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}"),     # Telegram bot token
    re.compile(r"(?<=key=)[^\s&\"'<>]+"),          # ?key=<value>
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),           # OpenAI / Anthropic style
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),          # Google API key
    re.compile(r"\bAQ\.[A-Za-z0-9_.-]{20,}"),       # Google API key (new format)
)
_APPROVAL_RE = re.compile(r"^(APPROVE|REJECT)\s+(mg-[0-9a-f]{10})\s*$", re.IGNORECASE)


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("REDACTED", text)
    return text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def item_id(field: str, item: str) -> str:
    return "mg-" + hashlib.sha256(f"{field}\n{item}".encode()).hexdigest()[:10]


@dataclass
class Turn:
    role: str      # "user" or "assistant"
    content: str


def chained_decisions(path: Path) -> list[tuple[str, str]]:
    """Owner decision lines that verify on the hash chain, as (text, chain). Anything else is ignored."""
    out, prev = [], "genesis"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- ") and " #chain=" in line:
            body, h = line.rsplit(" #chain=", 1)
            if hashlib.sha256((prev + "\n" + body).encode()).hexdigest()[:16] == h.strip():
                out.append((body[2:].split(" · ", 1)[-1].strip(), h.strip()))
                prev = h.strip()
    return out


def append_decision(path: Path, text: str, *, require_tty: bool = True) -> str:
    """Append one chained owner decision. Refuses unless a human terminal is attached.
    Limit: the chain is tamper-evident, not signed. A process running as the same user can compute a
    valid next line itself; this check stops accidents and lazy agents, not a determined one."""
    import sys
    if require_tty and not sys.stdin.isatty():
        raise PermissionError("owner decisions need a human terminal")
    prev = "genesis"
    for _, h in chained_decisions(path):
        prev = h
    body = f"- {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')} · {redact(text)}"
    h = hashlib.sha256((prev + "\n" + body).encode()).hexdigest()[:16]
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{body} #chain={h}\n")
    return h


class MemoryGate:
    def __init__(self, root: Path, fields: tuple[str, ...], min_quote: int = 12):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fields = fields
        self.min_quote = min_quote
        self.live_path = self.root / "memory.json"
        self.pending_path = self.root / "pending.json"
        self.dropped_path = self.root / "dropped.jsonl"
        self.decisions_path = self.root / "DECISIONS.md"

    # -- storage ---------------------------------------------------------------------------------
    def live(self) -> dict[str, list[str]]:
        if self.live_path.exists():
            return json.loads(self.live_path.read_text(encoding="utf-8"))
        return {f: [] for f in self.fields}

    def pending(self) -> list[dict]:
        if self.pending_path.exists():
            return json.loads(self.pending_path.read_text(encoding="utf-8"))
        return []

    def _write(self, path: Path, obj) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(redact(json.dumps(obj, indent=2, ensure_ascii=False)), encoding="utf-8")
        tmp.replace(path)

    def _drop(self, field: str, item: str, reason: str) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(), "field": field, "item": item, "reason": reason}
        with self.dropped_path.open("a", encoding="utf-8") as f:
            f.write(redact(json.dumps(row, ensure_ascii=False)) + "\n")

    # -- the gate --------------------------------------------------------------------------------
    def propose(self, proposals: dict, turns: list[Turn]) -> dict:
        """proposals: {field: [{"item", "evidence": "T<n>", "quote"}]} from the agent's reflection.
        turns: the recent conversation, numbered T1..Tn in order. Returns counts."""
        user_turns = {f"T{i}": t.content for i, t in enumerate(turns, 1) if t.role == "user"}
        rows, live = self.pending(), self.live()
        seen = {(r["field"], r["item"]) for r in rows}
        counts = {"proposed": 0, "dropped": 0}
        for field, items in (proposals or {}).items():
            for raw in items or []:
                if field not in self.fields:
                    self._drop(field, str(raw), "unknown field"); counts["dropped"] += 1; continue
                if not isinstance(raw, dict):
                    self._drop(field, str(raw), "no evidence object"); counts["dropped"] += 1; continue
                item = str(raw.get("item", "")).strip()
                ev, quote = str(raw.get("evidence", "")).strip(), str(raw.get("quote", "")).strip()
                if ev not in user_turns:
                    self._drop(field, item, f"evidence {ev or '-'} is not a user turn"); counts["dropped"] += 1; continue
                if len(_norm(quote)) < self.min_quote or _norm(quote) not in _norm(user_turns[ev]):
                    self._drop(field, item, f"quote not found in {ev}"); counts["dropped"] += 1; continue
                if not item or item in live.get(field, []) or (field, item) in seen:
                    continue
                rows.append({"id": item_id(field, item), "field": field, "item": item, "evidence": ev,
                             "quote": quote, "status": PROPOSED,
                             "ts": datetime.now(timezone.utc).isoformat()})
                seen.add((field, item)); counts["proposed"] += 1
        self._write(self.pending_path, rows)
        return counts

    def apply_owner_decisions(self) -> int:
        """Move PROPOSED items live only on a chained APPROVE line; REJECT never goes live. Idempotent."""
        verdicts = {}
        for text, chain in chained_decisions(self.decisions_path):
            m = _APPROVAL_RE.match(text)
            if m:
                verdicts[m.group(2).lower()] = (m.group(1).upper(), chain)
        rows, live, changed = self.pending(), self.live(), 0
        for r in rows:
            if r["status"] != PROPOSED or r["id"] not in verdicts:
                continue
            verb, chain = verdicts[r["id"]]
            if verb == "APPROVE":
                live.setdefault(r["field"], [])
                if r["item"] not in live[r["field"]]:
                    live[r["field"]].append(r["item"])
                r["status"] = f"{APPROVED} #chain={chain}"
            else:
                r["status"] = f"{REJECTED} #chain={chain}"
            changed += 1
        if changed:
            self._write(self.live_path, live)
            self._write(self.pending_path, rows)
        return changed
