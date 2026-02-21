from typing import Optional, Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent, ReadResourceResult, TextResourceContents, BlobResourceContents
from pydantic import AnyUrl

from task.tools.mcp.mcp_tool_model import MCPToolModel


class MCPClient:
    """Handles MCP server connection and tool execution"""

    def __init__(self, mcp_server_url: str) -> None:
        self.server_url = mcp_server_url
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None

    @classmethod
    async def create(cls, mcp_server_url: str) -> 'MCPClient':
        instance = cls(mcp_server_url)
        await instance.connect()
        return instance

    async def connect(self):
        if self.session is not None:
            return
        self._streams_context = streamablehttp_client(self.server_url)
        read_stream, write_stream, _ = await self._streams_context.__aenter__()
        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()
        await self.session.initialize()
        print("[MCPClient] Session initialized.")

    async def get_tools(self) -> list[MCPToolModel]:
        tools = await self.session.get_tools()
        return [MCPToolModel(**tool) for tool in tools]

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        result: CallToolResult = await self.session.call_tool(tool_name, tool_args)
        # result.content is a list of TextContent or similar
        if hasattr(result, "content") and isinstance(result.content, list):
            # If only one content, return its value, else join all as string
            if len(result.content) == 1:
                return result.content[0].value
            return "\n".join([c.value for c in result.content])
        return str(result)

    async def get_resource(self, uri: AnyUrl) -> str | bytes:
        resource: ReadResourceResult = await self.session.get_resource(str(uri))
        if isinstance(resource, TextResourceContents):
            return resource.value
        elif isinstance(resource, BlobResourceContents):
            return resource.value
        else:
            return b""

    async def close(self):
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)
        self.session = None
        self._session_context = None
        self._streams_context = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False