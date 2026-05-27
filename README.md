# CHW Triage API

## Overview

AI-assisted triage for Community Health Workers (CHWs) in sub-Saharan Africa.

A CHW in the field submits a patient report via a mobile app. This API validates the data, calls Anthropic Claude for clinical reasoning using iCCM (Integrated Community Case Management) protocols, and returns a structured triage decision in under 2 seconds.

Built to demonstrate the architecture needed for LMH's HEP Assist-style systems: AI-recommended, human-confirmed, offline-resilient, audit-logged.

```
CHW Mobile App
     │
     ▼
POST /triage
     │
     ├─ Pydantic validation (data quality flags)
     │
     ├─ Anthropic Claude (claude-3-haiku)
     │   └─ iCCM protocol prompt
     │
     ├─ PostgreSQL audit log
     │
     └─ Structured TriageResult
          ├─ decision: REFER_EMERGENCY / REFER_ROUTINE / TREAT_IN_PLACE / ESCALATE
          ├─ reasoning (plain language for CHW)
          ├─ red_flags (specific danger signs)
          ├─ action_steps (what to do right now)
          ├─ confidence: HIGH / MEDIUM / LOW
          └─ dq_flags (data quality issues for MERL review)
```

## Key Design Decisions

**Offline resilience:** If Anthropic's API is unavailable (common in low-bandwidth field settings), the system returns `ESCALATE` with a clear supervisor referral instruction. The report is always saved. The CHW always gets a response.

**Data quality as a first-class concern:** Missing fields (no MUAC, no temperature) are flagged in `dq_flags` without blocking the submission. Clean data is a MERL concern; a patient in the field should not be turned away because of an incomplete form.

**Structured output enforced by Pydantic:** Claude's response is parsed and validated against `TriageResult`. If the model hallucinates an unexpected field or format, the fallback triggers — never a 500 error to the CHW.

**FHIR-aware data model:**
- `PatientReport` maps to FHIR `Encounter` + `Observation` resources
- `TriageResult` maps to FHIR `ClinicalImpression` resource

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (for PostgreSQL)
- Anthropic API key (optional — works without it in fallback mode)

### 1. Clone and install

```bash
git clone https://github.com/SystemsRepo/chw-triage-api.git
cd chw-triage-api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start PostgreSQL

```bash
docker-compose up -d db
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY
# Without it, the API still works (returns ESCALATE fallback)
```

### 4. Run

```bash
export $(cat .env | xargs)
uvicorn app.main:app --reload
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### 5. Test it

```bash
curl -X POST http://localhost:8000/triage \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "RPT-001",
    "chw_id": "CHW-047",
    "community_id": "CMT-BONG-003",
    "patient_age_months": 18,
    "chief_complaint": "fever and fast breathing for 2 days",
    "temperature_c": 39.1,
    "muac_mm": 118,
    "respiratory_rate": 52
  }'
```

Expected response:
```json
{
  "report_id": "RPT-001",
  "decision": "REFER_EMERGENCY",
  "reasoning": "Child presents with multiple danger signs: fast breathing (52/min exceeds 50/min threshold for age), elevated temperature, and MUAC below 125mm. Immediate facility referral required.",
  "red_flags": ["respiratory_rate > 50/min (danger sign)", "MUAC 118mm < 125mm threshold"],
  "action_steps": [
    "Give first dose of amoxicillin now if available",
    "Refer immediately to nearest health facility",
    "Do not delay for any reason",
    "Call ahead to facility if possible"
  ],
  "confidence": "HIGH",
  "dq_flags": [],
  "ai_model_used": "claude-3-haiku-20240307",
  "fallback_used": false
}
```

## Run with Docker Compose (full stack)

```bash
cp .env.example .env  # add ANTHROPIC_API_KEY
docker-compose up
```

## Run tests

```bash
pytest tests/ -v
```

## Project Structure

```
chw-triage-api/
├── app/
│   ├── main.py        # FastAPI app, endpoints, lifespan
│   ├── schemas.py     # Pydantic input/output models with validators
│   ├── triage.py      # Anthropic Claude integration + graceful fallback
│   ├── models.py      # SQLAlchemy PostgreSQL models
│   └── database.py    # DB session management
├── tests/
│   └── test_triage.py # Pytest: validation, fallback, data quality
├── .github/
│   └── workflows/ci.yml  # GitHub Actions: test + Docker build
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Production Architecture

For 30,000 CHWs submitting ~100,000 reports/month:

```
                    ┌─────────────────────────┐
CHW Android App ───▶│  AWS ALB + ACM (HTTPS)  │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  ECS Fargate             │
                    │  2–8 tasks (auto-scale)  │
                    │  0.5 vCPU / 1GB RAM each │
                    └──────────┬──────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
  ┌────────▼──────┐  ┌────────▼──────┐  ┌────────▼──────┐
  │ RDS PostgreSQL│  │ Anthropic API │  │ SQS Queue     │
  │ Multi-AZ      │  │ claude-haiku  │  │ (offline sync)│
  │ 7yr retention │  │ $8.75/month   │  └───────────────┘
  └───────────────┘  └───────────────┘

Offline sync flow:
  CHW device offline → SQLite local queue
  → POST /triage/batch on reconnect
  → Server processes via Celery + SQS
  → CHW polls GET /triage/{report_id}
```

**Cost at scale:**
- Claude 3 Haiku: $0.25/million tokens
- Average report: ~350 tokens (in + out)
- 100,000 reports/month = **$8.75/month**

## Context

Built as a portfolio project demonstrating the architecture needed for AI-assisted CHW tools in global health settings. The patterns — structured LLM output, offline resilience, data quality flagging, audit logging — are directly applicable to systems like [HEP Assist](https://lastmilehealth.org) (Last Mile Health's AI CHW decision support tool).
