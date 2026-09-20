from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest


LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARN|ERROR|CRITICAL)\s+"
    r"(?P<service>[\w.-]+)\s+-\s+(?P<message>.*)$"
)


@dataclass(frozen=True)
class IncidentDecision:
    category: str
    team: str
    priority: str
    explanation: str
    sla_hours: int


ROUTES = {
    "authentication": ("Identity & Access", ("login", "auth", "permission", "token", "denied")),
    "database": ("Database Operations", ("sql", "database", "connection pool", "deadlock")),
    "network": ("Network Operations", ("network", "timeout", "dns", "socket", "unreachable")),
    "storage": ("Infrastructure", ("disk", "hdfs", "storage", "volume", "block")),
}


def parse_line(line: str) -> dict:
    match = LOG_PATTERN.match(line.strip())
    if match:
        event = match.groupdict()
    else:
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": "WARN",
            "service": "unknown",
            "message": line.strip(),
        }
    event["event_id"] = hashlib.sha256(line.encode()).hexdigest()[:12]
    return event


def load_logs(path: str | Path) -> pd.DataFrame:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    frame = pd.DataFrame(parse_line(line) for line in lines if line.strip())
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["message_length"] = frame["message"].str.len()
    frame["error_terms"] = frame["message"].str.lower().str.count(
        r"error|failed|failure|timeout|denied|critical|unavailable"
    )
    frame["level_weight"] = frame["level"].map(
        {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 4, "CRITICAL": 6}
    ).fillna(1)
    return frame


def score_anomalies(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.assign(anomaly_score=pd.Series(dtype=float), is_anomaly=pd.Series(dtype=bool))
    features = frame[["message_length", "error_terms", "level_weight"]]
    if len(frame) < 5:
        score = (frame["level_weight"] + frame["error_terms"] * 2) / 10
        return frame.assign(anomaly_score=score.clip(0, 1), is_anomaly=score >= 0.4)
    model = IsolationForest(contamination="auto", random_state=42)
    model.fit(features)
    raw = -model.decision_function(features)
    minimum, maximum = float(raw.min()), float(raw.max())
    normalized = (raw - minimum) / (maximum - minimum) if maximum > minimum else raw * 0
    rule_hit = (frame["level_weight"] >= 4) | (frame["error_terms"] >= 1)
    return frame.assign(anomaly_score=normalized, is_anomaly=(normalized >= 0.65) | rule_hit)


def decide(event: dict) -> IncidentDecision:
    text = f"{event.get('service', '')} {event.get('message', '')}".lower()
    category, team = "application", "Application Support"
    for candidate, (candidate_team, terms) in ROUTES.items():
        if any(term in text for term in terms):
            category, team = candidate, candidate_team
            break

    level = event.get("level", "WARN")
    score = float(event.get("anomaly_score", 0))
    if level == "CRITICAL" or score >= 0.9:
        priority, sla = "P1", 1
    elif level == "ERROR" or score >= 0.7:
        priority, sla = "P2", 4
    else:
        priority, sla = "P3", 24
    explanation = f"Routed to {team}: {category} indicators; {level} event; anomaly={score:.2f}."
    return IncidentDecision(category, team, priority, explanation, sla)


def deadline(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)
