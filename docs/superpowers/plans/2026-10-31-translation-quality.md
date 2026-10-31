# Estonian Translation Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recurring names and terms consistent, fix subtitle layout, catch blatant errors, and cut a 964-cue episode from about 36 minutes to about 11.

**Architecture:** Code places line breaks from the source cue's layout, so the model never sees layout. One call writes a short term sheet that every batch shares, batches run five at a time with English neighbours as context, and an error-only check runs after the output has been written. All stages use the existing client chain.

**Tech Stack:** Python 3.10+, `concurrent.futures`, existing tqdm, typer and httpx, pytest, Ruff.

**Spec:** [Issue #7](https://github.com/ktenman/mkv-subtitle-translator/issues/7). Read its Design, Non-goals and Acceptance sections before starting.

## Global Constraints

- **The output format does not change.** `write_srt` stays UTF-8 with BOM, and tags and the `.et.srt` name stay as they are.
- No new non-ASCII characters in the output. Quotes become straight `"`.
- Batch sizes do not change: 200 for the CLI backends and 50 for OpenRouter.
- `--effort` applies to translation and the error check. The term sheet is fixed at `high` on Codex.
- The fallback chain is unchanged.
- No line, length or quote rules in any prompt. These lowered quality when tested.
- OpenRouter stays one call at a time. CLI backends run 5 calls at a time.
- Python >=3.10. No new dependencies.
- The repo is public: no show titles, release names, subtitle sites or local paths in code, tests, commits, the PR or the issue.
- Branch `feat/translation-quality` from `feat/live-translation-progress`. Open the PR against that branch. Do not touch PR #6 or the uncommitted work in the main checkout.
- `uv run` rewrites the version line in `uv.lock`. Never stage it.
- Before each commit run `uv run ruff check src/ tests/` and `uv run ruff format src/ tests/`.
- Commits: one imperative subject of about 50 characters, no body, no AI attribution. The same goes for the PR.
- Merging to `main` publishes a release. Stop at an open PR.

## Review Focus

- Ctrl+C during parallel calls: calls not yet started never start, and the interrupt reaches the user. Pinned in Task 3.
- Codex and Claude run dry mid-title with an OpenRouter key set: workers already running must reach the paid API one at a time. Pinned in Task 3.
- A cue with `<font>` tags: a line break never lands inside a tag. Pinned in Task 1.
- A model without batch support: no term sheet, no check, no `.et.terms.md`, and its per-line translation still works. Pinned in Tasks 4 and 6.
- An SRT with no cues: no model call, and the output is still a valid empty file. Pinned in Task 4.

## Decisions This Plan Adds

- `Subtitle.line_count` is replaced by `source_lines`, because nothing reads it any more.
- A new `prompts.py` holds the three prompts, so `translator.py` stops growing and the text can be tested alone.
- `translate_file` is the new entry point for the CLI. `translate_subtitles` stays for the translation stage alone.
- The issue says results apply "in cue order". Each batch writes only to its own cues as it finishes, so the output is in cue order and progress still moves when an early batch is slow.
- When the chain reaches OpenRouter during a run, a lock inside `FallbackClient` keeps those calls one at a time.
- Reference files decode with `errors="replace"` on Windows-1252, so one undefined byte cannot stop a run.
- A line break never lands inside a tag, and only visible characters count toward 42. The issue doesn't ask for this, but `<font>` tags contain spaces and `{\an8}` is not shown on screen.

---

### Task 1: Line breaks in code

**Files:**
- Modify: `src/mkv_subtitle_translator/models.py:237-244`
- Modify: `src/mkv_subtitle_translator/linebreak.py`
- Modify: `src/mkv_subtitle_translator/translator.py:68-93`, `:414-421`
- Test: `tests/test_linebreak.py`, `tests/test_translator.py`

**Interfaces:**
- Produces: `Subtitle.source_lines: tuple[str, ...] = ()`, `restore_line_break(text: str, source_lines: Sequence[str] = ()) -> str`, `MAX_LINE_LENGTH = 42`

- [ ] **Step 1: Replace `tests/test_linebreak.py` with the rules below**

The old tests expect a split near the midpoint, which rule 3 now forbids for short text.

```python
from mkv_subtitle_translator.linebreak import restore_line_break

LONG = "Ma ei tea, kas me jõuame täna õhtul koju tagasi"


class TestSpeakers:
    def test_splits_at_the_inner_dash(self):
        result = restore_line_break("- Kas tuled? - Täna mitte.", ("- Are you?", "- Not tonight."))
        assert result == "- Kas tuled?\n- Täna mitte."

    def test_keeps_italic_wrapper(self):
        source = ("<i>- Are you coming?", "- Not tonight.</i>")
        result = restore_line_break("<i>- Kas tuled? - Täna mitte.</i>", source)
        assert result == "<i>- Kas tuled?\n- Täna mitte.</i>"

    def test_looks_past_an8(self):
        source = ("{\\an8}- Are you coming?", "- Not tonight.")
        result = restore_line_break("{\\an8}- Kas tuled? - Täna mitte.", source)
        assert result == "{\\an8}- Kas tuled?\n- Täna mitte."

    def test_finds_a_dash_inside_an_italic_tag(self):
        source = ("- ♪ music", "<i>- Line two</i>")
        result = restore_line_break("- ♪ muusika <i>- Teine rida</i>", source)
        assert result == "- ♪ muusika\n<i>- Teine rida</i>"

    def test_each_speaker_in_own_italics(self):
        source = ("<i>- Are you coming?</i>", "<i>- Not tonight.</i>")
        result = restore_line_break("<i>- Kas tuled?</i> <i>- Täna mitte.</i>", source)
        assert result == "<i>- Kas tuled?</i>\n<i>- Täna mitte.</i>"

    def test_no_inner_dash_falls_through_to_the_length_rules(self):
        assert restore_line_break("Kas tuled?", ("- Are you?", "- No.")) == "Kas tuled?"


class TestLabel:
    def test_keeps_a_lone_label_on_line_one(self):
        result = restore_line_break("[uks kriuksub] Kes seal on?", ("[door creaks]", "Who's there?"))
        assert result == "[uks kriuksub]\nKes seal on?"


class TestLength:
    def test_short_text_stays_on_one_line_even_from_a_two_line_source(self):
        text = "Tere, mu vana sõber"
        assert restore_line_break(text, ("Hello there,", "my old friend")) == text

    def test_splits_after_punctuation_when_over_the_limit(self):
        assert restore_line_break(LONG) == "Ma ei tea,\nkas me jõuame täna õhtul koju tagasi"

    def test_never_splits_between_two_capitalised_words(self):
        result = restore_line_break("Ma rääkisin eile õhtul pikalt Angel Bautista naisega kohvikus")
        assert result == "Ma rääkisin eile õhtul pikalt\nAngel Bautista naisega kohvikus"

    def test_text_too_long_for_two_lines_still_gets_two_lines_and_loses_nothing(self):
        text = " ".join(["üks"] * 30)
        result = restore_line_break(text)
        assert result.count("\n") == 1
        assert result.replace("\n", " ") == text

    def test_keeps_wrap_tags_outside_the_break(self):
        assert restore_line_break(f"{{\\an8}}{LONG}").startswith("{\\an8}Ma ei tea,\n")
        assert restore_line_break(f"<i>{LONG}</i>").endswith("koju tagasi</i>")

    def test_never_breaks_inside_a_tag(self):
        result = restore_line_break(f'<font color="#ffffff">{LONG}</font>')
        assert result == f'<font color="#ffffff">Ma ei tea,\n{LONG[11:]}</font>'


def test_leaves_already_multiline_text_unchanged():
    assert restore_line_break("line one\nline two") == "line one\nline two"


def test_single_word_with_no_spaces_unchanged():
    assert restore_line_break("Word") == "Word"
```

In `tests/test_translator.py`:

- `test_tracks_line_count_per_block` becomes `test_keeps_the_source_lines_of_each_block`: assert `[s.source_lines for s in subtitles] == [("Hello there", "my old friend"), ("[door creaks]",), ("Nice to see you", "again today")]`.
- `test_restores_two_line_blocks` becomes `test_two_speaker_block_keeps_its_two_lines`: build the `Subtitle` with `source_lines=("- Hello.", "- Hi.")` and `translated_text="- Tere. - Hei."`, and assert the text block is `"- Tere.\n- Hei."`.
- `test_leaves_single_line_blocks_alone` passes `source_lines=("[door creaks]",)` instead of `line_count=1`.
- Add `test_turns_curly_quotes_straight`: `translated_text="„Tere“ ütles ta ja “läks” ära."` gives `'"Tere" ütles ta ja "läks" ära.'`.
- Add `test_output_is_utf8_with_bom`: `out.read_bytes().startswith(b"\xef\xbb\xbf")`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_linebreak.py tests/test_translator.py -q`
Expected: FAIL. `restore_line_break` takes one argument and `Subtitle` has no `source_lines`.

- [ ] **Step 3: Replace `line_count` with `source_lines`**

`read_srt` sets `source_lines=tuple(line.strip() for line in lines[2:])`. `text` stays joined with a space.

- [ ] **Step 4: Rewrite `linebreak.py`**

Keep `_strip_wrap_tags`. Replace the header comment, `_WRAP_CONJUNCTIONS`, `_split_dash`, `_split_natural`, `restore_line_break` and `_demo` (update it to the new rules so `python -m mkv_subtitle_translator.linebreak` still passes). The cost values below were measured on 13,352 cues, so copy them exactly.

```python
MAX_LINE_LENGTH = 42

_SPEAKER_DASH = re.compile(r"^(?:\{[^}]*\})?(?:<i>)?\s*[-–—]\s")
_INNER_DASH = re.compile(r"\s(?:<i>)?\s*[-–—]\s")
_LABEL = re.compile(r"\[[^\]]+\]")
_LABEL_START = re.compile(r"(\[[^\]]+\])\s+(.+)")
_TAG = re.compile(r"<[^>]*>|\{[^}]*\}")
_SPACE_OUTSIDE_TAG = re.compile(r" (?![^<>]*>)")
_NO_BREAK_AFTER = set(
    "ja ning ega ehk või et kui aga vaid kuid sest mis kes kus ei on see seda selle oma mu su "
    "ta ma sa me te nad üks ühe mitte nii kas ka the a an of to".split()
)


def _visible(s: str) -> str:
    return _TAG.sub("", s).strip()


def _split_dash(s: str) -> tuple[str, str] | None:
    """Split at the second speaker's dash. Search from 1 to skip the first speaker's."""
    m = _INNER_DASH.search(s, 1)
    if m is None:
        return None
    return s[: m.start()].rstrip(), s[m.start() + 1 :].lstrip()


def _split_label(s: str) -> tuple[str, str] | None:
    m = _LABEL_START.fullmatch(s)
    return (m.group(1), m.group(2)) if m else None


def _split_natural(s: str) -> tuple[str, str] | None:
    """The cheapest break: both lines within the limit and close in length."""
    best = None
    best_cost = None
    for m in _SPACE_OUTSIDE_TAG.finditer(s):
        left, right = s[: m.start()], s[m.end() :]
        a, b = _visible(left), _visible(right)
        if not a or not b:
            continue
        cost = abs(len(a) - len(b))
        if max(len(a), len(b)) > MAX_LINE_LENGTH:
            cost += 1000
        last, first = a.split()[-1], b.split()[0]
        if a[-1] in ",.;:!?…":
            cost -= 25
        elif last[0].isupper() and first[0].isupper():
            cost += 60
        if last.lower() in _NO_BREAK_AFTER:
            cost += 15
        if last[-1].isdigit():
            cost += 30
        if first in ("-", "–", "—", "♪"):
            cost += 30
        if best_cost is None or cost < best_cost:
            best, best_cost = (left.strip(), right.strip()), cost
    return best


def restore_line_break(text: str, source_lines: Sequence[str] = ()) -> str:
    """Lay out one translated line from the source cue's lines. The words never change."""
    if "\n" in text:
        return text
    prefix, core, suffix = _strip_wrap_tags(text)
    result = None
    if len(source_lines) == 2:
        if all(_SPEAKER_DASH.match(line) for line in source_lines):
            result = _split_dash(core)
        elif _LABEL.fullmatch(source_lines[0]):
            result = _split_label(core)
    if result is None:
        if len(_visible(text)) <= MAX_LINE_LENGTH:
            return text
        result = _split_natural(core)
    if result is None:
        return text
    return f"{prefix}{result[0]}\n{result[1]}{suffix}"
```

- [ ] **Step 5: Update `write_srt`**

Add `_CURLY_QUOTES = re.compile("[„“”]")` at module level. For every subtitle: `text = _CURLY_QUOTES.sub('"', subtitle.translated_text or subtitle.text)`, then `text = restore_line_break(text, subtitle.source_lines)`. The `open(..., encoding="utf-8-sig")` line does not change.

- [ ] **Step 6: Run all offline tests and the self-check**

Run: `uv run pytest -q -m "not integration" && uv run python -m mkv_subtitle_translator.linebreak`
Expected: all pass, then `linebreak self-check OK`.

- [ ] **Step 7: Commit**

```bash
git add src/mkv_subtitle_translator/models.py src/mkv_subtitle_translator/linebreak.py src/mkv_subtitle_translator/translator.py tests/test_linebreak.py tests/test_translator.py
git commit -m "Place subtitle line breaks from the source layout"
```

---

### Task 2: Batch prompt with term sheet and context

**Files:**
- Create: `src/mkv_subtitle_translator/prompts.py`
- Modify: `src/mkv_subtitle_translator/translator.py:231-354`
- Test: `tests/test_prompts.py`, `tests/test_translator.py`

**Interfaces:**
- Produces: `BATCH_SYSTEM_PROMPT: str`, `numbered(subtitles: list[Subtitle]) -> str`, `batch_prompt(source_name: str, term_sheet: str, before: list[Subtitle], batch: list[Subtitle], after: list[Subtitle]) -> str`, `_parse_numbered(text: str) -> dict[str, str]` in `translator.py`, and keyword-only `source_name: str = ""`, `term_sheet: str = ""` on `translate_subtitles` and `_batch_translate`

- [ ] **Step 1: Write the failing tests**

`tests/test_prompts.py`:

```python
from mkv_subtitle_translator.models import Subtitle
from mkv_subtitle_translator.prompts import BATCH_SYSTEM_PROMPT, batch_prompt


def _subs(*numbers):
    return [Subtitle(index=str(n), timestamp="t", text=f"Line {n}") for n in numbers]


def test_keeps_the_ten_rules_and_adds_two():
    assert "10. Preserve any formatting (italics, dashes for speaker changes)" in BATCH_SYSTEM_PROMPT
    assert "11. Use the names, terms and sina or teie from the term sheet." in BATCH_SYSTEM_PROMPT
    assert '12. Lines under "Context only" are for understanding.' in BATCH_SYSTEM_PROMPT


def test_has_no_layout_rules():
    assert "42" not in BATCH_SYSTEM_PROMPT
    assert "line break" not in BATCH_SYSTEM_PROMPT.lower()


def test_orders_sheet_context_and_batch():
    prompt = batch_prompt("show.srt", "Code -> kood", _subs(1), _subs(2, 3), _subs(4))
    assert prompt == (
        "Source file: show.srt\n\n"
        "Term sheet:\nCode -> kood\n\n"
        "Context only, earlier subtitles:\n[1] Line 1\n\n"
        "Translate all 2 subtitles below to Estonian. "
        "Return each line as [number] Estonian translation.\n\n[2] Line 2\n[3] Line 3\n\n"
        "Context only, later subtitles:\n[4] Line 4"
    )


def test_leaves_out_empty_sections():
    prompt = batch_prompt("show.srt", "", [], _subs(1), [])
    assert "Term sheet" not in prompt
    assert "Context only" not in prompt
```

In `tests/test_translator.py`, class `TestBatchTranslate`:

```python
def test_each_batch_gets_english_neighbours_and_the_sheet(self, mocker):
    translator = OpenRouterTranslator("", "codex")
    subtitles = [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in range(1, 16)]
    translate = mocker.patch.object(translator.client, "translate", return_value=("[6] Rida", 0, 0))

    translator.translate_subtitles(
        subtitles, chunk_size=5, source_name="show.srt", term_sheet="Code -> kood"
    )

    prompt = translate.call_args_list[1].args[1]
    assert "Term sheet:\nCode -> kood" in prompt
    assert "earlier subtitles:\n[1] Line 1\n[2] Line 2\n[3] Line 3\n[4] Line 4\n[5] Line 5" in prompt
    assert "later subtitles:\n[11] Line 11\n[12] Line 12\n[13] Line 13\n[14] Line 14\n[15] Line 15" in prompt

def test_context_cue_returned_by_the_model_is_ignored(self, mocker):
    translator = OpenRouterTranslator("", "codex")
    subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in (1, 2)]
    mocker.patch.object(
        translator.client,
        "translate",
        side_effect=[("[1] Üks\n[2] Vale", 0, 0), ("[2] Kaks", 0, 0)],
    )

    translator.translate_subtitles(subtitles, chunk_size=1)

    assert [s.translated_text for s in subtitles] == ["Üks", "Kaks"]
    assert translator.stats.completed == 2
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_prompts.py tests/test_translator.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mkv_subtitle_translator.prompts'`.

