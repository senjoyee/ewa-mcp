"""get_section tool - Retrieve specific document section."""

import json
from typing import TYPE_CHECKING
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="get_section",
        description="Retrieve a specific section from an EWA report by section path",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "doc_id", "section_path"],
            "properties": {
                "customer_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Customer tenant ID"
                },
                "doc_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Document/report ID"
                },
                "section_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Hierarchical section path (e.g., '1. Overview/1.1 Hardware')"
                },
                "top_n_chunks": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 20,
                    "description": "Maximum chunks to return"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute get_section tool."""
    customer_id = arguments["customer_id"]
    doc_id = arguments["doc_id"]
    section_path = arguments["section_path"]
    top_n = arguments.get("top_n_chunks", 20)
    
    # Get chunks for the section
    chunks = await search_client.get_chunks(
        customer_id=customer_id,
        doc_id=doc_id,
        section_path=section_path,
        top_n=top_n
    )
    
    if not chunks:
        # Try partial match
        chunks = await search_client.get_chunks(
            customer_id=customer_id,
            doc_id=doc_id,
            top_n=top_n
        )
        # Filter by section path contains
        chunks = [c for c in chunks if section_path.lower() in c.section_path.lower()]
    
    result = {
        "doc_id": doc_id,
        "section_path": section_path,
        "chunks_found": len(chunks),
        "chunks": []
    }
    
    for chunk in chunks:
        chunk_info = {
            "chunk_id": chunk.chunk_id,
            "section_path": chunk.section_path,
            "page_range": f"{chunk.page_start}-{chunk.page_end}",
            "header_level": chunk.header_level,
            "content": chunk.content_md,
            "citation": {
                "doc_id": chunk.doc_id,
                "section_path": chunk.section_path,
                "page_range": f"{chunk.page_start}-{chunk.page_end}",
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_id": chunk.chunk_id,
                "quote": chunk.content_md[:200] if chunk.content_md else ""
            }
        }
        result["chunks"].append(chunk_info)
    
    return json.dumps(result, indent=2)
