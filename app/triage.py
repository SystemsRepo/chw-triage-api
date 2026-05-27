import anthropic
import json
import os
from app.schemas import PatientReport, TriageResult, TriageDecision

SYSTEM_PROMPT = """
You are a clinical decision support assistant for community health workers (CHWs)
trained in Integrated Community Case Management (iCCM) in sub-Saharan Africa.

Rules:
1. Base decisions ONLY on the information provided. Never invent symptoms.
2. When in doubt, choose ESCALATE — a false escalation is safer than a missed referral.
3. REFER_EMERGENCY for: convulsions, unconsciousness, inability to drink/breastfeed,
   stridor, severe acute malnutrition (MUAC <115mm), very fast breathing, high fever >39.5°C,
   chest in-drawing, or any sign of severe illness.
4. REFER_ROUTINE for: fast breathing without emergency signs, fever without danger signs,
   diarrhoea without dehydration signs, MUAC 115–125mm.
5. TREAT_IN_PLACE for: uncomplicated fever, mild diarrhoea, minor upper respiratory illness.
6. Output MUST be valid JSON matching the specified schema exactly.
"""

def build_prompt(report: PatientReport) -> str:
    return f"""Evaluate this CHW patient report and return a triage decision as JSON.

Patient details:
- Age: {report.patient_age_months} months old
- Chief complaint: {report.chief_complaint}
- Temperature: {f"{report.temperature_c}°C" if report.temperature_c else "not recorded"}
- MUAC (mid-upper arm circumference): {f"{report.muac_mm}mm" if report.muac_mm else "not recorded"}
- Respiratory rate: {f"{report.respiratory_rate}/min" if report.respiratory_rate else "not recorded"}
- Additional notes: {report.additional_notes or "none"}

Return a JSON object with EXACTLY these fields:
{{
  "decision": "REFER_EMERGENCY" | "REFER_ROUTINE" | "TREAT_IN_PLACE" | "ESCALATE",
  "reasoning": "2-3 sentences in plain language a CHW can understand",
  "red_flags": ["list of specific danger signs found, empty list if none"],
  "action_steps": ["numbered steps the CHW should take right now"],
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}}

Return only the JSON object. No markdown, no explanation outside the JSON.
"""

async def triage_patient(report: PatientReport) -> TriageResult:
    """Call Anthropic Claude to triage a CHW patient report. Degrades gracefully if unavailable."""
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_prompt(report)}]
            )
            raw = message.content[0].text.strip()
            # Strip markdown code fences if model wraps in ```json ... ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            return TriageResult(
                report_id=report.report_id,
                ai_model_used="claude-3-haiku-20240307",
                dq_flags=_check_data_quality(report),
                **data
            )
        except json.JSONDecodeError:
            pass  # fall through to fallback
        except Exception:
            pass  # network error, rate limit, etc.

    # Graceful fallback — NEVER crash, NEVER lose the report
    return TriageResult(
        report_id=report.report_id,
        decision=TriageDecision.ESCALATE,
        reasoning="AI system temporarily unavailable. Report has been saved. Escalate to supervisor for manual clinical review.",
        red_flags=[],
        action_steps=[
            "Contact your supervisor immediately with this report",
            "Do not attempt treatment without clinical guidance",
            "Record the report ID for follow-up: " + report.report_id
        ],
        confidence="LOW",
        dq_flags=_check_data_quality(report),
        ai_model_used="fallback-no-ai",
        fallback_used=True
    )

def _check_data_quality(report: PatientReport) -> list[str]:
    """Flag data quality issues for MERL review without blocking the submission."""
    flags = []
    if report.temperature_c is None:
        flags.append("temperature_not_recorded")
    if report.muac_mm is None and report.patient_age_months >= 6:
        flags.append("muac_not_recorded_for_age_group")
    if report.respiratory_rate is None:
        flags.append("respiratory_rate_not_recorded")
    if len(report.chief_complaint.strip()) < 5:
        flags.append("chief_complaint_too_brief")
    return flags