- [ ] **Step 3: Create `prompts.py`**

Move the system prompt out of `_translate_batches` as `BATCH_SYSTEM_PROMPT`, with rules 1 to 10 word for word, then append exactly:

```text
11. Use the names, terms and sina or teie from the term sheet.
12. Lines under "Context only" are for understanding. Do not return them.
```

`numbered(subtitles)` returns one `[index] text` line per subtitle. `batch_prompt` joins its sections with a blank line, in the order the test shows, and leaves out a section that is empty. The source text is `sub.text`, joined on one line as `read_srt` leaves it.

- [ ] **Step 4: Use the prompt in `_translate_batches`**

- Extract the `[number]` parser into module-level `_parse_numbered(text) -> dict[str, str]`, keeping `strip_wrapping_quotes`.
- A batch at position `start` gets `before = subtitles[max(0, start - self.context_window_size) : start]` and `after = subtitles[start + len(batch) : start + len(batch) + self.context_window_size]`, so `_translate_batches` needs `subtitles` and `batch_size`.
- `translate_subtitles` and `_batch_translate` pass `source_name` and `term_sheet` through. The per-line path ignores both.

- [ ] **Step 5: Run all offline tests**

Run: `uv run pytest -q -m "not integration"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mkv_subtitle_translator/prompts.py src/mkv_subtitle_translator/translator.py tests/test_prompts.py tests/test_translator.py
git commit -m "Give each batch English context and a term sheet"
```

