from datetime import datetime, timezone
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

st.set_page_config(page_title="IT Operations Control Centre", page_icon="⚙️", layout="wide")
st.title("IT Operations Control Centre")
st.caption("Automated anomaly detection, incident routing and SLA monitoring")

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///incidents.db"))
try:
    incidents = pd.read_sql("SELECT * FROM incidents ORDER BY created_at DESC", engine)
except Exception:
    st.info("Run `python -m src.pipeline --input data/sample_system.log` to create incidents.")
    st.stop()

if incidents.empty:
    st.info("No incidents detected.")
    st.stop()

incidents["sla_deadline"] = pd.to_datetime(incidents["sla_deadline"], utc=True)
incidents["sla_breached"] = (incidents["status"] != "resolved") & (incidents["sla_deadline"] < datetime.now(timezone.utc))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Open incidents", int((incidents.status != "resolved").sum()))
c2.metric("Critical P1", int((incidents.priority == "P1").sum()))
c3.metric("SLA breaches", int(incidents.sla_breached.sum()))
c4.metric("Services affected", incidents.service.nunique())

left, right = st.columns(2)
left.subheader("Incidents by priority")
left.bar_chart(incidents.priority.value_counts())
right.subheader("Incidents by support team")
right.bar_chart(incidents.assigned_team.value_counts())

st.subheader("Incident queue")
st.dataframe(
    incidents[["id", "priority", "status", "service", "category", "assigned_team", "message", "anomaly_score", "sla_deadline", "sla_breached"]],
    use_container_width=True,
    hide_index=True,
)
