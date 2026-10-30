from __future__ import annotations

import io
import threading

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
        display.report("Waiting for response")
        now[0] = 165.0
        assert stream.heartbeat.wait(2), stream.getvalue()
        output = stream.getvalue()
        assert "Waiting for response" in output
        assert "0/200" in output
        assert stream.flushes > 0
        if not terminal:
            assert "\r" not in output and "\x1b" not in output
        display.finish_batch(198, 2)

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
            display.finish_batch(1, 0)

    if error:
        with pytest.raises(error):
            run()
        assert "1/1 processed" not in stream.getvalue()
    else:
        run()
    assert progress_threads() == before
