from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from markdown_rag_mcp.store import get_collection

mcp = FastMCP("markdown-rag")


@mcp.tool()
def search_markdown_knowledge(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search locally indexed Markdown knowledge and return cited source chunks."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    result = get_collection().query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "content": document,
            "source": metadata["source"],
            "chunk": metadata["chunk"],
            "distance": distance,
        }
        for document, metadata, distance in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
            strict=True,
        )
    ]


@mcp.tool()
def rag_index_status() -> dict[str, Any]:
    """Return the number of Markdown chunks currently stored in the local vector database."""
    collection = get_collection()
    return {"collection": collection.name, "chunk_count": collection.count()}


def main() -> None:
    mcp.run(transport="http", host="127.0.0.1", port=8003, path="/mcp")


if __name__ == "__main__":
    main()
