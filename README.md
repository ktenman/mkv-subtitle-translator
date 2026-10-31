# mkv-subtitle-translator

Adds Estonian subtitles to MKV videos. It finds the English subtitles inside the video, translates them with AI and adds them back as a new track. It also works on plain `.srt` files.

**Contents:** [Install](#install) · [Your first translation](#your-first-translation) · [All commands](#all-commands) · [Examples](#examples) · [Models](#models) · [How it works](#how-it-works) · [When something goes wrong](#when-something-goes-wrong) · [License](#license)

## Install

You need [uv](https://docs.astral.sh/uv/) and [ffmpeg](https://ffmpeg.org/). Then install the tool and log in to Codex, which does the translating:

```bash
uv tool install git+https://github.com/ktenman/mkv-subtitle-translator
npm install -g @openai/codex
codex login
```

The [`claude` CLI](https://claude.com/claude-code) is optional. It takes over when Codex runs out of credits.

Each launch checks GitHub for a newer release. If there is one, the tool upgrades itself and asks you to re-run your command. To upgrade by hand:

```bash
uv tool upgrade mkv-subtitle-translator
```

## Your first translation

This is a real run on a short test video. It has three subtitle tracks: English, English for the hearing impaired (SDH) and German.

```bash
mkv-subtitle-translator -f episode.mkv
```

It prints this, shortened here:

```text
Extracting subtitles from episode.mkv
  Found 3 subtitle stream(s)
    Stream 0: eng - 845 bytes
  Detected as SDH subtitle (100.0% descriptions)
    Stream 1: eng - 403 bytes (SDH)
    Stream 2: ger - 211 bytes
  ✓ Extracted to: episode.extracted.srt

Processing: episode.extracted.srt
Found 12 unique subtitles
Term sheet 1/1: subtitles 1-12 (12 subtitles) | GPT-6 Astra (Codex CLI)
Term sheet 1/1 finished in 00:31: 1 written, 0 failed | 1/1 processed; 1 written, 0 failed
Term sheet saved: episode.et.terms.md
Batch 1/1: subtitles 1-12 (12 subtitles) | GPT-6 Astra (Codex CLI)
Batch 1/1 finished in 01:03: 12 translated, 0 failed | 12/12 processed; 12 translated, 0 failed
Check 1/1: subtitles 1-12 (12 subtitles) | GPT-6 Astra (Codex CLI)
Check 1/1 finished in 00:38: 12 checked, 0 failed | 12/12 processed; 12 checked, 0 failed
Error check corrected 0 subtitles
✅ Saved to: episode.et.srt

Merging subtitles into episode.mkv
  Running ffmpeg...
  Creating backup: episode.mkv.backup
  ✅ Successfully merged subtitles
```

It chose the plain English track over the SDH one and left these files next to the video:

```text
episode.mkv             now has an Estonian subtitle track
episode.mkv.backup      the original video
episode.extracted.srt   the English subtitles
episode.et.srt          the Estonian subtitles
episode.et.terms.md     the term sheet
```

An `episode.et.unchecked` file means the error check has not finished. [Run the same command again](#finish-a-stopped-check) to finish it.

To watch it, turn on the subtitle track called **Estonian (Translated)** in your player.

### The term sheet

Before translating, the tool reads the whole file and writes a term sheet. Every translation call gets a copy, so names and terms come out the same from start to end. This is `episode.et.terms.md` from the run above:

```text
SETTING:
A coastal lighthouse, late at night, with ships endangered by nearby rocks if its light fails. The watch lasts until dawn; the geographical location and historical period are unspecified.

CHARACTERS:
Leo: a late-arriving subordinate assigned to keep the lighthouse lamp burning overnight; addresses the Captain as teie.
Captain: Leo’s stern superior, who assigns the watch and explains the consequences of failure; addresses Leo as sina.
The Old Man is the lighthouse, not another character.

NAMES AND TITLES:
Leo → Leo (genitive Leo, partitive Leod).
Captain → kapten (genitive kapteni, partitive kaptenit); lowercase when addressing him.
Old Man → Vanamees (genitive Vanamehe, partitive Vanameest). Use this consistently as the lighthouse’s nickname. Leo initially understands it literally: retain vanamees, lowercase, for that misunderstanding.
Keeper → majakavaht (genitive majakavahi, partitive majakavahti).

RECURRING TERMS:
night watch → öövalve.
```

### The result

| # | English | Estonian |
|---|---|---|
| 1 | [door creaks]<br>Who's there? | [uks kriuksub]<br>Kes seal on? |
| 2 | - It's me, Captain.<br>- You're late again, Leo. | - Mina, kapten.<br>- Sa jäid jälle hiljaks, Leo. |
| 3 | The Old Man won't wait for us. | Vanamees ei jää meid ootama. |
| 4 | What old man? | Mis vanamees? |
| 5 | The lighthouse, you fool.<br>That's what we call it. | Majakas, sa tobu. Nii me seda kutsume. |
| 6 | Sorry, Captain.<br>I missed the last ferry. | Vabandage, kapten.<br>Jäin viimasest praamist maha. |
| 7 | You have the night watch.<br>Keep the lamp burning until dawn. | Öövalve on sinu kanda.<br>Hoia lamp koiduni põlemas. |
| 8 | Alone? | Üksi? |
| 9 | <i>Every keeper before you<br>stood the night watch alone.</i> | <i>Kõik majakavahid enne sind<br>on öövalvet üksi pidanud.</i> |
| 10 | And if the Old Man goes dark? | Ja kui Vanamees pimedaks jääb? |
| 11 | Then the ships hit the rocks,<br>and you explain it to their widows. | Siis jooksevad laevad karile ja sina<br>seletad seda meremeeste leskedele. |
| 12 | Yes, Captain. | Jah, kapten. |

What to look for:

- **Terms stay the same.** "The Old Man" is `Vanamees` in 3 and 10, and "night watch" is always `öövalve`. Subtitle 4 is lowercase on purpose, because Leo takes the name literally. The term sheet asked for that.
- **Sina and teie stay the same.** Leo says teie to the Captain (`Vabandage`), and the Captain says sina to Leo (`Hoia`).
- **The layout follows the English.** Two speakers keep their own lines (2), a sound label stays on its own line (1) and italics stay (9). A translation short enough for one line goes on one line (5).

## All commands

```text
mkv-subtitle-translator [PATH] [OPTIONS]
```

| Command | What it does | Default | Example |
|---|---|---|---|
| `PATH` | The folder to translate | current folder | [A whole folder](#a-whole-folder) |
| `-f FILE`, `--file FILE` | Translate one `.mkv` or `.srt` file instead of a folder | | [One video](#one-video), [A plain `.srt` file](#a-plain-srt-file) |
| `--force` | Translate again, even if a `.et.srt` already exists | off | [Translate again](#translate-again) |
| `--no-merge` | Write the subtitle files but leave the video as it is | off | [Leave the video as it is](#leave-the-video-as-it-is) |
| `--no-backup` | Merge without keeping a `.mkv.backup` | off | [Skip the backup](#skip-the-backup) |
| `--reference FILE` | Earlier Estonian subtitles for names and series terms. Repeat it for more files | | [Keep a series consistent](#keep-a-series-consistent) |
| `--model NAME` | Which model translates | `codex` | [Start on Claude](#start-on-claude), [Use OpenRouter](#use-openrouter) |
| `--effort LEVEL` | Codex reasoning effort: `low`, `medium`, `high`, `xhigh`, `max` or `ultra` | `max` | [Change the Codex effort](#change-the-codex-effort) |
| `--api-key KEY` | Your OpenRouter key, if `OPENROUTER_API_KEY` is not set | | [Use OpenRouter](#use-openrouter) |
| `--list-models` | List the models and their prices, then stop | | [See the models](#see-the-models) |
| `--estimate FILE` | Show what a `.mkv` or `.srt` would cost, then stop | | [See what a file costs](#see-what-a-file-costs) |
| `--chunk-size N` | How many subtitles go in each translation call | 200 on `codex` and `claude`, 50 otherwise | [Smaller batches](#smaller-batches) |
| `--max-workers N` | How many calls run at once on [line-by-line models](#models). Other models ignore it | 8 | [Parallel calls](#parallel-calls) |
| `--help` | Show this list in the terminal | | |

## Examples

### One video

```bash
mkv-subtitle-translator -f episode.mkv
```

[Your first translation](#your-first-translation) shows what this prints and the files it leaves.

### A whole folder

```bash
# Every .mkv in the current folder
mkv-subtitle-translator

# Every .mkv in another folder
mkv-subtitle-translator ~/Videos/season-2
```

Each video goes through the same steps, and the merges all run at the end. Subfolders are not searched, and plain `.srt` files in the folder are left alone.

### A plain `.srt` file

```bash
mkv-subtitle-translator -f subtitles.srt
```

This writes `subtitles.et.srt` and `subtitles.et.terms.md`. The file must be UTF-8. [When something goes wrong](#when-something-goes-wrong) shows how to convert one.

### Leave the video as it is

```bash
mkv-subtitle-translator -f episode.mkv --no-merge
```

The subtitle files are written, but the video is not touched and no backup is made. To add the track later, run the same command without `--no-merge`. The translation is skipped and only the merge runs.

### Skip the backup

```bash
mkv-subtitle-translator -f episode.mkv --no-backup
```

The video is replaced and there is no `.mkv.backup` to go back to, so use this only if you have another copy.

### Translate again

```bash
mkv-subtitle-translator -f episode.mkv --force
```

Without `--force`, a file that already has a `.et.srt` is not translated again. With it, the translation and the error check run again, but the saved term sheet is reused. Delete `episode.et.terms.md` first if you want a new one.

### Finish a stopped check

The `.et.srt` is saved before the error check starts. If the check stops because of Ctrl+C, a crash, a failed call or no credits, the run says so:

```text
Error check corrected 0 subtitles
1 of 1 batches could not be checked. The translation is saved. Run the same command again to finish the check.
```

Corrections that already came back stay in the file, and `episode.et.unchecked` marks the check as unfinished. Run the same command again:

```bash
mkv-subtitle-translator -f episode.mkv
```

The saved translation is kept and only the check runs, from its first batch. The marker is removed once every batch is checked, and the video gets the corrected track:

```text
Finishing the error check of episode.et.srt
Error check corrected 1 subtitles:
  #2: Mina, kapten -> Mina, kapten.
✅ Saved to: episode.et.srt
```

With `--force`, the whole file is translated again instead.

### Fix one line by hand

Edit `episode.et.srt` in a text editor, then run the same command again without `--force`:

```bash
mkv-subtitle-translator -f episode.mkv
```

The translation is skipped, no model is called, and your edited subtitles replace the Estonian track in the video.

### Fix a name everywhere

If a name comes out wrong, correct it in `episode.et.terms.md` and translate again:

```bash
mkv-subtitle-translator -f episode.mkv --force
```

### Keep a series consistent

Give `--reference` the Estonian subtitles of an earlier episode, so names and series terms stay the same across episodes. One episode is enough. It can be a file this tool wrote or one you downloaded, in UTF-8 or Windows-1252. It helps with names and terms, not with style.

```bash
# One episode
mkv-subtitle-translator -f s02e01.mkv --reference s01e10.et.srt

# A whole season: every episode reads the same reference
mkv-subtitle-translator ~/Videos/season-2 --reference ~/Videos/season-1/s01e10.et.srt

# More than one reference: repeat the option
mkv-subtitle-translator -f s02e01.mkv --reference s01e09.et.srt --reference s01e10.et.srt
```

Only a new term sheet reads the reference, so `--reference` is ignored while a term sheet exists. To use one on an episode you translated before, delete its term sheet first:

```bash
rm s02e01.et.terms.md
mkv-subtitle-translator -f s02e01.mkv --reference s01e10.et.srt --force
```

## Models

By default the tool uses the `codex` CLI, on your ChatGPT subscription. If that runs out of credits or is not installed, the next step takes over by itself:

```text
codex  ->  claude  ->  OpenRouter (gpt-5.6-sol)
```

The run tells you when it switches:

```text
Out of credits - switching to Opus 5 (Claude Code CLI)
```

The `claude` step uses the `claude` CLI, on your Claude subscription. The OpenRouter step only happens if a key is set, with `--api-key` or `OPENROUTER_API_KEY`, and it costs money per token.

The model decides how much of the process runs:

| Models | What runs |
|---|---|
| `codex`, `claude`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4`, `gemini-pro` | All of it: the term sheet, `--reference`, batches and the error check |
| Every other model | Line by line: one call per subtitle with a small glossary, and no term sheet, `--reference` or error check |

Every model except `codex` and `claude` needs an [OpenRouter key](https://openrouter.ai/keys).

### Start on Claude

```bash
mkv-subtitle-translator -f episode.mkv --model claude
```

This skips `codex`. OpenRouter can still take over if a key is set.

### Use OpenRouter

```bash
# Pass the key once
mkv-subtitle-translator -f episode.mkv --model gpt-5.6-sol --api-key YOUR_KEY

# Or set it for the whole session
export OPENROUTER_API_KEY=YOUR_KEY
mkv-subtitle-translator -f episode.mkv --model gpt-5.6-sol
```

When you pick an OpenRouter model, only that model runs. There is no fallback.

### Change the Codex effort

```bash
# Use less reasoning effort for a faster run
mkv-subtitle-translator -f episode.mkv --effort high
```

The default is `max`. In a test, `ultra` gave nothing over `max`. This only changes `codex`, and its term sheet always runs at `high`. `claude` always runs at `max`.

### See the models

```bash
mkv-subtitle-translator --list-models
```

```text
                                         PREMIUM
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key         ┃ Name                     ┃ $/1M tokens ┃ Best for                       ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ codex       │ GPT-6 Astra (Codex CLI)  │       $0.00 │ films, drama, everything       │
│ claude      │ Opus 5 (Claude Code CLI) │       $0.00 │ films, drama, complex dialogue │
│ gpt-5.6-sol │ GPT-5.6 Sol              │      $12.00 │ films, drama, everything       │
...
```

Use the `Key` column with `--model`. The price is the input and output rates added together.

### See what a file costs

```bash
mkv-subtitle-translator --estimate episode.mkv --model gpt-5.6-sol
```

Nothing is translated. For a 964-subtitle episode it prints:

```text
Cost Estimate for episode.mkv
Subtitles: 964
Model: GPT-5.6 Sol
Estimated tokens: ~638,168 in / ~29,920 out
Estimated cost: $1.5755
  Comparison across models
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Model         ┃ Est. cost ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ codex         │   $0.0000 │
│ claude        │   $0.0000 │
│ gpt-5.6-sol   │   $1.5755 │
│ gpt-5.5       │   $4.0884 │
...
```

`codex` and `claude` show $0 because they run on your subscription, not per token.

### Smaller batches

```bash
mkv-subtitle-translator -f episode.mkv --chunk-size 100
```

Try this if calls keep timing out or come back with lines missing. This only changes the translation calls. The error check keeps its own batch size, so a smaller size doesn't add check calls.

### Parallel calls

```bash
mkv-subtitle-translator -f episode.mkv --model gpt-5-mini --api-key YOUR_KEY --max-workers 4
```

This only applies to line-by-line models, so lower it if OpenRouter limits your requests. `codex` and `claude` always make five calls at once, and the other batch models make one at a time.

## How it works

A video goes through six steps. A plain `.srt` skips the first and the last. [Line-by-line models](#models) skip the term sheet and the error check.

1. **Extract.** Tries every subtitle track except Estonian ones and picks the largest English one without captions for the hearing impaired, then saves it as `episode.extracted.srt`. If there is none, it takes an English SDH track, then the largest other text track.
2. **Term sheet.** One call reads the whole file and writes [the term sheet](#the-term-sheet). Later runs reuse it. Related: [Fix a name everywhere](#fix-a-name-everywhere), [Keep a series consistent](#keep-a-series-consistent).
3. **Translate.** Each call gets one batch, the term sheet and the five subtitles on each side of the batch. `codex` and `claude` send 200 subtitles a call, five calls at a time. OpenRouter models send 50 a call, one at a time. Related: [Smaller batches](#smaller-batches), [Change the Codex effort](#change-the-codex-effort).
4. **Write.** Saves `episode.et.srt` as UTF-8 with a BOM. The tool places the line breaks itself from the English layout, keeping lines to 42 characters where it can, and straightens curly double quotes. Related: [The result](#the-result).
5. **Error check.** One more pass reads the English and the Estonian and corrects real errors only: wrong meaning, a name or term that differs from the term sheet, the wrong sina or teie, and grammar or spelling. It leaves correct lines alone, saves its corrections and prints each change, like this:

   ```text
   Error check corrected 1 subtitles:
     #7: Öövalve on minu kanda. -> Öövalve on sinu kanda.
   ```

   Related: [Finish a stopped check](#finish-a-stopped-check).

6. **Merge.** Adds the Estonian track to the video, replacing any older one, and keeps the original as `episode.mkv.backup`. Video, audio and other subtitles are copied as they are. Related: [Leave the video as it is](#leave-the-video-as-it-is), [Skip the backup](#skip-the-backup), [Fix one line by hand](#fix-one-line-by-hand).

On `codex`, a 964-subtitle episode took about 10 minutes: 1 for the term sheet, 6 for the translation and 3 for the check.

### Watching the progress

While calls are running, the terminal shows which batches have started and how long they have been waiting:

```text
Batch 1/5: subtitles 1-200 (200 subtitles) | GPT-6 Astra (Codex CLI)
Translating:   0%|          | 0/964, 0/5 batches done, 5 running | 01:05 elapsed | Waiting for Codex response (max effort; timeout 30m per call)
```

The counter moves when a batch finishes, so it can sit at 0% for minutes. A running timer means the tool is still waiting for the model. It does not show how far the model has got. If you send the output to a log file, you get a plain status line every 15 seconds instead.

## When something goes wrong

You can always run the same command again. Finished files are not translated twice.

- **More than 1% of the subtitles failed:** no `.et.srt` is written, so the next run tries that file again.
- **1% or fewer failed:** the `.et.srt` is written and those lines stay in English. `Failed:` in the summary shows how many. The next run skips the file, so use [`--force`](#translate-again) to translate it again.
- **Every model ran out of credits:** the run stops. Files already finished are kept, and the next run picks up where it stopped and merges any video still waiting.
- **The error check stopped or failed:** nothing is lost, because the `.et.srt` is saved before the check starts. The next run [finishes the check](#finish-a-stopped-check).

| What you see | What it means | What to do |
|---|---|---|
| `No subtitle streams found` | The video has no subtitle tracks, or `ffmpeg` is not installed | Install `ffmpeg`, or find a `.srt` and use it with `-f` |
| `Failed to extract any subtitles` | No track could be used. Usually they are images (PGS or VobSub), as on many Blu-ray rips | Find a `.srt` and use it with `-f` |
| `No files to translate` | The folder has no `.mkv` files, or `-f` got a file that is not `.mkv` or `.srt` | Check the path |
| `Skipping episode.extracted.srt - output exists` | It already has a `.et.srt` | Nothing, or add [`--force`](#translate-again) |
| `Error: OpenRouter API key required` | The model runs on OpenRouter | [Add a key](#use-openrouter) |
| `claude CLI not found on PATH` | Neither `codex` nor `claude` is installed | [Install `codex`](#install) |
| `claude is out of credits` | Every model you can use has run out | Wait for your limit to reset or set `OPENROUTER_API_KEY`, then run it again |
| `1 of 12 subtitles were not translated` | More than 1% failed | Read the errors above it, then run it again |
| `2 of 5 batches could not be checked` | The error check did not finish. The translation is saved | [Run it again](#finish-a-stopped-check) |
| `--reference files were not read because the term sheet already exists` | Only a new term sheet reads references | [Delete the term sheet](#keep-a-series-consistent) |
| `--reference needs a batch model and was ignored` | Line-by-line models have no term sheet | [Use a model that has one](#models) |
| `File name too long` | The name is too long for the files the tool writes next to it. Nothing was sent to a model, and a folder run carries on with the next video | Rename the file, then run it again |
| `UnicodeDecodeError` | The `.srt` is not UTF-8 | Convert it: `iconv -f WINDOWS-1252 -t UTF-8 old.srt > subtitles.srt` |

## License

[MIT](LICENSE)
