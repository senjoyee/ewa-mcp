"""FastAPI MCP server with Streamable HTTP transport."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add shared models to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from mcp_server.auth.api_key import APIKeyMiddleware
from mcp_server.search.client import SearchClient
from mcp_server.tools import (
    list_reports,
    get_alert_overview,
    get_alert_detail,
    get_section,
    ask_ewa_scoped,
    compare_reports,
    generate_action_pack,
)

# ---------------------------------------------------------------------------
# Shared search client (initialised once at startup)
# ---------------------------------------------------------------------------

search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    api_key=os.environ["AZURE_SEARCH_API_KEY"],
)

# ---------------------------------------------------------------------------
# Tool registry: name → (definition_fn, execute_fn)
# ---------------------------------------------------------------------------

_TOOLS = [
    list_reports,
    get_alert_overview,
    get_alert_detail,
    get_section,
    ask_ewa_scoped,
    compare_reports,
    generate_action_pack,
]

_TOOL_MAP = {mod.get_tool_definition().name: mod for mod in _TOOLS}


def _all_tool_definitions() -> list:
    """Return a list of Tool objects for every registered tool."""
    return [mod.get_tool_definition() for mod in _TOOLS]


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager (no-op for now)."""
    yield


app = FastAPI(
    title="EWA MCP Server",
    description="SAP EarlyWatch Alert MCP Server with Azure AI Search",
    version="1.0.0",
    lifespan=lifespan,
)

# Add API key middleware
app.add_middleware(APIKeyMiddleware)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "server": "ewa-mcp"}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP Streamable HTTP JSON-RPC endpoint."""
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    # ── initialize ──────────────────────────────────────────────────────────
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ewa-mcp", "version": "1.0.0"},
            },
        }

    # ── tools/list ──────────────────────────────────────────────────────────
    if method == "tools/list":
        tools = _all_tool_definitions()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [t.model_dump() for t in tools]},
        }

    # ── tools/call ──────────────────────────────────────────────────────────
    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments") or {}

        tool_module = _TOOL_MAP.get(name)
        if tool_module is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }

        try:
            result_text = await tool_module.execute(search_client, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f'{{"error": "{e}"}}'}],
                    "isError": True,
                },
            }

    # ── unknown method ───────────────────────────────────────────────────────
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


@app.get("/mcp/sse")
async def mcp_sse():
    """Legacy SSE endpoint for backward compatibility."""
    async def event_generator():
        yield "event: endpoint\ndata: /mcp\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
