from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ReferenceLibrary:
    """External-data interface. Reference spectra never live in application code."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def manifest(self, filename: str = "references.yaml") -> dict[str, Any]:
        path = self.root / filename
        if not path.exists():
            example = self.root / "references.example.yaml"
            path = example if example.exists() else path
        if not path.exists():
            return {"schema_version": 1, "references": [], "status": "not_configured"}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["manifest_path"] = str(path.resolve())
        data["datasets_external"] = True
        return data
