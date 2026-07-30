# Idempotency Scenarios v2.0 — The Illustrated Walkthrough

**Repo:** `SQS/` · **Date:** 2026-07-30 · **Versions:** this is the spacious, one-scenario-per-page edition; the compact reference edition is [IDEMPOTENCY_SCENARIOS.md](IDEMPOTENCY_SCENARIOS.md). Concepts live in [IDEMPOTENT_SQS_PROCESSING.md](IDEMPOTENT_SQS_PROCESSING.md).

Every scenario below follows the **same strict template**, so you always know where to look:

> **One line** — the whole story in a sentence
> **Before / After** — the state of the ledger and the queue, at a glance
> **Timeline** — what happens, millisecond by millisecond
> **What happened** — the plain-English explanation
> **Cost & proof** — what it costs the business, and the automated test that pins the behavior

---

## Part 0 — The world, in one picture

Two pods (running copies of the consumer), each with worker threads. One SQS queue delivering messages. One shared EFS volume holding the **ledger** — the marker files.

```text
        Pod 1 (one process)                Pod 2 (another process)
        Thread A     Thread B              Thread C     Thread D
            \           /                      \           /
       [threading.Lock in pod-1's         [threading.Lock in pod-2's
        memory — referees A vs B]          memory — referees C vs D]
              \                                  /
               \                                /
        ┌─────────── shared volume, mounted by BOTH pods ───────────┐
        │   abc-123__queue__lock      ← fcntl lock here referees    │
        │   abc-123__queue__start__…    pod-1 vs pod-2 (kernel/NFS) │
        │   abc-123__queue__end__…                                  │
        └───────────────────────────────────────────────────────────┘

                     ┌──────────────────────────┐
                     │  SQS queue               │  delivers each message
                     │  ▣ abc-123  ▣ def-456 …  │  AT LEAST once — duplicates
                     └──────────────────────────┘  are normal, not a bug
```

### The symbols used in every scenario

| Symbol | Meaning |
|---|---|
| `abc-123` | The message's `trace_id` — its serial number, the ledger key |
| `START` | Ledger entry: "I am working on this" |
| `END(success)` / `END(failed)` | Ledger entry: "done — it worked" / "done — it failed" (audit only) |
| `▣ abc-123` | The message sitting on the queue |
| `💥` | A crash, at that exact moment |
| `($)` | A paid OCR + LLM pipeline run |
| `Ledger: —` | The ledger holds nothing for this message |

### The golden rule — four possible decisions

Every arriving message lands in exactly **one** of four scenarios, decided by what the ledger already says:

```text
                 message arrives (trace_id abc-123)
                               │
                 END(success) in ledger? ──yes──►  A: SKIP + delete    (already done)
                               │no
                 START in ledger? ──no───────────►  D: PROCESS          (brand new)
                               │yes
                 START younger than 4h? ──yes────►  B: SKIP, leave on Q (someone's on it)
                               │no (stale)
                               └─────────────────►  C: TAKE OVER        (owner presumed dead)
```

Keep this tree in your head — all 22 scenarios below are just this tree meeting real life.

---
---

# Part 1 — The normal life of a message

---

## Scenario 1 — The happy path (Scenario D: brand new)

**One line:** a message arrives for the first time, gets processed once, paid once, and disappears.

```text
BEFORE   Ledger: —                              Queue: ▣ abc-123
AFTER    Ledger: END(success)                   Queue: empty
```

**Timeline**

```text
10:00:00  Queue → Pod A : deliver abc-123 (first time ever)
10:00:00  Pod A: ledger check → no END, no START  → Scenario D: PROCESS
10:00:00  Pod A: lock → GRANTED → double-check → still empty
10:00:00  Pod A: writes START → releases lock
10:00:01  Pod A: OCR + LLM work ($) ...
10:04:52  Pod A: publishes result to the output queue
10:04:52  Pod A: writes END(success)
10:04:53  Pod A: deletes abc-123 from the queue     ✓ done, paid exactly once
```

