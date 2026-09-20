from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///incidents.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    anomaly_score: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(50))
    assigned_team: Mapped[str] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(4), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    explanation: Mapped[str] = mapped_column(Text)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def init_db() -> None:
    Base.metadata.create_all(engine)
