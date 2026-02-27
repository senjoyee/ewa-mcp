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
    reference_page: Optional[str] = Field(None, description="Reference page to detailed section")
    reference_section: Optional[str] = Field(None, description="Reference section number/path")
    page_start: int = Field(..., description="Parsed page start from reference_page")
    page_end: int = Field(..., description="Parsed page end from reference_page")
    page_range: str = Field(..., description="Formatted reference page range")
    source_page: Optional[int] = Field(None, description="Page where row was detected")
    evidence_chunk_ids: List[str] = Field(default_factory=list, description="Linked evidence chunks")


# Backward compatibility alias used across current pipeline/tooling imports.
class Alert(CheckOverviewRow):
    """Compatibility alias for existing Alert references."""


class CheckOverviewExtractionResult(BaseModel):
    """Result from check overview extraction."""

    checks: List[CheckOverviewRow]
    pages_processed: int
    extraction_confidence: Optional[float] = None


# Backward compatibility alias used across current pipeline/tooling imports.
class AlertExtractionResult(CheckOverviewExtractionResult):
    """Compatibility alias for existing AlertExtractionResult references."""
