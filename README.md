# mkv-subtitle-translator

Translate SRT subtitles to Estonian through the Codex CLI, the Claude Code CLI, or OpenRouter (200+ models), with automatic MKV subtitle extraction and merging.

By default it translates with GPT-5.6 Sol through the local `codex` CLI, which bills to your ChatGPT subscription instead of a paid API. When that runs out of credits it switches automatically to Opus 5 through the `claude` CLI at max reasoning effort, and only then — if an OpenRouter API key is available — to the paid API. OpenRouter models can also be selected directly with `--model`.

Supports multi-model translation (GPT-5.x, Claude, Gemini, and budget models), context-aware terms of endearment, automatic subtitle extraction from MKV files, smart subtitle selection (prefers non-SDH English), automatic merging of translated subtitles back into the MKV, retry logic with exponential backoff, and cost tracking/estimation.

## Installation

```bash
uv tool install git+https://github.com/ktenman/mkv-subtitle-translator
```

Requires `ffmpeg`/`ffprobe` on `PATH` for MKV extraction and merging, and `codex` on `PATH` for the default model (`npm install -g @openai/codex`, then `codex login`). `claude` on `PATH` is optional - it is only used once codex runs out of credits.

## Usage

```bash
# Translate every .mkv in the current directory with the default model (codex)
mkv-subtitle-translator

# Translate a specific file
mkv-subtitle-translator -f episode.mkv

# Crank reasoning effort - free on the subscription, just slower
mkv-subtitle-translator -f episode.mkv --effort max

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

## Options

| Option | Description |
|---|---|
| `PATH` | Directory to scan for `.mkv`/`.extracted.srt` files (default: `.`) |
| `-f, --file` | Translate a specific `.srt` or `.mkv` file |
| `--api-key` | OpenRouter API key (or set `OPENROUTER_API_KEY`); not needed for `codex`/`claude` |
| `--model` | Model to use (default: `codex`); see `--list-models` |
| `--effort` | Codex reasoning effort: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (default: `high`) |
| `--list-models` | List available models with pricing and tier |
| `--estimate PATH` | Estimate translation cost for a file, no translation performed |
| `--no-merge` | Do not merge translated subtitles back into the MKV |
| `--no-backup` | Do not create a `.mkv.backup` when merging |
| `--force` | Re-translate even if the `.et.srt` output already exists |
| `--chunk-size` | Batch/chunk size for translation requests (default: 200 for CLI models, 50 otherwise) |
| `--max-workers` | Max parallel workers for non-batch models (default: 8) |