---

### Task 3: Five calls at a time

**Files:**
- Modify: `src/mkv_subtitle_translator/progress.py`
- Modify: `src/mkv_subtitle_translator/backends.py:13-24`, `:217-250`
- Modify: `src/mkv_subtitle_translator/translator.py` (`_translate_batches`)
- Modify: `README.md` (Translation progress section)
- Test: `tests/test_progress.py`, `tests/test_backends.py`, `tests/test_translator.py`

**Interfaces:**
- Consumes: `batch_prompt`, `_parse_numbered` from Task 2
- Produces: `CLI_WORKERS = 5` in `backends.py`, `BatchProgress(total: int, batches: int, *, stage: str = "Translating", label: str = "Batch", done: str = "translated")`, `report(number: int, message: str)`, `finish_batch(number: int, completed: int, failed: int)`, `OpenRouterTranslator._run_batches(batches, call, finish) -> None` where `call(number, batch)` runs on a worker and `finish(number, batch, future)` runs on the caller's thread

- [ ] **Step 1: Write the failing tests**

`tests/test_progress.py`: pass the batch number to every `report` and `finish_batch` call (`display.report(1, ...)`, `display.finish_batch(1, 198, 2)`), then add:

```python
def test_counts_finished_and_running_batches(mocker):
    from mkv_subtitle_translator import progress

    stream = ObservedStream()
    mocker.patch.object(progress.sys, "stderr", stream)

    with progress.BatchProgress(total=2, batches=2) as display:
        display.start_batch(1, ("1", "1"), 1, "Test model")
        display.start_batch(2, ("2", "2"), 1, "Test model")
        display.finish_batch(2, 1, 0)
        display.report(1, "Waiting")
        display.finish_batch(1, 1, 0)

    output = stream.getvalue()
    assert "0/2 batches done, 2 running" in output
    assert "1/2 batches done, 1 running" in output
    assert "Batch 2/2 finished" in output


def test_a_stage_can_rename_what_it_counts(mocker):
    from mkv_subtitle_translator import progress

    stream = ObservedStream()
    mocker.patch.object(progress.sys, "stderr", stream)

    with progress.BatchProgress(
        total=3, batches=1, stage="Checking", label="Check", done="checked"
    ) as display:
        display.start_batch(1, ("1", "3"), 3, "Test model")
        display.finish_batch(1, 3, 0)

    assert "Check 1/1" in stream.getvalue()
    assert "3/3 processed; 3 checked, 0 failed" in stream.getvalue()
```

