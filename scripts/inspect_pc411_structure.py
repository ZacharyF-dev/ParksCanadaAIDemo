from html.parser import HTMLParser
from pathlib import Path


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_anchor = False
        self.level = "1"
        self.text = ""
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.in_anchor = True
            self.text = ""
            self.level = dict(attrs).get("aria-level", "1") or "1"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.in_anchor:
            label = " ".join(self.text.split())
            if label:
                self.rows.append((self.level, label))
            self.in_anchor = False

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            self.text += data


parser = TreeParser()
parser.feed(Path("PC411_Structure.html").read_text(encoding="utf-8"))
print(f"Nodes: {len(parser.rows)}")
for level, label in parser.rows:
    print(f"{'  ' * (int(level) - 1)}{label}")
