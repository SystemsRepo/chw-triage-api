import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.schemas import PatientReport, TriageResult, TriageDecision
from app.triage import triage_patient
import asyncio

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_pydantic_rejects_invalid_muac():
    """MUAC outside 60-250mm range must be rejected at validation."""
    data = {
        "report_id": "TEST-001",
        "chw_id": "CHW-001",
        "community_id": "CMT-001",
        "patient_age_months": 18,
        "chief_complaint": "fever",
        "muac_mm": 20  # impossible value — should fail
    }
    report = client.post("/triage", json=data)
    assert report.status_code == 422

def test_pydantic_rejects_invalid_temperature():
    data = {
        "report_id": "TEST-002",
        "chw_id": "CHW-001",
        "community_id": "CMT-001",
        "patient_age_months": 18,
        "chief_complaint": "fever",
        "temperature_c": 55.0  # impossible — should fail
    }
    response = client.post("/triage", json=data)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_fallback_when_no_api_key():
    """When ANTHROPIC_API_KEY is absent, system should return ESCALATE gracefully."""
    with patch.dict("os.environ", {}, clear=True):
        # Remove API key to simulate offline/unavailable
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        report = PatientReport(
            report_id="TEST-FALLBACK-001",
            chw_id="CHW-099",
            community_id="CMT-TEST",
            patient_age_months=12,
            chief_complaint="fast breathing"
        )
        result = await triage_patient(report)
        assert result.decision == TriageDecision.ESCALATE
        assert result.fallback_used is True
        assert result.ai_model_used == "fallback-no-ai"
        # Data quality flags — respiratory_rate not recorded
        assert "respiratory_rate_not_recorded" in result.dq_flags
