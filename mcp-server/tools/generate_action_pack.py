"""generate_action_pack tool - Generate deliverable action package."""

import json
from typing import TYPE_CHECKING, List
from mcp.types import Tool

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient
    from shared.models.alert import Alert


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="generate_action_pack",
        description="Generate a structured action package from selected alerts",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "doc_id", "alert_ids"],
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
                "alert_ids": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                    "description": "List of alert IDs to include"
                },
                "format": {
                    "type": "string",
                    "enum": ["md", "json"],
                    "default": "md",
                    "description": "Output format"
                },
                "include_evidence": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include evidence snippets"
                },
                "max_evidence_snippets_per_alert": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "Max evidence chunks per alert"
                }
            }
        }
    )


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute generate_action_pack tool."""
    customer_id = arguments["customer_id"]
    doc_id = arguments["doc_id"]
    alert_ids = arguments["alert_ids"]
    output_format = arguments.get("format", "md")
    include_evidence = arguments.get("include_evidence", True)
    max_evidence = arguments.get("max_evidence_snippets_per_alert", 5)
    
    # Get all alerts for the document
    all_alerts = await search_client.get_alerts(customer_id, doc_id)
    
    # Filter selected alerts
    selected_alerts = [a for a in all_alerts if a.alert_id in alert_ids]
    
    if not selected_alerts:
        return json.dumps({"error": "No alerts found for the provided IDs"}, indent=2)
    
    # Group by severity
    severity_order = ["very_high", "high", "medium", "low", "info"]
    alerts_by_severity = {sev: [] for sev in severity_order}
    
    for alert in selected_alerts:
        sev = alert.severity.value
        if sev in alerts_by_severity:
            alerts_by_severity[sev].append(alert)
    
    # Build action pack
    action_pack = {
        "title": f"Action Pack - {len(selected_alerts)} Selected Alerts",
        "doc_id": doc_id,
        "generated_at": "",
        "summary": {
            "total_alerts": len(selected_alerts),
            "by_severity": {sev: len(alerts) for sev, alerts in alerts_by_severity.items() if alerts}
        },
        "alerts": []
    }
    
    for alert in selected_alerts:
        alert_data = {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "page_range": alert.page_range,
            "section_path": alert.section_path,
            "description": alert.description,
            "recommendation": alert.recommendation,
            "sap_note_ids": alert.sap_note_ids,
            "citation": {
                "doc_id": alert.doc_id,
                "section_path": alert.section_path,
                "page_range": alert.page_range,
                "page_start": alert.page_start,
                "page_end": alert.page_end
            }
        }
        
        # Include evidence if requested
        if include_evidence and alert.evidence_chunk_ids:
            chunks = await search_client.get_chunks(
                customer_id=customer_id,
                chunk_ids=alert.evidence_chunk_ids[:max_evidence]
            )
            
            alert_data["evidence"] = [
                {
                    "chunk_id": c.chunk_id,
                    "section_path": c.section_path,
                    "page_range": f"{c.page_start}-{c.page_end}",
                    "content_snippet": c.content_md[:500] + "..." if len(c.content_md) > 500 else c.content_md,
                    "citation": {
                        "doc_id": c.doc_id,
                        "section_path": c.section_path,
                        "page_range": f"{c.page_start}-{c.page_end}",
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "chunk_id": c.chunk_id,
                        "quote": c.content_md[:200] if c.content_md else ""
                    }
                }
                for c in chunks
            ]
        
        action_pack["alerts"].append(alert_data)
    
    # Format output
    if output_format == "md":
        return _format_as_markdown(action_pack, selected_alerts)
    else:
        return json.dumps(action_pack, indent=2)


def _format_as_markdown(action_pack: dict, alerts: List) -> str:
    """Format action pack as markdown document."""
    lines = [
        "# EWA Action Pack",
        "",
        f"**Document ID:** {action_pack['doc_id']}",
        f"**Total Alerts:** {action_pack['summary']['total_alerts']}",
        "",
        "## Summary by Severity",
        ""
    ]
    
    for sev, count in action_pack['summary']['by_severity'].items():
        emoji = {"very_high": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}.get(sev, "⚪")
        lines.append(f"- {emoji} **{sev.replace('_', ' ').title()}:** {count} alerts")
    
    lines.extend(["", "---", "", "## Action Items", ""])
    
    for alert_data in action_pack['alerts']:
        severity = alert_data['severity']
        emoji = {"very_high": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}.get(severity, "⚪")
        
        lines.extend([
            f"### {emoji} {alert_data['title']}",
            "",
            f"**Severity:** {severity.replace('_', ' ').title()}",
            f"**Category:** {alert_data['category'].title()}",
            f"**Location:** Page {alert_data['page_range']}, Section: {alert_data['section_path']}",
            ""
        ])
        
        if alert_data.get('description'):
            lines.extend(["**Description:**", alert_data['description'], ""])
        
        if alert_data.get('recommendation'):
            lines.extend(["**Recommended Action:**", alert_data['recommendation'], ""])
        
        if alert_data.get('sap_note_ids'):
            lines.append(f"**SAP Notes:** {', '.join(alert_data['sap_note_ids'])}")
            lines.append("")
        
        if alert_data.get('evidence'):
            lines.extend(["**Supporting Evidence:**", ""])
            for ev in alert_data['evidence'][:3]:  # Show top 3
                lines.extend([
                    f"- *{ev['section_path']} (Page {ev['page_range']}):*",
                    f"  > {ev['content_snippet'][:300]}..." if len(ev['content_snippet']) > 300 else f"  > {ev['content_snippet']}",
                    ""
                ])
        
        lines.extend(["---", ""])
    
    return "\n".join(lines)
