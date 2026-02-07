"""Tool implementations for EWA MCP server."""

from mcp_server.tools.list_reports import get_tool_definition, execute
from mcp_server.tools.get_alert_overview import get_tool_definition, execute
from mcp_server.tools.get_alert_detail import get_tool_definition, execute
from mcp_server.tools.get_section import get_tool_definition, execute
from mcp_server.tools.ask_ewa_scoped import get_tool_definition, execute
from mcp_server.tools.compare_reports import get_tool_definition, execute
from mcp_server.tools.generate_action_pack import get_tool_definition, execute

__all__ = [
    "list_reports",
    "get_alert_overview",
    "get_alert_detail",
    "get_section",
    "ask_ewa_scoped",
    "compare_reports",
    "generate_action_pack"
]