`tests/test_backends.py`, class `TestFallbackClient`:

```python
def test_two_calls_failing_together_advance_the_chain_once(self):
    barrier = threading.Barrier(2)

    class Dry(_StubClient):
        def translate(self, *args, **kwargs):
            barrier.wait(timeout=5)
            return super().translate(*args, **kwargs)

    first, second, third = Dry("first"), _StubClient("second", "Tere"), _StubClient("third", "Vale")
    chain = FallbackClient([first, second, third])

    with ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda _: chain.translate("s", "u"), range(2)))

    assert [reply[0] for reply in replies] == ["Tere", "Tere"]
    assert chain.clients == [second, third]

def test_api_backend_reached_by_the_chain_runs_one_call_at_a_time(self, mocker):
    api = OpenRouterClient("sk-key", "gpt-5.6-sol")
    lock = threading.Lock()
    running = peak = 0

    def translate(*args, **kwargs):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with lock:
            running -= 1
        return "Tere", 1, 1

    mocker.patch.object(api, "translate", side_effect=translate)
    chain = FallbackClient([api])

    with ThreadPoolExecutor(5) as pool:
        list(pool.map(lambda _: chain.translate("s", "u"), range(5)))

    assert peak == 1
```

`tests/test_translator.py`: add an autouse fixture to `TestBatchTranslate` that does `mocker.patch("mkv_subtitle_translator.translator.CLI_WORKERS", 1)`, so its call-order assertions stay valid. Then add:

```python
class TestParallelBatches:
    def test_runs_five_calls_at_once_on_a_cli_backend(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 6)]
        barrier = threading.Barrier(5)

        def translate(system, user, **kwargs):
            barrier.wait(timeout=5)  # breaks unless all five are in flight together
            return "\n".join(f"[{i}] Tere" for i in range(1, 6)), 0, 0

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert translator.stats.completed == 5

    def test_calls_the_api_one_at_a_time(self, mocker):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 4)]
        lock = threading.Lock()
        running = peak = 0

        def translate(system, user, **kwargs):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return "\n".join(f"[{i}] Tere" for i in range(1, 4)), 1, 1

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert peak == 1
        assert translator.stats.input_tokens == 3

    def test_each_batch_keeps_its_own_text_when_a_later_batch_finishes_first(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in (1, 2)]
        second_done = threading.Event()

        def translate(system, user, **kwargs):
            if "Estonian translation.\n\n[2] Line 2" in user:
                second_done.set()
                return "[2] Kaks", 0, 0
            assert second_done.wait(5)
            return "[1] Üks", 0, 0

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert [s.translated_text for s in subtitles] == ["Üks", "Kaks"]

    @pytest.mark.parametrize("error", [QuotaExhausted("dry"), KeyboardInterrupt()])
    def test_a_stop_cancels_calls_not_yet_started(self, mocker, error):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 13)]
        first = threading.Lock()

        def translate(system, user, **kwargs):
            if first.acquire(blocking=False):
                raise error
            time.sleep(0.05)
            return "", 0, 0

        translate_mock = mocker.patch.object(translator.client, "translate", side_effect=translate)

        with pytest.raises(type(error)):
            translator.translate_subtitles(subtitles, chunk_size=1)

        assert translate_mock.call_count < 12
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_progress.py tests/test_backends.py tests/test_translator.py -q`
Expected: FAIL. `report` and `finish_batch` take no number, and `CLI_WORKERS` does not exist.

- [ ] **Step 3: Update `BatchProgress`**

- Replace `_active`, `_number` and the per-batch `_started` with `_running: dict[int, float]` (batch number to its start time), `_finished: int`, and a stage `_started` set in `__init__`.
- `stage` is the tqdm description, `label` starts every message (`{label} {number}/{batches}: ...`), and `done` replaces the word `translated` in `_counts` and `finish_batch`.
- The status line is `{finished}/{batches} batches done, {running} running | {elapsed since stage start} elapsed | {status}`.
- The heartbeat refreshes while `_running` is not empty.
- `finished in` uses that batch's own start time.

- [ ] **Step 4: Make `FallbackClient` thread-safe**

Add `CLI_WORKERS = 5` beside `DEFAULT_BATCH_SIZE`. Add `self._lock` and `self._api_lock` (`threading.Lock()`) to `__init__`.

```python
while True:
    client = self.clients[0]
    try:
        if isinstance(client, OpenRouterClient):
            with self._api_lock:
                return client.translate(*args, **kwargs)
        return client.translate(*args, **kwargs)
    except QuotaExhausted:
        with self._lock:
            # Another call that failed at the same time may already have moved on.
            if self.clients[0] is client:
                if len(self.clients) == 1:
                    raise
                self.clients.pop(0)
                # existing switch message, unchanged
```

- [ ] **Step 5: Add `_run_batches` and split `_translate_batches`**

```python
def _run_batches(self, batches, call, finish) -> None:
    """Run call(number, batch) on workers, 5 at a time on a CLI backend, and
    finish(number, batch, future) here. Only this thread touches self.stats.
    Any exception, Ctrl+C included, cancels what has not started."""
    workers = CLI_WORKERS if uses_cli(self.model) else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(call, number, batch): (number, batch)
            for number, batch in enumerate(batches, 1)
        }
        try:
            for future in concurrent.futures.as_completed(futures):
                finish(*futures[future], future)
        except BaseException:
            for future in futures:
                future.cancel()
            raise
```

In `_translate_batches`:

- `call` does `progress.start_batch`, builds the prompt and returns `self.client.translate(...)`, with `progress=functools.partial(progress.report, number)`.
- `finish` calls `future.result()`, re-raises `QuotaExhausted`, reports other exceptions as `Error: {e}` and keeps the English for that batch, applies translations, updates `self.stats`, and calls `progress.finish_batch(number, completed, failed)`.

Keep today's counting and fallback rules.

- [ ] **Step 6: Update the README**

