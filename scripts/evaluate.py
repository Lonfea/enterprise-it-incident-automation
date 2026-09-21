from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import decide
from src.guidance import retrieve_guidance


CASES = [
    ("auth", "Repeated login denied after token refresh", "ERROR", 0.82, "authentication", "P2", "RB-AUTH-001"),
    ("iam", "Permission denied for service account", "CRITICAL", 0.95, "authentication", "P1", "RB-AUTH-001"),
    ("postgres", "Database connection pool exhausted", "ERROR", 0.76, "database", "P2", "RB-DB-001"),
    ("orders-db", "SQL deadlock detected", "WARN", 0.72, "database", "P2", "RB-DB-001"),
    ("gateway", "Network timeout contacting dependency", "ERROR", 0.81, "network", "P2", "RB-NET-001"),
    ("dns", "Host unreachable after DNS lookup", "CRITICAL", 0.91, "network", "P1", "RB-NET-001"),
    ("hdfs", "Storage volume unavailable", "ERROR", 0.78, "storage", "P2", "RB-STORAGE-001"),
    ("worker", "Disk capacity above threshold", "WARN", 0.68, "storage", "P3", "RB-STORAGE-001"),
    ("checkout", "Unexpected application exception", "ERROR", 0.75, "application", "P2", "RB-APP-001"),
    ("catalog", "Service unavailable after deployment", "CRITICAL", 0.93, "application", "P1", "RB-APP-001"),
]


def evaluate() -> dict:
    route_hits = priority_hits = runbook_hits = 0
    details = []
    for service, message, level, score, expected_category, expected_priority, expected_runbook in CASES:
        event = {"service": service, "message": message, "level": level, "anomaly_score": score}
        decision = decide(event)
        guidance = retrieve_guidance({**event, "category": decision.category, "explanation": decision.explanation})
        route_ok = decision.category == expected_category
        priority_ok = decision.priority == expected_priority
        runbook_ok = guidance.runbook_id == expected_runbook
        route_hits += int(route_ok)
        priority_hits += int(priority_ok)
        runbook_hits += int(runbook_ok)
        details.append(
            {
                "message": message,
                "category": decision.category,
                "priority": decision.priority,
                "runbook_id": guidance.runbook_id,
                "passed": route_ok and priority_ok and runbook_ok,
            }
        )
    total = len(CASES)
    return {
        "dataset": "curated portfolio validation scenarios",
        "cases": total,
        "routing_accuracy": round(route_hits / total, 3),
        "priority_accuracy": round(priority_hits / total, 3),
        "runbook_retrieval_accuracy": round(runbook_hits / total, 3),
        "production_benchmark": False,
        "details": details,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate routing, priority and runbook retrieval.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
