from __future__ import annotations

import argparse
import json
import os

import requests
from sqlalchemy.exc import IntegrityError

from .core import deadline, decide, load_logs, score_anomalies
from .database import Incident, SessionLocal, init_db


def notify(payload: dict) -> None:
    url = os.getenv("TEAMS_WEBHOOK_URL")
    if url:
        requests.post(url, json={"text": f"[{payload['priority']}] {payload['service']}: {payload['message']}"}, timeout=10).raise_for_status()


def run(input_path: str) -> dict:
    init_db()
    events = score_anomalies(load_logs(input_path))
    created = duplicates = 0
    with SessionLocal() as session:
        for event in events[events["is_anomaly"]].to_dict("records"):
            decision = decide(event)
            payload = {
                "event_id": event["event_id"],
                "source_timestamp": event["timestamp"].to_pydatetime(),
                "service": event["service"],
                "level": event["level"],
                "message": event["message"],
                "anomaly_score": float(event["anomaly_score"]),
                "category": decision.category,
                "assigned_team": decision.team,
                "priority": decision.priority,
                "explanation": decision.explanation,
                "sla_deadline": deadline(decision.sla_hours),
            }
            session.add(Incident(**payload))
            try:
                session.commit()
                created += 1
                notify(payload)
            except IntegrityError:
                session.rollback()
                duplicates += 1
    return {"processed": len(events), "incidents_created": created, "duplicates_skipped": duplicates}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert server logs into routed IT incidents.")
    parser.add_argument("--input", required=True, help="Path to a log file")
    args = parser.parse_args()
    print(json.dumps(run(args.input), indent=2))
