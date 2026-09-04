from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    knowledge_dir: Path = Path(os.getenv("RAG_KNOWLEDGE_DIR", PROJECT_ROOT / "knowledge"))
    chroma_dir: Path = Path(os.getenv("RAG_CHROMA_DIR", PROJECT_ROOT / "data" / "rag" / "chroma"))
    collection_name: str = os.getenv("RAG_COLLECTION_NAME", "markdown_knowledge")
    embedding_model: str = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    chunk_size: int = int(os.getenv("RAG_CHUNK_SIZE", "1200"))
    chunk_overlap: int = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
    embedding_batch_size: int = int(os.getenv("RAG_EMBED_BATCH_SIZE", "8"))
    embedding_max_retries: int = int(os.getenv("RAG_EMBED_MAX_RETRIES", "5"))

    def validate_embedding_settings(self) -> None:
        missing = [
            name
            for name, value in {
                "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
                "AZURE_OPENAI_EMBEDDING_MODEL": self.embedding_model,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required RAG settings: {', '.join(missing)}")


settings = Settings()
