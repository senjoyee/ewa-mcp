"""Shared Pydantic models for EWA MCP system."""

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


class Citation(BaseModel):
    """Grounding contract for all MCP tool responses."""
    doc_id: str = Field(..., description="Document ID")
    section_path: str = Field(..., description="Hierarchical section path")
    page_range: str = Field(..., description="Page range (e.g., '1-3' or '5')")
    page_start: Optional[int] = Field(None, description="Starting page number")
    page_end: Optional[int] = Field(None, description="Ending page number")
    chunk_id: Optional[str] = Field(None, description="Chunk ID in search index")
    source_url: Optional[str] = Field(None, description="Source document URL")
    quote: Optional[str] = Field(None, description="Evidence snippet")


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


class Chunk(BaseModel):
    """Document chunk for vector search."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    doc_id: str = Field(..., description="Parent document ID")
    customer_id: str = Field(..., description="Customer tenant ID")
    sid: str = Field(..., description="SAP System ID")
    environment: Optional[str] = Field(None, description="System environment")
    report_date: Optional[datetime] = Field(None, description="Report generation date")
    section_path: str = Field(..., description="Hierarchical section path")
    page_start: int = Field(..., description="Starting page")
    page_end: int = Field(..., description="Ending page")
    severity: Optional[Severity] = Field(None)
    category: Optional[Category] = Field(None)
    sap_note_ids: List[str] = Field(default_factory=list)
    content_md: str = Field(..., description="Markdown content")
    content_vector: Optional[List[float]] = Field(None, description="Embedding vector")
    parent_chunk_id: Optional[str] = Field(None, description="Parent chunk for hierarchy")


class Document(BaseModel):
    """EWA Document metadata."""
    doc_id: str = Field(..., description="Unique document ID")
    customer_id: str = Field(..., description="Customer tenant ID")
    sid: str = Field(..., description="SAP System ID")
    environment: Optional[str] = Field(None, description="System environment")
    report_date: Optional[datetime] = Field(None, description="Report date")
    analysis_from: Optional[datetime] = Field(None, description="Analysis period start")
    analysis_to: Optional[datetime] = Field(None, description="Analysis period end")
    title: Optional[str] = Field(None, description="Report title")
    file_name: str = Field(..., description="Original filename")
    pages: int = Field(..., description="Number of pages")
    sha256: str = Field(..., description="File hash")
    source_url: Optional[str] = Field(None, description="Blob storage URL")
    processing_status: str = Field(default="pending", description="Processing status")
    alert_count: Optional[int] = Field(None, description="Number of alerts extracted")


class ProcessingEvent(BaseModel):
    """Event Grid event for processing status."""
    event_type: str = Field(..., description="Event type (Started/Completed/Failed)")
    subject: str = Field(..., description="Event subject path")
    customer_id: str = Field(..., description="Customer tenant ID")
    doc_id: str = Field(..., description="Document ID")
    sid: Optional[str] = Field(None, description="SAP System ID")
    filename: str = Field(..., description="Original filename")
    stage: Optional[str] = Field(None, description="Current processing stage")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
