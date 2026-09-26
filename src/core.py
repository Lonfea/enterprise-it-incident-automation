from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .logformats import PARSERS, detect_format, parse

ERROR_TERMS = r"error|failed|failure|timeout|denied|critical|unavailable|exception"
# Errors the emitting system reports as already handled are not incidents on their own.
SELF_CORRECTED = r"\b(?:corrected|recovered)\b"
LEVEL_WEIGHTS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 4, "CRITICAL": 6}
ISOLATION_THRESHOLD = 0.65


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


def parse_line(line: str, log_format: str | None = None) -> dict:
    """Parse one line, trying every known format when none is given."""
    if log_format is None:
        log_format = next((name for name, parser in PARSERS.items() if parser(line.strip())), "native")
    event = parse(line, log_format)
    event["event_id"] = hashlib.sha256(line.encode()).hexdigest()[:12]
    return event


def template_of(message: str) -> str:
    """Mask variable tokens so repeated events share one template."""
    message = re.sub(r"0x[0-9a-fA-F]+|\b[0-9a-fA-F]{8,}\b", "<HEX>", message)
    message = re.sub(r"blk_-?\d+", "<BLOCK>", message)
    message = re.sub(r"\d+(?:\.\d+)*", "<NUM>", message)
    return re.sub(r"\s+", " ", message).strip()


def load_logs(path: str | Path, log_format: str | None = None) -> pd.DataFrame:
    lines = [
        line
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    log_format = log_format or detect_format(lines)
    frame = pd.DataFrame(parse_line(line, log_format) for line in lines)
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["template"] = frame["message"].map(template_of)
    frame["message_length"] = frame["message"].str.len()
    frame["error_terms"] = frame["message"].str.lower().str.count(ERROR_TERMS)
    frame["self_corrected"] = frame["message"].str.lower().str.contains(SELF_CORRECTED)
    frame["level_weight"] = frame["level"].map(LEVEL_WEIGHTS).fillna(1)
    return frame


def rule_hits(frame: pd.DataFrame) -> pd.Series:
    """Explainable alert rule.

    ERROR and CRITICAL events always alert. Failure keywords escalate WARN
    events, unless the message says the error was already corrected. INFO
    events never alert on keywords alone: the emitter classed them as routine.
    """
    severe = frame["level_weight"] >= LEVEL_WEIGHTS["ERROR"]
    keyword = (
        (frame["level_weight"] >= LEVEL_WEIGHTS["WARN"])
        & (frame["error_terms"] >= 1)
        & ~frame["self_corrected"]
    )
    return severe | keyword


def isolation_scores(frame: pd.DataFrame) -> np.ndarray:
    features = frame[["message_length", "error_terms", "level_weight"]]
    model = IsolationForest(contamination="auto", random_state=42)
    model.fit(features)
    raw = -model.decision_function(features)
    minimum, maximum = float(raw.min()), float(raw.max())
    return (raw - minimum) / (maximum - minimum) if maximum > minimum else raw * 0


def score_anomalies(
    frame: pd.DataFrame, suppressed_templates: set[str] | frozenset[str] = frozenset()
) -> pd.DataFrame:
    """Flag events that should become incidents.

    An event alerts when the explainable rule fires, or when Isolation Forest
    rates a WARN-or-higher event as an outlier. Templates that operators have
    consistently marked as noise are suppressed.
    """
    if frame.empty:
        return frame.assign(
            anomaly_score=pd.Series(dtype=float),
            is_anomaly=pd.Series(dtype=bool),
            suppressed=pd.Series(dtype=bool),
        )
    if len(frame) < 5:
        score = ((frame["level_weight"] + frame["error_terms"] * 2) / 10).clip(0, 1)
        flagged = score >= 0.4
    else:
        score = pd.Series(isolation_scores(frame), index=frame.index)
        outlier = (score >= ISOLATION_THRESHOLD) & (frame["level_weight"] >= LEVEL_WEIGHTS["WARN"])
        flagged = rule_hits(frame) | outlier
    suppressed = flagged & frame["template"].isin(suppressed_templates) if "template" in frame else flagged & False
    return frame.assign(anomaly_score=score, is_anomaly=flagged & ~suppressed, suppressed=suppressed)


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
