from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def clean_signal(energy: np.ndarray) -> np.ndarray:
    edge = 0.62 / (1 + np.exp(-(energy - 2152.0) / 0.55))
    white_line = 0.48 * np.exp(-0.5 * ((energy - 2154.0) / 1.15) ** 2)
    feature_1 = 0.12 * np.exp(-0.5 * ((energy - 2162.5) / 2.0) ** 2)
    feature_2 = 0.07 * np.exp(-0.5 * ((energy - 2170.0) / 2.8) ** 2)
    baseline = 0.0007 * (energy - 2135.0)
    return baseline + edge + white_line + feature_1 + feature_2


def generate(output: Path, scans: int, seed: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    energy = np.arange(2135.0, 2205.01, 0.15)
    rng = np.random.default_rng(seed)
    base = clean_signal(energy)
    for number in range(1, scans + 1):
        noise = rng.normal(0, 0.013, energy.size)
        low_frequency = 0.002 * np.sin(energy * 0.35 + number)
        signal = base + noise + low_frequency
        if number == 2:
            signal[np.argmin(np.abs(energy - 2139.5))] += 0.09
        if number == 3:
            signal[np.argmin(np.abs(energy - 2161.0))] += 0.035
        path = output / f"apatite_scan-{number:03d}.dat"
        lines = [
            "# Element: P", "# Edge: K", "# Scan Type: XANES", "# Sample ID: apatite",
            f"# Scan Number: {number}", f"# Duration: {92 + number * 1.7:.1f} s", "# Beamline: DEMO",
            "# energy_eV mu",
        ]
        lines.extend(f"{x:.3f} {y:.8f}" for x, y in zip(energy, signal))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("test_data/incoming"))
    parser.add_argument("--scans", type=int, default=6)
    parser.add_argument("--seed", type=int, default=12)
    args = parser.parse_args()
    generate(args.output, args.scans, args.seed)
