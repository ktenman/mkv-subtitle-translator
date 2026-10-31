# mkv-subtitle-translator

Translate SRT subtitles to Estonian through the Codex CLI, the Claude Code CLI, or OpenRouter (200+ models), with automatic MKV subtitle extraction and merging.

By default it translates with GPT-6 Astra at max reasoning effort through the local `codex` CLI, using your ChatGPT subscription allowance and credits. When that runs out of credits it switches automatically to Opus 5 through the `claude` CLI at max reasoning effort, and only then — if an OpenRouter API key is available — to the paid API. OpenRouter models can also be selected directly with `--model`.

## Installation

```bash
uv tool install git+https://github.com/ktenman/mkv-subtitle-translator
```

Requires `ffmpeg`/`ffprobe` on `PATH` for MKV extraction and merging, and `codex` on `PATH` for the default model (`npm install -g @openai/codex`, then `codex login`). `claude` on `PATH` is optional - it is only used once codex runs out of credits.

Each launch checks GitHub for a newer release. If there is one, the tool upgrades itself and asks you to re-run your command.

## Usage

### Translate

```bash
# Every .mkv in the current folder, with GPT-6 Astra through Codex
mkv-subtitle-translator

# Every .mkv in another folder
mkv-subtitle-translator ~/Videos/season-2

# One video
mkv-subtitle-translator -f episode.mkv

# A plain subtitle file, which writes subtitles.et.srt
mkv-subtitle-translator -f subtitles.srt

# Translate again, even if a .et.srt already exists
mkv-subtitle-translator -f episode.mkv --force

# Write the subtitles but leave the video as it is
mkv-subtitle-translator -f episode.mkv --no-merge
```

A translated video leaves these files next to it:

```text
episode.mkv             now has an Estonian subtitle track
episode.mkv.backup      the original video
episode.extracted.srt   the English subtitles
episode.et.srt          the Estonian subtitles
episode.et.terms.md     the term sheet, reused by later runs
```

### Keep series terms the same across episodes

Give `--reference` the Estonian subtitles of an earlier episode, and the new translation
reuses its names and series terms. One earlier episode is enough, and it can be a file this
tool wrote or one you downloaded. It needs a batch model, listed under
[How it works](#how-it-works).

```bash
# One episode
mkv-subtitle-translator -f s02e01.mkv --reference s01e10.et.srt

# A whole season: every episode reads the same reference
mkv-subtitle-translator ~/Videos/season-2 --reference ~/Videos/season-1/s01e10.et.srt

# More than one reference: repeat the flag
mkv-subtitle-translator -f s02e01.mkv --reference s01e09.et.srt --reference s01e10.et.srt

# An episode translated before: delete its term sheet first, or the reference is not read
rm s02e01.et.terms.md
mkv-subtitle-translator -f s02e01.mkv --reference s01e10.et.srt --force
```

### Choose the model and effort

```bash
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
```

The `codex` and `claude` models need no API key. Every other model requires an OpenRouter API key, via `--api-key` or the `OPENROUTER_API_KEY` environment variable. Get one at https://openrouter.ai/keys. Setting a key also unlocks the last step of the fallback chain.

The `codex` model explicitly selects `gpt-6-astra` at max reasoning effort, regardless of your global Codex configuration. Use `--effort` to override the reasoning effort for a run. On `codex`, the term sheet call stays at `high`. In a test, `ultra` gave nothing over `max`: its delegation failed and the run finished alone.

## How it works

An MKV on a batch model goes through six steps. A plain `.srt` skips steps 1 and 6. The
batch models are `codex`, `claude`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4` and `gemini-pro`.

1. **Extract:** pick the English track, preferring non-SDH, and save it as
   `<name>.extracted.srt`.
2. **Term sheet:** one call reads the whole file and fixes the wording of names and terms.
3. **Translate:** every call gets the term sheet and the five English subtitles on each
   side of its batch. `codex` and `claude` send 200 subtitles a call, five calls at a time.
   OpenRouter models send 50 a call, one at a time.
4. **Write:** save `<name>.et.srt` as UTF-8 with a BOM. Code places the line breaks from
   the English layout and straightens curly quotes, so the prompts carry no layout rules.
5. **Error check:** one more pass corrects real errors, and any corrections are saved.
6. **Merge:** add the Estonian track to the MKV, replacing any older one, and keep the
   original as `<name>.mkv.backup`. Video, audio and other subtitles are copied as they are.

Every other model translates line by line, with a small glossary for terms of endearment,
and skips the term sheet and the error check.

## Term sheet

On batch models, one call reads the whole file first and writes a short term sheet: the
setting, the characters, who says sina or teie to whom, and one Estonian form for each
name and recurring term. Every batch gets the sheet, so terms stay the same across the
file.

The sheet is saved next to the output as `<name>.et.terms.md`, and later runs reuse it,
even with `--force`. If a term is wrong, fix it there and re-run the file with `--force`.
To build a new sheet, delete the saved one first.

For a series, `--reference` gives that call Estonian subtitles of an earlier episode, so
names and series terms stay the same across episodes. One earlier episode is enough, in
UTF-8 or Windows-1252. It helps series terms, not style or general accuracy. Only the
term sheet call reads it, so with a saved sheet the file is not read, and the run says so.

## Error check

After translation, one more pass reads the whole title in English and Estonian and
corrects only real errors: wrong meaning, a name or term that differs from the sheet,
the wrong sina or teie, and grammar or spelling. It does not restyle correct lines, and
it prints each change as old and new text.

The output is written before the check starts, so a failed check loses nothing. On
`codex`, a 964-cue episode took about 10 minutes: 1 for the term sheet, 6 for the
translation and 3 for the check.

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
| `--reference FILE` | Earlier Estonian subtitles for names and series terms; repeatable; batch models only |
