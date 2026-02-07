"""Document chunk model for vector storage."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from .alert import Severity, Category


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
    content_vector: Optional[List[float]] = Field(None, description="Embedding vector (1536d)")
    parent_chunk_id: Optional[str] = Field(None, description="Parent chunk for hierarchy")
    header_level: Optional[int] = Field(None, description="Markdown header level (1-6)")


class ChunkSearchResult(BaseModel):
    """Result from vector search."""
    chunk: Chunk
    score: float
    reranker_score: Optional[float] = None