Translation progress section: batches run five at a time on the `codex` and `claude` models, the example status reads `Translating:   0%|          | 0/964, 0/5 batches done, 5 running | 01:05 elapsed | Waiting for Codex response (max effort; timeout 30m per call)`, and the timer is per stage.

- [ ] **Step 7: Run all offline tests**

Run: `uv run pytest -q -m "not integration"`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/mkv_subtitle_translator/progress.py src/mkv_subtitle_translator/backends.py src/mkv_subtitle_translator/translator.py README.md tests/test_progress.py tests/test_backends.py tests/test_translator.py
git commit -m "Translate five batches at a time on CLI backends"
```

---

### Task 4: Term sheet

**Files:**
- Modify: `src/mkv_subtitle_translator/prompts.py`
- Modify: `src/mkv_subtitle_translator/backends.py`, `src/mkv_subtitle_translator/client.py`
- Modify: `src/mkv_subtitle_translator/translator.py`
- Modify: `src/mkv_subtitle_translator/cli.py:122-164`, `:313-323`
- Modify: `README.md`
- Test: `tests/test_translator.py`, `tests/test_backends.py`, `tests/test_client.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `BatchProgress` with `stage`, `label` and `done` from Task 3
- Produces: `TERM_SHEET_SYSTEM_PROMPT: str`, `term_sheet_prompt(source_name: str, subtitles: list[Subtitle], references: list[str]) -> str`, `terms_path(output_path: str) -> str`, `OpenRouterTranslator.translate_file(subtitles: list[Subtitle], output_path: str, *, source_name: str, references: Sequence[str] = (), chunk_size: int | None = None, max_workers: int = 8) -> None`, `_term_sheet(subtitles, source_name, output_path, references) -> str`, `_chunk_size(chunk_size: int | None) -> int`, keyword-only `effort: str | None = None` on every client `translate`, `cli._estimated_tokens(cues: int, model: str) -> tuple[int, int]`

- [ ] **Step 1: Write the failing tests**

`tests/test_translator.py`, a shared fake backend and a new class:

```python
def _backend(sheet="Code -> kood", tokens=(0, 0)):
    """Answer each stage's prompt. Pass an exception as sheet to fail that stage."""

    def translate(system, user, **kwargs):
        if system == TERM_SHEET_SYSTEM_PROMPT:
            if isinstance(sheet, BaseException):
                raise sheet
            return (sheet, *tokens)
        block = user.split("Estonian translation.\n\n")[1].split("\n\nContext only")[0]
        numbers = re.findall(r"^\[(\d+)\]", block, re.M)
        return ("\n".join(f"[{n}] Tere" for n in numbers), *tokens)

    return translate


def _cues(count=3):
    return [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in range(1, count + 1)]


class TestTermSheet:
    def test_is_saved_and_reaches_every_batch(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert (tmp_path / "show.et.terms.md").read_text(encoding="utf-8").strip() == "Code -> kood"
        calls = translate.call_args_list
        batch_prompts = [c.args[1] for c in calls if c.args[0] == BATCH_SYSTEM_PROMPT]
        assert len(batch_prompts) == 3
        assert all("Term sheet:\nCode -> kood" in prompt for prompt in batch_prompts)
        assert out.exists()

    def test_call_reads_the_whole_source_at_high_effort(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex", "max")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        sheet_call = translate.call_args_list[0]
        assert "Source file: show.srt" in sheet_call.args[1]
        assert "[1] Line 1\n[2] Line 2\n[3] Line 3" in sheet_call.args[1]
        assert sheet_call.kwargs["effort"] == "high"
        assert sheet_call.kwargs["max_tokens"] == 8000
        assert "effort" not in translate.call_args_list[1].kwargs

    def test_existing_sheet_is_reused_and_named(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        (tmp_path / "show.et.terms.md").write_text("Code -> seadus\n", encoding="utf-8")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert all(c.args[0] != TERM_SHEET_SYSTEM_PROMPT for c in translate.call_args_list)
        assert "Term sheet:\nCode -> seadus" in translate.call_args.args[1]
        assert "Reusing term sheet" in capsys.readouterr().out

    def test_failed_call_warns_and_continues_without_a_sheet(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(
            translator.client, "translate", side_effect=_backend(RuntimeError("offline"))
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert "Term sheet:" not in translate.call_args.args[1]
        assert "continuing without" in capsys.readouterr().out
        assert out.exists()
        assert not (tmp_path / "show.et.terms.md").exists()

    def test_quota_raises_and_writes_nothing(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(QuotaExhausted("dry"))
        )
        out = tmp_path / "show.et.srt"

        with pytest.raises(QuotaExhausted):
            translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert not out.exists()

    def test_per_line_models_get_no_sheet(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        translate = mocker.patch.object(
            translator.client, "translate", return_value=("Tere", 1, 1)
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert translate.call_count == 1
        assert not (tmp_path / "show.et.terms.md").exists()
        assert "Tere" in out.read_text(encoding="utf-8-sig")

    def test_no_cues_makes_no_call_and_writes_an_empty_file(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate")
        out = tmp_path / "show.et.srt"

        translator.translate_file([], str(out), source_name="show.srt")

        translate.assert_not_called()
        assert out.read_bytes() == b""

    def test_stats_cover_the_sheet_and_start_fresh_for_each_file(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(tokens=(10, 1))
        )

        for name in ("one", "two"):
            translator.translate_file(
                _cues(1), str(tmp_path / f"{name}.et.srt"), source_name=f"{name}.srt"
            )

        assert translator.stats.input_tokens == 20
        assert translator.stats.total_subtitles == 1
```

`tests/test_backends.py`:

```python
def test_a_call_can_override_the_codex_effort(self, mocker):
    run = mocker.patch("mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_run())
    messages = []

    CodexClient(effort="max").translate("s", "u", progress=messages.append, effort="high")

    assert "model_reasoning_effort=high" in run.call_args.args[0]
    assert "high effort" in messages[0]

def test_claude_accepts_and_ignores_effort(self, mocker):
    run = mocker.patch(
        "mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_claude_run()
    )

    ClaudeClient().translate("s", "u", effort="high")

    command = run.call_args.args[0]
    assert command[command.index("--effort") + 1] == "max"
```

`tests/test_client.py`: `OpenRouterClient.translate("s", "u", effort="high")` succeeds, using `mock_transport`.

`tests/test_cli.py`:

```python
def test_estimate_adds_the_term_sheet_for_batch_models_only():
    from mkv_subtitle_translator.cli import _estimated_tokens

    assert _estimated_tokens(964, "gpt-5.4-pro") == (144_600, 28_920)
    assert _estimated_tokens(964, "gpt-5.6-sol") == (156_168, 29_920)


def test_translates_through_translate_file(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "codex"])

    assert result.exit_code == 0
    assert translate_file.call_args.args[1] == str(tmp_path / "show.et.srt")
    assert translate_file.call_args.kwargs["source_name"] == "show.extracted.srt"
```

