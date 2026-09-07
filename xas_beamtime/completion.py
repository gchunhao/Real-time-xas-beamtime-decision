from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CompletionResult:
    complete: bool
    reason: str
    size_bytes: int = 0


class FileCompletionValidator:
    def __init__(
        self,
        stable_checks: int = 3,
        stable_interval_seconds: float = 0.3,
        minimum_bytes: int = 256,
        require_final_newline: bool = True,
    ):
        self.stable_checks = max(2, stable_checks)
        self.stable_interval_seconds = stable_interval_seconds
        self.minimum_bytes = minimum_bytes
        self.require_final_newline = require_final_newline

    def validate(self, path: str | Path) -> CompletionResult:
        source = Path(path)
        sizes: list[int] = []
        for index in range(self.stable_checks):
            try:
                sizes.append(source.stat().st_size)
                with source.open("rb") as stream:
                    stream.read(1)
            except (FileNotFoundError, PermissionError, OSError) as exc:
                return CompletionResult(False, f"file_unavailable:{type(exc).__name__}")
            if index < self.stable_checks - 1:
                time.sleep(self.stable_interval_seconds)
        if sizes[-1] < self.minimum_bytes:
            return CompletionResult(False, "below_minimum_size", sizes[-1])
        if len(set(sizes)) != 1:
            return CompletionResult(False, "size_still_changing", sizes[-1])
        if self.require_final_newline:
            with source.open("rb") as stream:
                stream.seek(-1, 2)
                if stream.read(1) not in (b"\n", b"\r"):
                    return CompletionResult(False, "missing_final_newline", sizes[-1])
        return CompletionResult(True, "stable_and_readable", sizes[-1])
