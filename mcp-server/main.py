"""FastAPI MCP server with Streamable HTTP transport."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add shared models to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import TextContent, Tool

from mcp_server.auth.api_key import APIKeyMiddleware
from mcp_server.search.client import SearchClient
from mcp_server.tools import (
    list_reports,
    get_alert_overview,
    get_alert_detail,
    get_section,
    ask_ewa_scoped,
    compare_reports,
    generate_action_pack
)


# Initialize MCP server
server = Server("ewa-mcp")

# Initialize search client
search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    api_key=os.environ["AZURE_SEARCH_API_KEY"]
)


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        list_reports.get_tool_definition(),
        get_alert_overview.get_tool_definition(),
        get_alert_detail.get_tool_definition(),
        get_section.get_tool_definition(),
        ask_ewa_scoped.get_tool_definition(),
        compare_reports.get_tool_definition(),
        generate_action_pack.get_tool_definition()
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    """Handle tool calls."""
    arguments = arguments or {}
    
    try:
        if name == "list_reports":
            result = await list_reports.execute(search_client, arguments)
        elif name == "get_alert_overview":
            result = await get_alert_overview.execute(search_client, arguments)
        elif name == "get_alert_detail":
            result = await get_alert_detail.execute(search_client, arguments)
        elif name == "get_section":
            result = await get_section.execute(search_client, arguments)
        elif name == "ask_ewa_scoped":
            result = await ask_ewa_scoped.execute(search_client, arguments)
        elif name == "compare_reports":
            result = await compare_reports.execute(search_client, arguments)
        elif name == "generate_action_pack":
            result = await generate_action_pack.execute(search_client, arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
        
        return [TextContent(type="text", text=result)]
    
    except Exception as e:
        return [TextContent(type="text", text=f'{{"error": "{str(e)}"}}')]


# Create FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="EWA MCP Server",
    description="SAP EarlyWatch Alert MCP Server with Azure AI Search",
    version="1.0.0",
    lifespan=lifespan
)

# Add API key middleware
app.add_middleware(APIKeyMiddleware)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "server": "ewa-mcp"}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP Streamable HTTP endpoint."""
    body = await request.json()
    
    # Handle initialization
    if body.get("method") == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ewa-mcp",
                    "version": "1.0.0"
                }
            }
        }
    
    # Handle tools/list
    if body.get("method") == "tools/list":
        tools = await handle_list_tools()
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"tools": [t.model_dump() for t in tools]}
        }
    
    # Handle tools/call
    if body.get("method") == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        
        result = await handle_call_tool(name, arguments)
        
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "content": [{"type": "text", "text": r.text} for r in result],
                "isError": False
            }
        }
    
    return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "Method not found"}}


@app.get("/mcp/sse")
async def mcp_sse():
    """Legacy SSE endpoint for backward compatibility."""
    async def event_generator():
        yield "event: endpoint\ndata: /mcp\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
