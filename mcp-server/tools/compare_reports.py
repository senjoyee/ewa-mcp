"""compare_reports tool - Compare alerts between two reports."""

import json
from typing import TYPE_CHECKING
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="compare_reports",
        description="Compare alerts between two EWA reports to identify changes",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "sid", "doc_id_a", "doc_id_b"],
            "properties": {
                "customer_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Customer tenant ID"
                },
                "sid": {
                    "type": "string",
                    "minLength": 1,
                    "description": "SAP System ID"
                },
                "doc_id_a": {
                    "type": "string",
                    "minLength": 1,
                    "description": "First report ID"
                },
                "doc_id_b": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Second report ID"
                },
                "include_info": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include info-level alerts in comparison"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute compare_reports tool."""
    customer_id = arguments["customer_id"]
    sid = arguments["sid"]
    doc_id_a = arguments["doc_id_a"]
    doc_id_b = arguments["doc_id_b"]
    include_info = arguments.get("include_info", False)
    
    # Get alerts from both reports
    alerts_a = await search_client.get_alerts(customer_id, doc_id_a)
    alerts_b = await search_client.get_alerts(customer_id, doc_id_b)
    
    # Filter out info if requested
    if not include_info:
        alerts_a = [a for a in alerts_a if a.severity.value != "info"]
        alerts_b = [a for a in alerts_b if a.severity.value != "info"]
    
    # Create lookup by title
    alerts_a_by_title = {a.title.lower(): a for a in alerts_a}
    alerts_b_by_title = {a.title.lower(): a for a in alerts_b}
    
    # Find differences
    resolved = []  # In A but not in B
    new = []  # In B but not in A
    persisted = []  # In both
    severity_changed = []
    
    for alert_a in alerts_a:
        title_key = alert_a.title.lower()
        if title_key in alerts_b_by_title:
            alert_b = alerts_b_by_title[title_key]
            persisted.append({
                "alert": alert_b,
                "previous_severity": alert_a.severity.value,
                "current_severity": alert_b.severity.value
            })
            
            if alert_a.severity != alert_b.severity:
                severity_changed.append({
                    "title": alert_b.title,
                    "category": alert_b.category.value,
                    "from_severity": alert_a.severity.value,
                    "to_severity": alert_b.severity.value,
                    "page_range": alert_b.page_range
                })
        else:
            resolved.append(alert_a)
    
    for alert_b in alerts_b:
        title_key = alert_b.title.lower()
        if title_key not in alerts_a_by_title:
            new.append(alert_b)
    
    # Build result
    result = {
        "comparison": {
            "report_a": doc_id_a,
            "report_b": doc_id_b,
            "sid": sid,
            "alert_count_a": len(alerts_a),
            "alert_count_b": len(alerts_b)
        },
        "summary": {
            "resolved_count": len(resolved),
            "new_count": len(new),
            "persisted_count": len(persisted),
            "severity_changed_count": len(severity_changed)
        },
        "resolved_alerts": [
            {
                "alert_id": a.alert_id,
                "title": a.title,
                "severity": a.severity.value,
                "category": a.category.value,
                "citation": {
                    "doc_id": a.doc_id,
                    "section_path": a.section_path,
                    "page_range": a.page_range
                }
            } for a in resolved
        ],
        "new_alerts": [
            {
                "alert_id": a.alert_id,
                "title": a.title,
                "severity": a.severity.value,
                "category": a.category.value,
                "description": a.description,
                "recommendation": a.recommendation,
                "citation": {
                    "doc_id": a.doc_id,
                    "section_path": a.section_path,
                    "page_range": a.page_range
                }
            } for a in new
        ],
        "severity_changes": severity_changed,
        "persisted_alerts": [
            {
                "title": p["alert"].title,
                "category": p["alert"].category.value,
                "severity": p["current_severity"],
                "citation": {
                    "doc_id": p["alert"].doc_id,
                    "section_path": p["alert"].section_path,
                    "page_range": p["alert"].page_range
                }
            } for p in persisted
        ]
    }
    
    return json.dumps(result, indent=2)
