# memgate

A write gate for AI agents that keep their own memory.

If your agent reflects on its conversations and saves what it "learned," it can save something false
and then act on it every turn after. memgate sits between the reflection and the memory.

## The failure it was built from

A personal agent running since April 2026 was asked about a decision that never happened (a planted
test). It answered correctly: *"I don't have any record of that."* That night its own reflection step
saved three memories: that it had **failed to recall a real conversation**, and that it was corrected
for not **validating the user's memory over its records**. Those lines went into its prompt on every
reply until they were found and removed later that day.

This class of failure is documented in lab settings (see *Honest Lying: Understanding Memory
Confabulation in Reflexive Agents*, arXiv 2605.29463, ALFWorld/HumanEval). This happened in a
deployed personal agent; `demo.py` replays an adapted version (names, topic and wording changed; see
its docstring for exactly what was changed).

## Run it (no API keys, standard library only)

```
python3 demo.py          # the real incident, with and without the gate
python3 test_memgate.py  # 12 named checks: reject paths, positive paths, and one asserted limit
```

## What the gate does

1. **Evidence.** Every proposed memory must quote the *user's* exact words from a recent turn, and the
   code checks the quote is in that turn. The agent's own replies are never evidence. **This checks that
   the quote exists, not that the claim follows from it.** A false claim that cites a real sentence
   passes (the demo shows one, and `test_memgate.py` asserts it). It filters unbacked noise; it is not a
   truth check.
2. **Holding.** Items that pass go to a PROPOSED pile, not into live memory.
3. **Owner approval: the actual safeguard.** Every surviving claim waits, shown next to the user words it
   cites, until the owner approves or rejects it (`decide.py`; refuses without a human terminal;
   hash-chained). The gate makes the owner the judge; it does not judge for them.
4. **Audit.** Every dropped item is logged with its reason, so you can check the gate itself.
5. **Secrets.** Token- and key-shaped strings are redacted before anything is written.

## Use it in your agent

```python
from memgate import MemoryGate, Turn
gate = MemoryGate("agent_memory/", fields=("facts_about_user", "lessons"))
counts = gate.propose(reflection_output, recent_turns)   # {"proposed": n, "dropped": m}
gate.apply_owner_decisions()                             # call before each turn
prompt_memory = gate.live()                              # only approved items
```

Ask your reflection model for `{field: [{"item", "evidence": "T<n>", "quote"}]}` with the recent turns
numbered T1..Tn in the prompt.

## Limits, stated up front

- It does not decide truth. Unquoted items are dropped; quoted items, true or false, wait for the owner.
  If the owner approves a false claim, it goes live.
- It does not stop the model from *thinking* false things; a reflection can still be wrong in its text.
- A strict evidence rule drops some true items too. The dropped log is there so you can see the cost.
- The decision file is tamper-evident (hash chain), not signed. A process running as the same user can
  compute a valid next line and forge an approval; the terminal check in `append_decision` stops
  accidents and lazy agents, not a determined one, and `append_decision(..., require_tty=False)` (used
  by the demo and tests) skips it entirely. `memory.json` itself is unsigned.
- Quote matching is exact text after whitespace/case normalization. Paraphrased evidence is dropped.
