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
episode.mkv.backup      the original video
episode.extracted.srt   the English subtitles
episode.et.srt          the Estonian subtitles
episode.et.terms.md     the term sheet
```

Good to know:

- Files that already have a `.et.srt` are skipped. Add `--force` to translate them again.
- If a translation fails or runs out of credits, no `.et.srt` is written. Run the same command again to retry.
- Add `--no-merge` to leave the video as it is, or `--no-backup` to skip the backup.
- `--help` lists every option.

## Translating a series

Give `--reference` the Estonian subtitles of an earlier episode to keep names and series terms the same. One episode is enough. It can be a file this tool wrote or one you downloaded.

```bash
mkv-subtitle-translator ~/Videos/season-2 --reference ~/Videos/season-1/s01e10.et.srt
```

If a name comes out wrong, fix it in `episode.et.terms.md` and run the video again with `--force`. Later runs reuse that file, so `--reference` is ignored while it exists. Delete it to start over.

## Models

By default it uses the `codex` CLI, on your ChatGPT subscription. When that runs out of credits, the `claude` CLI takes over, then OpenRouter if you set `OPENROUTER_API_KEY`. Any CLI you don't have is skipped.

```bash
# Start on the claude CLI instead of codex
mkv-subtitle-translator -f episode.mkv --model claude

# Use an OpenRouter model
mkv-subtitle-translator -f episode.mkv --model gpt-5.6-sol --api-key YOUR_KEY

# Use less Codex reasoning effort for a faster run
mkv-subtitle-translator -f episode.mkv --effort high

# See all models with prices
mkv-subtitle-translator --list-models

# See what a file would cost
mkv-subtitle-translator --estimate episode.mkv
```

Every model except `codex` and `claude` needs an [OpenRouter key](https://openrouter.ai/keys).

Only `codex`, `claude`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4` and `gemini-pro` get the term sheet, `--reference` and the error check. Other models translate line by line.

## How it works

1. Picks the English subtitle track, preferring one without captions for the hearing impaired.
2. Reads the whole file once and writes a term sheet with the characters, names and recurring terms, so they stay the same throughout.
3. Translates the subtitles.
4. Reads the whole translation again and corrects real errors only, printing each change.
5. Adds the Estonian track to the video, replacing any older one. Video, audio and other subtitles are copied as they are.

On `codex`, a 964-subtitle episode took about 10 minutes.

## License

[MIT](LICENSE)
