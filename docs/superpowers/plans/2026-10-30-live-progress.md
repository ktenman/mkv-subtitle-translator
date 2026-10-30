# Live Translation Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make slow batch translation visibly active and understandable.

**Architecture:** A context-managed `BatchProgress` owns a tqdm bar and a heartbeat
thread; synchronous translation remains on the caller's thread. Optional string
callbacks from backends report waiting, retries, and fallback without exposing raw
output. Subtitle counts advance only after each batch is processed.

**Tech Stack:** Python, threading, time.monotonic, existing tqdm, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-30-live-progress-design.md`

## Global Constraints

- Python >=3.10; no new dependencies.
- Preserve model, effort, batch-size defaults, translation prompts, quota fallback rules, and output files.
- Routine progress must not expose subtitle text, prompts, credentials, or raw backend transcripts; failure messages retain the existing backend diagnostics.
- Optional callbacks preserve existing direct client calls.
- Non-batch progress is out of scope.

## Review Focus

- A completely silent backend must still produce timed updates before completion.
- Ctrl+C and quota exhaustion must stop display threads and propagate.
- Redirected output must be flushed, readable, and free of ANSI/carriage returns.
- Partial and failed batches must not claim all subtitles translated.
- Fallback and retries must reflect the actual active backend and attempt.

### Task 1: Observable batch progress

**Files:** Create `src/mkv_subtitle_translator/progress.py`, `tests/test_progress.py`,
`tests/test_client.py`; modify `translator.py`, `backends.py`, `client.py`,
`tests/test_translator.py`, `tests/test_backends.py`, and `README.md`.

**Interfaces:** `ProgressCallback = Callable[[str], None]`; optional keyword-only
`progress: ProgressCallback | None = None` on client translate methods and API
request helper. `BatchProgress(total: int, batches: int)` exposes `start_batch`
(batch number, subtitle indices, size, model name), `report(message: str)`, and
`finish_batch(completed: int, failed: int)` and supports `with` for cleanup.

- [x] Write regressions for visible batch start before the backend returns,
  heartbeat during a blocked call, redirected output, correct subtitle totals,
  and cleanup after quota errors and Ctrl+C. Mock only backend I/O and shorten
  heartbeat intervals in tests; synchronize using events rather than sleeps.
- [x] Run `uv run pytest tests/test_translator.py tests/test_progress.py -q`.
  Expected: new regressions fail because progress is absent.
- [x] Implement `BatchProgress`, integrate it into the batch loop, and forward
  status callbacks. Terminal interval: 1 second; log interval: 15 seconds.
- [x] Add backend and API regressions for waiting/timeout messages, quota fallback,
  attempt numbers, retry delays, and final errors without spurious final backoff.
- [x] Run the new tests and confirm missing status behaviors fail; implement
  sanitized callbacks and a concise subprocess timeout error.
- [x] Run `uv run pytest -q -m 'not integration'`; expected: all offline tests pass.
- [x] Document the progress display and explain that waiting time does not measure
  per-subtitle progress. Smoke-test both terminal and redirected output.
- [x] Run `uv run ruff check src/ tests/` and
  `uv run ruff format --check src/ tests/`; expected: both pass.
- [x] Request a fresh code review, fix any material findings, and leave verified
  changes in the user's checkout. No publishing or release is needed.
