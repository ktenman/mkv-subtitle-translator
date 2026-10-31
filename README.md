# mkv-subtitle-translator

Adds Estonian subtitles to MKV videos. It finds the English subtitles inside the video, translates them with AI and adds them back as a new track. It also works on plain `.srt` files.

## Install

You need [uv](https://docs.astral.sh/uv/) and `ffmpeg`. Then install the tool and log in to Codex, which does the translating:

```bash
uv tool install git+https://github.com/ktenman/mkv-subtitle-translator
npm install -g @openai/codex
codex login
```

Each launch checks GitHub for a newer release. If there is one, the tool upgrades itself and asks you to re-run your command.

## Usage

```bash
# Every .mkv in the current folder
mkv-subtitle-translator

# Every .mkv in another folder
mkv-subtitle-translator ~/Videos/season-2

# One video
mkv-subtitle-translator -f episode.mkv

# A plain subtitle file, which writes subtitles.et.srt
mkv-subtitle-translator -f subtitles.srt
```

A translated video leaves these files next to it:

```text
episode.mkv             now has an Estonian subtitle track
episode.mkv.backup      the video before the last merge
episode.extracted.srt   the English subtitles
episode.et.srt          the Estonian subtitles
episode.et.terms.md     the term sheet, reused by later runs
```

Good to know:

- Files that already have a `.et.srt` are skipped. Add `--force` to translate them again.
- Running a video again merges it again, and the backup is replaced by the already merged video.
- If a folder already has `.extracted.srt` files, only those are processed. Use `-f` for a new video in that folder.

## Translating a series

Give `--reference` the Estonian subtitles of an earlier episode to keep names and series terms the same. One episode is enough. It can be a file this tool wrote or one you downloaded, in UTF-8 or Windows-1252.

```bash
mkv-subtitle-translator ~/Videos/season-2 --reference ~/Videos/season-1/s01e10.et.srt
```

If a name comes out wrong, fix it in `episode.et.terms.md` and run the video again with `--force`. Later runs reuse that file, so `--reference` is ignored while it exists. Delete it to start over.

## Models

By default it uses GPT-6 Astra through the `codex` CLI, on your ChatGPT subscription. When that runs out of credits, Opus 5 takes over through the `claude` CLI, then `gpt-5.6-sol` on OpenRouter if you have an API key.

`claude` is optional, but without it nothing takes over when Codex runs out, even with an OpenRouter key.

```bash
# Start on the claude CLI instead of codex
mkv-subtitle-translator -f episode.mkv --model claude

# Use an OpenRouter model
mkv-subtitle-translator -f episode.mkv --model gpt-5.6-sol --api-key YOUR_KEY

# See all models with prices
mkv-subtitle-translator --list-models

# See what a file would cost
mkv-subtitle-translator --estimate episode.mkv
```

`codex` and `claude` need no API key. Every other model needs an [OpenRouter key](https://openrouter.ai/keys).

Only `codex`, `claude`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4` and `gemini-pro` get the term sheet, `--reference` and the error check. Other models translate line by line.

## Options

| Option | What it does |
|---|---|
| `PATH` | Folder to translate (default: the current folder) |
| `-f, --file` | Translate one `.mkv` or `.srt` file |
| `--force` | Translate again even if the `.et.srt` exists |
| `--no-merge` | Write the subtitles but leave the video as it is |
| `--no-backup` | Do not keep a `.mkv.backup` when merging |
| `--reference FILE` | Earlier Estonian subtitles for names and series terms; repeat it for more files |
| `--model` | Model to use (default: `codex`) |
| `--effort` | Codex reasoning effort: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (default: `max`) |
| `--api-key` | OpenRouter API key, or set `OPENROUTER_API_KEY` |
| `--list-models` | List models with prices |
| `--estimate PATH` | Show what a file would cost, without translating |

`--help` lists the rest.

## How it works

1. Picks the English subtitle track, preferring one without captions for the hearing impaired.
2. Reads the whole file once and writes a term sheet with the characters, names and recurring terms, so they stay the same throughout.
3. Translates the subtitles in batches.
4. Reads the whole translation again and corrects real errors only, printing each change.
5. Adds the Estonian track to the video, replacing any older one. Video, audio and other subtitles are copied as they are.

A plain `.srt` skips steps 1 and 5. On `codex`, a 964-subtitle episode took about 10 minutes.

## License

[MIT](LICENSE)
