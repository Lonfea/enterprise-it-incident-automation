# Enterprise IT Incident Automation

[![CI](https://github.com/Lonfea/enterprise-it-incident-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/Lonfea/enterprise-it-incident-automation/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Deployment-Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An end-to-end IT operations workflow that turns server logs into prioritised, routed and SLA-tracked incidents. The project is designed as a realistic portfolio demonstration of **IT automation, data analytics and service operations**.

## Business problem

Operations teams receive thousands of log events. Manual triage delays restoration and makes SLA breaches more likely. This system automates the first-response workflow while keeping every decision explainable.

```mermaid
flowchart LR
    A[Server logs] --> B[Parser and features]
    B --> C[Anomaly detection]
    C --> D[Priority and routing]
    D --> E[(Incident database)]
    E --> F[FastAPI]
    E --> G[Operations dashboard]
    D --> H[Teams webhook]
```

## What is automated

- Parses semi-structured enterprise logs into consistent events.
- Uses Isolation Forest plus transparent rules to detect abnormal events.
- Classifies incidents into authentication, database, network, storage or application queues.
- Calculates severity from anomaly score, event level and repeated failures.
- Applies configurable SLA deadlines and highlights breaches.
- Sends an optional Microsoft Teams-compatible webhook notification.
- Exposes incidents through a REST API and an interactive dashboard.
- Runs quality checks automatically with GitHub Actions.

## Data

The included sample makes the repository runnable immediately. For a real operational benchmark, the downloader uses the **HDFS log dataset from LogHub**, collected from a Hadoop Distributed File System cluster rather than manufactured help-desk records.

```bash
python scripts/download_hdfs.py
python -m src.pipeline --input data/HDFS_2k.log
```

Dataset source: [LogPAI/LogHub](https://github.com/logpai/loghub)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.pipeline --input data/sample_system.log
uvicorn src.api:app --reload
```

In a second terminal:

```bash
streamlit run dashboard/app.py
```

- API documentation: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

Or run everything with Docker:

```bash
docker compose up --build
```

## API examples

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/incidents?status=open&priority=P1"
curl -X PATCH http://localhost:8000/incidents/1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"resolved"}'
```

## Architecture decisions

| Decision | Reason |
|---|---|
| Hybrid ML + rules | Anomaly scores provide coverage; rules make routing auditable. |
| SQLite by default | Recruiters can run the demo without infrastructure. |
| PostgreSQL-ready SQLAlchemy | The same data model can support production deployment. |
| Optional webhook | Demonstrates integration without requiring private credentials. |
| Configurable SLA policy | Separates operational policy from application code. |

Set `DATABASE_URL` to a PostgreSQL connection string or `TEAMS_WEBHOOK_URL` to enable notifications. Never commit credentials.

## Repository structure

```text
src/                 parsing, detection, routing, persistence and API
dashboard/           Streamlit operations dashboard
scripts/             real dataset downloader
tests/               automated tests
data/                 small runnable demonstration log
.github/workflows/    continuous integration
```

## Responsible use

The model supports human operators; it does not autonomously execute remediation commands. Production use requires access control, encrypted secrets, audit logging, drift monitoring and organisation-specific validation.

## Roadmap

- Add live Kafka/MQTT ingestion
- Connect Microsoft Graph/ServiceNow sandbox adapters
- Add operator feedback and model monitoring
- Package an infrastructure-as-code deployment

## Author

**Berkant Duman** — MSc student in Business Management, Data Analytics and Artificial Intelligence at Steinbeis University, Berlin.

## License

MIT
