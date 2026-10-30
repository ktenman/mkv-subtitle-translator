# Live translation progress

The current batch bar only advances after a synchronous backend request returns.
Codex captures all output and permits a 30-minute wait, leaving a 200-subtitle
batch looking frozen. The user requested more useful progress and implementation
using Superpowers.

## Approaches

1. A timed status display around the existing synchronous calls works with every
   backend and exposes waiting time without changing translation behavior.
2. Streaming backend-specific events could show more internal activity, but needs
   separate protocols and still cannot report completed subtitles reliably before
   the response is validated.
3. Smaller batches advance sooner but increase request overhead and change context.

Builder choice: use the timed status display plus explicit backend status callbacks.
The user delegated implementation; no extra product choice is needed.

## Behavior

- Announce each batch, its subtitle index range, count, and active model immediately.
- Refresh terminal progress once per second while a request is pending. Report
  elapsed batch time and the current backend status; do not invent a percentage
  within an unfinished batch.
- For redirected stderr, emit plain, flushed lines on transitions and a heartbeat
  every 15 seconds. Do not emit terminal control sequences.
- Count processed subtitles, separately showing successful and failed translations.
- Report the CLI effort and per-call timeout, API attempts and retry delays, and
  fallback to another backend. Summarize batch results and elapsed time.
- Always stop the heartbeat and close the display on completion, quota failure,
  other errors, or Ctrl+C. Keep translation calls on the main thread so subprocess
  cancellation behavior is preserved.
- Replace verbose subprocess timeout errors with a concise timeout message.

## Constraints

Python >=3.10; no new dependencies. Preserve model, effort, batch-size defaults,
translation prompts, quota fallback rules, and output files. Routine progress must
not expose subtitle text, prompts, credentials, or raw backend transcripts;
failure messages retain the existing backend diagnostics. Optional
callbacks preserve existing direct client calls. Non-batch progress is out of scope.

## Verification

Regression tests must observe progress before a blocked call completes, increasing
elapsed time, correct accounting, retry/fallback messages, and cleanup on failure
and interruption. Use fake backend responses rather than paid translation calls.
Run all offline tests, Ruff lint and format checks, and a terminal smoke test.
