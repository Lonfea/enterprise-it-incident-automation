"""Measure alert quality on labelled logs from the LogHub BGL sample.

BGL (Blue Gene/L supercomputer) is one of the few public log datasets with
line-level anomaly labels, so it can show how many alerts are real.

Protocol
--------
Logs are split chronologically. The first half plays the role of history:
operators review the alerts it raised, and their verdicts (the dataset
labels) train the feedback suppression. Every detector is then scored on
the second half only, which it has not seen.

Caveat: the rule refinements in ``src.core`` were informed by error
analysis on this same 2,000-line sample, so the held-out numbers are
indicative, not an independent benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import ISOLATION_THRESHOLD, LEVEL_WEIGHTS, isolation_scores, load_logs, rule_hits
from src.feedback import noise_templates

URL = "https://raw.githubusercontent.com/logpai/loghub/master/BGL/BGL_2k.log"
DEFAULT_PATH = PROJECT_ROOT / "data" / "BGL_2k.log"
LEGACY_TERMS = r"error|failed|failure|timeout|denied|critical|unavailable"


def ensure_dataset(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(URL, timeout=30)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def metrics(labels: pd.Series, alerts: pd.Series, templates: pd.Series) -> dict:
    true_positives = int((labels & alerts).sum())
    alert_count = int(alerts.sum())
    anomalies = int(labels.sum())
    precision = true_positives / alert_count if alert_count else 0.0
    recall = true_positives / anomalies if anomalies else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "alerts": alert_count,
        "true_positives": true_positives,
        "false_positives": alert_count - true_positives,
        "missed_anomalies": anomalies - true_positives,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "distinct_alert_templates": int(templates[alerts].nunique()),
    }


def detectors(frame: pd.DataFrame, suppressed: set[str]) -> dict[str, pd.Series]:
    scores = pd.Series(isolation_scores(frame), index=frame.index)
    outlier = scores >= ISOLATION_THRESHOLD
    legacy_rule = (frame["level_weight"] >= LEVEL_WEIGHTS["ERROR"]) | frame["message"].str.lower().str.contains(
        LEGACY_TERMS
    )
    rules = rule_hits(frame)
    current = rules | (outlier & (frame["level_weight"] >= LEVEL_WEIGHTS["WARN"]))
    return {
        "v1 detector (rules OR isolation forest)": legacy_rule | outlier,
        "isolation forest only": outlier,
        "refined rules only": rules,
        "current detector (refined rules OR gated isolation forest)": current,
        "current detector + operator feedback": current & ~frame["template"].isin(suppressed),
    }


def benchmark(path: Path) -> dict:
    frame = load_logs(ensure_dataset(path), log_format="bgl")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    frame["label"] = frame["label"].astype(bool)
    cut = len(frame) // 2
    history, test = frame.iloc[:cut].copy(), frame.iloc[cut:].copy()

    # Operators only give verdicts on alerts they were shown.
    history_alerts = detectors(history, set())["current detector (refined rules OR gated isolation forest)"]
    reviewed = history[history_alerts]
    suppressed = noise_templates(zip(reviewed["template"], reviewed["label"]))

    results = {
        name: metrics(test["label"], alerts, test["template"])
        for name, alerts in detectors(test, suppressed).items()
    }
    return {
        "dataset": "LogHub BGL_2k (Blue Gene/L RAS logs, line-level labels)",
        "source": URL,
        "lines": len(frame),
        "labelled_anomalies": int(frame["label"].sum()),
        "protocol": "chronological split; feedback learned on first half, all scores on second half",
        "test_lines": len(test),
        "test_anomalies": int(test["label"].sum()),
        "reviewed_alerts_in_history": len(reviewed),
        "suppressed_templates": len(suppressed),
        "caveat": "rule refinements were informed by error analysis on this same sample",
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark alert quality on labelled BGL logs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = benchmark(args.input)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
