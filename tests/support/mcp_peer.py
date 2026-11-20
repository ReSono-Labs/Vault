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


def protected_server(port: int) -> None:
    """The SDK as both protected MCP server and OAuth 2.1 authorization server. The SDK serves
    metadata, registration, /authorize, /token and /revoke; this only stores what it issues and
    approves every sign-in at once (``login_hint`` names the person)."""
    import secrets
    import time

    from mcp.server import MCPServer
    from mcp.server.auth.provider import (
        AccessToken, AuthorizationCode, RefreshToken, construct_redirect_uri,
    )
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from mcp.server.mcpserver import Context
    from mcp.shared.auth import OAuthToken

    origin = f"http://127.0.0.1:{port}"

    class Provider:
        def __init__(self):
            self.clients, self.codes, self.access, self.refresh = {}, {}, {}, {}
            self.sign_ins = 0

        async def get_client(self, client_id):
            return self.clients.get(client_id)

        async def register_client(self, client_info):
            self.clients[client_info.client_id] = client_info

        async def authorize(self, client, params):
            code = secrets.token_urlsafe(16)
            self.sign_ins += 1
            self.codes[code] = AuthorizationCode(
                code=code, scopes=params.scopes or ["tools"], expires_at=time.time() + 300,
                client_id=client.client_id, code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri, redirect_uri_provided_explicitly=True,
                resource=params.resource, subject=f"user-{self.sign_ins}")
            return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state, iss=origin)

        async def load_authorization_code(self, client, authorization_code):
            return self.codes.get(authorization_code)

        def _issue(self, client_id, scopes, resource, subject):
            access, refresh = "at-" + secrets.token_hex(8), "rt-" + secrets.token_hex(8)
            self.access[access] = AccessToken(token=access, client_id=client_id, scopes=scopes,
                                              expires_at=int(time.time()) + 3600, resource=resource, subject=subject)
            self.refresh[refresh] = RefreshToken(token=refresh, client_id=client_id, scopes=scopes,
                                                 resource=resource, subject=subject)
            return OAuthToken(access_token=access, expires_in=3600, scope=" ".join(scopes), refresh_token=refresh)

        async def exchange_authorization_code(self, client, authorization_code):
            self.codes.pop(authorization_code.code, None)
            return self._issue(client.client_id, authorization_code.scopes, authorization_code.resource,
                               authorization_code.subject)

        async def load_refresh_token(self, client, refresh_token):
            return self.refresh.get(refresh_token)

        async def exchange_refresh_token(self, client, refresh_token, scopes):
            self.refresh.pop(refresh_token.token, None)
            return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource,
                               refresh_token.subject)

        async def load_access_token(self, token):
            found = self.access.get(token)
            # Audience check (RFC 8707): only tokens issued for this server.
            return found if found is not None and found.resource == f"{origin}/mcp" else None

        async def revoke_token(self, token):
            self.access.pop(token.token, None)
            self.refresh.pop(token.token, None)

    peer = MCPServer(
        "vault-interop-protected", auth_server_provider=Provider(),
        auth=AuthSettings(issuer_url=origin, resource_server_url=f"{origin}/mcp", required_scopes=["tools"],
                          client_registration_options=ClientRegistrationOptions(
                              enabled=True, valid_scopes=["tools"], default_scopes=["tools"]),
                          revocation_options=RevocationOptions(enabled=True)),
    )

    @peer.tool(description="Which signed-in person is calling.")
    def whoami(ctx: Context) -> str:
        from mcp.server.auth.middleware.auth_context import get_access_token
        token = get_access_token()
        return f"signed in as {token.subject if token else 'nobody'}"

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
    elif sys.argv[1] == "protected-server":
        protected_server(int(sys.argv[2]))
    else:
        asyncio.run(client(sys.argv[2]))
