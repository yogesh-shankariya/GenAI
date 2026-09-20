# SQS Consumer Code Review — SQS_01_08_2026

**Date:** 2026-08-01
**Scope:** `main.py`, `consumer_idempotency.py`, `sqs_service/` (all 5 files), `constant/`, `schema/`, `log_util/`.
The `app/` pipeline package is **not** in this folder and was **not** reviewed (see [Scope notes](#scope-notes)).
**Method:** Every file was read line-by-line. Every Critical/High finding below was then independently re-verified by an adversarial check (an agent instructed to *disprove* the claim with exact line evidence). Findings that could not be proven were dropped or downgraded. All line numbers refer to the files in this folder as of today.

---

## 1. The bottom line

| Question | Answer |
|---|---|
| Is the core idempotency **library** (marker files, locks, lease/takeover) correct? | **Yes, fundamentally sound.** The design is right and matches its documentation. It has a few narrow race-condition gaps (M1–M3) worth fixing, but no fundamental flaw. |
| Will idempotency work **as deployed today**? | **Only in serial mode, on a single pod, with well-formed messages.** Three wiring bugs in `main.py` break it outside that happy path. |
| Can this "break the pod"? | **Yes — two confirmed ways.** A single malformed message kills the pod in a permanent crash loop (**C1**), and in parallel mode every failed message loops forever and is eventually lost (**C2**). |
| Are the fixes hard? | **No.** C1 is a 3-line change, C2 is a 1-line change. The High findings are each small, local changes. |

**Priority order:** fix C1 and C2 before any deployment → then H1–H4 (error-path correctness) → then the deployment checklist (section 6) → then Medium/Low.

### What you already fixed during this review ✅

- `consumer_idempotency.py` was missing from this folder — **you added it**, and your logger adaptation (`logging.getLogger("DocMetaLogger.SQS")` replacing the absent `sqs_service._logging`) is exactly right.
- The folder was named `log_utils/` while every import says `log_util` — **you renamed it**. Startup no longer fails on this.

---

## 2. Quick glossary (terms used below)

- **Visibility timeout** — when a consumer receives an SQS message, SQS hides it from everyone else for this many seconds (here: 300s = 5 min). If the consumer doesn't *delete* the message in time, SQS makes it visible again and **redelivers** it. SQS never deletes a message by itself (except after the retention period, ~4–14 days).
- **MPS_START marker** — a small file created when a worker "claims" a message. It means *"I am processing this, everyone else back off."*
- **MPS_END marker** — a file created when processing finishes. Content `success` means *"done — if this message ever comes back, just delete it."* Content `failed` deliberately does **not** block a retry.
- **Lease** — a START marker older than 4 hours is treated as belonging to a crashed worker; another worker may then "take over" the message.
- **Poison message** — a malformed message that makes the consumer itself crash. Because it is never deleted, SQS redelivers it, and it crashes the consumer again, forever.
- **DLQ (dead-letter queue)** — an SQS feature that moves a message aside after N failed receives. **Not configured anywhere in this code**, which is why the loops described below never end on their own.

---

## 3. CRITICAL — will break the pod

### C1. `sys.exit(1)` on a bad message = permanent pod crash loop

**Where:** [main.py:126](main.py#L126), [main.py:135](main.py#L135), [main.py:143](main.py#L143)
**Verified:** CONFIRMED for both serial and parallel mode (parallel chain verified hop-by-hop).

**What's wrong, in plain words:**
When a message is blank, is not valid JSON, or has a traceId that is present but empty, the code calls `sys.exit(1)`. `sys.exit` does not "skip this message" — it **shuts down the whole Python process**, i.e. kills the pod. And because the message was never deleted from the queue, SQS will hand the *same* message to the restarted pod, which dies again.

**Simple example — what actually happens:**

```
1. Someone (a test, a misconfigured producer) sends the text "hello" to the input queue.
2. Your pod receives it. The idempotency gate claims it (writes MPS_START).
3. json.loads("hello") fails → main.py:135 → sys.exit(1) → THE POD DIES.
4. Kubernetes restarts the pod. The message "hello" is still on the queue.
5. After the 5-min visibility timeout, SQS redelivers "hello".
6. Because the MPS_START from step 2 is still there, the gate says
   "someone else owns this" (SKIP_OWNED) and leaves it on the queue...
   for 4 hours (the lease).
7. After 4 hours the lease expires → the pod claims it again → sys.exit(1) → dies again.
8. This repeats forever. There is no DLQ to break the loop.
   (If the marker folder is on /tmp — the current default — step 6 is skipped
   because the restart wiped the marker, so the pod crashes EVERY 5 minutes.)
```

One bad message = your consumer is down or crash-looping indefinitely, and **all other messages on the queue stall behind it**. In parallel mode it is just as bad: `SystemExit` is a `BaseException`, so it slips past every `except Exception` in `sqs_parallel_processor.py` ([:898](sqs_service/œ™¡_processor.py#L898), [:738](sqs_service/sqs_parallel_processor.py#L738), [:811](sqs_service/sqs_parallel_processor.py#L811)) and kills the whole processor loop.

**Precision note (from adversarial verification):** if the `metadata` or `traceId` *key is completely absent*, the code does **not** crash — that raises `KeyError`, which is caught and error-routed (but see H2). The crash happens for: blank body, non-JSON body, or traceId present but empty/blank.

**The irony:** a correct path already exists. `process_sqs_message`'s own docstring says *"False on any failure (the caller decides whether to route to the error queue)"*, and the serial loop + parallel wrapper both handle `False` properly (mark end → send to error queue → delete).

**Fix (3 lines):** replace each `sys.exit(1)` with `return False`.

```python
# main.py:126, :135, :143 — in all three places:
sys.exit(1)          # ❌ kills the pod, message loops forever
return False         # ✅ message goes to the error queue and is deleted
```

---

### C2. Parallel mode: failed messages loop forever and are then silently lost

**Where:** [main.py:482-486](main.py#L482-L486) vs [consumer_idempotency.py:186](consumer_idempotency.py#L186)
**Verified:** CONFIRMED by two independent verifiers.

**What's wrong, in plain words:**
`make_idempotent_handler` expects an error-routing function that takes **one** argument and calls it as `route_error_fn(message)`. But `main.py` hands it `_route_to_error_queue`, which requires **two** arguments `(input_client, message)`. Python can't fill in the missing argument, so the call raises `TypeError` — every single time a message fails in parallel mode.

This is a **regression**: the older `SQS_Migration/main.py:533` wired it correctly with a lambda. The new `main.py` dropped the lambda.

**Simple example:**

```
1. Parallel mode is on. A message's pipeline run fails (LLM error, status != 200).
2. The wrapper writes a "failed" END marker (correct) — a failed marker
   deliberately does NOT block retries.
3. The wrapper then calls  route_error_fn(message)  → TypeError:
   "_route_to_error_queue() missing 1 required positional argument: 'message'"
4. Because of the TypeError:
   - the message is NOT deleted from the input queue
   - the wrapper's error-routing/delete never runs
5. After 5 minutes SQS redelivers it. Nothing blocks it (failed END doesn't
   suppress, START was cleared). The FULL LLM pipeline runs again. Fails again.
6. Loop repeats every ~5 minutes: paying for a full LLM run each cycle,
   pushing ONE MORE duplicate error message to the error queue each cycle
   (process_sqs_message sends its own enriched error internally), and adding
   one more "failed" marker file each cycle.
7. After the queue's retention period (default 4 days) SQS silently deletes
   the message. Final state: hundreds of duplicate error messages, days of
   wasted LLM spend, and the original message vanished without a controlled record.
```

**Why testing missed it:** serial mode calls the same function *correctly* ([main.py:596](main.py#L596)), so all serial tests pass. The bug only fires in parallel mode, on the *failure* path. It's also quiet: the TypeError is swallowed into a "failed" count, not raised.

**Fix (1 line):**

```python
# main.py:485
route_error_fn=_route_to_error_queue,                              # ❌ 2-arg function, called with 1 arg
route_error_fn=lambda msg: _route_to_error_queue(input_client, msg),  # ✅ same as old main.py
```

---

## 4. HIGH — wrong behavior in real production situations

### H1. If sending to the error queue fails, the message gets stuck for 4 hours — repeatedly

**Where:** [main.py:249](main.py#L249), [main.py:324](main.py#L324) · **Verified:** CONFIRMED

**Plain words:** the two `error_client.send_message(...)` calls have no `try/except` of their own. If the *error-queue send itself* fails, the exception escapes `process_sqs_message` entirely — skipping the "mark end" and "delete/route" steps. The START marker stays alive, so every redelivery is told "another worker owns this" for the full 4-hour lease. Then it reprocesses, fails, and repeats.

**Example that is *deterministic*, not just bad luck:** SQS messages max out at 256 KB. If an incoming message is close to the cap, the *enriched* error copy (original + errorCode + errorMsg + …) exceeds 256 KB — `_validate_message_size` raises **every time**. That message reprocesses through the LLM every 4 hours forever and *never* reaches the error queue. A temporary IAM/permission problem on the error queue does the same to every failing message during the outage.

**Fix:** wrap both error-queue sends in `try/except Exception` (log loudly on failure) so `return False`/`return success` is always reached, and the normal mark-end/delete flow runs.

### H2. Certain malformed messages make the *error handler itself* crash — message stuck for 4h cycles

**Where:** [main.py:297-324](main.py#L297-L324) + [log_util/logger.py:32](log_util/logger.py#L32) · **Verified:** CONFIRMED (with one correction)

**Plain words:** if a message fails *early* — before line 158 sets `context_map` — the `except` block runs with `context_map = None`. The first thing it does is `kafka_msg_logger(..., context_map=None)`, and `set_context_map` runs `dict(None)` → `TypeError`. So the error handler **dies before reaching the error-queue send at line 324**. Same net effect as H1: no mark-end, no delete, START held → 4-hour lockout cycles, forever.

**Which messages trigger it:** valid JSON body whose inner `"Message"` field is not valid JSON; body without a `metadata` key; `metadata` that isn't a dict. (Verification note: the `deepcopy(input_message)` NameError I originally suspected at line 304 can never actually fire — the `dict(None)` TypeError always happens first.)

**Bonus damage in serial mode:** the escaping exception aborts the whole `for message in messages:` loop, so the *other* up-to-9 messages of the batch are abandoned that cycle and must redeliver.

**Fix:** initialize `context_map = {}` (not `None`) at [main.py:120](main.py#L120), and make `set_context_map` defensive: `_CONTEXT_MAP_CTX.set(dict(ctx or {}))`.

### H3. Every failed message is sent to the error queue TWICE, in two different formats

**Where:** [main.py:249](main.py#L249)/[324](main.py#L324) + [main.py:342](main.py#L342) · **Verified:** CONFIRMED

**Plain words:** on failure, `process_sqs_message` sends a nicely *enriched* error message (with errorCode, errorMsg, `status="ERROR"`). Then it returns `False`, and the serial loop calls `_route_to_error_queue`, which sends the **raw original body** to the *same* error queue again. Result: 2 messages per failure — one enriched dict, one raw string. A downstream error consumer will double-count failures, and the two copies don't even look alike.

**Fix (pick ONE owner of error-sending):** simplest is to remove the send at line 342 and let `_route_to_error_queue` only *delete* the input message (the enriched copy from inside `process_sqs_message` is the useful one). Do this together with H1/H2 so the enriched send is reliable first.

### H4. Missing ConfigMap value silently connects PRODUCTION to a DEV queue

**Where:** [constant/constant.py:153-166](constant/constant.py#L153-L166) · **Verified:** CONFIRMED

**Plain words:** the "TEMPORARY HARDCODE (2026-07-20)" block falls back to the hardcoded queue `dev-HOSSYTH_rallm` when `SQS_INPUT_QUEUE_NAME` is missing **or empty**, and even *overrides* the value `dev-HOSSYTH_docmeta_history` if configured. The only warning is a bare `print()` at import time — it bypasses your JSON logger entirely, so it has no log level and won't trip any alert. Meanwhile the output/error queue names use `_require_env` and fail loudly — the input queue is the odd one out.

**Example:** during a prod rollout someone renames the ConfigMap key. The pod starts *cleanly* and begins polling a **dev** queue — wrong environment, wrong data, in a healthcare pipeline — and nothing in the structured logs says so.

**Fix:** delete the fallback block; use `SQS_INPUT_QUEUE_NAME: Final[str] = _require_env("SQS_INPUT_QUEUE_NAME")` like its siblings (once the ConfigMap is corrected).

### H5. Marker files on `/tmp` = idempotency silently off across pods and restarts

**Where:** [constant/constant.py:173-176](constant/constant.py#L173-L176) · **Verified:** CONFIRMED

**Plain words:** all the duplicate protection lives in files under `SQS_MPS_PATH`, default `/tmp/mps_markers` — which is **private to each pod** and **erased on restart**. Two pods each have their own private marker folder, so their locks and markers can never see each other: both can claim and process the *same* message at the same time. And after any restart, a redelivered *already-completed* message is reprocessed because its `success` END marker is gone.

**Example:** run 2 replicas. A slow 6-minute message redelivers at minute 5 → pod B receives it → pod B's `/tmp` has no markers for it → B processes it too → **two identical outputs published downstream** — the exact thing this whole layer exists to prevent.

**Fix (deployment, not code):** mount one shared ReadWriteMany volume (EFS/NFS) at the same path in every replica and set `SQS_MPS_PATH` to it. The code already supports this (fcntl → NFSv4 locks). Until that volume exists, run **exactly one replica**.

### H6. The 4-hour lease knob `SQS_MPS_TIMEOUT_SECONDS` is displayed but not connected

**Where:** [sqs_service/sqs_idempotent_processor.py:406-408](sqs_service/sqs_idempotent_processor.py#L406-L408) · **Verified:** CONFIRMED (found independently by 3 separate reviewers)

**Plain words:** `constant.py` reads `SQS_MPS_TIMEOUT_SECONDS` from the environment and `main.py` proudly prints it in the startup config log — but nobody ever passes it to the marker store. The store always uses its hardcoded `4 * 60 * 60`. So ops can "change" the lease, see the new value in the startup log, and nothing actually changes.

**Example:** ops sees 5-hour worst-case LLM runs, sets the lease to 8h, log shows `28800.0` — but at hour 4 a redelivery still "takes over" the message from the still-running worker → double processing, the exact incident the change was meant to prevent.

**Fix:** thread it through: `SQSClient.__init__(..., mps_timeout_seconds=None)` → `create_marker_store(storage_path=..., timeout_seconds=mps_timeout_seconds or 4*60*60)`; `main.py` passes `Constant.SQS_MPS_TIMEOUT_SECONDS`.

### H7. Serial mode receives 10 messages at once but processes them one by one — the tail ones always redeliver

**Where:** [main.py:517-521](main.py#L517-L521) · **Verified:** CONFIRMED (one sub-detail corrected, see below)

**Plain words:** the visibility clock of *all 10* messages starts at receive time. If each message takes ~8 minutes of LLM work, message #2 already redelivers while #1 is still running, message #10 waits ~72 minutes. Raising the visibility timeout "for one message" can never fix this — it would need to cover the whole batch (~10×). Combined with H5 (`/tmp` markers), the redelivered tail messages get **fully processed by another pod → duplicate outputs**.

**Correction from verification:** my original claim that the late `delete_msg` raises an error was wrong for standard queues — AWS documents the delete as *silently succeeding-without-deleting* with an expired handle. That's actually worse: no error to notice, the message simply redelivers.

**Fix:** in serial mode use `max_messages=1`. Also raise `SQS_VISIBILITY_TIMEOUT` to genuinely exceed worst-case single-message time (H6 must be fixed for the lease to be tunable in proportion).

### H8. No SIGTERM handling — every routine deploy hard-kills in-flight LLM work

**Where:** [main.py:612](main.py#L612), [main.py:502-508](main.py#L502-L508) · **Verified:** CONFIRMED

**Plain words:** Kubernetes stops pods with SIGTERM. This code only handles `KeyboardInterrupt` (Ctrl-C / SIGINT). With no SIGTERM handler, Python's default applies: **instant death, no cleanup**. Every rolling update kills whatever is mid-flight. A message killed *between* "output published" and "END marker written" will be reprocessed on redelivery → **duplicate downstream publish on a routine deploy**. The carefully built graceful-drain machinery in `ParallelSQSProcessor` (stop_event + drain_timeout) is unreachable dead code because `main.py` never passes a `stop_event`. (Also: the Ctrl-C path logs "will finish in the background", then `close(wait=True)` blocks the shutdown for up to the full LLM runtime anyway.)

**Fix:**

```python
import signal, threading
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
# parallel: processor.process_pipelined_with_threads(wait_time_seconds=20, stop_event=stop)
# serial:   while not stop.is_set(): ...
```
Plus set `terminationGracePeriodSeconds` ≥ worst-case message time in the deployment.

### H9. No marker cleanup is wired — the marker folder grows forever

**Where:** `cleanup_old_markers()` defined at [sqs_service/mps_manager.py:494](sqs_service/mps_manager.py#L494) — zero callers in this repo · **Verified:** CONFIRMED

**Plain words:** every completed message permanently leaves 1 END file + 1 lock file. Nothing in this folder ever calls the cleanup function (`SQS_Migration/cleanup_markers.py`, the daily CronJob entrypoint, was not copied here). Every duplicate-check does a `glob` over that whole directory, so checks get slower as the folder grows; eventually the volume fills. Note the interplay with H5: today `/tmp` "cleans itself" by losing everything on restart — once you fix H5 with a durable volume, the unbounded growth becomes real. Fix H5 and H9 **together**.

**Fix:** copy `cleanup_markers.py` from `SQS_Migration/`, and deploy its daily CronJob (or spawn a daily cleanup thread in `main()`).

---

## 5. MEDIUM — real defects, narrower conditions

### M1. Tiny race in the gate: a duplicate arriving at the exact moment of completion is fully reprocessed

**Where:** [consumer_idempotency.py:107-110](consumer_idempotency.py#L107-L110), [sqs_service/mps_manager.py:332](sqs_service/mps_manager.py#L332) · CONFIRMED (found by 2 independent reviewers)

The gate is two steps — "is there an END?" then "claim a START" — and the claim step **never re-checks for an END** under its lock. Sequence: worker B checks "END? no" → worker A finishes right then (writes END, removes its START) → B claims successfully → B reprocesses a *completed* message → duplicate downstream publish. The 300s-visibility-vs-long-LLM situation (H7) makes duplicate deliveries of in-flight messages routine, so this window gets regular chances. **Fix:** inside `create_start_marker`'s locked section, re-check `has_end_marker` and refuse the claim if one exists (both file and in-memory backends).

### M2. Finishing a message deletes START markers it doesn't own

**Where:** [sqs_service/mps_manager.py:450-456](sqs_service/mps_manager.py#L450-L456) · CONFIRMED

Markers carry no owner ID, and `create_end_marker` removes **all** START markers for the trace. If worker A overruns the 4h lease, worker B legitimately takes over; when slow A finally fails, its "failed" END wipes **B's** live claim — so a third delivery starts worker C while B still runs. **Fix:** embed an owner id (pod+thread) in the START filename and delete only your own; longer-term, this is the argument for the DynamoDB/Redis backend with proper conditional writes.

### M3. A vanished marker file is mistaken for "already completed" → message deleted without being processed

**Where:** [sqs_service/mps_manager.py:226-228](sqs_service/mps_manager.py#L226-L228) · CONFIRMED

`has_end_marker` opens each END file; on *any* `OSError` it returns True ("err on suppression"). But `FileNotFoundError` is an OSError — and it means the file was *deleted* between the glob and the open (exactly what the future cleanup job does to old **failed** markers, which must NOT suppress). The consumer then logs "Duplicate — deleting" and **deletes an unprocessed message**: silent message loss. **Fix:** `except FileNotFoundError: continue` (skip), keep the suppress-on-other-OSError behavior.

### M4. Parallel mode has no per-message timeout and no stall alarm — a hung LLM call wedges the pod silently

**Where:** [sqs_service/sqs_parallel_processor.py:774-809](sqs_service/sqs_parallel_processor.py#L774-L809) · CONFIRMED

If handler calls hang (e.g. an LLM endpoint that accepts the connection but never responds), all 5 workers fill up, capacity hits 0, and the loop stops even *receiving* — it just spins silently. The pod stays Running/Ready, logs nothing, consumes nothing, forever. **Fix:** enforce a hard timeout inside the handler around the pipeline call, and add a watchdog log ("N in flight, oldest X min") so monitoring can see a stall.

### M5. `int(status)` crashes when the pipeline result has no `status_code` — real error replaced by a generic 500

**Where:** [main.py:215](main.py#L215) + [main.py:225](main.py#L225) · CONFIRMED

Line 215 reads `status` defensively with `.get()` (admits it may be `None`), then line 225 calls `int(status)` — `int(None)` raises `TypeError`. The except block then reports errorCode 500 with the *TypeError's* text; the pipeline's actual error (`LLM_EXECUTION_FAILED`, etc.) is lost to triage. **Fix:** `meta["errorCode"] = int(status) if status is not None else ErrorCodes.INTERNAL_SERVER_ERROR.value`. (Related nit: on the success path, `result_data[0]` at [main.py:257](main.py#L257) raises `IndexError` if `data` is an empty list — guard it.)

### M6. The field meant to be stripped from outputs is never stripped (key-name typo)

**Where:** [main.py:220](main.py#L220), [255](main.py#L255), [305](main.py#L305) vs [main.py:180](main.py#L180) · CONFIRMED

The input key is `DOCENCOUNTER_PATH` (singular, line 180), but all three output builders `pop("DOCENCOUNTER_PATHS", None)` (plural) — a guaranteed no-op with a silencing default. Every output/error message forwards the internal S3 pointer downstream, contradicting the declared output schema (`ResponseFromMetadata`). **Fix:** `output_message.pop("DOCENCOUNTER_PATH", None)` in all three places.

### M7. A replayed message that succeeds still carries `status="ERROR"` from its previous failure

**Where:** [main.py:253-296](main.py#L253-L296) · CONFIRMED

The success path never clears `errorCode` / `errorMsg` / `errorMessage` / `status` if they exist in the input, and sets no success status. The standard remediation for an error queue is replaying messages to the input queue — this service's own error messages are enriched copies of the input, so a replayed-then-successful message is published downstream still labeled `status="ERROR"`, `errorCode=502`. **Fix:** in the success branch, pop those four fields (and optionally set an explicit success status).

### M8. Config parsing: an empty ConfigMap value crashes the pod at import; negative values pass silently

**Where:** [constant/constant.py](constant/constant.py) lines 97, 98, 111, 119, 134, 135, 186, 190, 193, 206 · CONFIRMED

Ten values use bare `int()`/`float()`. Templated ConfigMaps commonly render `""` — `int('')` raises `ValueError` **during the very first import, before logging exists**, with no hint which key is wrong (unlike `_require_env`'s "Check deployment ConfigMap" message). And there are no bounds: `SQS_VISIBILITY_TIMEOUT: "-1"` parses fine and gets clamped to **0** at receive time → every message instantly visible to other pods while being processed → systematic duplicates. **Fix:** a `_require_int(name, default, min_value)` helper mirroring `_require_env`.

---

## 6. Deployment checklist (must-do before production)

These are not code edits in this repo, but the service is unsafe without them:

1. **`app/` package** — `main.py:30/36` and `log_util/bootstrap.py:32-36` import it; it is not in this folder. The build/deploy process must merge it in, or the pod dies at startup with `ModuleNotFoundError: No module named 'app'`. Nothing here (no Dockerfile/README) records that requirement — write it down.
2. **Shared RWX volume** mounted at `SQS_MPS_PATH` on **every** replica (H5). Until then: max 1 replica.
3. **Marker-cleanup CronJob** (H9) — deploy together with #2.
4. **DLQ / redrive policy on the input queue** (e.g. maxReceiveCount 5–10). Almost every loop described above (C1, C2, H1, H2) is unkillable *because* there is no DLQ. This is queue configuration, not code.
5. **`SQS_VISIBILITY_TIMEOUT`** sized above worst-case single-message time (and H6 fixed so the lease knob works; H7's `max_messages=1` so the sizing is per-message, not per-batch).
6. **`terminationGracePeriodSeconds`** + SIGTERM handling (H8).
7. **Fix or remove the dead config flags** — `SQS_ENABLE_IDEMPOTENCY`, `SQS_ENABLE_PARALLEL_PROCESSING`, `SQS_MAX_RETRIES` are printed in the startup config log but change nothing (idempotency is hardcoded ON; mode comes from `SQS_PROCESSING_MODE`; retries use the constructor default). An operator toggling them would be misled. Same class of problem as H6.
8. **This folder has no tests and no requirements files.** The original `SQS/` project has the 115-test suite; `SQS_Migration/` has `requirements*.txt`. Copy them (and run the tests) as part of making this folder the deployable unit.

---

## 7. Low / polish

- **Torn END write** ([mps_manager.py:433-436](sqs_service/mps_manager.py#L433-L436)): a kill between `open()` and the buffered write leaves an *empty* END file, which counts as success → a **failed** message could be suppressed and silently dropped. Write to a temp file then `os.rename` (atomic). CONFIRMED, tiny window.
- **Lock-file cleanup race** ([mps_manager.py:559](sqs_service/mps_manager.py#L559)): cleanup can unlink a lock file in the open→lock window of a claimant, allowing two "exclusive" claims on different inodes. Currently unreachable (nothing calls cleanup); becomes real when the CronJob lands. After locking, `fstat` the fd vs `stat` the path and retry on mismatch — or never unlink lock files.
- **Kafka audit markers** ([main.py:273](main.py#L273)): "pipeline completed" (END) is logged *before* the output publish, so a publish failure yields END + FAIL for the same trace and completion counts drift; failure paths never emit END at all. Move END after the publish; emit END in failure branches.
- **PHI/log hygiene:** full message bodies and outputs are logged at INFO ([main.py:175](main.py#L175), [247](main.py#L247), [272](main.py#L272)). In a healthcare pipeline, confirm these can never contain PHI, or drop to DEBUG/redact.
- **Instantly-closed tracer span** ([main.py:148-150](main.py#L148-L150)): the span opens and closes immediately, tagging nothing useful — set the tag on the decorator's active span instead.
- `meta["errorMessage"] = True` sets a **boolean** where the name suggests text — confirm what downstream expects.
- `_INTRAPROCESS_LOCKS` ([mps_manager.py:43](sqs_service/mps_manager.py#L43)) grows by one entry per trace forever (slow memory leak on long-lived pods).
- `datetime.utcfromtimestamp` ([log_util/logger.py:63](log_util/logger.py#L63)) is deprecated in Python 3.12 — use `datetime.fromtimestamp(epoch, tz=timezone.utc)`.
- The global `ThreadPoolExecutor` monkey-patch ([log_util/bootstrap.py:19](log_util/bootstrap.py#L19)) is what makes per-message log context isolation *work* in parallel mode — but it silently depends on `bootstrap` being imported before anything else touches `concurrent.futures`. Currently true (main.py line 4); document it, or scope the context-copying executor to the SQS processor explicitly.

---

## 8. What is solid ✅ (worth saying explicitly)

- **The marker-store core is well designed and previously hardened** (byte-identical to the reviewed `SQS_Migration` copy: 20 + 34 fixes already applied). Atomic claim = per-path thread lock + kernel `fcntl` lock with re-check under lock; crash-released locks (no stale-lock stealing); stale-lease takeover; "failed END does not suppress" (no message poisoning); END clears START (fast retries); `fsync` on the END marker; and the **END-before-delete ordering invariant is correctly implemented in both serial loop and parallel wrapper** — this is the heart of "will idempotency work", and it is right.
- `extract_idempotency_key` is genuinely robust: SNS envelope handling, MessageId fallback for malformed bodies, key sanitization matching the store's validation.
- `SQSClient` batching (10-entry + 1 MiB chunking, duplicate-Id detection, SenderFault-aware retry), size validation counting attributes, and non-retryable error classification are all correct and better than typical hand-rolled SQS code.
- The pipelined processor's core loop (capacity-bounded receive, 1s busy-poll, streaming results) is sound; context-isolated logging across worker threads works today.

## Scope notes

- `app/` (the actual doc-metadata pipeline: `execute_main`, `file_handler`, LLM calls) is **not in this folder and was not reviewed**. Findings involving it (e.g. whether `status_code` can be absent — M5) are marked with their dependency on that contract.
- No live AWS calls were made; the analysis is static, line-verified code review.
- The core `sqs_service/` library files are identical to the previously reviewed copies; this review therefore focused its depth on the **new integration layer** (`main.py`, wiring, config) — which is where all Critical/High findings live.

---

# Addendum (2026-08-02) — `log_util` deep-dive: thread pools, log-leak protection, monkey-patching

*Appended after the main review at the user's request. Sections 1–8 above are unchanged. Everything below was verified by **running actual experiments** against the real `ContextThreadPoolExecutor` class from this repo (not just reading the code), plus repo-wide grep evidence.*

## A. The two questions, answered directly

### Q1: "Does our mechanism to avoid log leaks actually work?" → **YES — proven by experiment.**

First, the leak your design guards against is **real**. Here is what would happen *without* your patch, demonstrated with a live run:

```
EXPERIMENT 1 — plain ThreadPoolExecutor, 1 worker thread:
  Task A (message A) sets the log context to {"trace": "MESSAGE-A"}.
  Task B (message B) runs next on the SAME pooled thread and just reads the context.
  Result: Task B sees {"trace": "MESSAGE-A"}   ← LEAK.
```

Why: a pooled worker thread keeps its own long-lived `ContextVar` state **across tasks**. So with a plain executor, any log line message B emits before setting its own context would carry **message A's trace IDs** — in a healthcare pipeline, log lines attributed to the wrong patient encounter.

Your `ContextThreadPoolExecutor` ([log_util/threading_helpers.py:4-8](log_util/threading_helpers.py#L4-L8)) closes exactly this hole:

```
EXPERIMENT 2 — the repo's ContextThreadPoolExecutor, same test:
  Task A sets {"trace": "MESSAGE-A"}.
  Task B reads the context.
  Result: Task B sees None   ← ISOLATED. Correct.
  Bonus check: Task A's write did NOT leak back into the submitting thread either.
```

Each `submit()` runs the task inside `contextvars.copy_context()` — a fresh snapshot of the *submitter's* context — so one message's context can never survive into the next task. And the submitter (the main polling loop in parallel mode) never calls `set_context_map` itself (verified: the only call sites are [main.py:167](main.py#L167) inside the per-message handler and inside `kafka_msg_logger` at [log_util/logger.py:139](log_util/logger.py#L139)), so every task starts **clean**, not stale.

You also have a **second, independent safety layer**: `finally: clear_context_map()` at [main.py:326](main.py#L326). A `finally` runs on normal return, on exceptions, and even on `SystemExit` — so even if the executor patch were somehow lost, each message clears its own context on the way out. Two layers, either one sufficient. This is the right design.

One nuance worth knowing (not a bug): messages skipped by the idempotency gate (duplicate/owned) log **before** any context is set — those lines carry an *empty* contextMap, never a *wrong* one. Empty-but-correct is the intended trade-off.

### Q2: "Is the monkey-patching proper?" → **YES for how `main.py` is wired today — with one structural weakness (finding L1 below).**

What the patch does: [log_util/bootstrap.py:19](log_util/bootstrap.py#L19) rebinds the *name* `ThreadPoolExecutor` inside the `concurrent.futures` module. Experiment-verified semantics:

```
EXPERIMENT 3:
  'from concurrent.futures import ThreadPoolExecutor' AFTER the patch  → gets the patched class ✓
  concurrent.futures.thread.ThreadPoolExecutor (the inner module)      → stays the original
  Anything that imported the name BEFORE the patch                     → keeps the original
```

So everything depends on **import order** — and today the order is correct: [main.py:4](main.py#L4) imports `log_util.bootstrap` (patch applied) *before* [main.py:18](main.py#L18) imports `sqs_service`, whose `sqs_parallel_processor` binds `ThreadPoolExecutor` at module load ([sqs_service/sqs_parallel_processor.py:30-38](sqs_service/sqs_parallel_processor.py#L30-L38)). Therefore the parallel worker pool, the dedicated receive executor, and the asyncio `run_in_executor` paths **all get the context-isolating class today**. The subclass only wraps `submit()` with a context copy — Future results, exceptions, and cancellation behave identically — so it is safe for any third-party code that happens to pick it up.

## B. New findings from this deep-dive (L1–L4)

### L1. The patch has no guard — a different entrypoint silently loses log isolation *(medium-low)*

**Where:** [log_util/bootstrap.py:19](log_util/bootstrap.py#L19) + [sqs_service/sqs_parallel_processor.py:30](sqs_service/sqs_parallel_processor.py#L30)

The whole isolation guarantee hinges on `log_util.bootstrap` being imported before anything binds `ThreadPoolExecutor` — and nothing checks or enforces that. If `sqs_service` is ever imported first (a pytest run collecting `sqs_service` tests, the future `cleanup_markers.py` CronJob gaining an executor, any new script/entrypoint), the processor silently gets the **plain** executor: everything still works, no error anywhere — logs just quietly become leak-capable again (Experiment 1 behavior). A failure mode with zero symptoms until someone reads cross-contaminated trace IDs.

**Fix (removes the fragility instead of documenting it):** have `main.py` pass the executor class explicitly instead of relying on the global patch — e.g. give `ParallelSQSProcessor.__init__` an optional `executor_class=ThreadPoolExecutor` parameter, and pass `ContextThreadPoolExecutor` from `main.py`. Then delete the global patch (or keep it as belt-and-braces). Explicit wiring can't be broken by import order.

### L2. `kafka_msg_logger`'s explicitly passed `contextMap` is dead — the filter silently overwrites it *(low)*

**Where:** [log_util/logger.py:143-148](log_util/logger.py#L143-L148) vs [log_util/logger.py:48](log_util/logger.py#L48) · **Proven by Experiment 4**

`kafka_msg_logger` passes `extra={"contextMap": context_map, ...}` — but `ContextFilter` runs *after* the record is created and unconditionally replaces `record.contextMap` with the ambient ContextVar value:

```
EXPERIMENT 4:
  ContextVar holds {"X-Trace-ID": "FROM-CONTEXTVAR"}
  logger.info("hello", extra={"contextMap": {"X-Trace-ID": "FROM-EXTRA"}, ...})
  Emitted record.contextMap == {"X-Trace-ID": "FROM-CONTEXTVAR"}   ← extra was discarded
  (the "marker" field from extra DOES survive — only contextMap is overwritten)
```

Today this is harmless *only because* `kafka_msg_logger` first calls `set_context_map(context_map)` (line 139) — so the ContextVar and the extra happen to hold the same dict. But it's a trap: any future caller who passes a *different* map than the ambient one will silently log the ambient one, and no test would notice. **Fix:** drop the `contextMap` key from `extra` (it's dead weight), or make `ContextFilter` respect a pre-existing `record.contextMap` (`if not hasattr(record, "contextMap"): ...`).

### L3. `MDCContext` is a latent cross-message leak — currently safe only because nobody uses it *(low)*

**Where:** [sqs_service/sqs_idempotent_processor.py:76-113](sqs_service/sqs_idempotent_processor.py#L76-L113)

`MDCContext` stores its data in `threading.local` — which, on **pooled** threads, persists across tasks (the exact mechanism Experiment 1 proved leaks; thread-locals don't get the ContextVar patch's protection). Grep across the repo proves the only usage today is the *read* in `log_lifecycle_marker` (line 125) — **nothing ever calls `MDCContext.set` or `MDCContext.scope`**, so the map is always empty and nothing can leak *today*. But the class is exported in the package's public API (`__all__`), inviting use: the first person who calls `MDCContext.set(...)` inside a parallel-mode handler creates stale cross-message data in every subsequent lifecycle log on that thread. **Fix:** reimplement it over `contextvars` (drop-in for its API), or remove it from `__all__` with a warning docstring until then.

### L4. If logging config fails, the service silently downgrades to plain-text logs *(low)*

**Where:** [log_util/logger.py:118-123](log_util/logger.py#L118-L123)

`setup_logger` wraps `dictConfig` in `except Exception` → falls back to `logging.basicConfig` plain text. Realistic triggers: an invalid `LOG_LEVEL` value in the ConfigMap, `python-json-logger` missing from the image, a typo in the formatter path string. The pod then runs *healthy* while every log line stops being JSON — the Kafka log collector and anything parsing `contextMap`/`marker` fields breaks quietly, which in this pipeline means the audit trail goes dark with no alert. **Fix:** in production, fail the pod on logging-config errors (config errors should be loud), or at minimum emit the fallback warning in a machine-detectable single-line JSON form.

## C. Verified-clean list (things you asked about that are ✅)

- **Leak-avoidance design works** — patched executor isolates per-message context (runtime-proven), backed by a second independent `finally: clear` layer; submitter context stays clean; no back-leak from workers.
- **Monkey-patch is picked up by the SQS processor today** — import order traced from `main.py` line 1; worker pool, receive executor, and asyncio paths all patched; subclass is behavior-preserving (submit-wrap only).
- **Serial mode set/clear pairing is correct** — one `set` per message ([main.py:167](main.py#L167)), one guaranteed `clear` ([main.py:326](main.py#L326)); between-message log lines carry an empty (not stale) context.
- **No double log emission** — `DocMetaLogger` defines no handlers and propagates to root's single console handler; one line per event.
- **No secrets in the startup config dump** — every key in `get_service_configuration` checked; `CLIENT_SECRET`, `OPENAI_API_KEY`, and the Horizon credentials are all excluded (KAFKA_URL/queue names are internal identifiers, not credentials).
- **The formatter reference string `"log_util.logger.CdiJsonFormatter"`** ([constant/constant.py:67](constant/constant.py#L67)) resolves correctly after your folder rename.
- Third-party log records (e.g. boto3's) that reach the root handler also get the current contextMap injected by the handler-level filter — useful for trace correlation; flagged here only so you know it's happening.

**Two caveats on verification limits:** (1) `marker`/`contextMap`/traceback emission into the final JSON line follows python-json-logger's documented behavior (non-reserved record attributes are merged; `exc_info` is formatted in), but could not be runtime-verified on this machine because `pythonjsonlogger` isn't installed in either local venv — itself a symptom of the missing requirements files (section 6, item 8). (2) `dd.service` is set to `""` once and never populated — a dead field in every contextMap; harmless, but either fill it (e.g. `Constant.SERVICE_NAME`) or drop it from the schema.

---

# Field note (2026-08-02) — double-processing **observed** during visibility-timeout testing

*Appended: real evidence from a dev test run that reproduces findings M1/H7. Existing sections unchanged.*

## What was observed

During a deliberate stress test (processing time ~50s per document, `SQS_VISIBILITY_TIMEOUT` set to **5 seconds**), the consumer's own marker files recorded the same message completing **twice**:

```
...__dev-HOSSYTH_rallm__end__0__1785499496.03   (success=True)   ← run #1, delivery #1
...__dev-HOSSYTH_rallm__end__1__1785499525.94   (success=True)   ← run #2, delivery #2
```

Reading the evidence: the `0`/`1` field is the delivery number (`ApproximateReceiveCount − 1`), so SQS delivered the message twice — expected, because the 5s visibility promise expired ~45s before processing finished. But **two success END markers means the full pipeline executed twice** (skipped duplicates never write an END), i.e. the duplicate protection was bypassed once and the output was in all likelihood published downstream twice.

The timestamps identify the mechanism: run #2 finished **29.9s** after run #1 — one full pipeline duration — meaning run #2 *started at the same instant run #1 completed*. That is precisely the **M1 race window**: the redelivered copy asked *"is there an END marker?"* milliseconds **before** run #1 wrote it, then claimed its START milliseconds **after** run #1's START was removed. (Alternative explanation if two consumer processes were polling the queue with separate marker directories: that would be **H5** instead. Either way, both findings and both fixes are already in this report.)

## Why this matters for the validation

- M1 was reported above as a "tiny race … medium severity". This field note shows the window is **reachable in practice** under redelivery pressure — any configuration where the visibility timeout is below worst-case processing time (H7) generates exactly that pressure in production.
- It also demonstrates the audit value of the marker design: the double-processing was *provable from two filenames* after the fact.

## Resolution stack (in order of leverage)

1. **Remove the redelivery pressure (H7 / checklist item 5):** visibility timeout must exceed worst-case single-message processing time — with `max_messages=1` in serial mode so the sizing is per-message. This alone eliminates ~all routine redeliveries of in-flight messages.
2. **Close the race itself (M1 fix):** inside `create_start_marker`'s locked section, re-check `has_end_marker` and refuse the claim if one exists — in both the file and in-memory backends. After this, the observed interleaving is impossible regardless of timeout settings.
3. **Long-term hardening (new recommendation, not previously listed):** a **visibility heartbeat** — a small background timer per in-flight message calling `ChangeMessageVisibility` every ~½-timeout to extend the hide window while processing is genuinely still running. This decouples the timeout setting from worst-case processing time entirely (a modest timeout stays safe for arbitrarily slow documents) and was already an open roadmap item in the earlier project reviews. It pairs with wiring `SQS_MPS_TIMEOUT_SECONDS` (H6) so the marker lease can be tuned consistently with it.
4. **Multi-pod prerequisite (H5):** none of the above protects across replicas until the marker directory is a shared volume — single replica until then.

---

# Fix implementation log (2026-08-03)

*The following findings were fixed in code on the user's instruction. Existing report sections above are unchanged and describe the pre-fix state.*

## What was fixed

| Finding | Fix applied | Where |
|---|---|---|
| **C1** (sys.exit poison pill) | All three `sys.exit(1)` calls removed. Blank/non-JSON/non-string bodies now build a **malformed-message envelope** (raw body + SQS MessageId standing in for the traceId), send it to the error queue **with retries**, and `return False`. A present-but-blank traceId raises `ValueError` into the normal enriched-error path. No code path in `process_sqs_message` can raise `SystemExit` anymore (the only remaining `sys.exit` is the legitimate startup mode validation). | [main.py](main.py) `process_sqs_message`, `_build_malformed_error_message`, `_send_malformed_to_error_queue` |
| **C2** (parallel error-routing arity) | `route_error_fn=lambda msg: _route_to_error_queue(input_client, msg)` — the one-argument contract is restored; failed messages in parallel mode are routed/deleted again. | [main.py](main.py) parallel wiring |
| **H1** (error-send failure; decided: keep 4h backoff + log + retry) | New public `SQSClient.send_message_with_retry()` (serializes, validates size *including* the trace_id attribute, bounded 1s/3s retries, non-retryable AWS errors abort early, raises `PublishError`). Used for the output publish and **all** error-queue sends. On ultimate error-send failure: `logger.critical(...)` then deliberate re-raise — the message stays lease-locked and retries after ~the MPS lease, exactly the chosen backoff behavior. `SQS_MAX_RETRIES` is now passed to all three clients (the knob is live). Retry loop extended to cover **network-level** transients (`BotoCoreError`), not just AWS API errors. | [sqs_service/sqs_idempotent_processor.py](sqs_service/sqs_idempotent_processor.py), [main.py](main.py) |
| **H2** (error handler crashes on malformed messages) | `context_map` starts as `{}` (never `None`); `set_context_map` accepts `None` defensively; the `except` block handles **all three** trigger shapes: unparsed body → envelope fallback; missing metadata/traceId keys → enriched message; metadata present but **not a dict** → replaced with `{}` before enrichment (the shape the first fix round missed — caught by adversarial verification). Every failure now produces an error-queue record. | [main.py](main.py), [log_util/logger.py](log_util/logger.py) |
| **H3** (double error routing) | `_route_to_error_queue` is now **delete-only**; the single sender of error messages is `process_sqs_message` itself. Exactly one error-queue message per failure, in both modes. Docstring updated to match. | [main.py](main.py) |
| **H6** (lease knob not wired) | `SQSClient` gained `mps_timeout_seconds`; `main.py` passes `Constant.SQS_MPS_TIMEOUT_SECONDS` through to the marker store. The startup-logged value now IS the live lease. | [sqs_service/sqs_idempotent_processor.py](sqs_service/sqs_idempotent_processor.py), [main.py](main.py) |
| **M1** (gate race → double processing) | Completion re-check added **under the claim lock** in both backends (file: inside the fcntl-locked section; memory: inline under its lock), plus a gate-level re-check that converts "completed during the gate" into `SKIP_DUPLICATE` (delete) instead of leaving the message. A failing re-check degrades safely to `SKIP_OWNED`, never to fail-open `PROCESS`. Failed ENDs still allow claims (retry rights intact). The interleaving observed in the visibility-timeout field test is now impossible. | [sqs_service/mps_manager.py](sqs_service/mps_manager.py), [sqs_service/marker_store.py](sqs_service/marker_store.py), [consumer_idempotency.py](consumer_idempotency.py) |
| **M3** (vanished marker = false "completed") | `FileNotFoundError` is caught separately and **skips** the vanished file (checks the rest; processes normally if none suppress). Present-but-unreadable markers keep the deliberate err-on-suppression behavior. | [sqs_service/mps_manager.py](sqs_service/mps_manager.py) |
| Hardening from verification | Non-string `trace_id` coerced to `str` before publish (a JSON-numeric `traceId` would otherwise raise un-retried `ParamValidationError` and wedge the message); `json.loads` guard catches `TypeError` (non-string Body); non-dict `message_body` guard; dead `get_sqs_client` import removed. | [main.py](main.py), [sqs_service/sqs_idempotent_processor.py](sqs_service/sqs_idempotent_processor.py) |

## Skipped by explicit decision (still open)

**H4** (dev-queue fallback), **H5** (shared marker volume — deployment), **H7** (serial batch of 10; parallel mode planned instead), **H8** (SIGTERM handling), **M2** (ownerless START deletion), plus M4–M8 and L1–L4 from the earlier sections. The deployment checklist (section 6) — especially the **DLQ** — remains the backstop for everything the code cannot solve alone.

## Accepted limitations (documented, not bugs)

- **Oversized error messages** (enriched copy > 256 KB) fail validation deterministically: CRITICAL log + lease-backoff retry loop, per the H1 keep-current-behavior decision. Real resolution: truncate `errorMsg`/payload in the enriched message, and the queue-level DLQ.
- `mps_timeout_seconds` is ignored when an explicit `marker_store` object is injected (no caller does this today).
- On the success path, a failure in the post-publish Kafka log calls would still error-route an already-published message (pre-existing ordering; unchanged).

## How the fixes were verified

1. **22 behavioral smoke checks** run against the real code (marker-store races with a temp directory, gate outcomes with stub clients, retry/wrapping semantics with stubbed boto3 errors, trace-id coercion, metadata-guard shapes) — all passing.
2. **A 4-agent adversarial verification workflow** reviewed the first fix round against the spec (message-lifecycle trace, library API, marker races, cross-cutting regressions). It confirmed the implementation and caught 1 high (non-dict metadata, fixed), 2 medium (trace-id coercion, network-error retries — both fixed), and several low items (fixed or documented above) — all resolved in the second round and re-covered by the smoke checks.

---

# Redis marker-store backend — implemented (2026-08-03)

*New section. Existing sections above are unchanged. Implemented on the user's instruction: "ignore dynamodb, implement redis completely" — the client will provide `REDIS_HOST_NAME`, `REDIS_PORT_NUMBER`, `REDIS_AUTH_TOKEN`.*

## What this is, in plain language

Until now the duplicate-protection markers (MPS_START / MPS_END) lived as **files on the pod's disk**. That works on one pod, but two pods can't see each other's files unless they share a volume (finding H5). The new backend stores the same markers in **Redis** instead — a small shared database every pod can see. Nothing about the message flow changes; only *where* the markers live.

**Switching it on is a pure config change** — no code edit, no redeploy of new code:

```
MPS_BACKEND=redis
REDIS_HOST_NAME=<client's ElastiCache endpoint>     # required
REDIS_PORT_NUMBER=6379                              # optional, default 6379
REDIS_AUTH_TOKEN=<secret>                           # optional; requires TLS
REDIS_SSL=true                                      # default true; only "true"/"false" accepted
```

Rollback is the same change in reverse: set `MPS_BACKEND=file` again.

## How a marker looks in Redis

Each message gets **two keys** (the number at the end pins the trace-id length so two different messages can never share a key):

| Key | Type | Holds | Meaning |
|---|---|---|---|
| `mps__{<trace>__<queue>}__<len>__start` | hash `{owner, ts, retry, token}` | who claimed it, when | "a worker is processing this now" |
| `mps__{<trace>__<queue>}__<len>__end` | string `success` / `failed` | the outcome | `success` suppresses reprocessing forever; `failed` allows retry |

- The **claim** (start marker) is one atomic Lua script: it checks "already completed?", then "someone else's live claim?", then writes the claim — all in a single indivisible step. The M1 race from the field test **cannot happen by construction** here.
- The **finish** is one atomic Lua script too: success is sticky (a later failed run can never overwrite it), and it releases **only its own** claim (owner check — the M2 hazard is structurally gone).
- The 4-hour lease works exactly like the file backend (timestamp comparison), so a crashed pod's claim is taken over after `SQS_MPS_TIMEOUT_SECONDS`.
- Every key carries a **7-day TTL**, so Redis cleans up by itself — the cleanup CronJob is not needed for this backend (`cleanup_old_markers` is a documented no-op).

## What the adversarial verification caught, and what was fixed

A 3-reviewer adversarial workflow (Lua semantics, contract/integration, tests/rollout) attacked the first implementation. Everything it confirmed was fixed and regression-tested:

| Finding (severity) | Plain-language problem | Fix |
|---|---|---|
| Key collision via underscore shift (**high**) | trace `a_` + queue `x` and trace `a` + queue `_x` produced the *same* key — one message's success could silently suppress a *different* message (data loss disguised as dedup) | Key now ends with the trace-id **length**, which makes collisions mathematically impossible. Regression test proves the two pairs no longer interact. |
| Auto-retry replay wedges a message (**medium**, found by 2 reviewers) | redis-py can transparently re-run the claim script after a network blip. The re-run saw the claim it had *just written itself* and answered "someone else owns this" — parking the message for the full 4-hour lease with nobody processing it | Every claim call carries a unique **token**; a replay recognizes its own token and still gets "claimed", while a genuine second claim (fresh token) is still refused. Both behaviors are regression-tested. |
| Corrupt `ts` crashes the gate (**medium**) | A non-numeric timestamp in a claim hash (ops edit, foreign writer) crashed the Lua script AND `get_start_marker` — that message would run with **no protection** for up to 7 days | Guarded `tonumber` in Lua + safe parsing in Python: a corrupt timestamp now reads as "maximally stale", is claimed over, and the broken hash is **replaced** (self-healing). |
| Config typo kills file-backend pods (**medium**) | `constant.py` parsed `REDIS_PORT_NUMBER` with `int()` at import time — a typo in the shared ConfigMap would crash-loop **every** pod, including file-backend pods that never touch Redis | The constant now stays a raw string (used only by the startup config dump); `from_env` validates it loudly at boot of redis-opted-in pods only. Proven: `REDIS_PORT_NUMBER=6379x` + `MPS_BACKEND=file` imports fine. |
| `REDIS_SSL: "1"` silently disables TLS (**medium**) | Only the literal `true` enabled TLS; common spellings like `1`/`yes` quietly meant *plaintext* | `from_env` now accepts exactly `true`/`false` (empty = unset = TLS on) and **rejects anything else at boot**. |
| GC TTL vs lease unchecked (low) | Setting the lease longer than the 7-day TTL would let a *live* claim expire mid-processing → double processing | Constructor now raises unless `gc_ttl > lease`. |
| Takeover residue / braces in ids / broken-vs-missing redis package (low) | Stale hash fields survived takeover; `{`/`}` in a trace id would corrupt the cluster hash tag; a *broken* redis install looked identical to a *missing* one | Takeover now `DEL`s before writing; `{`/`}` rejected in ids; `sqs_service` logs the real import error when redis is installed but broken. |
| Caller-clock lease (low) | A pod with a badly skewed clock stretches/shrinks the takeover window (same exposure as the file backend) | **Documented, not changed** (deliberate parity with the file backend): pods must be NTP-synced — standard on EKS. |

The test suite also got the coverage the reviewers demanded: `from_env` tests now assert the **actual connection kwargs** (host/port/password/ssl/timeouts) and that the boot `ping()` really runs and really aborts on failure; and a new end-to-end test flips `MPS_BACKEND=redis` through the **exact `SQSClient` composition `main.py` ships**.

**Final state: 71/71 tests green** — the full contract suite runs identically against file, memory, and redis (via fakeredis, never a live server), plus redis-specific and regression tests.

## Failure behavior (what ops must know)

- **Boot**: a redis-opted-in pod with bad config (missing host, bad port, invalid `REDIS_SSL`, token without TLS, unreachable endpoint) **dies loudly at startup** — it can never run half-configured. The auth token is never logged (shown as `***`/`auth=yes`).
- **Runtime outage**: if Redis becomes unreachable mid-run, marker calls fail within ~2 seconds (socket timeouts) and the gate **fails open** — messages are processed *without* duplicate protection rather than not at all. This is the same deliberate policy the file backend has. **Ops should alert on the "proceeding without duplicate protection" / marker-error log lines** — that is the signal dedup is off.
- **Clock**: leases compare pod clocks (like the file backend). Keep nodes NTP-synced.

## Rollout checklist (redis backend)

1. **Add `redis>=5,<6` to the deployment image's requirements** — this snapshot has no requirements file, so the dependency must be added wherever the image is built (verified against redis-py 5.3.1; without it, an `MPS_BACKEND=redis` pod fails loudly at boot with ImportError). Tests additionally need `fakeredis[lua]`.
2. ElastiCache: use the **cluster-mode-disabled primary endpoint** (cluster-mode-enabled is not supported by this adapter yet); AUTH token ⇒ in-transit encryption (TLS) must be on; set the parameter group's `maxmemory-policy` to **`noeviction`** (an evicted marker = forgotten dedup memory); size for ~7 days of markers (tiny: two small keys per message).
3. Set the `REDIS_*` variables and flip `MPS_BACKEND=redis`. The startup config dump shows host/port/ssl and masks the token.
4. The marker **cleanup CronJob is unnecessary** for this backend (TTL does it); harmless if it still runs (returns 0).
5. The DLQ recommendation (section 6) is **unchanged and still the top backstop** — the backend swap does not replace it.
