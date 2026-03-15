# -*- coding: utf-8 -*-
import os
import site
import sys
from pathlib import Path

# -- Ensure we are running inside the repo .venv -----------------------
# When launched via Claude Desktop / uv run / another external runner the
# process may use a different Python than the one the .venv was built for.
# Detect this and re-exec with the correct interpreter.
_VENV_DIR = Path(__file__).resolve().parent / ".venv"
_REEXEC_FLAG = "_REVIT_MCP_REEXEC"

if _VENV_DIR.is_dir() and _REEXEC_FLAG not in os.environ:
    if sys.platform == "win32":
        _venv_python = _VENV_DIR / "Scripts" / "python.exe"
    else:
        _venv_python = _VENV_DIR / "bin" / "python"

    _current = Path(sys.executable).resolve()
    if _venv_python.exists() and _current != _venv_python.resolve():
        # Re-exec under the venv interpreter, carrying all CLI args.
        # Use subprocess on Windows — os.execv mishandles paths with spaces.
        print(
            "Re-launching with venv Python ({} -> {})".format(
                sys.version.split()[0], _venv_python
            ),
            file=sys.stderr,
        )
        os.environ[_REEXEC_FLAG] = "1"
        if sys.platform == "win32":
            import subprocess

            raise SystemExit(subprocess.call([str(_venv_python)] + sys.argv))
        else:
            os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

# If we are already in the venv (or there is no venv), ensure the
# site-packages are on sys.path as a safety net.
if _VENV_DIR.is_dir():
    if sys.platform == "win32":
        _site_pkgs = _VENV_DIR / "Lib" / "site-packages"
    else:
        _py = f"python{sys.version_info.major}.{sys.version_info.minor}"
        _site_pkgs = _VENV_DIR / "lib" / _py / "site-packages"
    if _site_pkgs.is_dir() and str(_site_pkgs) not in sys.path:
        site.addsitedir(str(_site_pkgs))

# ----------------------------------------------------------------------

# -- Logging (must happen before any module that calls getLogger) ------
import logging
from logging_config import setup_logging

_log_path = setup_logging()
logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("Revit MCP Server starting")
logger.info("Python %s | PID %s", sys.version, os.getpid())
logger.info("Log file: %s", _log_path)
if _VENV_DIR.is_dir():
    logger.info("venv activated: %s", _VENV_DIR)
else:
    logger.warning("No .venv found beside main.py")
# ----------------------------------------------------------------------

import httpx
import anyio
from mcp.server.fastmcp import FastMCP, Context
from typing import Dict, Any, Union

logger.info("Third-party imports OK (httpx, anyio, mcp)")

# Create a generic MCP server for interacting with Revit
# Use stateless_http=True and json_response=True for better compatibility
mcp = FastMCP(
    "Revit MCP Server",
    host="127.0.0.1",
    port=8000,
    stateless_http=True,
    json_response=True,
    instructions=(
        "You are connected to a Revit MCP server with a searchable library "
        "of ~2900 pre-built Python helper functions (duHast) for working "
        "with Revit elements.\n\n"
        "WORKFLOW:\n\n"
        "Call the 'main' tool for EVERY user request about Revit. "
        "It runs the full pipeline in one call: "
        "AST+BM25 search → code production sub-agent → code review sub-agent. "
        "The response contains matched duHast functions, generated IronPython "
        "code, and review notes. "
        "Present the code and review notes to the user and ask for approval "
        "before executing anything.\n\n"
        "Do NOT answer Revit questions from your own training knowledge "
        "without first calling main. "
        "Do NOT write code yourself — always call main and use its output."
    ),
)

logger.info(
    "FastMCP instance created (host=%s, port=%s)", mcp.settings.host, mcp.settings.port
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
    url = f"{BASE_URL}{endpoint}"
    logger.debug("Revit API %s %s (timeout=%.1fs)", method, url, timeout)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(url, params=params)
            else:  # POST
                response = await client.post(
                    url, json=data, headers={"Content-Type": "application/json"}
                )

            if response.status_code == 200:
                logger.debug("Revit API %s %s -> 200 OK", method, endpoint)
                return response.json()
            else:
                msg = f"Error: {response.status_code} - {response.text}"
                logger.warning("Revit API %s %s -> %s", method, endpoint, msg)
                return msg
    except Exception as e:
        logger.error("Revit API %s %s failed: %s", method, endpoint, e, exc_info=True)
        return f"Error: {e}"


# Register tools
logger.info("Registering MCP tools...")
from revit_mcp.tools import register_code_execution_tools

register_code_execution_tools(mcp, revit_get, revit_post)
logger.info("MCP tools registered (1 tool: main)")

# Load the AST+BM25 index at startup.  JSON load + BM25 build typically
# completes in < 0.5 s, so we do it in the main thread before serving.
# If the index JSON does not exist yet, get_state() will auto-build it
# from the library source (takes a few seconds on first run).
try:
    from rag.config import load_config
    from rag.ast_index import get_state

    _cfg = load_config()
    _enabled = [lib for lib in _cfg.libraries if lib.enabled]
    _lib_path = _enabled[0].path if _enabled else ""
    get_state(_cfg.rag.vector_store_dir, _lib_path)
    logger.info("AST index loaded and ready")
except Exception as _exc:
    logger.warning("AST index startup load failed: %s", _exc)


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
        logger.info("Starting combined server (SSE + streamable-http)...")
        print(
            "Starting combined server with SSE (/sse, /messages/) and streamable-http (/mcp) endpoints..."
        )
        anyio.run(run_combined_async)
        sys.exit(0)

    logger.info("Starting server with transport=%s", transport)
    mcp.run(transport=transport)
