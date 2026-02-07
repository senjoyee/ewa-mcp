"""get_alert_detail tool - Get detailed alert with evidence."""

import json
from typing import TYPE_CHECKING
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="get_alert_detail",
        description="Get detailed alert information with supporting evidence chunks",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "doc_id", "alert_id"],
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
                "alert_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Alert ID"
                },
                "max_evidence_snippets": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 8,
                    "description": "Maximum evidence chunks to return"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute get_alert_detail tool."""
    customer_id = arguments["customer_id"]
    doc_id = arguments["doc_id"]
    alert_id = arguments["alert_id"]
    max_evidence = arguments.get("max_evidence_snippets", 8)
    
    # Get alert
    alert = await search_client.get_alert(customer_id, doc_id, alert_id)
    
    if not alert:
        return json.dumps({"error": "Alert not found"}, indent=2)
    
    # Get evidence chunks
    evidence_chunks = []
    if alert.evidence_chunk_ids:
        chunks = await search_client.get_chunks(
            customer_id=customer_id,
            chunk_ids=alert.evidence_chunk_ids[:max_evidence]
        )
        
        for chunk in chunks:
            evidence_chunks.append({
                "chunk_id": chunk.chunk_id,
                "section_path": chunk.section_path,
                "page_range": f"{chunk.page_start}-{chunk.page_end}",
                "content_snippet": chunk.content_md[:500] + "..." if len(chunk.content_md) > 500 else chunk.content_md,
                "citation": {
                    "doc_id": chunk.doc_id,
                    "section_path": chunk.section_path,
                    "page_range": f"{chunk.page_start}-{chunk.page_end}",
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chunk_id": chunk.chunk_id,
                    "quote": chunk.content_md[:200]
                }
            })
    
    result = {
        "alert": {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "description": alert.description,
            "recommendation": alert.recommendation,
            "page_range": alert.page_range,
            "section_path": alert.section_path,
            "sap_note_ids": alert.sap_note_ids,
            "citation": {
                "doc_id": alert.doc_id,
                "section_path": alert.section_path,
                "page_range": alert.page_range,
                "page_start": alert.page_start,
                "page_end": alert.page_end
            }
        },
        "evidence_count": len(evidence_chunks),
        "evidence_snippets": evidence_chunks
    }
    
    return json.dumps(result, indent=2)
