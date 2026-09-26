import pytest
import requests
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src import pipeline
from src.core import template_of
from src.database import Base, Incident, IncidentFeedback

LOG = "\n".join(
    [
        "2026-09-20 08:00:01 INFO auth-service - User session created successfully",
        "2026-09-20 08:00:08 INFO inventory-api - Health check completed in 42ms",
        "2026-09-20 08:01:00 ERROR storage-node - Replica 0x1a2b3c4d4e lost on volume-04",
        "2026-09-20 08:02:00 ERROR storage-node - Replica 0x9f8e7d6c5b lost on volume-04",
        "2026-09-20 08:03:00 CRITICAL network-gateway - DNS unavailable; upstream unreachable",
        "2026-09-20 08:04:00 INFO inventory-api - Request completed with status 200",
    ]
)


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pipeline, "SessionLocal", factory)
    monkeypatch.setattr(pipeline, "init_db", lambda: Base.metadata.create_all(engine))
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    return factory


@pytest.fixture()
def log_file(tmp_path):
    path = tmp_path / "system.log"
    path.write_text(LOG, encoding="utf-8")
    return path


def test_creates_incidents_and_skips_duplicates_on_rerun(session_factory, log_file):
    first = pipeline.run(str(log_file))
    second = pipeline.run(str(log_file))
    assert first["incidents_created"] == 3
    assert second["incidents_created"] == 0
    assert second["duplicates_skipped"] == 3
    with session_factory() as session:
        assert session.scalar(select(func.count(Incident.id))) == 3


def test_webhook_outage_does_not_stop_ingestion(session_factory, log_file, monkeypatch):
    def failing_post(*args, **kwargs):
        raise requests.ConnectionError("webhook down")

    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(pipeline.requests, "post", failing_post)
    result = pipeline.run(str(log_file))
    assert result["incidents_created"] == 3
    assert result["notification_failures"] == 3


def test_operator_feedback_suppresses_repeated_noise(session_factory, log_file, tmp_path):
    pipeline.run(str(log_file))
    noisy = template_of("Replica 0x1a2b3c4d4e lost on volume-04")
    with session_factory() as session:
        incident_id = session.scalar(select(Incident.id).limit(1))
        for _ in range(3):
            session.add(
                IncidentFeedback(incident_id=incident_id, template=noisy, verdict="false_positive", actor="sre")
            )
        session.commit()

    later = tmp_path / "later.log"
    later.write_text(
        "2026-09-21 09:00:00 ERROR storage-node - Replica 0x0000aaaa11 lost on volume-04\n"
        "2026-09-21 09:01:00 CRITICAL network-gateway - DNS unavailable again\n",
        encoding="utf-8",
    )
    result = pipeline.run(str(later))
    assert result["suppressed_by_feedback"] == 1
    assert result["incidents_created"] == 1


def test_hdfs_lines_keep_their_source_timestamp(session_factory, tmp_path):
    path = tmp_path / "hdfs.log"
    path.write_text(
        "081109 203615 148 WARN dfs.DataNode: Got exception while serving blk_1 to /10.0.0.1\n", encoding="utf-8"
    )
    result = pipeline.run(str(path))
    assert result["unparsed_lines"] == 0
    with session_factory() as session:
        incident = session.scalars(select(Incident)).one()
        assert incident.source_timestamp.year == 2008
