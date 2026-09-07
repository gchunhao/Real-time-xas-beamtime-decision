from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable

import numpy as np

from .calibration import BeamlineCalibration
from .models import ScanMetadata, Spectrum


class ParseError(ValueError):
    pass


HEADER_RE = re.compile(r"^[#;!%\s]*([^:=]+?)\s*[:=]\s*(.*?)\s*$")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


ALIASES = {
    "element": ("element", "absorber", "atomic symbol"),
    "edge": ("edge", "absorption edge"),
    "scan_type": ("scan type", "scan_type", "mode"),
    "sample_id": ("sample", "sample id", "sample_id", "sample name"),
    "scan_number": ("scan", "scan number", "scan_number", "scan no"),
    "duration_seconds": ("duration", "scan duration", "elapsed", "elapsed seconds"),
    "started_at": ("started", "start time", "timestamp", "date"),
    "beamline": ("beamline", "beam line"),
}


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _metadata_value(header: dict[str, str], field: str) -> str | None:
    normalized = {_normal_key(k): v for k, v in header.items()}
    for alias in ALIASES[field]:
        if _normal_key(alias) in normalized:
            return normalized[_normal_key(alias)]
    return None


def _as_float(value: str | None) -> float | None:
    if not value:
        return None
    match = NUMBER_RE.search(value)
    if not match:
        return None
    number = float(match.group())
    lower = value.lower()
    if "min" in lower:
        number *= 60
    elif "hour" in lower or " hr" in lower:
        number *= 3600
    return number


def _as_int(value: str | None) -> int | None:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


class UniversalXASParser:
    """Permissive text-table parser with beamline calibration hooks."""

    extensions = {".dat", ".txt", ".csv", ".xas", ".xy"}

    def __init__(self, calibration: BeamlineCalibration | None = None):
        self.calibration = calibration or BeamlineCalibration.identity()

    def parse(self, path: str | Path) -> Spectrum:
        source = Path(path)
        text = source.read_text(encoding="utf-8", errors="replace")
        header, table_lines, declared_columns = self._split_header(text.splitlines())
        if len(table_lines) < 3:
            raise ParseError(f"Not enough numeric rows: {source}")
        delimiter = "," if sum("," in line for line in table_lines[:5]) >= 3 else None
        rows = self._numeric_rows(table_lines, delimiter)
        if not rows:
            raise ParseError(f"No numeric table found: {source}")
        width = max(len(row) for row in rows)
        rows = [row for row in rows if len(row) == width]
        data = np.asarray(rows, dtype=float)
        if data.shape[1] < 2:
            raise ParseError("At least energy and one signal column are required")
        names = self._column_names(declared_columns, width)
        energy_index = self._find_column(names, ("energy", "energy_ev", "e", "mono"), 0)
        signal_index = self._signal_index(names, data, energy_index)
        energy = self.calibration.apply_energy(data[:, energy_index])
        signal = self.calibration.apply_signal(data, names, signal_index)
        order = np.argsort(energy)
        energy, signal = energy[order], signal[order]
        finite = np.isfinite(energy) & np.isfinite(signal)
        metadata = self._metadata(source, header)
        raw_columns = {names[i]: data[:, i][order][finite] for i in range(width)}
        return Spectrum(energy[finite], signal[finite], metadata, raw_columns)

    def _split_header(self, lines: Iterable[str]) -> tuple[dict[str, str], list[str], list[str]]:
        header: dict[str, str] = {}
        table: list[str] = []
        columns: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            cleaned = stripped.lstrip("#;!% ")
            match = HEADER_RE.match(stripped)
            if match and not self._looks_numeric(cleaned):
                header[match.group(1).strip()] = match.group(2).strip()
                continue
            if not self._looks_numeric(cleaned):
                tokens = re.split(r"[,\t\s]+", cleaned)
                if any(_normal_key(t) in {"energy", "energy ev", "mu", "i0", "it", "if"} for t in tokens):
                    columns = tokens
                continue
            table.append(cleaned)
        return header, table, columns

    @staticmethod
    def _looks_numeric(line: str) -> bool:
        first = re.split(r"[,\t\s]+", line.strip())[0]
        try:
            float(first)
            return True
        except ValueError:
            return False

    @staticmethod
    def _numeric_rows(lines: list[str], delimiter: str | None) -> list[list[float]]:
        rows: list[list[float]] = []
        for line in lines:
            tokens = next(csv.reader(io.StringIO(line))) if delimiter else re.split(r"\s+", line.strip())
            try:
                rows.append([float(token) for token in tokens if token != ""])
            except ValueError:
                continue
        return rows

    @staticmethod
    def _column_names(declared: list[str], width: int) -> list[str]:
        if len(declared) == width:
            return [_normal_key(name).replace(" ", "_") for name in declared]
        defaults = ["energy", "mu"] + [f"column_{i}" for i in range(2, width)]
        return defaults[:width]

    @staticmethod
    def _find_column(names: list[str], aliases: tuple[str, ...], fallback: int) -> int:
        normalized = {_normal_key(name).replace(" ", "_"): i for i, name in enumerate(names)}
        for alias in aliases:
            if alias in normalized:
                return normalized[alias]
        return fallback

    def _signal_index(self, names: list[str], data: np.ndarray, energy_index: int) -> int:
        for alias in ("mu", "mutrans", "mufluor", "signal", "norm"):
            if alias in names:
                return names.index(alias)
        candidates = [i for i in range(data.shape[1]) if i != energy_index]
        return candidates[0]

    def _metadata(self, source: Path, header: dict[str, str]) -> ScanMetadata:
        filename = source.stem
        scan_number = _as_int(_metadata_value(header, "scan_number"))
        if scan_number is None:
            match = re.search(r"(?:scan|s)[-_ ]?(\d+)$", filename, re.IGNORECASE)
            scan_number = int(match.group(1)) if match else None
        sample_id = _metadata_value(header, "sample_id")
        if sample_id is None:
            sample_id = re.sub(r"(?:[-_ ]?(?:scan|s)[-_ ]?\d+)$", "", filename, flags=re.IGNORECASE)
        return ScanMetadata(
            source_path=str(source.resolve()),
            element=_metadata_value(header, "element"),
            edge=_metadata_value(header, "edge"),
            scan_type=_metadata_value(header, "scan_type"),
            sample_id=sample_id,
            scan_number=scan_number,
            duration_seconds=_as_float(_metadata_value(header, "duration_seconds")),
            started_at=_metadata_value(header, "started_at"),
            beamline=_metadata_value(header, "beamline") or self.calibration.beamline,
            header=header,
        )
