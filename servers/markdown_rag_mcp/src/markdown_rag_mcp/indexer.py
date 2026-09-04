from __future__ import annotations

import hashlib
from pathlib import Path

from markdown_rag_mcp.settings import settings
from markdown_rag_mcp.store import get_collection


def chunk_markdown(content: str) -> list[str]:
    """Create deterministic overlapping chunks while favoring paragraph boundaries."""
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + settings.chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind("\n\n", start, end)
            if boundary > start + settings.chunk_size // 2:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - settings.chunk_overlap, start + 1)
    return chunks


def index_markdown_files() -> dict[str, int]:
    settings.validate_embedding_settings()
    files = sorted(settings.knowledge_dir.rglob("*.md"))
    if not files:
        return {"files": 0, "chunks": 0}

    collection = get_collection()
    collection.delete(where={"source": {"$ne": ""}})

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int]] = []
    for file_path in files:
        relative_path = file_path.relative_to(settings.knowledge_dir).as_posix()
        for index, chunk in enumerate(chunk_markdown(file_path.read_text(encoding="utf-8"))):
            digest = hashlib.sha256(f"{relative_path}:{index}:{chunk}".encode()).hexdigest()[:24]
            ids.append(f"{relative_path}:{index}:{digest}")
            documents.append(chunk)
            metadatas.append({"source": relative_path, "chunk": index})

    if ids:
        for start in range(0, len(ids), settings.embedding_batch_size):
            end = start + settings.embedding_batch_size
            collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
    return {"files": len(files), "chunks": len(ids)}


def main() -> None:
    result = index_markdown_files()
    print(f"Indexed {result['chunks']} chunks from {result['files']} Markdown files.")


if __name__ == "__main__":
    main()
