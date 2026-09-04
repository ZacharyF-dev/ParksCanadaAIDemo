from __future__ import annotations

from collections.abc import Sequence
import time
from typing import Any, cast

import chromadb
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from openai import OpenAI, RateLimitError

from markdown_rag_mcp.settings import settings


class AzureOpenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    """Chroma embedding adapter using Foundry with DefaultAzureCredential."""

    def __init__(self) -> None:
        settings.validate_embedding_settings()
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://ai.azure.com/.default",
        )
        self.client = OpenAI(
            base_url=f"{settings.azure_openai_endpoint.rstrip('/')}/openai/v1/",
            api_key=token_provider,
        )

    def __call__(self, input: Documents) -> Embeddings:
        for attempt in range(settings.embedding_max_retries):
            try:
                response = self.client.embeddings.create(
                    model=settings.embedding_model,
                    input=list(input),
                )
                return cast(Embeddings, [item.embedding for item in response.data])
            except RateLimitError as exc:
                if attempt == settings.embedding_max_retries - 1:
                    raise
                retry_after = exc.response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else min(60.0, 5.0 * (2**attempt))
                time.sleep(delay)
        raise RuntimeError("Embedding retry loop ended unexpectedly")

    @staticmethod
    def name() -> str:
        return "azure_openai_foundry"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "AzureOpenAIEmbeddingFunction":
        return AzureOpenAIEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {
            "provider": "azure_openai_foundry",
            "model": settings.embedding_model,
            "endpoint": settings.azure_openai_endpoint,
        }


def get_collection() -> Any:
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return client.get_or_create_collection(
        name=settings.collection_name,
        embedding_function=cast(Any, AzureOpenAIEmbeddingFunction()),
        metadata={"description": "Markdown knowledge-base chunks"},
    )
