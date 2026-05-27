from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from app.schemas import PatientReport, TriageResult
from app.triage import triage_patient
from app.database import engine, Base, get_db
from app import models
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="CHW Triage API",
    description="""
AI-assisted triage for Community Health Workers (CHWs) in sub-Saharan Africa.

**What it does:**
A CHW submits a patient report from the field. Pydantic validates the data quality.
Anthropic Claude (claude-3-haiku) evaluates clinical urgency using iCCM protocols.
A structured triage decision is returned and persisted to PostgreSQL.

**Offline behaviour:**
If Claude is unavailable (no internet, API outage), the system returns an ESCALATE decision
rather than crashing. The report is always persisted. The CHW always gets a response.

**FHIR mapping:**
- `PatientReport` → FHIR Encounter + Observation resources
- `TriageResult` → FHIR ClinicalImpression resource

**Data quality:**
Missing fields are flagged as `dq_flags` without blocking submission — clean data is a
MERL concern, not a reason to lose a patient report.
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/triage", response_model=TriageResult, tags=["Triage"])
async def triage_endpoint(report: PatientReport, db: Session = Depends(get_db)):
    """
    Evaluate a CHW patient report and return a triage decision.

    - Validates data quality (MUAC range, temperature range, age)
    - Calls Anthropic Claude for clinical reasoning
    - Returns REFER_EMERGENCY / REFER_ROUTINE / TREAT_IN_PLACE / ESCALATE
    - Degrades gracefully if AI unavailable (returns ESCALATE, never crashes)
    - Logs every report and decision to PostgreSQL for audit trail
    """
    result = await triage_patient(report)

    db_record = models.TriageRecord(
        report_id=result.report_id,
        chw_id=report.chw_id,
        community_id=report.community_id,
        decision=result.decision,
        confidence=result.confidence,
        fallback_used=result.fallback_used,
        ai_model_used=result.ai_model_used,
        raw_report=report.model_dump_json(),
        raw_result=result.model_dump_json(),
    )
    db.add(db_record)
    db.commit()

    return result

@app.get("/triage/{report_id}", tags=["Triage"])
def get_triage_result(report_id: str, db: Session = Depends(get_db)):
    """Retrieve a previously submitted triage result by report ID."""
    record = db.query(models.TriageRecord).filter(
        models.TriageRecord.report_id == report_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {
        "report_id": record.report_id,
        "decision": record.decision,
        "confidence": record.confidence,
        "fallback_used": record.fallback_used,
        "ai_model_used": record.ai_model_used,
        "created_at": record.created_at
    }

@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "chw-triage-api"}

@app.get("/", tags=["System"])
async def root():
    return {"message": "CHW Triage API — see /docs for usage"}
