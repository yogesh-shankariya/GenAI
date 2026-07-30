# Two-Thread Idempotency Test Plan — doc-meta, single pod

**Date:** 2026-07-30 · **Service under test:** doc-meta consumer (NOT doc-extract) · **Audience:** Claude Code (client side) for implementation, then business for results.

## Purpose and scope

Prove, with visible log evidence, that a **single pod running 2 worker threads** never processes the same message twice when fed **20 messages built from 10 REAL payloads, each sent twice** (10 originals + 10 duplicate copies).

**In scope:** the idempotency gate only — duplicate detection, the thread race, marker lifecycle. Using real payloads additionally validates that the **trace-id extraction works on the real message contract** (real body shape, SNS envelope if present, real `metadata.traceId`) — something synthetic bodies cannot prove.
**Out of scope (deliberately):** the real processing pipeline. Processing stays **stubbed** (see task 3) even though payloads are real — this phase tests the gate, not the pipeline, and the stub keeps the run free of side effects (no S3/OCR/LLM cost, no downstream publishes). Full end-to-end testing is a later phase.

---

## Part 1 — Implementation tasks (for Claude Code on the client side)

### Task 1: Add the thread name to every log line

Add `%(threadName)s` to the active log format (both the `logger_config.yaml` used in the client environment AND the `sqs_service/_logging.py` fallback formatter):

```
%(asctime)s %(levelname)s [%(threadName)s] %(name)s %(message)s
```

