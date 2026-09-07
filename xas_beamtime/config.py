from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import RuntimeLimits


@dataclass(slots=True)
class AppConfig:
    source_path: Path
    data: dict[str, Any]

    @property
    def base_dir(self) -> Path:
        return self.source_path.parent.parent

    def path(self, dotted_key: str, default: str) -> Path:
        value = self.get(dotted_key, default)
        path = Path(value)
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def get(self, dotted_key: str, default: Any = None) -> Any:
        value: Any = self.data
        for key in dotted_key.split("."):
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    @property
    def limits(self) -> RuntimeLimits:
        return RuntimeLimits(
            maximum_scans=self.get("limits.maximum_scans"),
            maximum_time_seconds=self.get("limits.maximum_time_seconds"),
        )


def load_config(path: str | Path) -> AppConfig:
    source = Path(path).resolve()
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return AppConfig(source, data)
