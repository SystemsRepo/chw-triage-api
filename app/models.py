from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid

class TriageRecord(Base):
    __tablename__ = "triage_records"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id       = Column(String, unique=True, index=True, nullable=False)
    chw_id          = Column(String, index=True, nullable=False)
    community_id    = Column(String, index=True, nullable=False)
    decision        = Column(String, nullable=False)
    confidence      = Column(String, nullable=False)
    fallback_used   = Column(Boolean, default=False)
    ai_model_used   = Column(String)
    raw_report      = Column(Text)   # full JSON of the incoming report
    raw_result      = Column(Text)   # full JSON of the triage result
    created_at      = Column(DateTime, default=datetime.utcnow)
