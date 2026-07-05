# translate-subs-openrouter

Translate SRT subtitles to Estonian using OpenRouter's API (200+ models), with automatic MKV subtitle extraction and merging.

Supports multi-model translation (GPT-5.x, Claude, Gemini, and budget models), context-aware terms of endearment, automatic subtitle extraction from MKV files, smart subtitle selection (prefers non-SDH English), automatic merging of translated subtitles back into the MKV, retry logic with exponential backoff, and cost tracking/estimation.

## Installation

```bash
uv tool install git+https://github.com/ktenman/translate-subs-openrouter
```

Requires `ffmpeg`/`ffprobe` on `PATH` for MKV extraction and merging.

## Usage

```bash
# Translate every .mkv in the current directory with the default model (gpt-5.4)
translate-subs-openrouter

# Translate a specific file
translate-subs-openrouter -f episode.mkv

# Use a different model
translate-subs-openrouter -f episode.mkv --model gpt-5.4-pro

# List available models
translate-subs-openrouter --list-models

# Estimate cost before translating
translate-subs-openrouter --estimate episode.mkv

# Re-translate even if a .et.srt already exists
translate-subs-openrouter -f episode.mkv --force
```

Requires an OpenRouter API key, via `--api-key` or the `OPENROUTER_API_KEY` environment variable. Get one at https://openrouter.ai/keys.

## Options

| Option | Description |
|---|---|
| `PATH` | Directory to scan for `.mkv`/`.extracted.srt` files (default: `.`) |
| `-f, --file` | Translate a specific `.srt` or `.mkv` file |
| `--api-key` | OpenRouter API key (or set `OPENROUTER_API_KEY`) |
| `--model` | Model to use (default: `gpt-5.4`); see `--list-models` |
| `--list-models` | List available models with pricing and tier |
| `--estimate PATH` | Estimate translation cost for a file, no translation performed |
| `--no-merge` | Do not merge translated subtitles back into the MKV |
| `--no-backup` | Do not create a `.mkv.backup` when merging |
| `--force` | Re-translate even if the `.et.srt` output already exists |
| `--chunk-size` | Batch/chunk size for translation requests (default: 50) |
| `--max-workers` | Max parallel workers for non-batch models (default: 8) |
