from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

from tqdm import tqdm

ProgressCallback = Callable[[str], None]

TERMINAL_INTERVAL = 1.0
LOG_INTERVAL = 15.0


class BatchProgress:
    """Keep synchronous requests visible without guessing their completion rate."""

    def __init__(
        self,
        total: int,
        batches: int,
        *,
        stage: str = "Translating",
        label: str = "Batch",
        done: str = "translated",
    ):
        self.total = total
        self.batches = batches
        self.completed = 0
        self.failed = 0
        self._stage = stage
        self._label = label
        self._done = done
        self._stream = sys.stderr
        self._terminal = self._stream.isatty()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._running: dict[int, float] = {}
        self._finished = 0
        self._started = time.monotonic()
        self._status = ""
        self._bar = tqdm(
            total=total,
            desc=stage,
            unit="sub",
            file=self._stream,
            disable=not self._terminal,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar:10}| {n_fmt}/{total_fmt}{postfix}",
        )
        self._thread = threading.Thread(
            target=self._heartbeat, name="translation-progress", daemon=True
        )

    def __enter__(self) -> BatchProgress:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        self._thread.join()
        self._bar.close()
        if exc_type is not None:
            action = "interrupted" if issubclass(exc_type, KeyboardInterrupt) else "stopped"
            self._write(f"{self._stage} {action}; {self._counts()}")

    def _write(self, message: str) -> None:
        if self._terminal:
            tqdm.write(message, file=self._stream)
            self._stream.flush()
        else:
            print(message, file=self._stream, flush=True)

    def _elapsed(self, since: float) -> str:
        return tqdm.format_interval(max(0, time.monotonic() - since))

    def _counts(self) -> str:
        return (
            f"{self.completed + self.failed}/{self.total} processed; "
            f"{self.completed} {self._done}, {self.failed} failed"
        )

    def _refresh(self) -> None:
        status = (
            f"{self._finished}/{self.batches} batches done, {len(self._running)} running | "
            f"{self._elapsed(self._started)} elapsed | {self._status}"
        )
        if self._terminal:
            self._bar.set_postfix_str(status)
        else:
            self._write(f"{status} | {self._counts()}")

    def _heartbeat(self) -> None:
        interval = TERMINAL_INTERVAL if self._terminal else LOG_INTERVAL
        while not self._stop.wait(interval):
            with self._lock:
                if self._running:
                    self._refresh()

    def start_batch(self, number: int, indices: tuple[str, str], size: int, model: str) -> None:
        with self._lock:
            self._running[number] = time.monotonic()
            self._status = "Preparing request"
            self._write(
                f"{self._label} {number}/{self.batches}: subtitles {indices[0]}-{indices[1]} "
                f"({size} subtitles) | {model}"
            )
            self._refresh()

    def report(self, number: int, message: str) -> None:
        with self._lock:
            self._status = message
            if self._terminal:
                self._write(f"{self._label} {number}/{self.batches}: {message}")
            self._refresh()

    def finish_batch(self, number: int, completed: int, failed: int) -> None:
        with self._lock:
            self.completed += completed
            self.failed += failed
            started = self._running.pop(number)
            self._finished += 1
            self._status = f"{self.completed} {self._done}, {self.failed} failed"
            self._bar.update(completed + failed)
            if self._terminal:
                self._refresh()
            self._write(
                f"{self._label} {number}/{self.batches} finished in {self._elapsed(started)}: "
                f"{completed} {self._done}, {failed} failed | {self._counts()}"
            )
