from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from pc411_directory_mcp.db import db_cursor, init_db
from pc411_directory_mcp.settings import settings


class OrganizationTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[tuple[str, str, int]] = []
        self._in_anchor = False
        self._text = ""
        self._attributes: dict[str, str | None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._in_anchor = True
            self._text = ""
            self._attributes = dict(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_anchor:
            name = " ".join(self._text.split())
            source_id = self._attributes.get("id", "").removesuffix("_anchor")
            depth = int(self._attributes.get("aria-level") or 1)
            if name and source_id:
                self.nodes.append((source_id, name, depth))
            self._in_anchor = False

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._text += data


def import_structure(path: Path | None = None) -> int:
    source_path = path or settings.structure_path
    parser = OrganizationTreeParser()
    parser.feed(source_path.read_text(encoding="utf-8"))
    if not parser.nodes:
        raise ValueError(f"No organization nodes found in {source_path}")

    init_db()
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM people")
        cursor.execute("DELETE FROM organizations")
        parents: dict[int, int] = {}
        paths: dict[int, str] = {}
        for source_id, name, depth in parser.nodes:
            parent_id = parents.get(depth - 1)
            parent_path = paths.get(depth - 1, "")
            node_path = f"{parent_path} / {name}".strip(" / ")
            cursor.execute(
                "INSERT INTO organizations (source_id, name, parent_id, depth, path) VALUES (?, ?, ?, ?, ?)",
                (source_id, name, parent_id, depth, node_path),
            )
            organization_id = int(cursor.lastrowid)
            parents[depth] = organization_id
            paths[depth] = node_path
            for level in tuple(parents):
                if level > depth:
                    del parents[level]
                    del paths[level]
    return len(parser.nodes)


def main() -> None:
    count = import_structure()
    print(f"Imported {count} organizations from {settings.structure_path.name}.")


if __name__ == "__main__":
    main()
