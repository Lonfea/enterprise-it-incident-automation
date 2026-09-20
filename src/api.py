from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Incident, SessionLocal, init_db

app = FastAPI(title="IT Incident Automation API", version="1.0.0")


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


def get_db():
    with SessionLocal() as session:
        yield session


@app.on_event("startup")
def startup() -> None:
    init_db()


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
    db.commit()
    db.refresh(incident)
    return incident
