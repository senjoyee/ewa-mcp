"""Citation/grounding model for MCP tool responses."""

from typing import Optional
from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Grounding contract for all MCP tool responses.
    
    Every factual response from MCP tools must include citations
    linking back to source documents.
    """
    doc_id: str = Field(..., description="Document ID")
    section_path: str = Field(..., description="Hierarchical section path")
    page_range: str = Field(..., description="Page range (e.g., '1-3' or '5')")
    page_start: Optional[int] = Field(None, description="Starting page number")
    page_end: Optional[int] = Field(None, description="Ending page number")
    chunk_id: Optional[str] = Field(None, description="Chunk ID in search index")
    source_url: Optional[str] = Field(None, description="Source document URL")
    quote: Optional[str] = Field(None, description="Evidence snippet")
