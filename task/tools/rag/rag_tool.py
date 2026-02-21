import json
from typing import Any

import faiss
import numpy as np
from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Role
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams
from task.tools.rag.document_cache import DocumentCache
from task.utils.dial_file_conent_extractor import DialFileContentExtractor

_SYSTEM_PROMPT = """
You are a helpful assistant that answers questions based on provided document content. Use only the information from the document to answer the user's question. If the answer is not present in the document, say so clearly.
"""

class RagTool(BaseTool):
    """
    Performs semantic search on documents to find and answer questions based on relevant content.
    Supports: PDF, TXT, CSV, HTML.
    """

    def __init__(self, endpoint: str, deployment_name: str, document_cache: DocumentCache):
        self.endpoint = endpoint
        self.deployment_name = deployment_name
        self.document_cache = document_cache
        self.model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    @property
    def show_in_stage(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return "RAG Document QA Tool"

    @property
    def description(self) -> str:
        return (
            "Performs semantic search and question answering on documents (PDF, TXT, CSV, HTML). "
            "Finds relevant content and answers user questions based on the document. "
            "Uses embeddings and chunking for efficient retrieval."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The search query or question to search for in the document."
                },
                "file_url": {
                    "type": "string",
                    "description": "URL of the file to search in."
                }
            },
            "required": ["request", "file_url"]
        }

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        request = arguments.get("request")
        file_url = arguments.get("file_url")
        stage = tool_call_params.stage

        stage.append_content("## Request arguments: \n")
        stage.append_content(f"**Request**: {request}\n\r")
        stage.append_content(f"**File URL**: {file_url}\n\r")

        cache_document_key = f"{tool_call_params.conversation_id}:{file_url}"
        cached_data = self.document_cache.get(cache_document_key)
        if cached_data:
            index, chunks = cached_data
        else:
            extractor = DialFileContentExtractor(self.endpoint, tool_call_params.api_key)
            text_content = extractor.extract_text(file_url)
            if not text_content:
                stage.append_content("File content not found or could not be extracted.")
                return "Error: File content not found."
            chunks = self.text_splitter.split_text(text_content)
            embeddings = self.model.encode(chunks, convert_to_numpy=True)
            index = faiss.IndexFlatL2(384)
            index.add(np.array(embeddings, dtype='float32'))
            self.document_cache.set(cache_document_key, index, chunks)

        query_embedding = self.model.encode([request], convert_to_numpy=True).astype('float32')
        distances, indices = index.search(query_embedding, k=3)
        retrieved_chunks = [chunks[idx] for idx in indices[0] if idx < len(chunks)]

        augmented_prompt = self.__augmentation(request, retrieved_chunks)
        stage.append_content("## RAG Request: \n")
        stage.append_content(f"```text\n\r{augmented_prompt}\n\r```\n\r")
        stage.append_content("## Response: \n")

        client = AsyncDial(base_url=self.endpoint, api_version="2025-01-01-preview", api_key=tool_call_params.api_key)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": augmented_prompt}
        ]
        stream = await client.chat.completions.create(
            messages=messages,
            deployment_name=self.deployment_name,
            stream=True
        )
        content = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta
                stage.append_content(delta.content)
                content += delta.content
        return content

    def __augmentation(self, request: str, chunks: list[str]) -> str:
        context = "\n\n".join(chunks)
        return (
            f"Context:\n{context}\n\n"
            f"Question: {request}\n"
            f"Answer:"
        )