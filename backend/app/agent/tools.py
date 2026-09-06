from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ..config import get_settings


class ToolPermissionError(PermissionError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    scope: str
    handler: Callable[..., Awaitable[dict[str, Any]]]
    requires_confirmation: bool = False


class ToolRegistry:
    """The model selects tools; this registry remains the security authority."""

    def __init__(self):
        self.tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition):
        self.tools[definition.name] = definition

    async def call(self, name: str, arguments: dict[str, Any], scopes: set[str], *, confirmed: bool = False):
        definition = self.tools.get(name)
        if not definition:
            raise ValueError(f"Unknown tool: {name}")
        if definition.scope not in scopes:
            raise ToolPermissionError(f"Missing scope: {definition.scope}")
        if definition.requires_confirmation and not confirmed:
            return {"status": "confirmation_required", "tool": name, "arguments": arguments}
        return await asyncio.wait_for(definition.handler(**arguments), timeout=get_settings().tool_timeout_seconds)


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call the standalone server via the official MCP session lifecycle."""
    async with (
        streamable_http_client(get_settings().mcp_server_url) as (read_stream, write_stream, _),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments)
        return {
            "status": "ok" if not result.isError else "error",
            "content": [block.model_dump() for block in result.content],
        }
