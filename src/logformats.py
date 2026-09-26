"""Parsers for the log formats the pipeline accepts.

Every parser returns the same event shape so detection and routing do not
need to know where a line came from:

    timestamp  ISO-like string, or None when the line has no usable time
    level      one of DEBUG, INFO, WARN, ERROR, CRITICAL
    service    emitting component
    message    free text
    label      ground-truth anomaly flag when the source provides one, else None
    parsed     False when no known format matched and the raw line was kept
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")

# Vendor level names mapped onto the five levels used for routing.
LEVEL_ALIASES = {
    "WARNING": "WARN",
    "SEVERE": "ERROR",
    "FATAL": "CRITICAL",
    "FAILURE": "CRITICAL",
}

NATIVE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARN|ERROR|CRITICAL)\s+"
    r"(?P<service>[\w.-]+)\s+-\s+(?P<message>.*)$"
)

# LogHub HDFS: "081109 203615 148 INFO dfs.DataNode$PacketResponder: message"
HDFS_PATTERN = re.compile(
    r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+\d+\s+"
    r"(?P<level>[A-Z]+)\s+(?P<service>[\w.$]+):\s+(?P<message>.*)$"
)

# LogHub BGL: "<label> <epoch> <date> <node> <time> <node> <type> <component> <level> message"
# The first field is "-" for normal lines and an alert category for anomalies.
BGL_PATTERN = re.compile(
    r"^(?P<label>\S+)\s+\d+\s+\S+\s+\S+\s+"
    r"(?P<time>\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2})\.\d+\s+\S+\s+\S+\s+"
    r"(?P<service>\S+)\s+(?P<level>[A-Z]+)\s?(?P<message>.*)$"
)


def normalize_level(level: str) -> str:
    level = level.upper()
    level = LEVEL_ALIASES.get(level, level)
    return level if level in LEVELS else "WARN"


def parse_native(line: str) -> dict | None:
    match = NATIVE_PATTERN.match(line)
    if not match:
        return None
    return {**match.groupdict(), "label": None}


def parse_hdfs(line: str) -> dict | None:
    match = HDFS_PATTERN.match(line)
    if not match:
        return None
    stamp = datetime.strptime(match["date"] + match["time"], "%y%m%d%H%M%S")
    return {
        "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "level": match["level"],
        "service": match["service"],
        "message": match["message"],
        "label": None,
    }


def parse_bgl(line: str) -> dict | None:
    match = BGL_PATTERN.match(line)
    if not match:
        return None
    stamp = datetime.strptime(match["time"], "%Y-%m-%d-%H.%M.%S")
    return {
        "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "level": match["level"],
        "service": match["service"],
        "message": match["message"],
        "label": match["label"] != "-",
    }


PARSERS: dict[str, Callable[[str], dict | None]] = {
    "native": parse_native,
    "hdfs": parse_hdfs,
    "bgl": parse_bgl,
}


def detect_format(lines: Iterable[str], sample_size: int = 50) -> str:
    """Pick the parser that matches the most of the first non-empty lines."""
    sample = [line.strip() for line in lines if line.strip()][:sample_size]
    if not sample:
        return "native"
    hits = {name: sum(parser(line) is not None for line in sample) for name, parser in PARSERS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else "native"


def parse(line: str, log_format: str) -> dict:
    """Parse one line; unmatched lines are kept as WARN events so nothing is silently dropped."""
    line = line.strip()
    event = PARSERS[log_format](line)
    if event is None:
        return {
            "timestamp": None,
            "level": "WARN",
            "service": "unknown",
            "message": line,
            "label": None,
            "parsed": False,
        }
    event["level"] = normalize_level(event["level"])
    event["parsed"] = True
    return event
