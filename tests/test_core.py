from src.core import decide, parse_line, score_anomalies

import pandas as pd


def test_parse_structured_log():
    event = parse_line("2026-09-20 10:00:00 ERROR auth-service - Login denied")
    assert event["level"] == "ERROR"
    assert event["service"] == "auth-service"
    assert len(event["event_id"]) == 12


def test_route_authentication_error():
    decision = decide({"service": "auth", "message": "token denied", "level": "ERROR", "anomaly_score": 0.8})
    assert decision.category == "authentication"
    assert decision.team == "Identity & Access"
    assert decision.priority == "P2"


def test_small_batch_uses_explainable_score():
    frame = pd.DataFrame({"message_length": [10, 80], "error_terms": [0, 2], "level_weight": [1, 6]})
    scored = score_anomalies(frame)
    assert bool(scored.iloc[1]["is_anomaly"])
