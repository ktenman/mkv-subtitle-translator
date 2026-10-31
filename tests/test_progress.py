from __future__ import annotations

import io
import threading
import time

import pytest

from mkv_subtitle_translator.backends import QuotaExhausted


class ObservedStream(io.StringIO):
    def __init__(self, terminal=False):
        super().__init__()
        self.terminal = terminal
        self.heartbeat = threading.Event()
        self.flushes = 0

    def isatty(self):
        return self.terminal

    def write(self, text):
        result = super().write(text)
        if "01:05 elapsed" in text:
            self.heartbeat.set()
        return result

    def flush(self):
        self.flushes += 1
        super().flush()


@pytest.mark.parametrize("terminal", [False, True])
def test_heartbeat_updates_elapsed_time_while_no_subtitles_finish(mocker, terminal):
    from mkv_subtitle_translator import progress

    stream = ObservedStream(terminal)
    now = [100.0]
    mocker.patch.object(progress.time, "monotonic", side_effect=lambda: now[0])
    mocker.patch.object(progress, "TERMINAL_INTERVAL", 0.01)
    mocker.patch.object(progress, "LOG_INTERVAL", 0.01)
    mocker.patch.object(progress.sys, "stderr", stream)

    with progress.BatchProgress(total=200, batches=1) as display:
        display.start_batch(1, ("1", "200"), 200, "Test model")
        display.report(1, "Waiting for response")
        now[0] = 165.0
        assert stream.heartbeat.wait(2), stream.getvalue()
        output = stream.getvalue()
        assert "Waiting for response" in output
        assert "0/200" in output
        assert stream.flushes > 0
        if not terminal:
            assert "\r" not in output and "\x1b" not in output
        display.finish_batch(1, 198, 2)

    assert "198 translated, 2 failed" in stream.getvalue()


@pytest.mark.parametrize("error", [None, KeyboardInterrupt, QuotaExhausted])
def test_stops_heartbeat_on_normal_exit_error_or_interrupt(mocker, error):
    from mkv_subtitle_translator import progress

    stream = ObservedStream()
    mocker.patch.object(progress.sys, "stderr", stream)

    def progress_threads():
        return {
            thread.ident
            for thread in threading.enumerate()
            if thread.name == "translation-progress"
        }

    before = progress_threads()

    def run():
        with progress.BatchProgress(total=1, batches=1) as display:
            display.start_batch(1, ("1", "1"), 1, "Test model")
            assert progress_threads() - before
            if error:
                raise error()
            display.finish_batch(1, 1, 0)

    if error:
        with pytest.raises(error):
            run()
        assert "1/1 processed" not in stream.getvalue()
    else:
        run()
    assert progress_threads() == before


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


def test_finish_time_is_per_batch_and_the_timer_is_per_stage(mocker):
    from mkv_subtitle_translator import progress

    stream = ObservedStream()
    now = [100.0]
    mocker.patch.object(progress.time, "monotonic", side_effect=lambda: now[0])
    mocker.patch.object(progress.sys, "stderr", stream)

    with progress.BatchProgress(total=2, batches=2) as display:
        display.start_batch(1, ("1", "1"), 1, "Test model")
        now[0] = 160.0
        display.start_batch(2, ("2", "2"), 1, "Test model")
        now[0] = 170.0
        display.finish_batch(2, 1, 0)
        display.report(1, "Waiting")
        display.finish_batch(1, 1, 0)

    output = stream.getvalue()
    assert "Batch 2/2 finished in 00:10" in output
    assert "Batch 1/2 finished in 01:10" in output
    assert "01:10 elapsed" in output


def test_heartbeat_stays_quiet_when_nothing_is_running(mocker):
    from mkv_subtitle_translator import progress

    stream = ObservedStream()
    mocker.patch.object(progress, "LOG_INTERVAL", 0.01)
    mocker.patch.object(progress.sys, "stderr", stream)

    with progress.BatchProgress(total=1, batches=1) as display:
        display.start_batch(1, ("1", "1"), 1, "Test model")
        display.finish_batch(1, 1, 0)
        written = stream.getvalue()
        time.sleep(0.05)
        assert stream.getvalue() == written