Why: the worker threads are already named (`sqs-worker_0`, `sqs-worker_1` via the executor's `thread_name_prefix`). With the thread name in every line, a race becomes directly readable in Splunk — thread 0 claiming, thread 1 being refused, milliseconds apart.

### Task 2: Add a PICKED_UP log line at handler entry

In the idempotent handler (`consumer_idempotency.make_idempotent_handler`), log one INFO line **before** the idempotency gate runs:

```python
logger.info("PICKED_UP trace=%s", trace_id)
```

Why: this makes every pickup countable. Expected accounting for this test: **20 PICKED_UP → 10 processed + ~10 suppressed** (some suppressed copies are picked up twice — see "expectation setting" below — so PICKED_UP may slightly exceed 20; that is normal).

### Task 3: Add a stub-processing mode (REQUIRED for this test)

Add a config flag, e.g. `SQS_STUB_PROCESSING=1` (default **off**; must never be on in production — fail fast if set together with a production profile). When on, the consumer replaces the real `process_sqs_message` with a stub that:

1. parses nothing beyond what the gate needs (the body's `metadata.traceId`),
2. sleeps **300–500 ms** (simulates work AND holds the message in-flight so its duplicate twin genuinely races the second thread),
3. returns `True` (success) — so `END(success)` markers are written and no error-routing fires.

Why: this phase tests the gate in isolation. Even with real payloads, running the real pipeline would cost real S3/OCR/LLM money, publish real downstream results twice-attempted, and mix pipeline behavior into the idempotency evidence. The stub keeps the run cheap, side-effect-free, and unambiguous. (The pipeline gets its turn in the end-to-end phase — with these same payloads if desired, see cleanup warning.)

### Task 4: Keep the existing gate log lines EXACTLY as worded

The Splunk queries below depend on these strings (already emitted by the shared wiring — do not reword them):

| Log line (substring) | Meaning |
|---|---|
| `Created MPS_START` | a thread won the claim |
| `Lock held - another thread is creating MPS_START for <trace>` | **the smoking gun** — two threads hit the same trace at the same instant; the loser was refused |
| `owned by another worker - left on queue` | Scenario B suppression (duplicate while original in flight) |
| `already completed - deleting` | Scenario A suppression (duplicate after completion) |
| `MESSAGE_SUCCESS` (JSON lifecycle marker with `trace_id`) | business work completed for this trace |

If doc-meta's consumer wraps or renames any of these, adjust the queries in Part 3 to match — but prefer keeping the wording.

### Task 5: Test configuration (single pod, two threads)

```bash
# scale the doc-meta consumer deployment to exactly 1 replica, then:
SQS_PROCESSING_MODE=parallel
SQS_MAX_WORKERS=2
SQS_STUB_PROCESSING=1          # the new flag from task 3
SQS_VISIBILITY_TIMEOUT=30      # test-only: lets refused duplicates redeliver
                               # in ~30s instead of 5 min, so the run drains fast
# idempotency stays ON: enable_idempotency=True + SQS_MPS_PATH on the mounted volume
```

### Task 6: The ingestion script (10 real payloads → 20 sends)

Use **10 real messages** (real bodies, real `metadata.traceId` values) and send **each one twice** — 10 originals + 10 duplicate copies = 20 sends. Rules:

- **Capture the real bodies verbatim.** Get the 10 full message bodies from wherever they exist (a dev-queue dump, producer team sample, logged bodies) and store them as files. Do NOT edit or re-serialize them — the duplicate must be the **byte-identical body sent a second time**; same `metadata.traceId` is what makes it a duplicate to the ledger, and an untouched body is what makes the contract-parsing test real.
- **Send each duplicate immediately after its original** (order: `real-1, real-1, real-2, real-2, …`). Adjacent copies land in the same 2-message receive batch, forcing the genuine two-thread race.
- Write the 10 trace_ids to a report file — needed for verification and for the pre-flight/cleanup steps below.

⚠️ **Pre-flight check — mandatory with real trace_ids.** If any of these 10 trace_ids was EVER processed in this environment before, an `END(success)` marker may already exist on the volume — and the whole test would short-circuit: every copy instantly Scenario-A-skipped, nothing processed, nothing proven. Before sending, verify and clear:

```bash
# for each of the 10 trace_ids: expect NO existing markers
ls $SQS_MPS_PATH | grep "<trace-id>"
# if any appear, delete them (or point SQS_MPS_PATH at a fresh test
# directory for this run) BEFORE ingesting
```

---

## Part 2 — Execution runbook

1. Deploy with the Task 5 configuration; confirm 1 pod, and confirm in startup logs: idempotency enabled, backend=file, parallel mode with 2 workers, stub mode ON.
2. Confirm the input queue is empty (or purge and wait out the 60 s purge window).
3. Run the Task 6 pre-flight marker check for all 10 trace_ids — must be clean before sending.
4. Run the ingestion script → 20 messages sent (10 real payloads × 2).
5. Wait for the queue to drain: `ApproximateNumberOfMessages` and `ApproximateNumberOfMessagesNotVisible` both 0. Expected: about one minute (20 messages × ~0.4 s ÷ 2 workers, plus one 30 s visibility cycle for refused duplicates).
6. Run the Part 3 queries and capture the Part 4 evidence.

---

## Part 3 — Verification: Splunk queries and expected results

> Adjust `index=` / `source=` to the doc-meta logging setup. If lifecycle markers are JSON-in-message, use `spath` or a `rex` on `trace_id`.

**Q1 — THE HEADLINE: no message processed twice.**

```
index=<idx> "MESSAGE_SUCCESS" | spath trace_id
| stats count by trace_id | where count > 1
```

**Expected: zero rows.** And on the same search, `| stats dc(trace_id)` must return **10** — exactly the 10 trace_ids from the ingestion report.

**Q2 — every pickup accounted for.**

```
index=<idx> "PICKED_UP" | rex "trace=(?<trace_id>\S+)"
| stats count by trace_id | where count > 1
```

Expected: only duplicated traces appear (a trace picked up 2–3 times), and **every** trace listed here still has exactly one `MESSAGE_SUCCESS` in Q1.

**Q3 — suppressions happened.**

```
index=<idx> ("already completed - deleting" OR "owned by another worker")
| stats count
```

Expected: **≥ 10** (see expectation setting below for why it can exceed 10).

**Q4 — the simultaneous thread race was caught (the manager's question).**

```
index=<idx> "Lock held - another thread is creating MPS_START"
| stats count
```

Expected: **> 0** — each hit is a moment both threads held copies of the same trace at the same instant and the second was refused. (Not all 10 duplicates produce this line — only the truly simultaneous ones; the rest suppress via the calmer Scenario A/B paths.)

**Q5 — one race, end to end (the screenshot for business).** Pick one trace_id from Q4's events:

```
index=<idx> "<that-trace-id>" | sort _time
| table _time, threadName, _raw
```

Expected shape:

```
[sqs-worker_0] PICKED_UP trace=abc-123
[sqs-worker_1] PICKED_UP trace=abc-123          ← both threads had it
[sqs-worker_0] Created MPS_START: abc-123__...  ← thread 0 won
[sqs-worker_1] Lock held - another thread ...   ← thread 1 refused
[sqs-worker_1] Message abc-123 owned by another worker - left on queue
[sqs-worker_0] MESSAGE_SUCCESS abc-123          ← work ran ONCE
[sqs-worker_?] Duplicate abc-123 already completed - deleting   ← ~30s later
```

**Non-Splunk cross-check — the ledger.** On the pod (or the volume):

```bash
ls $SQS_MPS_PATH | grep "__end__" | wc -l     # expected: exactly 10
```

> Note: with stub processing there are **no downstream/output-queue results** — the publish step lives inside the real pipeline, which is stubbed out. The output-queue count check belongs to the later end-to-end phase, not this test.

### Expectation setting (read before interpreting numbers)

- **Suppression count is ≥ 10, not == 10.** A duplicate caught mid-flight logs `owned by another worker` (left on queue), then redelivers after the visibility timeout and logs `already completed - deleting`. One duplicate copy → up to two suppression lines. The invariant is Q1, not Q3's exact count.
- **Q4 > 0 but < 10 is normal.** The `Lock held` line appears only on same-instant collisions; duplicates arriving even slightly later take the Scenario B or A path instead. All three lines are successful suppressions.
- **PICKED_UP > 20 is normal** for the same reason: refused copies get picked up again after redelivery.
- **A `trace_id ... falling back to MessageId` warning is a FINDING, not noise.** With real payloads, this warning means the real message contract did not yield a usable trace_id — exactly the kind of contract problem this test exists to surface. Record any occurrence in the results.

---

## Part 4 — Results template for business

| # | Metric | Expected | Actual | Pass? |
|---|--------|----------|--------|-------|
| 1 | Messages sent (10 real payloads × 2) | 20 | | |
| 2 | Distinct trace_ids with `MESSAGE_SUCCESS` (Q1) | 10 | | |
| 3 | Trace_ids processed MORE than once (Q1) | **0** | | |
| 4 | Suppression events (Q3) | ≥ 10 | | |
| 5 | Simultaneous thread races caught (Q4) | > 0 | | |
| 6 | `END(success)` markers on the volume | 10 | | |
| 7 | Error-queue routings during the run | 0 | | |
| 8 | `falling back to MessageId` warnings (real-contract check) | 0 | | |
| 9 | Queue fully drained at end | yes | | |

**Attach:** the Q5 single-trace timeline screenshot (both thread names visible), the Q1 zero-row screenshot, and the ingestion report file (the 10 real trace_ids).

**Pass statement for the report:** *"Ten real production message payloads were each sent twice — 20 deliveries containing 10 deliberate duplicates — to one pod running two concurrent worker threads. Every unique message was processed exactly once (10/10) with its real message contract parsed correctly; all 10 duplicate copies were detected and suppressed, including N same-instant thread collisions caught by the claim lock. Zero double-processing incidents."*

---

## Part 5 — Pass / fail criteria

**PASS** requires ALL of: row 3 = 0, row 2 = 10, row 4 ≥ 10, row 5 > 0, row 6 = 10, row 7 = 0, row 8 = 0, row 9 = yes.

**FAIL** if any trace_id shows two `MESSAGE_SUCCESS` events (row 3 > 0) — capture that trace's full Q5 timeline immediately; it is the debugging artifact.

**INCONCLUSIVE** if row 5 = 0 (no simultaneous race ever happened — the test didn't exercise the thread lock): re-run with duplicates sent back-to-back (Task 6 ordering) and/or increase the stub sleep to 500 ms.

---

## Part 6 — Explicitly out of scope (later phases)

1. **Full end-to-end** with real payloads, real pipeline, real output-queue verification (stub off).
2. **Multi-pod test** (2+ replicas racing via the shared EFS volume — same plan, `Lock held` evidence replaced by cross-pod `owned by another worker` evidence).
3. Crash/takeover testing (kill the pod mid-processing, verify the 4-hour-lease takeover — see IDEMPOTENCY_SCENARIOS_V2.md, Scenario 4).

## Cleanup after the run

- Set `SQS_STUB_PROCESSING=0` (or remove it), restore `SQS_VISIBILITY_TIMEOUT` to its production value, scale replicas back.
- ⚠️ **MANDATORY with real trace_ids — delete the 10 test markers from `$SQS_MPS_PATH`.** This test wrote `END(success)` for 10 REAL trace_ids without doing the real work. If those markers remain, any later run with these messages — including your own end-to-end test, or a real redelivery — will be **silently Scenario-A-skipped as "already done"**. Do not rely on the 7-day GC for this; delete them explicitly:

```bash
for t in $(cat trace_ids_report.txt); do rm -v $SQS_MPS_PATH/${t}__*; done
```
