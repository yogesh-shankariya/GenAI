# Plan §11 (v2) — Sharding, wire logging, externalized prompts, folder structure

Status: APPROVED FOR IMPLEMENTATION. **Supersedes v1** (`plan_s11_sharding_and_wire_logging.md`) — hand only this file to the implementing agent. Where this document quotes prompt text, use it **verbatim, byte for byte** — the prompts are the core quality mechanism of the design.

Changes vs v1: shard carry is now **2 pages** (default); prompts move out of Python into `prompts/*.md` with a loader (§12); folder structure reorganized (§13); explicit cleanup policy (§14).

---

## §11.0 Context and goals

The pipeline currently runs ONE deep-agent invoke over the whole worklist. The orchestrator never reads pages, but it accumulates every subagent's JSON reply in its history (~1,000–1,300 tokens per page with findings). Fine at the original ~30-page target; fatal at the new requirement of 1000+ page documents.

Scope of this plan — four changes, nothing else:

1. **Sharding.** Python slices the (already split and overlap-decorated) page files into batches of `HORIZON_SHARD_SIZE` (default **25**) and runs one full agent invoke per batch, merging results deterministically in Python.
2. **Wire logging.** At DEBUG, every LLM request/response body is logged with unique grep-able markers (`===LLM_REQUEST===` etc.) so a human can Ctrl+F the log file.
3. **Prompt externalization.** All prompt text moves to `prompts/*.md` files loaded at startup (§12).
4. **Folder reorganization + cleanup** (§13, §14).

Explicitly deferred: the "findings files" refactor (subagents writing per-page files) — at 25 pages/shard the in-context replies are safely bounded. The §3b "header carry" is a design sketch only (§18) — do NOT implement it now.

## §11.1 Decisions (locked — do not revisit during implementation)

- Shard size default **25** (`HORIZON_SHARD_SIZE`, CLI `--shard-size`). Values < 1 → warn, use 25.
- Shards run **sequentially**, in page order, reusing ONE `ChatHorizon` and ONE agent built once.
- **Metadata runs once**, in shard 1 only. Shards 2+ receive `visit_date` / `document_id` as text in their task message and skip the metadata step.
- **Carry = last 2 pages** of the previous shard, injected into each shard k>1 as CONTEXT-ONLY files (`HORIZON_SHARD_CARRY`, default 2, clamped to 0–2 with a warning). Two, not one: the chained stitch (primary + 2 context pages) for the FIRST page of a batch then has exactly the same reach as the unsharded pipeline — the shard boundary becomes invisible to §3a.
- The §3a overlap window needs no change: it is baked into every page file by the splitter BEFORE sharding, so page 26's file already carries page 25's 20-line tail.
- **Merge moves to Python.** Per shard: validate + evidence-gate only. Globally: concatenate → dedupe → sort → write, reusing existing `_dedupe` / `_sort`.
- **Shard failure**: retry the whole shard (invoke + gate) once; second failure raises with shard index and page range. Fail-fast is deliberate — silently skipping pages of a medical document is worse than a loud failure.
- `postprocess()` keeps its exact current signature as a single-shard wrapper so existing callers/tests stay valid.
- Prompts live in `prompts/*.md` (Markdown, not YAML — §12 explains why) and are loaded by `src/agent/prompt_loader.py`; `src/agent/prompts.py` becomes a thin shim so no call site changes.
- **The test suite is kept** (§14). It is the mechanism by which the implementing agent verifies this refactor.

## §11.2 Unchanged — do not touch

`src/pipeline/splitter.py` (splitting, §3a decoration, `_b` duplicate suffixing, 2/3-digit padding), `src/pipeline/schemas.py`, `src/horizon/adapters.py`, `src/horizon/token_manager.py`, `src/agent/build_agent.py` (except the import source of prompts stays `src.agent.prompts` — unchanged by the shim), the EXTRACTOR / VERIFIER / METADATA prompt **content**, evidence-gate semantics (RAW pages only), the trace-guard hard cap (≤3 page paths per task call), `recursion_limit=1000` (now per shard — ample).

