from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import api
from src.database import Base, Incident


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "SessionLocal", testing_session)

    with testing_session() as session:
        session.add(
            Incident(
                event_id="test-event-1",
                source_timestamp=datetime.now(timezone.utc),
                service="orders-db",
                level="ERROR",
                message="Database connection pool exhausted",
                anomaly_score=0.82,
                category="database",
                assigned_team="Database Operations",
                priority="P2",
                explanation="Database indicators detected",
                sla_deadline=datetime.now(timezone.utc) + timedelta(hours=4),
            )
        )
        session.commit()
    yield TestClient(api.app)


def test_guidance_and_human_approval_flow(client):
    guidance = client.get("/incidents/1/guidance")
    assert guidance.status_code == 200
    assert guidance.json()["runbook_id"] == "RB-DB-001"
    assert guidance.json()["requires_human_approval"] is True

    proposal = client.post(
        "/incidents/1/actions",
        json={
            "action": "Restart the connection pool",
            "rationale": "Connections remain saturated after read-only checks",
            "requested_by": "assistant",
        },
    )
    assert proposal.status_code == 201
    assert proposal.json()["status"] == "pending"

    decision = client.post(
        f"/actions/{proposal.json()['id']}/decision",
        json={"decision": "approved", "decided_by": "on-call-engineer", "reason": "Change window confirmed"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    audit = client.get("/audit-events")
    assert audit.status_code == 200
    assert [event["event_type"] for event in audit.json()] == ["action_approved", "action_proposed"]


def test_feedback_is_recorded_with_template_and_audited(client):
    response = client.post("/incidents/1/feedback", json={"verdict": "false_positive", "actor": "sre-oncall"})
    assert response.status_code == 201
    assert response.json()["template"] == "Database connection pool exhausted"
    assert client.get("/audit-events").json()[0]["event_type"] == "incident_feedback"


def test_feedback_validation_and_missing_incident(client):
    assert client.post("/incidents/1/feedback", json={"verdict": "maybe", "actor": "sre"}).status_code == 422
    assert client.post("/incidents/99/feedback", json={"verdict": "true_positive", "actor": "sre"}).status_code == 404
