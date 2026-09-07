from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .completion import FileCompletionValidator


class _Handler(FileSystemEventHandler):
    def __init__(self, submit: Callable[[str], None]):
        self.submit = submit

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.submit(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory and hasattr(event, "dest_path"):
            self.submit(event.dest_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.submit(event.src_path)


class FolderWatcher:
    def __init__(
        self,
        folder: str | Path,
        validator: FileCompletionValidator,
        on_complete: Callable[[Path], None],
        extensions: set[str],
        recursive: bool = False,
        retry_seconds: float = 0.5,
    ):
        self.folder = Path(folder).resolve()
        self.validator = validator
        self.on_complete = on_complete
        self.extensions = {extension.lower() for extension in extensions}
        self.recursive = recursive
        self.retry_seconds = retry_seconds
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._pending: set[str] = set()
        self._processed: dict[str, tuple[int, int]] = {}
        self._observer: Observer | None = None
        self._worker: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self, include_existing: bool = True) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._stopping.clear()
        self._worker = threading.Thread(target=self._work, name="xas-completion-validator", daemon=True)
        self._worker.start()
        self._observer = Observer()
        self._observer.schedule(_Handler(self.submit), str(self.folder), recursive=self.recursive)
        self._observer.start()
        if include_existing:
            pattern = "**/*" if self.recursive else "*"
            for path in sorted(self.folder.glob(pattern)):
                if path.is_file():
                    self.submit(str(path))

    def submit(self, path: str) -> None:
        source = Path(path)
        if source.suffix.lower() not in self.extensions:
            return
        normalized = str(source.resolve())
        if normalized not in self._pending:
            self._pending.add(normalized)
            self._queue.put(normalized)

    def _work(self) -> None:
        while not self._stopping.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            source = Path(item)
            result = self.validator.validate(source)
            if result.complete:
                try:
                    stat = source.stat()
                    signature = (stat.st_size, stat.st_mtime_ns)
                    if self._processed.get(item) != signature:
                        self.on_complete(source)
                        self._processed[item] = signature
                finally:
                    self._pending.discard(item)
            else:
                self._pending.discard(item)
                if result.reason in {"size_still_changing", "missing_final_newline", "file_unavailable:PermissionError"}:
                    time.sleep(self.retry_seconds)
                    self.submit(item)
            self._queue.task_done()

    def stop(self) -> None:
        self._stopping.set()
        self._queue.put(None)
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
        if self._worker:
            self._worker.join(timeout=3)
