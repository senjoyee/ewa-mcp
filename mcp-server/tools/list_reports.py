"""list_reports tool - Query available EWA reports."""

import json
from typing import TYPE_CHECKING
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="list_reports",
        description="List available SAP EarlyWatch Alert reports for a customer",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id"],
            "properties": {
                "customer_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Customer tenant ID"
                },
                "sid": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Filter by SAP System ID"
                },
                "date_from": {
                    "type": "string",
                    "format": "date",
                    "description": "Filter reports from this date (YYYY-MM-DD)"
                },
                "date_to": {
                    "type": "string",
                    "format": "date",
                    "description": "Filter reports to this date (YYYY-MM-DD)"
                },
                "latest_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 10,
                    "description": "Return latest N reports"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute list_reports tool."""
    customer_id = arguments["customer_id"]
    sid = arguments.get("sid")
    date_from = arguments.get("date_from")
    date_to = arguments.get("date_to")
    latest_n = arguments.get("latest_n", 10)
    
    reports = await search_client.list_reports(
        customer_id=customer_id,
        sid=sid,
        date_from=date_from,
        date_to=date_to,
        latest_n=latest_n
    )
    
    result = {
        "count": len(reports),
        "reports": []
    }
    
    for r in reports:
        report_info = {
            "doc_id": r.doc_id,
            "sid": r.sid,
            "environment": r.environment,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "file_name": r.file_name,
            "pages": r.pages,
            "processing_status": r.processing_status,
            "alert_count": r.alert_count
        }
        result["reports"].append(report_info)
    
    return json.dumps(result, indent=2)
