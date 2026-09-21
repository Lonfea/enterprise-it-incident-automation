from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import ActionProposal, AuditEvent, Incident, SessionLocal, init_db
from .guidance import retrieve_guidance


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="IT Incident Automation API", version="2.0.0", lifespan=lifespan)


class IncidentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    service: str
    level: str
    message: str
    anomaly_score: float
    category: str
    assigned_team: str
    priority: str
    status: str
    explanation: str
    sla_deadline: datetime


class StatusUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"]


class GuidanceView(BaseModel):
    runbook_id: str
    title: str
    category: str
    relevance_score: float
    actions: list[str]
    safeguards: list[str]
    requires_human_approval: bool


class ActionRequest(BaseModel):
    action: str = Field(min_length=3, max_length=500)
    rationale: str = Field(min_length=3, max_length=1000)
    requested_by: str = Field(default="system", min_length=2, max_length=100)


class ActionDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)


class ActionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    incident_id: int
    action: str
    rationale: str
    status: str
    requested_by: str
    requested_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None


class AuditEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    incident_id: int | None
    action_id: int | None
    event_type: str
    actor: str
    details: str
    created_at: datetime


def get_db():
    with SessionLocal() as session:
        yield session


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}


@app.get("/incidents", response_model=list[IncidentView])
def incidents(status: str | None = None, priority: str | None = None, db: Session = Depends(get_db)):
    query = select(Incident).order_by(Incident.created_at.desc())
    if status:
        query = query.where(Incident.status == status)
    if priority:
        query = query.where(Incident.priority == priority)
    return db.scalars(query).all()


@app.patch("/incidents/{incident_id}/status", response_model=IncidentView)
def update_status(incident_id: int, update: StatusUpdate, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.status = update.status
    db.add(
        AuditEvent(
            incident_id=incident.id,
            event_type="incident_status_changed",
            actor="api_user",
            details=json.dumps({"status": update.status}),
        )
    )
    db.commit()
    db.refresh(incident)
    return incident


@app.get("/incidents/{incident_id}/guidance", response_model=GuidanceView)
def incident_guidance(incident_id: int, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    guidance = retrieve_guidance(
        {
            "category": incident.category,
            "service": incident.service,
            "message": incident.message,
            "explanation": incident.explanation,
        }
    )
    return guidance.to_dict()


@app.get("/actions", response_model=list[ActionView])
def actions(status: str | None = None, db: Session = Depends(get_db)):
    query = select(ActionProposal).order_by(ActionProposal.requested_at.desc())
    if status:
        query = query.where(ActionProposal.status == status)
    return db.scalars(query).all()


@app.post("/incidents/{incident_id}/actions", response_model=ActionView, status_code=201)
def propose_action(incident_id: int, request: ActionRequest, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    proposal = ActionProposal(
        incident_id=incident.id,
        action=request.action,
        rationale=request.rationale,
        requested_by=request.requested_by,
    )
    db.add(proposal)
    db.flush()
    db.add(
        AuditEvent(
            incident_id=incident.id,
            action_id=proposal.id,
            event_type="action_proposed",
            actor=request.requested_by,
            details=json.dumps({"action": request.action, "rationale": request.rationale}),
        )
    )
    db.commit()
    db.refresh(proposal)
    return proposal


@app.post("/actions/{action_id}/decision", response_model=ActionView)
def decide_action(action_id: int, decision: ActionDecision, db: Session = Depends(get_db)):
    proposal = db.get(ActionProposal, action_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Action proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Action proposal has already been decided")
    proposal.status = decision.decision
    proposal.decided_by = decision.decided_by
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decision_reason = decision.reason
    db.add(
        AuditEvent(
            incident_id=proposal.incident_id,
            action_id=proposal.id,
            event_type=f"action_{decision.decision}",
            actor=decision.decided_by,
            details=json.dumps({"reason": decision.reason}),
        )
    )
    db.commit()
    db.refresh(proposal)
    return proposal


@app.get("/audit-events", response_model=list[AuditEventView])
def audit_events(limit: int = 100, db: Session = Depends(get_db)):
    safe_limit = min(max(limit, 1), 200)
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(safe_limit)
    return db.scalars(query).all()
