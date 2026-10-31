# mkv-subtitle-translator

Translate SRT subtitles to Estonian through the Codex CLI, the Claude Code CLI, or OpenRouter (200+ models), with automatic MKV subtitle extraction and merging.

By default it translates with GPT-6 Astra at max reasoning effort through the local `codex` CLI, using your ChatGPT subscription allowance and credits. When that runs out of credits it switches automatically to Opus 5 through the `claude` CLI at max reasoning effort, and only then — if an OpenRouter API key is available — to the paid API. OpenRouter models can also be selected directly with `--model`.

Supports multi-model translation (GPT-6 Astra, GPT-5.x, Claude, Gemini, and budget models), context-aware terms of endearment, automatic subtitle extraction from MKV files, smart subtitle selection (prefers non-SDH English), automatic merging of translated subtitles back into the MKV, retry logic with exponential backoff, and cost tracking/estimation.

## Installation

```bash
uv tool install git+https://github.com/ktenman/mkv-subtitle-translator
```

Requires `ffmpeg`/`ffprobe` on `PATH` for MKV extraction and merging, and `codex` on `PATH` for the default model (`npm install -g @openai/codex`, then `codex login`). `claude` on `PATH` is optional - it is only used once codex runs out of credits.

## Usage

```bash
# Translate every .mkv in the current directory with GPT-6 Astra through Codex
mkv-subtitle-translator

# Translate a specific file
mkv-subtitle-translator -f episode.mkv

# Use less reasoning effort for faster translations (default: max)
mkv-subtitle-translator -f episode.mkv --effort high

# Start on the Claude Code CLI instead of codex
mkv-subtitle-translator -f episode.mkv --model claude

# Use an OpenRouter model instead (needs an API key)
mkv-subtitle-translator -f episode.mkv --model gpt-5.4-pro

# List available models
mkv-subtitle-translator --list-models

# Estimate cost before translating
mkv-subtitle-translator --estimate episode.mkv

# Re-translate even if a .et.srt already exists
mkv-subtitle-translator -f episode.mkv --force
```

The `codex` and `claude` models need no API key. Every other model requires an OpenRouter API key, via `--api-key` or the `OPENROUTER_API_KEY` environment variable. Get one at https://openrouter.ai/keys. Setting a key also unlocks the last step of the fallback chain.

The `codex` model explicitly selects `gpt-6-astra` at max reasoning effort, regardless of your global Codex configuration. Use `--effort` to override the reasoning effort for a run.

## Term sheet

On models that translate in batches, one call reads the whole file first and writes a
short term sheet: the setting, the characters, who says sina or teie to whom, and one
Estonian form for each name and recurring term. Every batch gets the sheet, so terms
stay the same across the file.

The sheet is saved next to the output as `<name>.et.terms.md`, and a saved sheet is
reused. If a term is wrong, fix it there and re-run with `--force`.

## Translation progress

Batches run five at a time on the `codex` and `claude` models and one at a time on
every other model. Each batch announces its subtitle range and active model before
the request starts. While batches wait, the terminal display refreshes every second
with finished and running batches, time elapsed in the stage, and backend status.
Codex and Claude show their reasoning effort and 30-minute
per-call timeout; OpenRouter shows request attempts and retry delays. Switching
backends after a quota error is also reported immediately.

For example, while the first five batches run:

```text
Batch 1/5: subtitles 1-200 (200 subtitles) | GPT-6 Astra (Codex CLI)
Translating:   0%|          | 0/964, 0/5 batches done, 5 running | 01:05 elapsed | Waiting for Codex response (max effort; timeout 30m per call)
```

The counter advances when a batch has been processed, with translated and failed
subtitles counted separately. An updating timer means the translator is still
waiting; it does not measure the model's internal progress or guarantee that the
backend is responding. Batch summaries show how many translations were returned.

When stderr is redirected to a log, updates are plain, flushed lines every
15 seconds, plus immediate batch, retry, fallback, and completion messages.

## Options

| Option | Description |
|---|---|
| `PATH` | Directory to scan for `.mkv`/`.extracted.srt` files (default: `.`) |
| `-f, --file` | Translate a specific `.srt` or `.mkv` file |
| `--api-key` | OpenRouter API key (or set `OPENROUTER_API_KEY`); not needed for `codex`/`claude` |
| `--model` | Model to use (default: `codex`); see `--list-models` |
| `--effort` | Codex reasoning effort: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (default: `max`) |
| `--list-models` | List available models with pricing and tier |
| `--estimate PATH` | Estimate translation cost for a file, no translation performed |
| `--no-merge` | Do not merge translated subtitles back into the MKV |
| `--no-backup` | Do not create a `.mkv.backup` when merging |
| `--force` | Re-translate even if the `.et.srt` output already exists |
| `--chunk-size` | Batch/chunk size for translation requests (default: 200 for CLI models, 50 otherwise) |
| `--max-workers` | Max parallel workers for non-batch models (default: 8) |