Add `import re` and imports of `BATCH_SYSTEM_PROMPT` and `TERM_SHEET_SYSTEM_PROMPT` to `tests/test_translator.py`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_translator.py tests/test_backends.py tests/test_client.py tests/test_cli.py -q`
Expected: FAIL. `translate_file` and the `effort` keyword do not exist.

- [ ] **Step 3: Add the prompt**

Exact text, tested on two titles. The instructions are the system prompt and the data is the user prompt.

```python
TERM_SHEET_SYSTEM_PROMPT = """You are preparing a short term sheet for an English to Estonian \
subtitle translator. The translator works in separate batches with no memory, so this sheet is \
the only thing the batches share.

Read the whole episode and return plain text with these sections:
SETTING: two sentences on where and when.
CHARACTERS: who they are and who says sina or teie to whom.
NAMES AND TITLES: one fixed Estonian form for each nickname and title that needs translating, \
with its genitive and partitive where these are not obvious.
RECURRING TERMS: English word or short phrase used more than once in the episode as a fixed \
term, insult or catchphrase -> one Estonian wording.

Do not quote or suggest translations of whole lines. Do not cover song lyrics or sound labels. \
Keep it under 400 words. No preamble."""
```

`term_sheet_prompt` returns `Source file: {source_name}`, then a reference block when `references` is not empty (Task 5 fills it, so here it stays empty), then `English episode:\n{numbered(subtitles)}`, with sections separated by blank lines.

- [ ] **Step 4: Add per-call effort**

`translate(..., *, progress=None, effort=None)` on `CodexClient`, `ClaudeClient` and `OpenRouterClient`. Codex uses `effort or self.effort` in both the command and the waiting message. The other two ignore it, because neither has a per-call setting that this design uses. `FallbackClient` forwards it through `**kwargs` with no change.

- [ ] **Step 5: Add `translate_file` and `_term_sheet`**

Module-level in `translator.py`: `TERM_SHEET_EFFORT = "high"`, `TERM_SHEET_MAX_TOKENS = 8000`, and `terms_path(output_path)`, which returns `output_path.removesuffix(".et.srt") + ".et.terms.md"`. `_chunk_size(chunk_size)` holds the default that `translate_subtitles` picks today.

`translate_file`, in order:

1. Reset `self.stats` with `total_subtitles` and `start_time`. Both resets leave `_batch_translate` and the per-line branch of `translate_subtitles`.
2. `batch_mode = bool(subtitles) and bool(self.client.model_config.get("supports_batch"))`.
3. `term_sheet = self._term_sheet(...) if batch_mode else ""`.
4. `self.translate_subtitles(subtitles, chunk_size, max_workers, source_name=source_name, term_sheet=term_sheet)`.
5. `self.write_srt(subtitles, output_path)`.
6. Set `end_time` and `estimated_cost`, then `self._print_stats()`. These three also leave `_batch_translate` and the per-line branch.

`_term_sheet`:

1. If `terms_path` exists, read it as UTF-8, print `Reusing term sheet: {path}`, and return it stripped.
2. Otherwise open `BatchProgress(total=1, batches=1, stage="Term sheet", label="Term sheet", done="written")`, `start_batch(1, (first, last), len(subtitles), model name)`, and call `self.client.translate(TERM_SHEET_SYSTEM_PROMPT, prompt, max_tokens=TERM_SHEET_MAX_TOKENS, effort=TERM_SHEET_EFFORT, progress=partial(progress.report, 1))` with `prompt = term_sheet_prompt(source_name, subtitles, [])`. Task 5 replaces `[]` with the reference texts.
3. `QuotaExhausted` raises. Any other `Exception` calls `finish_batch(1, 0, 1)`, prints `Term sheet failed, continuing without one: {e}`, and returns `""`.
4. On success add the tokens to `self.stats`, `finish_batch(1, 1, 0)`, write the text plus a newline as UTF-8, print `Term sheet saved: {path}`, and return it.

- [ ] **Step 6: Wire the CLI and `--estimate`**

In `_main`, replace `translate_subtitles` and `write_srt` with one `translator.translate_file(subtitles, output_file, source_name=Path(input_file).name, chunk_size=chunk_size, max_workers=max_workers)` inside the existing `try`. The `QuotaExhausted` handling stays.

Add `SHEET_INPUT_PER_CUE = 12` and `SHEET_OUTPUT_TOKENS = 1_000`. `_estimated_tokens(cues, model)` starts from `cues * 150` in and `cues * 30` out, and adds the sheet when the model has `supports_batch`. `estimate_cost` uses it for the chosen model and for each row of the comparison table.

- [ ] **Step 7: Update the README**

Cover: the term sheet runs first on batch models, it is saved as `<name>.et.terms.md` next to the output, an existing sheet is reused, and you can fix a wrong term there and re-run with `--force`.

- [ ] **Step 8: Run all offline tests**

Run: `uv run pytest -q -m "not integration"`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/mkv_subtitle_translator/prompts.py src/mkv_subtitle_translator/backends.py src/mkv_subtitle_translator/client.py src/mkv_subtitle_translator/translator.py src/mkv_subtitle_translator/cli.py README.md tests/test_translator.py tests/test_backends.py tests/test_client.py tests/test_cli.py
git commit -m "Share a term sheet across translation batches"
```

---

### Task 5: Reference subtitles

**Files:**
- Modify: `src/mkv_subtitle_translator/prompts.py` (`term_sheet_prompt`)
- Modify: `src/mkv_subtitle_translator/translator.py`
- Modify: `src/mkv_subtitle_translator/cli.py`
- Modify: `README.md`
- Test: `tests/test_translator.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `translate_file`, `_term_sheet`, `term_sheet_prompt` from Task 4
- Produces: `read_reference(path: str) -> str`, CLI option `--reference FILE` (repeatable)

- [ ] **Step 1: Write the failing tests**

`tests/test_translator.py`:

```python
class TestReference:
    def test_reads_windows_1252_and_drops_numbers_and_timing(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_bytes("1\r\n00:00:01,000 --> 00:00:02,000\r\nTüdruk õues\r\n".encode("cp1252"))
        assert read_reference(str(path)) == "Tüdruk õues"

    def test_reads_utf8_with_bom(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_text("1\n00:00:01,000 --> 00:00:02,000\nTüdruk\n", encoding="utf-8-sig")
        assert read_reference(str(path)) == "Tüdruk"

    def test_an_undefined_byte_does_not_stop_the_run(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_bytes(b"T\xfcdruk \x81")
        assert read_reference(str(path)).startswith("Tüdruk")

    def test_reaches_only_the_sheet_prompt(self, mocker, tmp_path):
        reference = tmp_path / "old.srt"
        reference.write_text("Tume Reisija", encoding="utf-8")
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(reference)],
        )

        first, *rest = [c.args[1] for c in translate.call_args_list]
        assert "Earlier Estonian subtitles" in first and "Tume Reisija" in first
        assert rest and all("Tume Reisija" not in prompt for prompt in rest)

    def test_is_not_read_when_a_sheet_exists_and_the_run_says_so(self, mocker, tmp_path, capsys):
        (tmp_path / "show.et.terms.md").write_text("Code -> kood\n", encoding="utf-8")
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(tmp_path / "gone.srt")],
        )

        assert "not read" in capsys.readouterr().out

    def test_per_line_models_say_it_was_ignored(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        mocker.patch.object(translator.client, "translate", return_value=("Tere", 1, 1))

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(tmp_path / "old.srt")],
        )

        assert "--reference" in capsys.readouterr().out
