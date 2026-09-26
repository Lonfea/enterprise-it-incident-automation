import pandas as pd

from src.core import load_logs, rule_hits, score_anomalies, template_of


def frame(rows):
    data = pd.DataFrame(rows, columns=["level", "message"])
    data["template"] = data["message"].map(template_of)
    data["message_length"] = data["message"].str.len()
    data["error_terms"] = data["message"].str.lower().str.count(
        r"error|failed|failure|timeout|denied|critical|unavailable|exception"
    )
    data["self_corrected"] = data["message"].str.lower().str.contains(r"\b(?:corrected|recovered)\b")
    data["level_weight"] = data["level"].map({"INFO": 1, "WARN": 2, "ERROR": 4, "CRITICAL": 6})
    return data


def test_template_masks_variable_tokens():
    assert template_of("data address: 0x00c4f2a8") == template_of("data address: 0xdeadbeef")
    assert template_of("block blk_-123 on 10.0.0.1:50010") == "block <BLOCK> on <NUM>:<NUM>"


def test_rule_semantics():
    data = frame(
        [
            ("ERROR", "anything at all"),
            ("WARN", "request timeout"),
            ("WARN", "parity error detected and corrected"),
            ("INFO", "42 critical input interrupts"),
            ("WARN", "disk at 82 percent"),
        ]
    )
    assert rule_hits(data).tolist() == [True, True, False, False, False]


def test_feedback_suppresses_only_listed_templates():
    rows = [("ERROR", f"register dump 0x{index:08x}") for index in range(5)]
    rows += [("ERROR", "data TLB error interrupt")] * 5
    data = frame(rows)
    scored = score_anomalies(data, suppressed_templates={"register dump <HEX>"})
    assert scored["suppressed"].sum() == 5
    assert scored.loc[scored["message"] == "data TLB error interrupt", "is_anomaly"].all()


def test_sample_log_routine_info_is_not_an_incident():
    scored = score_anomalies(load_logs("data/sample_system.log"))
    routine = scored["message"] == "Backup checkpoint completed"
    assert not scored.loc[routine, "is_anomaly"].any()
    assert scored.loc[scored["level"].isin(["ERROR", "CRITICAL"]), "is_anomaly"].all()
