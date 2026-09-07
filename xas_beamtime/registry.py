from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    data: dict[str, Any]
    source: Path

    def get(self, dotted_key: str, default: Any = None) -> Any:
        value: Any = self.data
        for key in dotted_key.split("."):
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class ProfileRegistry:
    def __init__(self, *profile_roots: Path):
        default = Path(__file__).parent / "profiles"
        self.roots = tuple(profile_roots) or (default,)
        self._profiles: dict[str, Profile] = {}
        self.reload()

    def reload(self) -> None:
        profiles: dict[str, Profile] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.yaml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                profile_id = data.get("id")
                if not profile_id:
                    raise ProfileError(f"Profile has no id: {path}")
                self._validate(data, path)
                profiles[profile_id] = Profile(profile_id, data, path)
        self._profiles = profiles

    @staticmethod
    def _validate(data: dict[str, Any], path: Path) -> None:
        required = ["identity", "energy", "normalization", "quality", "decision"]
        missing = [key for key in required if key not in data]
        if missing:
            raise ProfileError(f"Missing {missing} in {path}")
        if data.get("schema_version") != 1:
            raise ProfileError(f"Unsupported profile schema in {path}")

    def get(self, profile_id: str) -> Profile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise ProfileError(f"Unknown profile: {profile_id}") from exc

    def match(self, element: str | None, edge: str | None, scan_type: str | None) -> Profile | None:
        for profile in self._profiles.values():
            identity = profile.data["identity"]
            if (
                (element or "").upper() == str(identity["element"]).upper()
                and (edge or "").upper() == str(identity["edge"]).upper()
                and (scan_type or "").upper() == str(identity["scan_type"]).upper()
            ):
                return profile
        return None

    def list(self) -> list[dict[str, Any]]:
        return [
            {"id": p.id, "identity": p.data["identity"], "version": p.data.get("version")}
            for p in self._profiles.values()
        ]