---

## §11.3 Configuration (`src/config.py`, inside `load_config()`)

```python
# Sharding (plan §11 v2)
"shard_size": int(os.getenv("HORIZON_SHARD_SIZE", "25")),
"shard_carry": int(os.getenv("HORIZON_SHARD_CARRY", "2")),   # context-only carry files, 0..2
# Wire logging (plan §11 v2): off | response | full
"wire_log": os.getenv("HORIZON_WIRE_LOG", "response"),
"wire_log_max_chars": int(os.getenv("HORIZON_WIRE_LOG_MAX_CHARS", "0")),  # 0 = unlimited
```

Validate in `run()` (keep `load_config()` a dumb reader): `shard_size < 1` → warn + 25; `shard_carry` outside 0..2 → warn + clamp; `wire_log` not in `{"off","response","full"}` → warn + `"response"`.

CLI in `main()`: `--shard-size` (int, default None, overrides config); optional `--log-file` (see §11.8).

## §11.4 The run loop (`src/pipeline/run.py`)

`ChatHorizon` construction and `build_agent` stay exactly as today, built once before the loop.

```python
def run(input_path: str, output_path: str, shard_size: Optional[int] = None) -> ExtractionResult:
    document = Path(input_path).read_text(encoding="utf-8")
    config = load_config()
    split = split_pages(document)

    size = shard_size or config["shard_size"]
    if size < 1:
        logger.warning("Invalid shard size %r; using 25.", size)
        size = 25
    carry_n = max(0, min(2, config["shard_carry"]))

    set_wire_log_config(config["wire_log"], config["wire_log_max_chars"])

    token_manager = build_token_manager(config)
    model = ChatHorizon(...)        # unchanged args
    agent = build_agent(model)      # built ONCE

    page_paths = sorted(split.agent_files)          # splitter padding makes sort correct
    shards = [page_paths[i:i + size] for i in range(0, len(page_paths), size)]
    shard_count = len(shards)
    logger.info("Invoking deep agent on %d page(s) in %d shard(s) of up to %d.",
                len(page_paths), shard_count, size)

    gated: list[ExtractionResult] = []
    visit_date_s, document_id_s = "null", "null"

    for idx, paths in enumerate(shards, start=1):
        set_llm_log_tag(f"{idx:02d}/{shard_count:02d}")
        files = {p: split.agent_files[p] for p in paths}
        if idx == 1:
            content = USER_TASK_TEMPLATE.format(worklist="\n".join(paths))
            carry_paths: list[str] = []
        else:
            carry_paths = shards[idx - 2][-carry_n:] if carry_n else []
            for c in carry_paths:
                files[c] = split.agent_files[c]     # in the FS, NOT in the worklist
            content = SHARD_TASK_TEMPLATE.format(
                shard_index=idx, shard_count=shard_count,
                worklist="\n".join(paths),
                visit_date=visit_date_s, document_id=document_id_s,
                carry_paths="\n".join(carry_paths),
            )
        log_shard_start(idx, shard_count, paths, carry_paths)

        shard_model = _run_shard_with_retry(agent, content, files, split.raw_pages,
                                            idx, shard_count, paths)
        if idx == 1:
            visit_date_s = shard_model.visit_date or "null"
            document_id_s = shard_model.document_id or "null"
        log_shard_done(idx, shard_count, shard_model)
        gated.append(shard_model)

    shard_note = (f"processed in {shard_count} shard(s) of up to {size} page(s)"
                  if shard_count > 1 else None)
    return merge_shards(gated, output_path, extra_flags=split.flags, shard_note=shard_note)
```

