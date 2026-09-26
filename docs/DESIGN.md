# Design notes

How the incident pipeline works, why it is built this way, and where it falls short.

## Data flow

1. **Parse** (`src/logformats.py`). Each input file is matched against the known formats by trying every parser on the first 50 lines and picking the one with the most matches. Every parser returns the same event shape, so nothing downstream depends on the source format. Vendor level names are normalized (`FATAL` → `CRITICAL`, `SEVERE` → `ERROR`, `WARNING` → `WARN`).
2. **Featurize** (`src/core.py:load_logs`). The main feature is the message *template*: the message with hex values, block IDs and numbers masked, so `data address: 0x00c4f2a8` and `data address: 0xdeadbeef` count as the same event type.
3. **Detect** (`src/core.py:score_anomalies`). An event alerts when the rule fires, or when Isolation Forest rates a WARN-or-higher event as an outlier. Templates suppressed by operator feedback are dropped.
4. **Route and prioritize** (`src/core.py:decide`). The first matching keyword group picks the team. Priority comes from level and anomaly score, and SLA deadlines follow from priority.
5. **Persist and notify** (`src/pipeline.py`). The event ID is a hash of the raw line, and a unique constraint makes reruns idempotent. Webhook failures are counted, not raised.
6. **Human loop** (`src/api.py`). Operators record verdicts, propose and approve actions, and every change writes an audit event.

## Decisions

**Rules first, ML second.** On labelled BGL logs the rules catch every anomaly, while Isolation Forest alone catches 13% (see the README). The forest scores events on three shallow features (length, keyword count, level weight), which can't separate a hardware fault from a verbose but harmless message. Its output still sets priority and covers WARN events that match no rule. It is not allowed to alert on INFO events: in the demo log it scores "Backup checkpoint completed" (0.91) above the CRITICAL DNS outage (0.78).

**INFO never alerts on keywords alone.** The emitting system already classed the event as routine. In BGL, INFO lines include "42 critical input interrupts" and "ddr errors detected and corrected". None are labelled anomalies, but together they produced most of the v1 false positives.

**Feedback works on templates, not lines.** Operators judge types of alert. Recording a verdict against the masked template lets three "not an incident" verdicts silence every future variant of a register-dump line.

**Suppression needs agreement and has zero tolerance.** A template is suppressed after at least 3 verdicts, and only if none of them confirmed a real incident. One mistaken click cannot hide a class of alerts, and a template that has ever been a real incident keeps alerting.

**Idempotency comes from a content hash.** Re-ingesting the same file creates no duplicates. The downside is that two identical lines at different times collapse into one incident. That is acceptable for formats with timestamps in the line (all three supported ones), but not for formats without them.

**Notifications are best-effort.** Incidents are committed before the webhook is called, and a webhook outage is logged and counted. Before this change, one failed webhook call aborted the rest of the batch.

## Known limitations

- **Precision is low on BGL (0.26).** Many BGL FATAL events are normal (jobs that fail to load a program image), and severity can't separate them from hardware faults. Improving this needs per-component rules or a supervised model trained on labelled history.
- **Feedback is unproven.** On the 2,000-line sample, the noise templates learned from the first half never recur in the second half. The full BGL dataset (4.7M lines) would be the right test.
- **The benchmark is small and was not held out from development.** The rule refinements came from error analysis on the same sample, so the numbers are indicative.
- **Isolation Forest is refit on every batch.** Scores are relative to the batch, so the same line can score differently in a different file.
- **Routing is keyword-based.** The first matching group wins, so "database timeout" goes to Database Operations because that group is checked before Network. The curated evaluation covers these cases, but there is no routing ground truth on real data.
- **No authentication.** The API trusts the `actor` field, so the audit trail records who a caller *says* they are.
- **Schema changes are not migrated.** `init_db` creates missing tables but does not alter existing ones. A production deployment would use Alembic.
