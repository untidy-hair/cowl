#!/usr/bin/env python3
"""Convert one HTML document into ordered, meaningful text blocks.

Setup from the project root::

    uv sync

Run::

    uv run python scripts/normalize_html_to_blocks.py page.html \\
        --page-id page-001 \\
        --url https://example.com/article \\
        --output page-001.json

The output is intended for offline dataset preparation. It preserves source text
and DOM order; it does not attempt to decide which blocks are article content.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse


BLOCK_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "dt",
    "dd",
    "pre",
    "blockquote",
    "td",
    "th",
    "figcaption",
}
IGNORED_TAGS = {"head", "script", "style", "template", "noscript", "svg", "canvas"}
WHITESPACE = re.compile(r"\s+")


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    parent: Node | None
    path: str
    visible: bool
    text_parts: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)

    def has_candidate_descendant(self) -> bool:
        return any(
            child.is_candidate() or child.has_candidate_descendant()
            for child in self.children
        )

    def is_candidate(self) -> bool:
        return self.visible and self.tag in BLOCK_TAGS

    def text(self) -> str:
        value = "".join(self.text_parts)
        if self.tag == "pre":
            return value.strip()
        return WHITESPACE.sub(" ", value).strip()


class BlockHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, None, "document", True)
        self.stack: list[Node] = [self.root]
        self.nodes: list[Node] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        parent = self.stack[-1]
        same_tag_count = sum(child.tag == tag for child in parent.children) + 1
        path = f"{parent.path}/{tag}[{same_tag_count}]"
        visible = parent.visible and not self._is_hidden(tag, attributes)
        node = Node(tag, attributes, parent, path, visible)
        parent.children.append(node)
        self.nodes.append(node)

        if tag == "title":
            self._in_title = True
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if not data:
            return
        for node in self.stack:
            if node.visible:
                node.text_parts.append(data)
        if self._in_title:
            self.title_parts.append(data)

    @staticmethod
    def _is_hidden(tag: str, attrs: dict[str, str]) -> bool:
        return (
            tag in IGNORED_TAGS
            or "hidden" in attrs
            or attrs.get("aria-hidden", "").lower() == "true"
            or attrs.get("type", "").lower() == "hidden"
        )

    def blocks(self, minimum_characters: int) -> list[dict[str, object]]:
        blocks: list[dict[str, object]] = []
        for node in self.nodes:
            if not node.is_candidate() or node.has_candidate_descendant():
                continue

            text = node.text()
            if len(text) < minimum_characters:
                continue

            blocks.append(
                {
                    "id": len(blocks) + 1,
                    "tag": node.tag,
                    "path": node.path.removeprefix("document/"),
                    "ordinal": len(blocks),
                    "text": text,
                }
            )
        return blocks

    def title(self) -> str:
        return WHITESPACE.sub(" ", "".join(self.title_parts)).strip()


def read_html(input_path: str) -> tuple[str, str]:
    if input_path == "-":
        return sys.stdin.read(), "stdin"

    path = Path(input_path)
    return path.read_text(encoding="utf-8"), path.stem


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="HTML file to normalize, or - to read HTML from stdin")
    parser.add_argument("--output", "-o", help="Write JSON output to this file instead of stdout")
    parser.add_argument("--page-id", help="Stable page identifier; defaults to the input file stem")
    parser.add_argument("--url", help="Source page URL, used only to set the output URL and domain")
    parser.add_argument(
        "--min-chars",
        type=int,
        default=2,
        help="Discard blocks shorter than this many characters (default: 2)",
    )
    return parser.parse_args()


def write_json(document: dict[str, object], output_path: str | None) -> None:
    output: TextIO
    if output_path:
        output = Path(output_path).open("w", encoding="utf-8")
    else:
        output = sys.stdout

    try:
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")
    finally:
        if output is not sys.stdout:
            output.close()


def main() -> None:
    arguments = parse_arguments()
    if arguments.min_chars < 0:
        raise SystemExit("--min-chars must be zero or greater")

    html, default_page_id = read_html(arguments.input)
    parser = BlockHTMLParser()
    parser.feed(html)
    parser.close()

    domain = urlparse(arguments.url).hostname if arguments.url else None
    document: dict[str, object] = {
        "page_id": arguments.page_id or default_page_id,
        "title": parser.title(),
        "blocks": parser.blocks(arguments.min_chars),
    }
    if arguments.url:
        document["url"] = arguments.url
    if domain:
        document["domain"] = domain

    write_json(document, arguments.output)


if __name__ == "__main__":
    main()
