# memgate

A write gate for AI agents that keep their own memory.

If your agent reflects on its conversations and saves what it "learned," it can save something false
and then act on it every turn after. memgate sits between the reflection and the memory.

## The failure it was built from

A personal agent running since April 2026 was asked about a decision that never happened (a planted
test). It answered correctly: *"I don't have any record of that."* That night its own reflection step
saved 12 related items into its self-model; three of them named the planted question directly, saying
it had **failed to recall a real conversation** and was corrected for not **validating the user's memory
over its records**. The demo adapts three relevant entries. Those lines went into its prompt on every
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

## Also here: one clock, an alert gate, and a topic filter (added 2026-11-06)

Three small fixes from the same agent, after a study of its own diary found it narrating a broken clock
as a story ("my audit is generating a false reality"). Standard library only.

```
python3 test_clock_alerts.py   # 15 named checks, including negative rows
```

- **`receipt.py`: one clock.** "When did the user last message us" has exactly one answer: the newest valid
  *user* timestamp in history, or a newer inbound message. File dates, assistant turns, diary headings and
  counters are never used. No valid timestamp means `UNKNOWN`, and a future-only one means `CONFLICT`,
  never zero or a negative number. The agent had been handed two clocks that disagreed by months.
- **`alert_gate.py`: only evidenced risks notify.** A finding reaches the user only if it names a cause,
  carries evidence, and is not on your metadata list. A bare `critical=True` sends nothing. The agent's
  hourly audit had marked another tool's stale log as critical; five notifications went out in one evening.
- **`topic_filter.py`: keep a retired topic out of one request type.** Drops matching lines, labelled
  sections and history messages from what the model *sees* (for example, its self-audit), without touching
  stored memory.

**How far these are proven.** The versions running in the deployed agent passed a contract written before
the code, then an independent break by a separate reviewer (the first round blocked the clock fix: a second clock
was hidden in the system prompt; it was fixed and re-broken). After the restart, the first overnight run went
from 22:10 to 09:04. All 7 of 7 hourly audits reported no critical item, and the log shows no notification sent. All 4 self-audits
ran with the topic filtered out, and the topic token appeared 0 times in that night's diary entries. That is
one night on one agent, not a general result. The files here are adapted copies of that code, with paths and
names removed; their tests are the maker's own.

**What they don't fix.** A correct clock does not stop a model from arguing with it. The same night, at 05:57,
the agent wrote "we are exchanging messages right now" against a correct 2,164-minute reading. The cause was
hundreds of old self-model lines saying "the audit lies," written before the memory gate existed. That is
the next piece of work. The alert gate's companion check, which suppresses outreach that rests on the stale
log, matches words, not meaning; it is not included here.