**What happened.** This is the baseline every other scenario varies. Note the strict order of the last three steps — **publish → END → delete** — chosen so that a crash between any two of them is survivable (Scenarios 8 and 9 show why).

**Cost:** one `($)` run — the intended cost. **Proof:** every test in the suite exercises this path.

---

## Scenario 2 — A duplicate of a finished message (Scenario A)

**One line:** the same message shows up again after the work is done — the ledger remembers, and the duplicate costs nothing.

```text
BEFORE   Ledger: END(success)                   Queue: ▣ abc-123 (a second copy)
AFTER    Ledger: END(success)  (unchanged)      Queue: empty
```

**Timeline**

```text
10:04:52  (earlier) END(success) for abc-123 sits in the ledger
10:05:31  Queue → Pod B : delivers abc-123 AGAIN
          (why? producer retry, or the crash in Scenario 9)
10:05:31  Pod B: ledger check → END(success) found → Scenario A: SKIP
10:05:31  Pod B: DELETES the duplicate from the queue
                                        ✓ milliseconds spent, zero dollars
```

**What happened.** The END marker is *proof* the work is fully done, so it is **safe to delete** this copy. Compare with Scenario 3, where deleting would be dangerous.

**Cost:** zero — this is the payoff scenario of the entire system.
**Proof:** `test_full_idempotent_lifecycle`, `test_duplicate_delivery_is_suppressed_and_deleted`.

---

## Scenario 3 — A duplicate while another pod is still working (Scenario B)

**One line:** a copy arrives while the original is mid-processing — skip it, but do NOT delete it.

```text
BEFORE   Ledger: START (1 min old)              Queue: ▣ abc-123 (redelivered copy)
AFTER    Ledger: START (unchanged)              Queue: ▣ abc-123 (left in place!)
```

**Timeline**

```text
10:00:00  Pod A: START written, begins a multi-minute job
10:01:00  Queue → Pod B: delivers abc-123 again
          (the visibility timeout expired while A was still working)
10:01:00  Pod B: ledger check → END? no → START? yes, 1 minute old (< 4h lease)
10:01:00  Pod B: Scenario B: SKIP — and LEAVES the message on the queue
   ...    the queue keeps redelivering; every copy is skipped while A works
10:04:53  Pod A finishes: END(success) + delete
          → any copy arriving after this hits Scenario 2 instead
```

**What happened.** The crucial asymmetry versus Scenario 2: here there is **no END yet** — the work is not provably done. If Pod A turns out to be dead, that queued copy is the *only* way the message ever gets rescued (Scenario 4). So a B-skip must always leave the message alone.

**Cost:** a few wasted receives — no money.
**Proof:** `test_owned_message_is_left_on_queue`, `test_second_start_marker_refused`.

---

## Scenario 4 — The crashed pod and the takeover (Scenario C)

**One line:** a pod dies mid-work; after a 4-hour waiting period, another pod rescues the message.

```text
BEFORE   Ledger: START (>4h old, owner dead)    Queue: ▣ abc-123 (still redelivering)
AFTER    Ledger: END(success)                   Queue: empty
```

**Timeline**

```text
09:00:00  Pod A: START written, begins work
09:10:00  💥 Pod A dies (OOM-kill)
          → its START file remains on the volume
          → the message was never deleted from the queue

09:15:31  Queue → Pod B: redelivery → START is 15 min old → Scenario B: skip
          (the system cannot tell a dead pod from a slow one — so it waits)

   ...    redeliveries arrive and are skipped, for 4 hours (the lease)

13:00:02  Queue → Pod B: redelivery → START is now OVER 4h old → STALE
13:00:02  Pod B: deletes the stale START on sight → Scenario C: TAKEOVER
13:00:02  Pod B: lock → writes its OWN START → processes ($)
13:04:40  Pod B: publish → END(success) → delete    ✓ message rescued, never lost
```

