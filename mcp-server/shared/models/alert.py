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


class CheckOverviewRow(BaseModel):
    """Normalized row extracted from EWA Check Overview table."""

    check_id: str = Field(..., description="Unique check row identifier")
    customer_id: str = Field(..., description="Customer tenant ID")
    doc_id: str = Field(..., description="Document/report ID")
    sid: str = Field(..., description="SAP System ID")
    environment: Optional[str] = Field(None, description="System environment")
    report_date: Optional[datetime] = Field(None, description="Report generation date")
    row_type: str = Field(..., description="topic|subtopic")
    topic_name: str = Field(..., description="Topic column value")
    subtopic_name: Optional[str] = Field(None, description="Subtopic column value")
    topic_rating_raw: Optional[str] = Field(None, description="Raw symbol/text from topic rating column")
    subtopic_rating_raw: Optional[str] = Field(None, description="Raw symbol/text from subtopic rating column")
    topic_rating_normalized: Optional[str] = Field(None, description="red|yellow|green|grey|unknown")
    subtopic_rating_normalized: Optional[str] = Field(None, description="red|yellow|green|grey|unknown")
    priority_bucket: Optional[str] = Field(None, description="high|medium|ok|info|unknown")
    reference_page: Optional[str] = Field(None, description="Reference page to detailed section")
    reference_section: Optional[str] = Field(None, description="Reference section number/path")
    page_start: int = Field(..., description="Parsed page start from reference_page")
    page_end: int = Field(..., description="Parsed page end from reference_page")
    page_range: str = Field(..., description="Formatted reference page range")
    source_page: Optional[int] = Field(None, description="Page where row was detected")
    report_date: Optional[datetime] = Field(None, description="Processing date acquired from associated Document")
    sap_note_ids: List[str] = Field(default_factory=list, description="Referenced SAP notes")
    evidence_chunk_ids: List[str] = Field(default_factory=list, description="Linked evidence chunks")
    description: Optional[str] = Field(None, description="Optional visible description text")
    recommendation: Optional[str] = Field(None, description="Optional visible recommendation text")

    @property
    def alert_id(self) -> str:
        """Backward-compatible alias for check ID."""
        return self.check_id

    @property
    def title(self) -> str:
        """Derived display title for legacy alert-centric tool payloads."""
        if self.subtopic_name:
            return self.subtopic_name
        return self.topic_name

    @property
    def severity(self) -> Severity:
        """Backward-compatible severity from priority bucket."""
        bucket = (self.priority_bucket or "unknown").lower()
        try:
            return Severity(bucket)
        except ValueError:
            return Severity.UNKNOWN

    @property
    def category(self) -> Category:
        """Backward-compatible category projection (coarse)."""
        text = (self.topic_name or "").lower()
        if "security" in text:
            return Category.SECURITY
        if "performance" in text:
            return Category.PERFORMANCE
        if "stability" in text:
            return Category.STABILITY
        if "configuration" in text:
            return Category.CONFIGURATION
        if "lifecycle" in text or "maintenance" in text or "upgrade" in text:
            return Category.LIFECYCLE
        if "database" in text or "hana" in text:
            return Category.DATABASE
        if "bw" in text:
            return Category.BW
        return Category.UNKNOWN

    @property
    def section_path(self) -> str:
        """Backward-compatible section path."""
        if self.reference_section:
            return self.reference_section
        if self.subtopic_name:
            return f"{self.topic_name} / {self.subtopic_name}"
        return self.topic_name

    @property
    def tags(self) -> List[str]:
        """Backward-compatible tags list."""
        return []


class Alert(CheckOverviewRow):
    """Backward-compatible alias for tools still named around alerts."""
