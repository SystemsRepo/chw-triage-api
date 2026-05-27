from pydantic import BaseModel, field_validator
from enum import Enum
from datetime import datetime
from typing import Optional

class TriageDecision(str, Enum):
    REFER_EMERGENCY = "REFER_EMERGENCY"
    REFER_ROUTINE   = "REFER_ROUTINE"
    TREAT_IN_PLACE  = "TREAT_IN_PLACE"
    ESCALATE        = "ESCALATE"

class PatientReport(BaseModel):
    """
    CHW patient report submitted at point of care.
    Maps to FHIR Encounter resource with embedded Observation resources.
    """
    report_id:          str
    chw_id:             str
    community_id:       str
    patient_age_months: int
    chief_complaint:    str
    temperature_c:      Optional[float] = None
    muac_mm:            Optional[float] = None
    respiratory_rate:   Optional[int]   = None
    additional_notes:   str = ""
    submitted_at:       datetime = datetime.utcnow()

    @field_validator("muac_mm")
    @classmethod
    def validate_muac(cls, v):
        if v is not None and not (60 <= v <= 250):
            raise ValueError(f"MUAC {v}mm outside plausible range (60–250mm). Check measurement.")
        return v

    @field_validator("temperature_c")
    @classmethod
    def validate_temp(cls, v):
        if v is not None and not (30.0 <= v <= 43.0):
            raise ValueError(f"Temperature {v}°C outside plausible range (30–43°C). Check reading.")
        return v

    @field_validator("patient_age_months")
    @classmethod
    def validate_age(cls, v):
        if v < 0 or v > 1800:
            raise ValueError(f"Age {v} months is not plausible.")
        return v

class TriageResult(BaseModel):
    """
    Structured triage output — Pydantic-enforced to prevent hallucination.
    Maps to FHIR ClinicalImpression resource.
    """
    report_id:      str
    decision:       TriageDecision
    reasoning:      str
    red_flags:      list[str]
    action_steps:   list[str]
    confidence:     str
    dq_flags:       list[str] = []
    ai_model_used:  str
    fallback_used:  bool = False
    processed_at:   datetime = datetime.utcnow()