**What happened.** The 4-hour **lease** is the agreed answer to an unanswerable question — "is that pod dead, or just slow?" Shorter lease = faster rescue but more risk of stealing from a slow-but-alive pod (Scenario 13). It is one tunable number.

**Cost:** up to 4 hours of delay, plus one `($)` run (the dead pod's half-finished run produced nothing).
**Proof:** `test_stale_start_marker_allows_takeover`.

---
---

# Part 2 — A crash at every possible moment

Walk the happy path of Scenario 1 and kill the pod at each step. Every gap is covered by something — and by something *different* each time.

---

## Scenario 5 — Crash before anything was written

**One line:** the pod dies before touching the ledger — the retry starts from a clean slate.

```text
BEFORE   Ledger: —                              Queue: ▣ abc-123
AFTER    Ledger: —  (nothing was ever written)  Queue: ▣ abc-123 (redelivers)
```

**Timeline**

```text
10:00:00  Queue → Pod A: receives abc-123
10:00:00  💥 dies before the ledger check, before START, before any work
10:05:31  Queue → Pod B: redelivery → ledger empty → Scenario D → processes normally
```

**What happened.** Nothing to clean up, nothing paid twice. The message simply starts over as if the first delivery never happened.

**Cost:** none.

---

## Scenario 6 — Crash while holding the lock

**One line:** the pod dies at the worst microsecond — holding the lock — and the operating system cleans up instantly.

```text
BEFORE   Ledger: —   (lock held by Pod A)       Queue: ▣ abc-123
AFTER    Ledger: —   (lock FREE — kernel did it) Queue: ▣ abc-123 (redelivers)
```

**Timeline**

```text
10:00:00  Pod A: lock → GRANTED
10:00:00  💥 dies before writing START

10:00:00  KERNEL: process is dead → lock released automatically
          (no code of ours runs — dead processes cannot run code;
           instant on local disk, a short lease delay on EFS/NFS)

10:05:31  Queue → Pod B: redelivery → lock → GRANTED immediately
          → Scenario D → processes normally
```

**What happened.** This is why the design needs **no lock timeout and no lock-stealing**: the lock's lifetime is tied to its holder being alive. A dead holder *cannot* keep the lock — the kernel guarantees it.

**Cost:** none.
**Proof:** `test_orphaned_lock_does_not_block_forever`.

---

## Scenario 7 — Crash mid-processing

**One line:** the pod dies halfway through the OCR — the message waits out the lease, then gets rescued.

```text
BEFORE   Ledger: START                          Queue: ▣ abc-123
AFTER    (identical to Scenario 4 from here)
```

**Timeline**

```text
10:00:00  Pod A: START written, working ($) ...
10:02:10  💥 dies halfway through the OCR
   ...    → exactly the Scenario 4 movie: skips for 4h, then takeover
```

**What happened.** The half-finished work produced **no output**, so nothing duplicates downstream — the only losses are the delay and one repeated `($)` run.

**Cost:** lease delay + one duplicate `($)` run.

---

## Scenario 8 — Crash after publish, before END (the honest window)

**One line:** the one milliseconds-wide gap where a duplicate can escape downstream — kept deliberately, because the alternative is worse.

```text
BEFORE   Ledger: START      Result: PUBLISHED   Queue: ▣ abc-123
AFTER    Ledger: END(success) — via takeover    Queue: empty
         ...but the result was published TWICE
```

**Timeline**

```text
10:04:52  Pod A: publishes the result to the output queue
10:04:52  💥 dies before writing END(success)

          ledger still says only "START"
   ...    → after the 4h lease: Scenario C takeover

13:00:05  Pod B: reprocesses ($) → publishes a SECOND result downstream
```

**What happened.** Why does the code publish *before* writing END? Consider the reverse order: write END first, crash before publishing. The ledger would then say "done" about a result that **was never published** — a silently lost result, forever. When forced to choose a failure mode for this tiny window, the design picks the *visible* one (a rare duplicate) over the *invisible* one (a lost result).

**Cost:** one duplicate `($)` run and one duplicate downstream message — only if a crash lands inside a milliseconds-wide window.

---

## Scenario 9 — Crash after END, before delete — THE classic

**One line:** the scenario the entire system was built for — the crash that used to cost double now costs nothing.

```text
BEFORE   Ledger: END(success)                   Queue: ▣ abc-123 (never deleted)
AFTER    Ledger: END(success)                   Queue: empty
```

**Timeline**

```text
10:04:52  Pod A: END(success) written
10:04:53  💥 dies before deleting the message from the queue

10:05:31  Queue → Pod B: redelivery
10:05:31  Pod B: ledger check → END(success) → Scenario A → skip + delete
                                               ✓ zero double cost
```

**What happened.** Without a ledger, this exact crash means a full second `($)` run plus a duplicate downstream message — and it is the *most common* duplicate cause in queue systems. With the ledger, it costs a few milliseconds of lookup.

**Cost:** zero.
**Proof:** `test_full_idempotent_lifecycle`.

---
---

# Part 3 — Races: two workers at the same instant

---

## Scenario 10 — Two pods race; the lock refuses the loser

**One line:** both pods see an empty ledger at the same instant — the kernel picks exactly one winner.

```text
BEFORE   Ledger: —          Queue: ▣ abc-123 delivered to BOTH pods
AFTER    Ledger: START (Pod A's)      Pod B backed off, message redelivers later
```

**Timeline**

```text
10:00:00.000  Pod A: check ledger → empty          ┐ both saw "empty" —
10:00:00.000  Pod B: check ledger → empty          ┘ this IS the race
10:00:00.001  Pod A: fcntl lock → GRANTED
10:00:00.001  Pod B: fcntl lock → DENIED (kernel: "taken") → backs off instantly,
              leaves the message on the queue
10:00:00.002  Pod A: double-check → empty → writes START → processes

   later      B's copy redelivers → finds A's live START → Scenario B → skipped
```

**What happened.** "Check, then act" always has a gap — two workers can both *check* before either *acts*. The kernel lock closes the simultaneous case: it admits **exactly one holder**, always, with no ambiguity.

**Cost:** zero.

---

## Scenario 11 — Two pods race; the double-check catches the latecomer

**One line:** the loser gets the lock a moment *after* the winner finished — and the second look at the ledger saves the day.

```text
BEFORE   Ledger: —          Queue: ▣ abc-123 delivered to BOTH pods
AFTER    Ledger: START (Pod A's only)     Pod B aborted — no second START
```

**Timeline**

```text
10:00:00.000  Pod A: check ledger → empty          ┐ both saw "empty"
10:00:00.000  Pod B: check ledger → empty          ┘
10:00:00.001  Pod A: fcntl lock → GRANTED
10:00:00.002  Pod A: double-check → still empty → writes START → releases lock
10:00:00.003  Pod B: fcntl lock → GRANTED   ← A already released! B gets in!
10:00:00.004  Pod B: double-check → sees A's START → ABORTS. Skips the message.
```

**What happened.** Without step `.004`, Pod B — holding a *legitimately acquired* lock — would have written a second START and processed the message a second time. The division of labor:

> **The lock guarantees one at a time. The double-check guarantees only the first one acts.**

**Cost:** zero.
**Proof:** the two-worker single-winner race in the `test_marker_store.py` contract suite.

---

## Scenario 12 — Two threads inside the same pod

**One line:** the kernel lock is blind to threads of one process — the in-memory lock covers exactly that blind spot.

```text
BEFORE   Ledger: —          Queue: ▣ abc-123 handed to two threads of Pod 1
AFTER    Ledger: START (Thread A's only)   Thread B aborted
```

**Timeline**

```text
Thread A (pod 1): acquire in-memory lock for abc-123 → WINS
Thread B (pod 1): acquire in-memory lock for abc-123 → BLOCKED behind A

Thread A: fcntl lock → double-check → writes START → releases both locks
Thread B: proceeds → double-check → sees A's START → ABORTS
```

**What happened.** fcntl locks **never conflict between threads of the same process** — the kernel would grant "exclusive" access to both. So every claim passes through two turnstiles in sequence:

```text
turnstile 1: in-memory lock  → beats my sibling threads
turnstile 2: kernel lock     → beats every other process and pod
```

Each turnstile covers the other's blind spot. Neither is enough alone. (Child *processes* need no special handling — to the kernel they are ordinary separate processes, refereed by turnstile 2 like any pod.)

**Cost:** zero.

---

## Scenario 13 — The slow-but-alive pod loses to a takeover (the honest limit)

**One line:** a pod alive but slower than the 4-hour lease is indistinguishable from a dead one — and gets its work taken over.

```text
BEFORE   Ledger: START (>4h old, owner ALIVE)   Queue: ▣ abc-123 (redelivering)
AFTER    Ledger: two workers ran; up to two results published
```

**Timeline**

```text
09:00:00  Pod A: START written, begins a pathologically slow job — but is ALIVE
13:00:02  Queue → Pod B: redelivery → START is over 4h old → looks exactly like a crash
13:00:02  Pod B: Scenario C takeover → starts processing the same message

          → BOTH pods are now doing the work; two results may publish
```

**What happened.** No lease-based system can distinguish "dead for 4 hours" from "alive but 4 hours slow" — AWS's own Powertools has the identical property. The defense is **sizing**: keep the lease far longer than any legitimate job. If jobs can genuinely run for hours, raise the lease (one config number) or add the visibility-heartbeat pattern.

**Cost:** one duplicate `($)` run — only when a job exceeds the lease while alive.

---
---

# Part 4 — Failures and retries

---

## Scenario 14 — Processing fails

**One line:** the work fails — the ledger records it for the audit trail, but deliberately blocks nothing.

```text
BEFORE   Ledger: START                          Queue: ▣ abc-123
AFTER    Ledger: END(failed) — audit only,      Queue: (today: copied to error
                 START cleared                          queue, original deleted)
```

**Timeline**

```text
10:00:00  Pod A: START → begins work
10:00:10  💥 S3 download fails (a transient blip) → processing returns failure
10:00:10  Pod A: writes END(failed) — kept purely as an audit record —
          and the START is cleared at the same moment

          → the ledger now blocks NOTHING:
            the next attempt will land in Scenario D and run fresh

10:00:10  (today's consumer: copy the message to the error queue, then delete)
```

**What happened.** The key rule of the whole ledger:

> **Only END(success) causes a skip. A failed END never blocks a retry.**

If failure *did* block, one transient blip would permanently poison the message. Success is remembered; failure is recorded but never blocks.

**Cost:** the failed attempt's partial work.
**Proof:** `test_failed_processing_allows_retry`.

---

## Scenario 15 — Redelivery after a failure: the retry

**One line:** the message comes back after a failure and is retried immediately — no waiting, no leftover blocks.

```text
BEFORE   Ledger: END(failed), no START          Queue: ▣ abc-123 (redelivered)
AFTER    Ledger: END(success)                   Queue: empty
```

**Timeline**

```text
10:00:10  ledger: END(failed) for abc-123 — and no START (cleared in Scenario 14)
10:05:31  Queue → Pod B: redelivery
10:05:31  Pod B: END(success)? no → START? no → Scenario D
10:05:31  Pod B: processes fresh — retry counter now 1 (stamped by SQS)
10:09:42  Pod B: succeeds → END(success) → delete       ✓ recovered by retrying
```

**What happened.** Clearing the START in Scenario 14 is what makes the retry **immediate** — otherwise the dead attempt's START would force a pointless 4-hour Scenario-B wait for a worker that isn't working anymore.

**Cost:** the intended retry run.

---

## Scenario 16 — The delete call fails after successful processing

**One line:** the work succeeded but the "remove from queue" call hiccupped — the ledger absorbs it.

```text
BEFORE   Ledger: END(success)                   Queue: ▣ abc-123 (delete FAILED)
AFTER    Ledger: END(success)                   Queue: empty (second delete works)
```

**Timeline**

```text
10:04:52  Pod A: publish → END(success) written
10:04:53  Pod A: delete_msg → AWS hiccup → delete FAILS
          Pod A: still reports success — the WORK is done
                 (result carries "deleted: false" for visibility)

10:05:31  Queue: redelivery (the message was never removed)
10:05:31  → Scenario A → skip + delete             ✓ cleaned up on the second pass
```

**What happened.** Delete-failure is *bookkeeping* failure, not *work* failure — conflating them would falsely mark finished work as failed. The redelivery is suppressed by the END marker, and the second delete attempt clears the queue.

**Cost:** zero — one extra receive.

---

## Scenario 17 — The error-queue routing itself fails

**One line:** the failure handler fails — so do nothing irreversible and let the queue drive another attempt.

```text
BEFORE   Ledger: END(failed)                    Queue: ▣ abc-123
AFTER    Ledger: END(failed)                    Queue: ▣ abc-123 (kept — retries)
```

**Timeline**

```text
10:00:10  processing failed → Pod A: send copy to error queue → THAT send fails
          (or: the send worked, but the input-queue delete after it fails)
10:00:10  Pod A: leaves the message alone — reports failure

10:05:31  Queue: redelivery → the whole failure path runs again
          (in the delete-failed variant the error queue already holds one copy,
           so this retry can create a duplicate THERE — a known, minor cost)
```

**What happened.** Design principle: **when the failure handler itself fails, touch nothing.** The message survives on the input queue, and redelivery retries the whole path.

**Cost:** possibly one duplicate copy in the error queue.

---

## Scenario 18 — The END write fails (volume error at the worst moment)

**One line:** the ledger itself couldn't be written — acknowledge anyway, accept one possible future reprocess.

```text
BEFORE   Ledger: START      Result: PUBLISHED   Queue: ▣ abc-123
AFTER    Ledger: — (write failed!)              Queue: empty (acked anyway)
```

**Timeline**

```text
10:04:52  Pod A: publish OK → tries to write END(success) → OSError (volume blip)
10:04:52  Pod A: logs it LOUDLY → acknowledges anyway → delete proceeds

          → the ledger holds no memory of this message
   later  IF a duplicate of it ever arrives: Scenario D → reprocessed once ($)
```

**What happened.** This is deliberate **fail-open**: broken bookkeeping must *degrade protection*, never *halt the pipeline*. The cost is bounded — one possible reprocess of one message. The alternative (refuse to acknowledge until the ledger works) would loop the message forever.

**Cost:** at most one future duplicate `($)` run for this one message.

---
---

# Part 5 — Operational edge cases

---

## Scenario 19 — The marker volume is broken or wrongly mounted

**One line:** the whole ledger is unreachable — keep processing, drop the protection, shout in the logs.

```text
BEFORE   Ledger: UNREACHABLE                    Queue: ▣ messages flowing
AFTER    messages still processed — with NO duplicate protection until fixed
```

**Timeline**

```text
Pod A: ledger check → volume unreachable → exception inside the idempotency layer
Pod A: FAIL OPEN — logs a loud warning → processes the message normally

→ the pipeline keeps running
→ duplicate PROTECTION is off until the volume is fixed
```

**What happened.** The dedup layer is a **bodyguard, not a gatekeeper** — if the bodyguard collapses, the business keeps walking. One trap deserves special mention: the *silent* variant, where each pod accidentally mounts its own **private** volume. That produces **no error at all** — only quietly missing dedup. It's the single most important deployment checklist item.

**Cost:** duplicates possible while broken — bounded by how fast the loud logs get noticed.
**Proof:** `test_gate_fails_open_when_marker_layer_errors`.

---

## Scenario 20 — A duplicate arrives after the 7-day cleanup window

**One line:** the ledger's memory is exactly as long as the garbage collector allows — a week, by default.

```text
BEFORE   Ledger: — (GC removed the old END)     Queue: ▣ abc-123 (very late copy)
AFTER    Ledger: END(success) (new)             Queue: empty — but paid twice
```

**Timeline**

```text
day 0   abc-123 processed → END(success) written
day 7   nightly GC (cleanup_markers CronJob) removes markers older than 7 days
day 9   Queue → a VERY late duplicate of abc-123 arrives
        → ledger has forgotten it → Scenario D → reprocessed once ($)
```

**What happened.** The dedup memory **is** the GC window. Seven days comfortably outlives any realistic SQS redelivery (queue retention maxes at 14 days; typical redelivery is minutes) — and it is a knob if very late duplicates ever become real.

**Cost:** one duplicate `($)` run per post-window duplicate — expected to be ~never.

---

## Scenario 21 — The message has no usable `trace_id`

**One line:** without a serial number the ledger falls back to SQS's own ID — which protects redeliveries but not producer re-sends.

```text
BEFORE   message body malformed / missing metadata.traceId
AFTER    keyed by MessageId instead — dedup HALF works (see below)
```

**Timeline**

```text
Queue → Pod A: message with no usable trace_id
Pod A: falls back to the SQS MessageId as the ledger key + logs a warning

  redelivery of THIS message  → same MessageId → dedup still works ✓
  producer RE-SEND            → a brand-new message = NEW MessageId
                              → NOT recognized as a duplicate ✗ (paid twice)
```

**What happened.** The fallback preserves the common case (redelivery) and only loses the producer-resend case. The real fix is upstream — the producer contract should make `trace_id` mandatory — and every warning log line is a message flying without full insurance.

**Cost:** re-sends of key-less messages are paid twice.
**Proof:** `test_extract_key_malformed_body_falls_back_to_message_id`.

---

## Scenario 22 — Idempotency switched off in config

**One line:** the "before" picture — one missing config flag reduces the entire ledger to no-ops.

```text
BEFORE   SQSClient built WITHOUT enable_idempotency=True
AFTER    plain at-least-once: every duplicate delivery is a full ($) re-run
```

**Timeline**

```text
check_duplicates      → always answers "not a duplicate"
mark_processing_start → always answers "go ahead"
mark_processing_end   → does nothing

= no ledger, no scenarios, no protection — every duplicate costs money
```

**What happened.** This was production's actual behavior before the 2026-07-28 wiring. It is kept here as the baseline that every other scenario improves on — and as a reminder that the protection is a *deliberate switch*, worth verifying in every environment's config.

**Cost:** every duplicate is paid in full.

---
---

# The one-paragraph summary

A message can arrive twice for many reasons — but every path lands in one of four ledger decisions: **done → skip and delete (A)**, **being worked → skip and leave (B)**, **abandoned → take over (C)**, **new → process (D)**. Crashes at any instant are covered by three different janitors: the **kernel** frees the lock the moment its holder dies, the **next pod** deletes a stale START after the 4-hour lease, and the **nightly CronJob** sweeps week-old markers. Races are settled twice — the **lock** admits one worker at a time, the **double-check** ensures only the first admitted one acts. Failures never poison a message — only *success* is remembered as "done" — and if the ledger itself breaks, the system **fails open**: it keeps processing and temporarily gives up protection rather than stopping the pipeline.