```python
def _run_shard_with_retry(agent, content, files, raw_pages, idx, count, paths):
    for attempt in (1, 2):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": content}], "files": files},
                config={"recursion_limit": 1000},
            )
            return gate_shard(result, raw_pages)   # §11.6
        except Exception as exc:                    # noqa: BLE001 — retry-once boundary
            if attempt == 1:
                logger.warning("===SHARD_RETRY=== shard=%02d/%02d after error: %s",
                               idx, count, exc)
                continue
            raise RuntimeError(
                f"shard {idx}/{count} (pages {paths[0]} .. {paths[-1]}) failed twice; aborting run"
            ) from exc
```

Notes: `visit_date=null` propagates as the literal string `null` when shard 1's metadata found nothing (amended step 2 handles it). Documents with `pages <= size` produce one shard via `USER_TASK_TEMPLATE` — output identical to today, no shard-note flag.

## §11.5 Prompt TEXT changes — this text lands in `prompts/*.md` (§12), verbatim

**(a) New file `prompts/shard_task.md`** (whole file, ends with one trailing newline):

```
Extract every blood-pressure and HbA1c reading, each with its date, from this batch of
pages (batch {shard_index} of {shard_count} of one document).

The batch's page files, in order:
{worklist}

Batch mode: visit_date={visit_date} and document_id={document_id} are already known —
skip the metadata step and use these values (visit_date=null means the date is unknown;
note a flag and use date fallback "none").

The following file(s) are CONTEXT-ONLY — the page(s) immediately before this batch,
in document order:
{carry_paths}
Never extract from them and never name one as a PRIMARY page; they may be used only as
CONTEXT paths in the stitch pass and the matching verifier calls.

Follow your procedure and finish by writing /results.json.
```

**(b) In `prompts/orchestrator.md`, replace the current step 2 with:**

```
2. If the user message already provides visit_date and document_id (batch mode), skip
   the metadata call and use those values; visit_date=null means unknown — note a flag
   and continue (date fallback becomes "none"). Otherwise call task("metadata", ...)
   with ONLY the first page path. It returns visit_date and member id. If visit_date
   is null, note a flag and continue (date fallback becomes "none" instead of
   "visit_date").
```

**(c) In `prompts/orchestrator.md`, append to the end of step 4** (after "If no pairs qualify, mark the todo done and skip."):

```
   Batch-boundary rule: if the user message names CONTEXT-ONLY file(s) and the FIRST
   page in your list reported starts_mid_table=true and returned one or more table
   readings with date null or date_source "none", issue ONE stitched re-extraction
   with that first page as PRIMARY and the nearest context-only file as CONTEXT; add
   the second context-only file only under the same chain condition as above — never
   more than 3 page paths in one call. Context-only files have no extractor flags of
   their own — for them, this relaxed trigger replaces the ends_mid_table check.
```

**(d) In `prompts/orchestrator.md`, add one rule to the Rules block:**

```
- A file marked CONTEXT-ONLY in the user message is never a PRIMARY page: never send
  an extractor or verifier with it as the primary path, never extract values from it,
  and never include readings sourced from it in /results.json. It may appear only as a
  CONTEXT path in stitch-pass extractor calls and the matching verifier calls.
```

No content changes to extractor / verifier / metadata prompts — they already understand PRIMARY + CONTEXT paths from §3a.

## §11.6 Postprocess refactor (`src/pipeline/postprocess.py`)

Split the current `postprocess()` into two public functions plus a compatibility wrapper. Reuse `_load_results_json`, `_evidence_gate`, `_dedupe`, `_sort`, `PostprocessError` unchanged.

