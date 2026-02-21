import json
from abc import ABC, abstractmethod
from typing import Any

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Role, CustomContent
from pydantic import StrictStr

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams


class DeploymentTool(BaseTool, ABC):

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    @property
    @abstractmethod
    def deployment_name(self) -> str:
        pass

    @property
    def tool_parameters(self) -> dict[str, Any]:
        return {}

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        prompt = arguments.get("prompt", "")
        arguments.pop("prompt", None)
        custom_fields = arguments if arguments else None

        client = AsyncDial(base_url=self.endpoint, api_version="2025-01-01-preview", api_key=tool_call_params.api_key)
        messages = []
        if hasattr(self, "system_prompt") and getattr(self, "system_prompt", None):
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await client.chat.completions.create(
            messages=messages,
            deployment_name=self.deployment_name,
            stream=True,
            extra_body={"custom_fields": custom_fields} if custom_fields else {},
            **self.tool_parameters
        )

        content = ""
        attachments = []
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                if delta.content:
                    content += delta.content
                if delta.custom_content and delta.custom_content.attachments:
                    attachments.extend(delta.custom_content.attachments)

        if attachments:
            custom_content = CustomContent(attachments=attachments)
        else:
            custom_content = None

        return Message(
            role=Role.TOOL,
            name=StrictStr(tool_call_params.tool_call.function.name),
            tool_call_id=StrictStr(tool_call_params.tool_call.id),
            content=content,
            custom_content=custom_content
        )