"""Independent MCP peer for interop tests: the official MCP Python SDK, run as a subprocess.

    python mcp_peer.py server PORT   # SDK server (2026-07-28, also answers 2025-11-25)
    python mcp_peer.py client URL    # SDK client: list tools, call starter_greeting, print JSON

Needs the ``mcp`` package on ``PYTHONPATH``; Vault itself never imports it. The tests
that use this skip when ``VAULT_MCP_PEER_PATH`` is not set.
"""


import asyncio
import json
import sys
from typing import Annotated


def server(port: int) -> None:
    from pydantic import BaseModel, Field
    from mcp.server import MCPServer
    from mcp.types import ImageContent

    peer = MCPServer("vault-interop-peer")

    class Weather(BaseModel):
        city: str
        region: str
        celsius: int

    @peer.tool(description="Weather for a city in a region.")
    def weather(city: str, region: Annotated[str, Field(json_schema_extra={"x-mcp-header": "Region"})]) -> Weather:
        return Weather(city=city, region=region, celsius=21)

    @peer.tool(description="A one-pixel picture.")
    def picture() -> ImageContent:
        return ImageContent(type="image", data="iVBORw0KGgo=", mime_type="image/png")

    @peer.tool(description="Always fails.")
    def broken() -> str:
        raise ValueError("the weather service is down")

    peer.run("streamable-http", host="127.0.0.1", port=port)


async def client(url: str) -> None:
    from mcp import Client

    async with Client(url) as session:
        tools = await session.list_tools()
        result = await session.call_tool("starter_greeting", {"name": "Ada"})
        print(json.dumps({
            "tools": [tool.name for tool in tools.tools],
            "structured": result.structured_content,
            "is_error": result.is_error,
        }))


if __name__ == "__main__":
    if sys.argv[1] == "server":
        server(int(sys.argv[2]))
    else:
        asyncio.run(client(sys.argv[2]))