```python
def gate_shard(result: Dict[str, Any], raw_pages: Dict[int, str]) -> ExtractionResult:
    """Load /results.json from ONE agent invoke, validate, evidence-gate.
    No dedupe, no sort, no file write. raw_pages is the FULL SplitResult.raw_pages —
    page numbers are global, so the gate needs no shard awareness."""
    data = _load_results_json(result)
    model = ExtractionResult.model_validate(data)
    return _evidence_gate(model, raw_pages)


def merge_shards(shard_models, output_path, extra_flags=None, shard_note=None) -> ExtractionResult:
    """Deterministic global merge: concatenate readings/flags in shard order, take
    visit_date/document_id from the first shard that has them, then dedupe, sort,
    and write output_path exactly as postprocess() does today."""
    merged = ExtractionResult(
        document_id=next((m.document_id for m in shard_models if m.document_id), None),
        visit_date=next((m.visit_date for m in shard_models if m.visit_date), None),
    )
    for m in shard_models:
        merged.blood_pressure.extend(m.blood_pressure)
        merged.hba1c.extend(m.hba1c)
        merged.flags.extend(m.flags)
    if extra_flags:
        merged.flags.extend(extra_flags)
    if shard_note:
        merged.flags.append(shard_note)
    merged = _dedupe(merged)
    merged = _sort(merged)
    # ... identical file write + INFO log as the current postprocess() tail ...
    return merged


def postprocess(result, raw_pages, output_path, extra_flags=None) -> ExtractionResult:
    """Single-shard wrapper — signature and behavior preserved."""
    return merge_shards([gate_shard(result, raw_pages)], output_path, extra_flags=extra_flags)
```

Flag CONTENT is identical to today; if any existing test asserts flag ORDER, adjust the test, not the design. Cross-shard duplicates near a stitched boundary are collapsed by the existing `_dedupe_key` (includes `source_page` + `evidence`).

## §11.7 Sharding edge cases (implement / accept as stated)

