#!/usr/bin/env python3
"""Measure ANPR recognition accuracy and latency from a labeled prediction file.

Input CSV columns: expected_plate,predicted_plate,latency_ms
The harness is model-agnostic so EasyOCR or a future production OCR provider can
be benchmarked against the same ground-truth dataset.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
import re


def normalize(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--max-error-rate", type=float, default=1.0)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.predictions.open(encoding="utf-8-sig", newline="")))
    if not rows:
        raise SystemExit("No labeled ANPR rows supplied")
    expected = [normalize(r.get("expected_plate")) for r in rows]
    predicted = [normalize(r.get("predicted_plate")) for r in rows]
    valid = [bool(x) for x in expected]
    exact = [e == p and bool(e) for e, p in zip(expected, predicted)]
    char_total = sum(max(len(e), len(p)) for e, p in zip(expected, predicted))
    char_correct = sum(sum(a == b for a, b in zip(e, p)) for e, p in zip(expected, predicted))
    latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") not in (None, "")]
    exact_accuracy = sum(exact) / max(1, sum(valid))
    result = {
        "samples": len(rows),
        "labeled_samples": sum(valid),
        "exact_plate_accuracy": round(exact_accuracy, 6),
        "character_accuracy": round(char_correct / max(1, char_total), 6),
        "error_rate": round(1.0 - exact_accuracy, 6),
        "latency_ms": {
            "count": len(latencies),
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "p95": round(sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
        },
        "pass": (1.0 - exact_accuracy) <= args.max_error_rate,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
