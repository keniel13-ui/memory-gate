"""Run: python3 test_clock_alerts.py   (no dependencies). Named checks for receipt.py, alert_gate.py and
topic_filter.py, including negative rows (cases where the fix must NOT fire)."""
from datetime import datetime, timedelta, timezone

from alert_gate import AuditResult, Finding, alert_text, sendable
from receipt import inbound_receipt, newest, resolve_user_receipt
from topic_filter import OMITTED_MESSAGE, OmissionReceipt, project_messages, project_text, token_pattern

res = []


def ok(name, cond):
    res.append(bool(cond)); print("PASS" if cond else "FAIL", name)


EST = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 4, 18, 3, tzinfo=EST)

# ---- receipt.py: one clock ----
hist = [{"role": "user", "timestamp": "2026-11-04T17:53:00-05:00"},
        {"role": "assistant", "timestamp": "2026-11-04T18:01:00-05:00"}]
r = resolve_user_receipt(hist, NOW, source_name="history.json")
ok("clock counts from the user's last message, not the assistant's", r.elapsed_seconds(NOW) == 600)
out_of_order = [{"role": "user", "timestamp": "2026-11-04T22:53:00Z"},
                {"role": "user", "timestamp": "2026-11-04T17:40:00-05:00"}]
ok("latest instant wins even when it is not the last row; Z offsets normalised",
   resolve_user_receipt(out_of_order, NOW, source_name="h").elapsed_seconds(NOW) == 600)
ok("no user rows -> UNKNOWN, not zero and not a file date",
   resolve_user_receipt([{"role": "assistant", "timestamp": "2026-11-04T18:00:00-05:00"}], NOW, source_name="h").status == "unknown")
ok("only a future timestamp -> CONFLICT, never a negative duration",
   resolve_user_receipt([{"role": "user", "timestamp": "2026-11-04T19:00:00-05:00"}], NOW, source_name="h").status == "conflict")
ok("unreadable timestamp -> UNKNOWN",
   resolve_user_receipt([{"role": "user", "timestamp": "yesterday-ish"}], NOW, source_name="h").status == "unknown")
later = datetime(2026, 11, 4, 18, 4, tzinfo=EST)
both = newest(r, inbound_receipt(datetime(2026, 11, 4, 18, 3, tzinfo=EST), "m-1"))
ok("an inbound message advances the same clock", both.elapsed_seconds(later) == 60 and "m-1" in both.source)
ok("the description says 'recorded', not 'away'", "not proof" in r.describe(NOW))

# ---- alert_gate.py: only evidenced live risks notify ----
META = frozenset({"stale_tool_log"})
legacy = AuditResult(critical=True)
ok("a bare critical flag sends nothing", sendable(legacy, META) == [])
stale = AuditResult(findings=(Finding("stale_tool_log", "last session 2026-10-22"),), critical=True)
ok("a metadata cause sends nothing even when marked critical", sendable(stale, META) == [])
ok("a cause with no evidence sends nothing", sendable(AuditResult(findings=(Finding("disk_full", "  "),)), META) == [])
real = AuditResult(findings=(Finding("stale_tool_log", "2026-10-22"), Finding("disk_full", "/ at 98%")), critical=True)
s = sendable(real, META)
ok("NEGATIVE: a real evidenced risk still sends, without the metadata riding along",
   [f.cause for f in s] == ["disk_full"] and "stale_tool_log" not in alert_text(s))

# ---- topic_filter.py: retired topic out of one request type ----
P = token_pattern("btc", "bitcoin")
rc = OmissionReceipt()
text = "a BTC b\nb btc c\nBitcoin d\npair BTC-USDT\n# BTC notes\nno ticker duty\n# Other\nclean line\n"
ok("lines, variants and a whole labelled section are dropped",
   project_text(text, P, rc) == "# Other\nclean line\n" and rc.sections == 1)
rc2 = OmissionReceipt()
clean = "ABTCX is a fund code.\nForum is paused.\n"
ok("NEGATIVE: a non-token string is left alone", project_text(clean, P, rc2) == clean and rc2.total() == 0)
msgs = [{"role": "user", "content": "btc signal?"}, {"role": "assistant", "content": "checking"}]
pm = project_messages(msgs, P, OmissionReceipt())
ok("a matching history message is replaced whole; role order kept",
   pm[0] == {"role": "user", "content": OMITTED_MESSAGE} and pm[1] == msgs[1])
ok("the input list is not modified (stored memory never changes)", msgs[0]["content"] == "btc signal?")

print(f"\n{sum(res)}/{len(res)} checks passed")
raise SystemExit(0 if all(res) else 1)
