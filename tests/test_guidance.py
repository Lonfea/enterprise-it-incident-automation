from src.guidance import retrieve_guidance


def test_database_incident_retrieves_database_runbook():
    guidance = retrieve_guidance(
        {
            "category": "database",
            "service": "orders-db",
            "message": "Connection pool exhausted after SQL timeout",
            "explanation": "Database indicators detected",
        }
    )
    assert guidance.runbook_id == "RB-DB-001"
    assert guidance.requires_human_approval
    assert guidance.relevance_score > 0


def test_storage_incident_never_recommends_unapproved_deletion():
    guidance = retrieve_guidance(
        {
            "category": "storage",
            "service": "hdfs",
            "message": "Disk full and volume unavailable",
        }
    )
    assert guidance.runbook_id == "RB-STORAGE-001"
    assert any("approval" in safeguard.lower() for safeguard in guidance.safeguards)
