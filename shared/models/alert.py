"""Alert models for SAP EarlyWatch Alert extraction."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Alert severity levels."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


class Category(str, Enum):
    """Alert categories."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    STABILITY = "stability"
    CONFIGURATION = "configuration"
    LIFECYCLE = "lifecycle"
    DATA_VOLUME = "data_volume"
    DATABASE = "database"
    BW = "bw"
    OTHER = "other"
    UNKNOWN = "unknown"


class Alert(BaseModel):
    """SAP EarlyWatch Alert model."""
    alert_id: str = Field(..., description="Unique alert identifier")
    customer_id: str = Field(..., description="Customer tenant ID")
    doc_id: str = Field(..., description="Document/report ID")
    sid: str = Field(..., description="SAP System ID")
    environment: Optional[str] = Field(None, description="System environment")
    report_date: Optional[datetime] = Field(None, description="Report generation date")
    title: str = Field(..., description="Alert title")
    severity: Severity = Field(default=Severity.UNKNOWN)
    category: Category = Field(default=Category.UNKNOWN)
    section_path: str = Field(..., description="Section path in document")
    page_start: int = Field(..., description="Starting page")
    page_end: int = Field(..., description="Ending page")
    page_range: str = Field(..., description="Formatted page range")
    evidence_chunk_ids: List[str] = Field(default_factory=list, description="Linked evidence chunks")
    sap_note_ids: List[str] = Field(default_factory=list, description="Referenced SAP notes")
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(None, description="Alert description")
    recommendation: Optional[str] = Field(None, description="Recommended action")


class AlertExtractionResult(BaseModel):
    """Result from GPT-5.2 Vision alert extraction."""
    alerts: List[Alert]
    pages_processed: int
    extraction_confidence: Optional[float] = None
