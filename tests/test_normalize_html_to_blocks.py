from __future__ import annotations

SAMPLE = """
<html>
  <head>
    <title>AWS Lambda tips</title>
    <script>var ads = true;</script>
    <style>body { color: red; }</style>
  </head>
  <body>
    <nav><p>Home Pricing Login</p></nav>
    <article>
      <h1>AWS Lambda tips</h1>
      <p>Nov 17, 2019</p>
      <p>I use Pipenv to bundle Python libraries.</p>
      <ul>
        <li>Create a deploy directory</li>
        <li>Zip the libraries</li>
      </ul>
      <pre>pipenv lock -r</pre>
    </article>
    <aside hidden><p>Secret promo</p></aside>
    <div aria-hidden="true"><p>Invisible banner</p></div>
    <footer><p>Always be loose-coupled :)</p></footer>
  </body>
</html>
"""


def blocks_by_text(mod, html: str, min_chars: int = 2) -> list[dict]:
    parser = mod.BlockHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.blocks(min_chars), parser.title()


def test_extracts_title_and_visible_article_blocks(normalize_mod):
    blocks, title = blocks_by_text(normalize_mod, SAMPLE)
    texts = [block["text"] for block in blocks]
    assert title == "AWS Lambda tips"
    assert "AWS Lambda tips" in texts
    assert "Nov 17, 2019" in texts
    assert "I use Pipenv to bundle Python libraries." in texts
    assert "Create a deploy directory" in texts
    assert "Zip the libraries" in texts
    assert "pipenv lock -r" in texts
    assert "Always be loose-coupled :)" in texts
    assert "Home Pricing Login" in texts


def test_skips_script_style_and_hidden_nodes(normalize_mod):
    blocks, _title = blocks_by_text(normalize_mod, SAMPLE)
    texts = [block["text"] for block in blocks]
    assert "var ads = true;" not in texts
    assert "color: red" not in " ".join(texts)
    assert "Secret promo" not in texts
    assert "Invisible banner" not in texts


def test_assigns_stable_ids_and_paths(normalize_mod):
    blocks, _title = blocks_by_text(normalize_mod, SAMPLE)
    assert [block["id"] for block in blocks] == list(range(1, len(blocks) + 1))
    assert [block["ordinal"] for block in blocks] == list(range(len(blocks)))
    h1 = next(block for block in blocks if block["tag"] == "h1")
    assert "h1" in h1["path"]
    assert h1["path"].startswith("html")


def test_min_chars_drops_short_blocks(normalize_mod):
    html = "<html><body><p>Hi</p><p>A longer paragraph stays.</p></body></html>"
    blocks, _title = blocks_by_text(normalize_mod, html, min_chars=10)
    assert [block["text"] for block in blocks] == ["A longer paragraph stays."]


def test_cli_writes_json(normalize_mod, tmp_path):
    html_path = tmp_path / "page.html"
    out_path = tmp_path / "page.json"
    html_path.write_text("<html><head><title>T</title></head><body><p>Hello world</p></body></html>")
    raise_system = None
    import sys

    argv = [
        "normalize_html_to_blocks.py",
        str(html_path),
        "--page-id",
        "001",
        "--url",
        "https://example.com/post",
        "--output",
        str(out_path),
    ]
    old = sys.argv
    sys.argv = argv
    try:
        normalize_mod.main()
    except SystemExit as error:
        raise_system = error
    finally:
        sys.argv = old
    assert raise_system is None
    import json

    document = json.loads(out_path.read_text(encoding="utf-8"))
    assert document["page_id"] == "001"
    assert document["title"] == "T"
    assert document["url"] == "https://example.com/post"
    assert document["domain"] == "example.com"
    assert document["blocks"][0]["text"] == "Hello world"
