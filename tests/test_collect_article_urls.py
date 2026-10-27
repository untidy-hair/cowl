from __future__ import annotations

def test_english_likely(collect_mod):
    assert collect_mod.english_likely("How to build a reader for the web")
    assert not collect_mod.english_likely("こんにちは 世界 です")
    assert not collect_mod.english_likely("ok")


def test_domain_key_handles_multi_label_suffixes(collect_mod):
    assert collect_mod.domain_key("https://www.example.com/post") == "example.com"
    assert collect_mod.domain_key("https://news.bbc.co.uk/article") == "bbc.co.uk"
    assert collect_mod.domain_key("https://localhost/post") is None
    assert collect_mod.domain_key("https://127.0.0.1/post") is None


def test_canonical_url_strips_utm_and_rejects_non_articles(collect_mod):
    cleaned = collect_mod.canonical_url(
        "https://Example.com/posts/hello?utm_source=rss&id=1"
    )
    assert cleaned == "https://example.com/posts/hello?id=1"

    assert collect_mod.canonical_url("https://nytimes.com/2024/01/01/story") is None
    assert collect_mod.canonical_url("https://youtube.com/watch?v=abc") is None
    assert collect_mod.canonical_url("https://example.com/podcasts/episode-1") is None
    assert collect_mod.canonical_url("https://example.com/") is None
    assert collect_mod.canonical_url("https://example.com/tags/python") is None
    assert collect_mod.canonical_url("https://example.com/photo.jpg") is None


def test_feed_candidates_parses_rss_and_skips_non_english(collect_mod, monkeypatch):
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <language>en</language>
      <item>
        <title>How to test a feed parser</title>
        <link>https://example.com/posts/how-to-test</link>
        <description>This is an article about the parser.</description>
      </item>
      <item>
        <title>Not an article</title>
        <link>https://example.com/tags/news</link>
      </item>
      <item>
        <title>Video hour</title>
        <link>https://youtube.com/watch?v=1</link>
      </item>
    </channel></rss>
    """
    monkeypatch.setattr(collect_mod, "fetch", lambda url, timeout=20: rss.encode("utf-8"))
    found = collect_mod.feed_candidates("https://example.com/feed.xml", "Example Blog")
    assert [item.url for item in found] == ["https://example.com/posts/how-to-test"]
    assert found[0].entry_title == "How to test a feed parser"


def test_feed_candidates_skips_podcast_titled_feeds(collect_mod):
    assert collect_mod.feed_candidates("https://example.com/feed.xml", "Weekly Podcast") == []
