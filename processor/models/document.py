"""Document metadata model."""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


class Document(BaseModel):
    """EWA Document metadata."""

    doc_id: str = Field(..., description="Unique document ID (UUID)")
    customer_id: str = Field(..., description="Customer tenant ID")
    sid: str = Field(..., description="SAP System ID")
    analysis_from: Optional[date] = Field(None, description="Analysis period start date")
    analysis_to: Optional[date] = Field(None, description="Analysis period end date")
    title: Optional[str] = Field(None, description="Report title")
    file_name: str = Field(..., description="Original filename")
    pages: int = Field(default=0, description="Number of pages")
    sha256: str = Field(..., description="File SHA256 hash")
    product: Optional[str] = Field(None, description="SAP Product Name")
    db_system: Optional[str] = Field(None, description="Database System")
    installation_no: Optional[str] = Field(None, description="SAP Installation Number")
    processing_status: str = Field(
        default="pending",
        description="Processing status: pending/extracting/chunking/embedding/completed/failed",
    )
    alert_count: Optional[int] = Field(None, description="Number of alerts extracted")
    chunk_count: Optional[int] = Field(None, description="Number of chunks created")


class ProcessingEvent(BaseModel):
    """Event Grid event for processing status tracking."""

    event_type: str = Field(..., description="Event type: EwaProcessingStarted/EwaProcessingCompleted/EwaProcessingFailed")
    subject: str = Field(..., description="Event subject path /ewa/{customer_id}/{doc_id}")
    customer_id: str = Field(..., description="Customer tenant ID")
    doc_id: str = Field(..., description="Document ID")
    sid: Optional[str] = Field(None, description="SAP System ID")
    filename: str = Field(..., description="Original filename")
    stage: Optional[str] = Field(None, description="Current processing stage")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
