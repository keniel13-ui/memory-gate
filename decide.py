#!/usr/bin/env python3
"""Owner CLI. Shows what the agent proposes to believe and records your approve/reject.

  python3 decide.py <memory-dir>                  list proposed items
  python3 decide.py <memory-dir> APPROVE mg-xxxx  record an approval (asks you to type YES)
  python3 decide.py <memory-dir> REJECT  mg-xxxx

Refuses to record unless a human terminal is attached. That is a speed bump, not a guarantee: the
library's append_decision(..., require_tty=False) skips the check (the demo and tests use it), and any
process running as the same user can write a valid chained line. Tamper-evident, not signed.
"""
import sys
from pathlib import Path

from memgate import MemoryGate, append_decision


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gate = MemoryGate(Path(sys.argv[1]), fields=())
    if len(sys.argv) == 2:
        rows = [r for r in gate.pending() if r["status"] == "PROPOSED"]
        print(f"{len(rows)} proposed")
        for r in rows:
            print(f"\n[{r['id']}] {r['field']}\n  claim: {r['item']}\n  your words ({r['evidence']}): \"{r['quote']}\"")
        return
    verb, rid = sys.argv[2].upper(), sys.argv[3]
    if verb not in ("APPROVE", "REJECT"):
        sys.exit("verb must be APPROVE or REJECT")
    if not sys.stdin.isatty():
        sys.exit("refused: no human terminal attached")
    if input(f"Record '{verb} {rid}'? Type YES: ").strip() != "YES":
        sys.exit("not recorded")
    print("recorded #chain=" + append_decision(gate.decisions_path, f"{verb} {rid}"))


if __name__ == "__main__":
    main()
