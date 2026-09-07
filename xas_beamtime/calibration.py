from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(slots=True)
class BeamlineCalibration:
    beamline: str | None
    energy_offset_ev: float = 0.0
    energy_scale: float = 1.0
    incident_channel: str | None = None
    transmission_channel: str | None = None
    fluorescence_channels: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None

    @classmethod
    def identity(cls) -> "BeamlineCalibration":
        return cls(None)

    @classmethod
    def load(cls, path: str | Path | None) -> "BeamlineCalibration":
        if path is None or not Path(path).exists():
            return cls.identity()
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(
            beamline=data.get("beamline"),
            energy_offset_ev=float(data.get("energy_offset_ev", 0.0)),
            energy_scale=float(data.get("energy_scale", 1.0)),
            incident_channel=data.get("incident_channel"),
            transmission_channel=data.get("transmission_channel"),
            fluorescence_channels=tuple(data.get("fluorescence_channels") or ()),
            raw=data,
        )

    def apply_energy(self, energy: np.ndarray) -> np.ndarray:
        return energy * self.energy_scale + self.energy_offset_ev

    def apply_signal(self, data: np.ndarray, names: list[str], fallback_index: int) -> np.ndarray:
        lower = [name.lower() for name in names]
        if self.incident_channel and self.incident_channel.lower() in lower:
            i0 = data[:, lower.index(self.incident_channel.lower())]
            if self.transmission_channel and self.transmission_channel.lower() in lower:
                it = data[:, lower.index(self.transmission_channel.lower())]
                with np.errstate(divide="ignore", invalid="ignore"):
                    return -np.log(np.clip(it / i0, 1e-12, None))
            available = [channel.lower() for channel in self.fluorescence_channels if channel.lower() in lower]
            if available:
                fluorescence = sum(data[:, lower.index(channel)] for channel in available)
                with np.errstate(divide="ignore", invalid="ignore"):
                    return fluorescence / i0
        return data[:, fallback_index]
