"""get_alert_overview tool - Get all alerts from a report."""

import json
from typing import TYPE_CHECKING
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="get_alert_overview",
        description="Get overview of all alerts in a specific EWA report",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "doc_id"],
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
                "include_info": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include info-level alerts"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute get_alert_overview tool."""
    customer_id = arguments["customer_id"]
    doc_id = arguments["doc_id"]
    include_info = arguments.get("include_info", True)
    
    # Get all alerts for the document
    alerts = await search_client.get_alerts(
        customer_id=customer_id,
        doc_id=doc_id
    )
    
    # Filter out info if requested
    if not include_info:
        alerts = [a for a in alerts if a.severity.value != "info"]
    
    # Group by severity
    severity_groups = {}
    for alert in alerts:
        sev = alert.severity.value
        if sev not in severity_groups:
            severity_groups[sev] = []
        severity_groups[sev].append(alert)
    
    # Sort severity order
    severity_order = ["very_high", "high", "medium", "low", "info", "unknown"]
    
    result = {
        "doc_id": doc_id,
        "total_alerts": len(alerts),
        "severity_summary": {},
        "alerts": []
    }
    
    # Build summary
    for sev in severity_order:
        count = len(severity_groups.get(sev, []))
        if count > 0:
            result["severity_summary"][sev] = count
    
    # Build alert list with citations
    for alert in alerts:
        alert_info = {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "page_range": alert.page_range,
            "section_path": alert.section_path,
            "sap_note_ids": alert.sap_note_ids,
            "description": alert.description,
            "citation": {
                "doc_id": alert.doc_id,
                "section_path": alert.section_path,
                "page_range": alert.page_range,
                "page_start": alert.page_start,
                "page_end": alert.page_end
            }
        }
        result["alerts"].append(alert_info)
    
    return json.dumps(result, indent=2)