- Duplicate page files (`page_NN_b.md`): `sorted()` keeps them adjacent; a boundary can split base/duplicate — accept (each file's baked-in overlap is already correct; the evidence gate uses `raw_pages[n]`, which contains both copies).
- Carry files that are `_b` duplicates: carry is simply "last `carry_n` paths of the previous shard in sorted order" — no special handling.
- Chained stitch across a boundary: **solved by carry=2** — identical reach to the unsharded pipeline. (`HORIZON_SHARD_CARRY=1` reproduces the v1 behavior if ever needed.)
- Headers more than ~2 pages before their values are beyond the 3-path cap **by design, sharded or not** — rows come out `date: null`, `date_source: "none"`, low confidence, flagged. See §18 for the optional future fix; do not implement it now.
- ≥100-page documents: splitter already 3-digit-pads filenames, so lexicographic `sorted()` stays numerically correct.
- One-page or empty shards: allowed, no special-casing.

## §11.8 Wire-level debug logging

### New module `src/horizon/wire_log.py`

Owns: a process-wide call counter (`itertools.count(1)` — thread-safe `next()`), a module-level shard tag, mode/max-chars settings, and all marker formatting. Logs to the existing `llm_service` logger.

```python
def set_wire_log_config(mode: str, max_chars: int) -> None      # called from run()
def set_llm_log_tag(tag: str) -> None                           # "03/40"; default "-"
def next_call_id() -> int
def log_request(call_id, payload, params) -> None               # DEBUG, mode == "full" only
def log_response(call_id, status, elapsed_s, body) -> None      # DEBUG, mode != "off"
def log_error(call_id, status, body_text) -> None               # DEBUG
def log_shard_start(idx, count, paths, carry_paths) -> None     # INFO (paths/counts only)
def log_shard_results(idx, count, results_json_text) -> None    # DEBUG
def log_shard_done(idx, count, model) -> None                   # INFO (counts only)
```

Bodies rendered with `json.dumps(obj, indent=2, ensure_ascii=False, default=str)`. If `max_chars > 0` and longer, truncate and append `…[truncated, N chars total]`. Default 0 = no truncation (full bodies are the requirement).

### Marker format — exact; one log record per marker (multi-line messages are fine)

```
===LLM_REQUEST=== call=00042 shard=03/40 messages=17 tools=4
{ ...full request payload JSON... }

===LLM_RESPONSE=== call=00042 shard=03/40 status=200 elapsed=4.31s
{ ...full response body JSON... }

===LLM_ERROR=== call=00042 shard=03/40 status=503
{ ...response text... }

===SHARD_START=== shard=03/40 pages=25 first=/pages/page_051.md last=/pages/page_075.md carry=/pages/page_049.md,/pages/page_050.md
===SHARD_RESULTS=== shard=03/40
{ ...that shard's /results.json content... }
===SHARD_DONE=== shard=03/40 bp=12 hba1c=7 flags=1
```

Rules:
- Marker tokens are exactly `===NAME===` — unique in the codebase, so Ctrl+F on `===LLM_RESPONSE===` finds every response and nothing else.
- `call` is zero-padded to 5 digits and shared by a request and its response. Each HTTP **attempt** gets a fresh call id (generated at the top of `_post_once` / `_apost_once`), so tenacity retries appear as consecutive ids with identical payloads — no attempt-number plumbing.
- Levels: `LLM_REQUEST` / `LLM_RESPONSE` / `LLM_ERROR` / `SHARD_RESULTS` are DEBUG-only (they contain PHI). `SHARD_START` / `SHARD_DONE` / `SHARD_RETRY` are INFO (paths and counts only — PHI-safe per plan §10).
- Modes: `off` = no wire records; `response` (default) = responses + errors; `full` = also request payloads (verbose — the system prompt repeats in every call).

### `src/horizon/chat_horizon.py` integration

In `_post_once` (mirrored in `_apost_once`): `call_id = next_call_id()` at the top; wrap the POST in `time.monotonic()` for `elapsed`; `log_request(call_id, payload, params)`; after receiving the response and BEFORE `raise_for_status()`, if `status_code >= 400` call `log_error(call_id, status, response.text)` (401 handling stays exactly as is); on success `log_response(call_id, status, elapsed, body)` where `body = response.json()` parsed once and returned.

In `_log_request`: KEEP the INFO summary line; DELETE the existing `logger.debug("Request payload: %s", payload)` line — `wire_log.log_request` replaces it (otherwise `full` mode double-logs).

### `src/pipeline/run.py` integration

`set_wire_log_config(...)` once after `load_config()`; `set_llm_log_tag(...)` at the top of every shard iteration (shards are sequential, so a module-level tag is safe; parallel subagent calls WITHIN a shard correctly share the tag). `log_shard_start` before invoke; after `gate_shard` succeeds, `log_shard_results(idx, count, <raw /results.json text from result["files"]>)` — reuse `postprocess._file_text` — then `log_shard_done`.

### Log-to-file support (small, include it)

`configure_logging(verbose, log_file=None)`: when `HORIZON_LOG_FILE` (or CLI `--log-file`) is set, attach a `FileHandler(path, encoding="utf-8")` with the same formatter to BOTH the root config and the `llm_service` logger. Keep the existing `StreamHandler` as `llm_service.handlers[0]` — the verbatim-copied TokenManager flushes `handlers[0]` in `get_token()`; both handler types support `.flush()`, but preserving the current first handler avoids any behavior change.

### PHI reminder (unchanged policy; restate in code comments)

DEBUG output now contains full prompts, page text, and extracted values. `--verbose` (and therefore all `===LLM_*===` / `===SHARD_RESULTS===` records) must only ever be enabled inside the client PHI boundary. INFO remains counts/paths/timings only.

---

## §12 Prompt externalization — `prompts/*.md` + loader

### Why Markdown, not YAML

The prompts are long multi-line text containing quotes, colons, pipes, and literal JSON braces. In `.md` files the file content IS the prompt — zero escaping, exact whitespace, clean diffs. YAML block scalars invite silent corruption (indent/chomping mistakes change the prompt without any error). Decision: **one `.md` file per prompt**.

### Layout

```
prompts/
├── README.md          # provenance + editing rules (below); NEVER loaded as a prompt
├── orchestrator.md
├── extractor.md
├── verifier.md
├── metadata.md
├── user_task.md       # template — placeholders: {worklist}
└── shard_task.md      # template — placeholders: {shard_index} {shard_count} {worklist}
                       #                          {visit_date} {document_id} {carry_paths}
```

Hard rule, put it in `prompts/README.md`: **everything inside a prompt file is sent to the model.** No comment headers, no metadata blocks, no HTML comments. Provenance and editing notes live only in README.md. Each file ends with exactly one trailing newline.

### Loader — new `src/agent/prompt_loader.py`

```python
"""Load prompt text from prompts/*.md — the single source of truth (plan §11 v2 / §12).

System prompts (orchestrator/extractor/verifier/metadata) are used VERBATIM and may
contain literal { } (JSON examples) — they must NEVER pass through str.format().
Task templates (user_task/shard_task) ARE .format()-ed and must contain exactly the
expected placeholder set — validated here so a typo fails at startup, not mid-run.
"""
import os, string
from functools import lru_cache
from pathlib import Path

class PromptLoadError(RuntimeError):
    pass

TEMPLATE_FIELDS = {
    "user_task": {"worklist"},
    "shard_task": {"shard_index", "shard_count", "worklist",
                   "visit_date", "document_id", "carry_paths"},
}

def _prompts_dir() -> Path:
    override = os.getenv("HORIZON_PROMPTS_DIR")
    return Path(override) if override else Path(__file__).resolve().parents[2] / "prompts"

@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    path = _prompts_dir() / f"{name}.md"
    if not path.is_file():
        raise PromptLoadError(f"Prompt file missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise PromptLoadError(f"Prompt file empty: {path}")
    if name in TEMPLATE_FIELDS:
        found = {f for _, f, _, _ in string.Formatter().parse(text) if f}
        if found != TEMPLATE_FIELDS[name]:
            raise PromptLoadError(
                f"{path} placeholders {sorted(found)} != expected {sorted(TEMPLATE_FIELDS[name])}"
            )
    return text
```

Note for the implementer: `HORIZON_PROMPTS_DIR` is a process-environment override (export in the shell); it is intentionally NOT read from `.env`, because prompts load at import time, before `load_dotenv()` runs. The `__file__`-relative default needs no environment at all.

### `src/agent/prompts.py` becomes a thin shim (no call-site changes anywhere)

```python
"""Prompt access shim. The single source of truth is prompts/*.md (plan §11 v2 / §12).
Do not put prompt text in this file."""
from src.agent.prompt_loader import load_prompt

ORCHESTRATOR_PROMPT = load_prompt("orchestrator")
EXTRACTOR_PROMPT = load_prompt("extractor")
VERIFIER_PROMPT = load_prompt("verifier")
METADATA_PROMPT = load_prompt("metadata")
USER_TASK_TEMPLATE = load_prompt("user_task")
SHARD_TASK_TEMPLATE = load_prompt("shard_task")
```

Eager import-time loading is deliberate: a missing or malformed prompt file kills the process at startup (fail-fast), never mid-document.

### Migration order (do it exactly in this sequence)

1. Create `prompts/` and copy each existing string constant into its file **byte for byte** — do not retype, reflow, re-wrap, or "improve" any line. Strip only the Python `"""\` scaffolding.
2. Apply the §11.5 verbatim edits to `prompts/orchestrator.md` and create `prompts/shard_task.md`.
3. Add `prompt_loader.py`; convert `prompts.py` to the shim; delete the old string literals.
4. Run the full test suite — the existing prompt-content tests double as migration verification.

## §13 Folder structure (target)

```
.
├── prompts/                      # NEW (§12) — prompt source of truth
├── src/
│   ├── config.py
│   ├── agent/
│   │   ├── build_agent.py
│   │   ├── prompt_loader.py      # NEW
│   │   └── prompts.py            # thin shim
│   ├── horizon/
│   │   ├── adapters.py
│   │   ├── chat_horizon.py
│   │   ├── token_manager.py
│   │   └── wire_log.py           # NEW (§11.8)
│   └── pipeline/
│       ├── splitter.py
│       ├── schemas.py
│       ├── postprocess.py
│       └── run.py
├── scripts/
│   ├── __init__.py               # empty — enables `python -m scripts.probe_tool_chats`
│   └── probe_tool_chats.py       # MOVED from src/horizon/ (diagnostic, not runtime code)
├── tests/                        # KEPT — see §14
├── docs/
├── Input/
└── out/
```

Rules: move `probe_tool_chats.py` with `git mv`; update its docstring usage lines to `python -m scripts.probe_tool_chats`; its imports (`src.config`) keep working when run from the repo root. Do NOT invent deeper nesting inside `src/` — the agent/horizon/pipeline split is already right. Leave `Input/` and `out/` names untouched (client paths depend on them).

## §14 Cleanup policy

**Remove/relocate:**
- `src/horizon/probe_tool_chats.py` → `scripts/` (kept per its own docstring for regression-probing after gateway upgrades, but it is not pipeline runtime code and does not belong in the package).
- The now-dead prompt string literals in `src/agent/prompts.py` (replaced by the shim).
- Nothing else. The "defensive tolerance" branches in `adapters.py` and the `PageExtraction` schema are deliberate — keep them.

**The test suite stays. Do not delete `tests/`.** Rationale, for the record:
1. "Running fine" describes the CURRENT code. This plan rewrites the run loop, the merge, the prompt delivery mechanism, and the transport logging — the suite is the only automated way the implementing agent can prove the NEW code still honors the contract.
2. Several tests are safety invariants, not conveniences: the trace-guard (3-path cap, PRIMARY/CONTEXT rules), the evidence-gate tests (overlap text must never pass as evidence — a PHI-grade correctness property), and the splitter duplicate/padding behavior.
3. They cost nothing in production: tests never ship into the runtime path, and integration tests are already deselected by default (`-m "not integration"`).

If a leaner deployment checkout is wanted, exclude `tests/` (and `scripts/`, `docs/`) when building the deployment artifact — do not delete them from the repository.

## §15 Tests

Existing suite must pass (the `postprocess()` wrapper guarantees the postprocess tests; splitter/adapters/trace-guard untouched). Prompt-content substring tests keep working through the shim and now also verify the migration.

New:
1. `tests/test_sharding.py` (with `agent.invoke` mocked): 60 pages, size 25 → 3 invokes with worklists 1–25 / 26–50 / 51–60; invoke 2's `files` contains `/pages/page_24.md` AND `/pages/page_25.md` (carry=2) while its message worklist does not; message contains `batch 2 of 3`, propagated `visit_date=`, and the CONTEXT-ONLY sentence listing both carry paths; metadata-null shard 1 → later messages contain `visit_date=null`; first invoke raising once → retried, twice → `RuntimeError` naming `shard 1/3` and the page range; 10 pages, size 25 → exactly 1 invoke via `USER_TASK_TEMPLATE`, no shard-note flag; `HORIZON_SHARD_CARRY=1` carries one file.
2. `tests/test_postprocess.py` additions — `merge_shards`: visit_date/document_id from first non-null shard; dedupes an identical reading appearing in two shard models; global sort; `shard_note` appended when provided.
3. `tests/test_prompt_loader.py`: all six files load non-empty; orchestrator contains sentinel lines (`NEVER read a page file`, `Batch-boundary rule`, `CONTEXT-ONLY`); template placeholder validation raises on a tampered copy (tmp_path + `HORIZON_PROMPTS_DIR`); `shard_task` / `user_task` `.format()` round-trip with all fields succeeds.
4. `tests/test_wire_log.py` (caplog at DEBUG): request+response markers share a call id; ids increment; shard tag appears; `mode="off"` emits no `===LLM_` records; `max_chars` truncation suffix present.
5. `tests/test_chat_horizon.py` additions (`responses` lib): one POST at DEBUG → exactly one `===LLM_REQUEST===` (mode `full`) and one `===LLM_RESPONSE===`; **at INFO, caplog contains no `===LLM_` marker at all** (PHI guard); a 503 → `===LLM_ERROR===`.

Optional nice-to-have: trace-guard helper asserting a carry path never appears as the single/PRIMARY path of an extractor call.

## §16 Acceptance criteria & manual verification

- `python -m src.pipeline.run --input Input/input.md --output out/results.json --shard-size 25 --verbose --log-file out/run.log` completes on a large fixture; per-invoke context bounded by ~25 pages of results; final JSON validates and carries the shard-note flag when shards > 1.
- `grep -c "===SHARD_START===" out/run.log` equals `ceil(pages/25)`; every `===LLM_REQUEST=== call=NNNNN` (full mode) has a matching `===LLM_RESPONSE=== call=NNNNN`; `grep "===SHARD_DONE===" out/run.log` shows per-shard counts.
- `grep "===LLM_" out/run.log` returns nothing when run WITHOUT `--verbose` (PHI guard).
- Deleting `prompts/orchestrator.md` and starting the pipeline fails immediately at import with `PromptLoadError` naming the missing path.
- A ≤25-page document produces byte-identical output to the pre-change pipeline.
- `pytest` green; integration markers still deselected by default.

## §17 File-by-file change list

| File | Change |
|---|---|
| `prompts/*.md` + `prompts/README.md` | NEW — prompt source of truth (§12); §11.5 text lands here |
| `src/agent/prompt_loader.py` | NEW — loader, caching, placeholder validation |
| `src/agent/prompts.py` | becomes the thin shim; string literals deleted |
| `src/config.py` | +`shard_size`, `shard_carry`, `wire_log`, `wire_log_max_chars`; `HORIZON_LOG_FILE` in `configure_logging` |
| `src/pipeline/run.py` | shard loop, carry-file injection (2 files), `_run_shard_with_retry`, template selection, `--shard-size` / `--log-file`, shard markers, wire-log setup |
| `src/pipeline/postprocess.py` | new `gate_shard` + `merge_shards`; `postprocess()` becomes the single-shard wrapper |
| `src/horizon/wire_log.py` | NEW — counter, tag, modes, all marker formatting |
| `src/horizon/chat_horizon.py` | integrate wire_log in `_post_once`/`_apost_once`; remove old raw payload debug line |
| `scripts/probe_tool_chats.py` | MOVED from `src/horizon/`; usage docstring updated |
| `tests/` | new `test_sharding.py`, `test_prompt_loader.py`, `test_wire_log.py`; additions per §15 — **suite kept** |
| `docs/how-it-works` (if present) | one paragraph on batching + prompt files (optional) |

## §18 OPTIONAL — §3b "header carry" design sketch (DO NOT IMPLEMENT NOW)

Recorded for the future, only if fixtures show date headers sitting more than ~2 pages before their table values (check first — OCR of long lab tables usually repeats the header per page). Deterministic Python extension to the splitter's decorator: when a page's first non-empty lines look like table rows and no header-like row (≥2 date-like tokens in cells) exists in its own context section, scan `raw_pages` backward up to `HORIZON_HEADER_SCAN_PAGES` (default 0 = off) for the nearest header-looking row and inject that single line into the context section inside a marked block, e.g. `<TABLE_HEADER_CARRY from_page="23">…</TABLE_HEADER_CARRY>`, plus one permitting sentence in `prompts/extractor.md`. Python does the long-range lookup; every LLM rule (evidence from the PAGE section only, `date_source: "table_header"`, note provenance) stays untouched.
