# -*- coding: utf-8 -*-
import sys
import httpx
import anyio
from mcp.server.fastmcp import FastMCP, Context
from typing import Dict, Any, Union

# Create a generic MCP server for interacting with Revit
# Use stateless_http=True and json_response=True for better compatibility
mcp = FastMCP(
    "Revit MCP Server",
    host="127.0.0.1",
    port=8000,
    stateless_http=True,
    json_response=True,
)

# Configuration
REVIT_HOST = "localhost"
REVIT_PORT = 48884  # Default pyRevit Routes port
BASE_URL = f"http://{REVIT_HOST}:{REVIT_PORT}/revit_mcp"


async def revit_get(endpoint: str, ctx: Context = None, **kwargs) -> Union[Dict, str]:
    """Simple GET request to Revit API"""
    return await _revit_call("GET", endpoint, ctx=ctx, **kwargs)


async def revit_post(
    endpoint: str, data: Dict[str, Any], ctx: Context = None, **kwargs
) -> Union[Dict, str]:
    """Simple POST request to Revit API"""
    return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)


async def _revit_call(
    method: str,
    endpoint: str,
    data: Dict = None,
    ctx: Context = None,
    timeout: float = 30.0,
    params: Dict = None,
) -> Union[Dict, str]:
    """Internal function handling all HTTP calls"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{BASE_URL}{endpoint}"

            if method == "GET":
                response = await client.get(url, params=params)
            else:  # POST
                response = await client.post(
                    url, json=data, headers={"Content-Type": "application/json"}
                )

            return (
                response.json()
                if response.status_code == 200
                else f"Error: {response.status_code} - {response.text}"
            )
    except Exception as e:
        return f"Error: {e}"


# Register all tools BEFORE the main block

# 1. Core Revit tools (status health-check only)
from tools import register_tools

register_tools(mcp, revit_get, revit_post)

# 2. Internal stems (parameterized code building blocks)
from internal_stems.tools import register_internal_stem_tools

register_internal_stem_tools(mcp, revit_get, revit_post)

# 3. External stems (indexed libraries + Revit API docs)
from external_stems.tools import register_external_stem_tools

register_external_stem_tools(mcp, revit_get, revit_post)

# 4. Code execution (workflow planner + approved-execution)
from code_execution.tools import register_code_execution_tools

register_code_execution_tools(mcp, revit_get, revit_post)


async def run_combined_async():
    """Run server with both SSE and streamable-http endpoints.

    This allows clients to connect via either:
    - SSE: GET /sse, POST /messages/
    - Streamable-HTTP: POST/GET /mcp
    """
    import uvicorn

    # Get the streamable-http app first - it has the proper lifespan
    # that initializes the session manager's task group
    http_app = mcp.streamable_http_app()

    # Get SSE routes (SSE doesn't need special lifespan - it creates
    # task groups per-request in connect_sse())
    sse_app = mcp.sse_app()

    # Add SSE routes to the http app (preserving its lifespan)
    for route in sse_app.routes:
        http_app.routes.append(route)

    config = uvicorn.Config(
        http_app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    transport = "stdio"

    if "--sse" in sys.argv:
        transport = "sse"
    elif "--http" in sys.argv or "--streamable-http" in sys.argv:
        transport = "streamable-http"
    elif "--combined" in sys.argv:
        # Run both SSE and streamable-http transports simultaneously
        print(
            "Starting combined server with SSE (/sse, /messages/) and streamable-http (/mcp) endpoints..."
        )
        anyio.run(run_combined_async)
        sys.exit(0)

    mcp.run(transport=transport)
