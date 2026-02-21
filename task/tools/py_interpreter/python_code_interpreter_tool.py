import base64
import json
from typing import Any, Optional

from aidial_client import Dial
from aidial_sdk.chat_completion import Message, Attachment
from pydantic import StrictStr, AnyUrl

from task.tools.base import BaseTool
from task.tools.py_interpreter._response import _ExecutionResult
from task.tools.mcp.mcp_client import MCPClient
from task.tools.mcp.mcp_tool_model import MCPToolModel
from task.tools.models import ToolCallParams


class PythonCodeInterpreterTool(BaseTool):
    """
    Uses https://github.com/khshanovskyi/mcp-python-code-interpreter PyInterpreter MCP Server.

    ⚠️ Pay attention that this tool will wrap all the work with PyInterpreter MCP Server.
    """

    def __init__(
            self,
            mcp_client: MCPClient,
            mcp_tool_models: list[MCPToolModel],
            tool_name: str,
            dial_endpoint: str,
    ):
        self.dial_endpoint = dial_endpoint
        self.mcp_client = mcp_client
        self._code_execute_tool: Optional[MCPToolModel] = None
        for tool in mcp_tool_models:
            if tool.name == tool_name:
                self._code_execute_tool = tool
                break
        if self._code_execute_tool is None:
            raise ValueError("PythonCodeInterpreterTool requires a tool with name 'execute_code' in mcp_tool_models.")

    @classmethod
    async def create(
            cls,
            mcp_url: str,
            tool_name: str,
            dial_endpoint: str,
    ) -> 'PythonCodeInterpreterTool':
        mcp_client = await MCPClient.create(mcp_url)
        tools = await mcp_client.get_tools()
        return cls(mcp_client, tools, tool_name, dial_endpoint)

    @property
    def show_in_stage(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return self._code_execute_tool.name

    @property
    def description(self) -> str:
        return self._code_execute_tool.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._code_execute_tool.parameters

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        code = arguments.get("code")
        session_id = arguments.get("session_id", None)
        stage = tool_call_params.stage

        stage.append_content("## Request arguments: \n")
        stage.append_content(f"```python\n\r{code}\n\r```\n\r")
        if session_id and session_id != 0:
            stage.append_content(f"**session_id**: {session_id}\n\r")
        else:
            stage.append_content("New session will be created\n\r")

        result_str = await self.mcp_client.call_tool(self._code_execute_tool.name, arguments)
        execution_result = _ExecutionResult.model_validate_json(result_str)

        if execution_result.files:
            dial_client = Dial(base_url=self.dial_endpoint, api_key=tool_call_params.api_key)
            files_home = await dial_client.my_appdata_home()
            attachments = []
            for file in execution_result.files:
                file_name = file.name
                mime_type = file.mime_type
                resource = await self.mcp_client.get_resource(file.uri)
                if mime_type.startswith("text/") or mime_type in ("application/json", "application/xml"):
                    upload_data = resource.encode("utf-8") if isinstance(resource, str) else resource
                else:
                    upload_data = base64.b64decode(resource) if isinstance(resource, str) else resource
                upload_path = f"files/{(files_home / file_name).as_posix()}"
                await dial_client.files.upload(upload_path, upload_data, mime_type=mime_type)
                attachment = Attachment(url=upload_path, type=mime_type, title=file_name)
                stage.add_attachment(attachment)
                attachments.append(attachment)
            # Add attachments to execution_result for output
            if not hasattr(execution_result, "attachments"):
                execution_result.attachments = []
            execution_result.attachments.extend(attachments)

        if execution_result.output:
            execution_result.output = [o[:1000] for o in execution_result.output]

        stage.append_content(f"```json\n\r{execution_result.model_dump_json(indent=2)}\n\r```\n\r")
        return execution_result.model_dump_json()