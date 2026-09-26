from src.logformats import detect_format, normalize_level, parse

HDFS_LINE = (
    "081109 203615 148 INFO dfs.DataNode$PacketResponder: "
    "PacketResponder 1 for block blk_38865049064139660 terminating"
)
BGL_NORMAL = (
    "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 "
    "R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected"
)
BGL_ANOMALY = (
    "KERNDTLB 1118536327 2005.06.11 R30-M0-N9-C:J16-U01 2005-06-11-17.32.07.581048 "
    "R30-M0-N9-C:J16-U01 RAS KERNEL FATAL data TLB error interrupt"
)
BGL_NULL_TYPE = (
    "- 1120241131 2005.07.01 R37-M1-N4 2005-07-01-11.05.31.120732 R37-M1-N4 "
    "NULL DISCOVERY SEVERE Can not get assembly information for node card"
)


def test_hdfs_line_is_parsed_with_real_timestamp():
    event = parse(HDFS_LINE, "hdfs")
    assert event["parsed"] is True
    assert event["timestamp"] == "2008-11-09 20:36:15"
    assert event["service"] == "dfs.DataNode$PacketResponder"
    assert event["message"].startswith("PacketResponder 1")


def test_bgl_labels_and_levels_are_normalized():
    normal, anomaly = parse(BGL_NORMAL, "bgl"), parse(BGL_ANOMALY, "bgl")
    assert normal["label"] is False and normal["level"] == "INFO"
    assert anomaly["label"] is True and anomaly["level"] == "CRITICAL"
    assert anomaly["message"] == "data TLB error interrupt"


def test_bgl_accepts_non_ras_event_types():
    event = parse(BGL_NULL_TYPE, "bgl")
    assert event["parsed"] is True
    assert event["service"] == "DISCOVERY"
    assert event["level"] == "ERROR"


def test_unknown_level_names_fall_back_to_warn():
    assert normalize_level("WARNING") == "WARN"
    assert normalize_level("fatal") == "CRITICAL"
    assert normalize_level("NOTICE") == "WARN"


def test_unmatched_line_is_kept_but_marked_unparsed():
    event = parse("free text without structure", "hdfs")
    assert event["parsed"] is False
    assert event["timestamp"] is None
    assert event["message"] == "free text without structure"


def test_format_detection():
    assert detect_format([HDFS_LINE, HDFS_LINE]) == "hdfs"
    assert detect_format(["", BGL_NORMAL, BGL_ANOMALY]) == "bgl"
    assert detect_format(["2026-09-20 10:00:00 ERROR auth - denied"]) == "native"
    assert detect_format(["nothing matches"]) == "native"
