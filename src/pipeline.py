from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd
import requests
from sqlalchemy.exc import IntegrityError

from .core import deadline, decide, load_logs, score_anomalies
from .database import Incident, SessionLocal, init_db
from .feedback import load_noise_templates
from .logformats import PARSERS

logger = logging.getLogger(__name__)


def notify(payload: dict) -> bool:
    """Send an optional webhook notification; return False if delivery failed.

    A notification outage must not stop incidents from being recorded, so
    failures are logged and counted instead of raised.
    """
    url = os.getenv("TEAMS_WEBHOOK_URL")
    if not url:
        return True
    try:
        requests.post(
            url,
            json={"text": f"[{payload['priority']}] {payload['service']}: {payload['message']}"},
            timeout=10,
        ).raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Notification failed for event %s: %s", payload["event_id"], exc)
        return False
    return True


def source_time(value) -> datetime:
    """Use the log's own timestamp, falling back to ingestion time when it has none."""
    if value is None or pd.isna(value):
        return datetime.now(timezone.utc)
    return value.to_pydatetime()


def run(input_path: str, log_format: str | None = None) -> dict:
    init_db()
    with SessionLocal() as session:
        suppressed_templates = load_noise_templates(session)
    events = score_anomalies(load_logs(input_path, log_format), suppressed_templates)
    created = duplicates = notification_failures = 0
    with SessionLocal() as session:
        for event in events[events["is_anomaly"]].to_dict("records"):
            decision = decide(event)
            payload = {
                "event_id": event["event_id"],
                "source_timestamp": source_time(event["timestamp"]),
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
            except IntegrityError:
                session.rollback()
                duplicates += 1
                continue
            created += 1
            notification_failures += int(not notify(payload))
    return {
        "processed": len(events),
        "unparsed_lines": int((~events["parsed"]).sum()) if "parsed" in events else 0,
        "incidents_created": created,
        "duplicates_skipped": duplicates,
        "suppressed_by_feedback": int(events["suppressed"].sum()) if "suppressed" in events else 0,
        "notification_failures": notification_failures,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert server logs into routed IT incidents.")
    parser.add_argument("--input", required=True, help="Path to a log file")
    parser.add_argument(
        "--format", choices=sorted(PARSERS), help="Log format; detected automatically when omitted"
    )
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.format), indent=2))