```

`tests/test_cli.py`:

```python
def test_missing_reference_file_is_rejected():
    result = runner.invoke(app, ["--reference", "/no/such/file.srt", "--list-models"])
    assert result.exit_code != 0


def test_reference_files_reach_translate_file(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
    one, two = tmp_path / "one.srt", tmp_path / "two.srt"
    one.touch()
    two.touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    args = ["-f", str(srt), "--reference", str(one), "--reference", str(two)]
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert translate_file.call_args.kwargs["references"] == [str(one), str(two)]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_translator.py tests/test_cli.py -q`
Expected: FAIL with `ImportError: cannot import name 'read_reference'`.

- [ ] **Step 3: Implement `read_reference`**

Decode with `utf-8-sig`. On `UnicodeDecodeError` decode with `cp1252, errors="replace"`. Drop blank lines, lines that are only digits, and lines containing `-->`. Join what is left with newlines. `read_srt` and `write_srt` are not touched.

- [ ] **Step 4: Add references to the sheet**

In `term_sheet_prompt`, when `references` is not empty, add this block between the source file and the English, with the texts joined by a blank line:

```text
Earlier Estonian subtitles from the same series follow. Reuse their established names and series terms. Ignore their style, line breaks and typos.

{references}
```

In `_term_sheet`, read references only after the reuse check. When a sheet is reused and `references` is not empty, also print `--reference files were not read because the term sheet already exists`. In `translate_file`, when the model has no batch support and `references` is not empty, print `--reference needs a batch model and was ignored`.

- [ ] **Step 5: Add the CLI option**

```python
reference: Annotated[
    list[Path] | None,
    typer.Option(
        "--reference",
        exists=True,
        dir_okay=False,
        help="Earlier Estonian subtitles for names and series terms (repeatable)",
    ),
] = None,
```

Pass `references=[str(path) for path in reference or []]` to `translate_file`.

- [ ] **Step 6: Update the README**

Add the option to the Options table and a usage example. Say that it helps series terms, not style, that one earlier episode is enough, and that only the term sheet call reads it.

- [ ] **Step 7: Run all offline tests**

Run: `uv run pytest -q -m "not integration"`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/mkv_subtitle_translator/prompts.py src/mkv_subtitle_translator/translator.py src/mkv_subtitle_translator/cli.py README.md tests/test_translator.py tests/test_cli.py
git commit -m "Add --reference for earlier Estonian subtitles"
```

---

### Task 6: Error check

Keep this whole task in one commit, including its README and `--estimate` lines, so it can be dropped alone.

**Files:**
- Modify: `src/mkv_subtitle_translator/prompts.py`
- Modify: `src/mkv_subtitle_translator/translator.py`
- Modify: `src/mkv_subtitle_translator/cli.py` (`_estimated_tokens`)
- Modify: `README.md`
- Test: `tests/test_prompts.py`, `tests/test_translator.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `_run_batches`, `_parse_numbered`, `numbered`, `translate_file`, `BatchProgress`
- Produces: `CHECK_SYSTEM_PROMPT: str`, `check_prompt(source_name: str, term_sheet: str, subtitles: list[Subtitle], batch: list[Subtitle]) -> str`, `_check_errors(subtitles, source_name, term_sheet, batch_size) -> int` returning the number of corrected cues

- [ ] **Step 1: Write the failing tests**

`tests/test_prompts.py`:

```python
def test_check_prompt_carries_the_whole_title_and_the_range():
    subs = _subs(1, 2, 3)
    for sub in subs:
        sub.translated_text = f"Rida {sub.index}"

    prompt = check_prompt("show.srt", "Code -> kood", subs, subs[1:2])

    assert "Term sheet:\nCode -> kood" in prompt
    assert "Complete English source:\n[1] Line 1\n[2] Line 2\n[3] Line 3" in prompt
    assert "Complete Estonian translation:\n[1] Rida 1\n[2] Rida 2\n[3] Rida 3" in prompt
    assert "Check subtitles [2] to [2]." in prompt
    assert "If none need correcting, return NONE." in prompt
```

`tests/test_translator.py`: change the expected input tokens in `test_stats_cover_the_sheet_and_start_fresh_for_each_file` from 20 to 30, import `CHECK_SYSTEM_PROMPT`, and replace `_backend`:

```python
def _backend(sheet="Code -> kood", check="NONE", tokens=(0, 0)):
    """Answer each stage's prompt. A stage is a reply, a function of the prompt or an exception."""

    def answer(stage, user):
        if isinstance(stage, BaseException):
            raise stage
        return (stage(user) if callable(stage) else stage, *tokens)

    def translate(system, user, **kwargs):
        if system == TERM_SHEET_SYSTEM_PROMPT:
            return answer(sheet, user)
        if system == CHECK_SYSTEM_PROMPT:
            return answer(check, user)
        block = user.split("Estonian translation.\n\n")[1].split("\n\nContext only")[0]
        numbers = re.findall(r"^\[(\d+)\]", block, re.M)
        return ("\n".join(f"[{n}] Tere" for n in numbers), *tokens)

    return translate
```

Then add:

```python
class TestErrorCheck:
    def test_corrections_reach_the_final_file(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(check="[2] Parandatud")
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert "Parandatud" in out.read_text(encoding="utf-8-sig")
        output = capsys.readouterr().out
        assert "#2" in output and "Tere" in output and "Parandatud" in output

    def test_none_changes_nothing_and_writes_once(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend())
        write = mocker.spy(translator, "write_srt")

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert write.call_count == 1

    def test_same_text_is_not_a_correction(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend(check="[2] Tere"))
        write = mocker.spy(translator, "write_srt")

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert write.call_count == 1

    def test_cue_outside_the_batch_is_not_applied(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        replies = {"[1] to [1]": "[2] Vale", "[2] to [2]": "NONE", "[3] to [3]": "NONE"}

        def check(user):
            return next(reply for key, reply in replies.items() if key in user)

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert "Vale" not in out.read_text(encoding="utf-8-sig")

    def test_output_exists_before_the_first_check_call(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        out = tmp_path / "show.et.srt"
        seen = []

        def check(user):
            seen.append(out.exists())
            return "NONE"

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert seen == [True]

    def test_batch_error_keeps_that_batch_and_is_counted(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")

        def check(user):
            if "[1] to [1]" in user:
                raise RuntimeError("offline")
            return "[2] Parandatud" if "[2] to [2]" in user else "NONE"

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert "Parandatud" in out.read_text(encoding="utf-8-sig")
        assert "1 of 3 batches could not be checked" in capsys.readouterr().out

    def test_quota_stops_the_check_and_keeps_the_output(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(check=QuotaExhausted("dry"))
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert "Tere" in out.read_text(encoding="utf-8-sig")
        assert "could not be checked" in capsys.readouterr().out

    def test_sheet_reaches_the_check_and_stats_include_it(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        translate = mocker.patch.object(
            translator.client, "translate", side_effect=_backend(tokens=(10, 1))
        )

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert "Term sheet:\nCode -> kood" in translate.call_args.args[1]
        assert translate.call_count == 3
        assert translator.stats.input_tokens == 30

    def test_per_line_models_get_no_check(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        translate = mocker.patch.object(
            translator.client, "translate", return_value=("Tere", 1, 1)
        )

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert translate.call_count == 1
```

`tests/test_cli.py`: change the batch-model assertion in `test_estimate_adds_the_term_sheet_for_batch_models_only` to `(638_168, 29_920)`, and add `assert _estimated_tokens(2_790, "gpt-5.6-sol")[0] == 4_357_980`, which is 418,500 for translation, 33,480 for the sheet and 3,906,000 (56 × 2,790 × 25) for the check.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_prompts.py tests/test_translator.py tests/test_cli.py -q`
Expected: FAIL with `ImportError: cannot import name 'CHECK_SYSTEM_PROMPT'`.

- [ ] **Step 3: Add the prompt**

Exact text, tested on two titles. `CHECK_SYSTEM_PROMPT` is the first paragraph and everything else is the user prompt.

```text
You are a senior Estonian subtitle reviser. You check a finished translation against the English source and correct real errors. You do not restyle correct lines.
```

`check_prompt` returns these sections, separated by blank lines. Leave out the term sheet section when the sheet is empty. Estonian text is `sub.translated_text or sub.text`.

```text
Source file: {source_name}

Term sheet:
{term_sheet}

Complete English source:
{every cue, numbered}

Complete Estonian translation:
{every cue, numbered}

Check subtitles [{first}] to [{last}]. A sentence may run across several subtitles, so read neighbouring subtitles together before deciding.

Correct a subtitle only if it has one of these:
- meaning that differs from the English: wrong person, number, negation, tense or sense, or something important left out
- a name or term that differs from the term sheet
- the wrong sina or teie
- an Estonian grammar or spelling error

Leave every other subtitle as it is. Do not improve style, change word choice or shorten.
Return only the subtitles you correct, as [number] text. If none need correcting, return NONE.
```

- [ ] **Step 4: Implement `_check_errors`**

- Same batch boundaries as translation, with `max_tokens=min(len(batch) * 80, max_output)` and `max_output` read as `_batch_translate` reads it.
- Open `BatchProgress(total=len(subtitles), batches=len(batches), stage="Checking", label="Check", done="checked")`.
- `call` does `start_batch` and returns `self.client.translate(CHECK_SYSTEM_PROMPT, check_prompt(...), max_tokens=..., progress=partial(progress.report, number))`, so the run's own `--effort` applies.
- `finish` re-raises `QuotaExhausted`. Another `Exception` reports `Error: {e}` and calls `finish_batch(number, 0, len(batch))`.
- On success, add the tokens to `self.stats`. For each cue in the batch with a non-empty reply that differs from its text, remember the old text and set `translated_text`. Count the batch as checked, then `finish_batch(number, len(batch), 0)`.
- Catch `QuotaExhausted` around `_run_batches`, inside the `with`, and print `Error check stopped: {e}`.

After the `with`, print `Error check corrected {n} subtitles:` and one `  #{index}: {old} -> {new}` line for each, in cue order. If some batches were not checked, print `{unchecked} of {len(batches)} batches could not be checked`. Return `n`.

In `translate_file`, resolve `chunk_size = self._chunk_size(chunk_size)` first, then after the first `write_srt`:

```python
if batch_mode and self._check_errors(subtitles, source_name, term_sheet, chunk_size):
    self.write_srt(subtitles, output_path)
```

- [ ] **Step 5: Extend `_estimated_tokens`**

Add `CHECK_INPUT_PER_CUE = 25`. For a batch model, add `math.ceil(cues / size) * cues * CHECK_INPUT_PER_CUE` to the input, where `size` is `DEFAULT_BATCH_SIZE` for a CLI model and `API_CHUNK_SIZE` otherwise. The check returns few lines, so it adds no output estimate.

- [ ] **Step 6: Update the README**

Cover: the check corrects meaning, names and terms, sina or teie, and grammar or spelling only, it prints each change, the output is written first so a failed check loses nothing, and a 964-cue episode takes about 11 minutes.

- [ ] **Step 7: Run all offline tests and Ruff**

Run: `uv run pytest -q -m "not integration" && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/mkv_subtitle_translator/prompts.py src/mkv_subtitle_translator/translator.py src/mkv_subtitle_translator/cli.py README.md tests/test_prompts.py tests/test_translator.py tests/test_cli.py
git commit -m "Add an error check after translation"
```

---

### Task 7: Real run and PR

The sample and reference paths come from the session, not from this file. Never commit them.

- [ ] **Step 1: Run on a copy, because `--force` would overwrite the real `.et.srt`**

```bash
RUN="$(mktemp -d)"
cp "$SAMPLE_EXTRACTED_SRT" "$RUN/sample.extracted.srt"
time uv run mkv-subtitle-translator -f "$RUN/sample.extracted.srt" --reference "$REFERENCE_SRT"
```

Expected: about 11 minutes and about 1 point of the weekly Codex limit. Note the time of each stage.

- [ ] **Step 2: Compare with the old output**

Check each line against the issue's Acceptance list:

- 964 cues with the same timings, UTF-8 with BOM.
- No character that the old `.et.srt` does not already contain.
- 0 broken two-speaker cues, 35 of 35 labels alone on line 1, 0 split names, and 0 lines over 42 characters outside two-speaker cues.
- One Estonian form for each recurring name and term, one quote style, and series terms that match the reference.
- At most 1 line changed by the check changes the meaning for the worse. Read every line it printed.

If the check changes meaning for the worse, fix the prompt once and re-run. If it fails again, revert the Task 6 commit and keep the rest.

- [ ] **Step 3: Open the PR**

Push `feat/translation-quality` and open a PR against `feat/live-translation-progress` that references #7 without closing it. Add the time per stage as a comment on #7.

- [ ] **Step 4: Stop**

Do not merge. An Estonian reader does the blind read and the Samsung TV check first, and merging to `main` ships a release.
