from typing import Any

from aidial_sdk.chat_completion import Message
from pydantic import StrictStr

from task.tools.deployment.base import DeploymentTool
from task.tools.models import ToolCallParams


class ImageGenerationTool(DeploymentTool):

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        message = await super()._execute(tool_call_params)
        attachments = []
        if hasattr(message, "custom_content") and message.custom_content and getattr(message.custom_content, "attachments", None):
            attachments = [
                att for att in message.custom_content.attachments
                if att.type in ("image/png", "image/jpeg")
            ]
        content = message.content or ""
        for attachment in attachments:
            content += f"\n\r![image]({attachment.url})\n\r"
        if not content.strip():
            content = 'The image has been successfully generated according to request and shown to user!'
        message.content = content
        return message

    @property
    def deployment_name(self) -> str:
        return "dall-e-3"

    @property
    def name(self) -> str:
        return "Image Generation Tool"

    @property
    def description(self) -> str:
        return (
            "Generates images based on a detailed prompt using the DALL-E 3 model. "
            "Use this tool when a user requests an image, illustration, or visual content. "
            "Supports customization of image size, style, and quality. "
            "Returns images directly in the chat for immediate viewing. "
            "Handles tricky cases such as requests for specific styles, aspect ratios, or high-resolution outputs."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Extensive description of the image that should be generated."
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1024x1792", "1792x1024"],
                    "description": "The size of the generated image. Optional."
                },
                "style": {
                    "type": "string",
                    "enum": ["natural", "vivid"],
                    "description": "The style of the generated image. Optional."
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "The quality of the image that will be generated. Optional."
                }
            },
            "required": ["prompt"]
        }