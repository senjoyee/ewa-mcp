"""EWA MCP tool sub-package.

Each sub-module (list_reports, get_alert_overview, etc.) exposes:
  - get_tool_definition() -> mcp.types.Tool
  - execute(search_client, arguments) -> str  (JSON)

main.py imports each sub-module directly by name so no re-exports are
needed here. This file is intentionally minimal to avoid circular imports.
"""
