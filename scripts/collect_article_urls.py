#!/usr/bin/env python3
"""Collect English-leaning article URLs from the Plenary public RSS catalog."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


CATALOG_API = (
    "https://api.github.com/repos/spians/awesome-RSS-feeds/contents/"
    "recommended/with_category"
)
USER_AGENT = "COWL/1.0 (Content-Only Web Labeler; URL-only research collection)"
ENGLISH_WORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be", "by",
    "for", "from", "how", "in", "is", "it", "new", "of", "on", "or", "the",
    "this", "to", "what", "when", "why", "with",
}
NON_ARTICLE_PATHS = re.compile(
    r"/(?:author|authors|tag|tags|category|categories|search|page|feed|privacy|terms)(?:/|$)",
    re.IGNORECASE,
)
MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "com.au", "net.au", "org.au", "co.nz",
    "com.br", "com.cn", "com.hk", "com.sg", "co.in", "co.za", "com.mx",
    "com.tr", "com.tw", "com.ar", "com.pl", "co.jp", "ne.jp",
}
EXCLUDED_HOSTS = {
    "reddit.com", "youtube.com", "youtu.be", "tiktok.com", "instagram.com",
    "facebook.com", "x.com", "twitter.com", "soundcloud.com", "spreaker.com",
    "libsyn.com", "podbean.com", "simplecast.com", "megaphone.fm", "acast.com",
    "omnycontent.com", "fireside.fm", "audioboom.com", "prx.org",
}
PODCAST_FEED = re.compile(r"\b(?:podcasts?|radio show|episodes?)\b", re.IGNORECASE)
PODCAST_PATH = re.compile(r"/(?:podcasts?|episodes?[^/]*|programmes?|talks?)(?:/|$)", re.IGNORECASE)
NON_ARTICLE_FEED = re.compile(r"\b(?:memes?|videos?|music videos?|talks? daily)\b", re.IGNORECASE)
LIKELY_PAYWALL_HOSTS = {
    "nytimes.com", "wsj.com", "washingtonpost.com", "bostonglobe.com",
    "latimes.com", "ft.com", "economist.com", "bloomberg.com", "thetimes.co.uk",
    "telegraph.co.uk", "newyorker.com", "hbr.org",
}


@dataclass(frozen=True)
class Candidate:
    url: str
    feed_url: str
    feed_title: str
    entry_title: str
    language: str
    timestamp: str


def fetch(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def english_likely(text: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    if len(tokens) < 3:
        return False
    return len(ENGLISH_WORDS.intersection(tokens)) >= 2


def domain_key(url: str) -> str | None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return None
    labels = host.split(".")
    if len(labels) < 2:
        return None
    last_two = ".".join(labels[-2:])
    if last_two in MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def canonical_url(url: str) -> str | None:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if any(host == excluded or host.endswith("." + excluded) for excluded in EXCLUDED_HOSTS):
        return None
    if any(host == excluded or host.endswith("." + excluded) for excluded in LIKELY_PAYWALL_HOSTS):
        return None
    if PODCAST_PATH.search(parts.path):
        return None
    if parts.path in {"", "/"} or NON_ARTICLE_PATHS.search(parts.path):
        return None
    if any(ext in parts.path.lower() for ext in (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".mp3", ".mp4", ".xml")):
        return None
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if not key.lower().startswith("utm_")]
    clean_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, clean_query, ""))


def feed_candidates(feed_url: str, feed_title: str) -> list[Candidate]:
    if PODCAST_FEED.search(feed_title) or NON_ARTICLE_FEED.search(feed_title):
        return []
    try:
        root = ET.fromstring(fetch(feed_url))
    except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as error:
        print(f"Skip feed {feed_url}: {error}", file=sys.stderr)
        return []

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    channel = root.find("channel") if root_name == "rss" else root
    language = ""
    if channel is not None:
        for child in channel:
            if child.tag.rsplit("}", 1)[-1].lower() in {"language", "lang"}:
                language = (child.text or "").strip().lower()
                break

    entries = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}:
            entries.append(element)

    candidates: list[Candidate] = []
    for entry in entries:
        fields: dict[str, str] = {}
        link = ""
        for child in entry.iter():
            name = child.tag.rsplit("}", 1)[-1].lower()
            if name == "link":
                link = child.attrib.get("href", "") or (child.text or "").strip() or link
            elif name in {"title", "description", "summary", "content", "pubdate", "published", "updated", "language"}:
                fields.setdefault(name, " ".join(child.itertext()).strip())

        clean_url = canonical_url(link)
        title = fields.get("title", "")
        if not clean_url or not title:
            continue
        entry_language = fields.get("language", "").lower() or language
        text_hint = " ".join((title, fields.get("description", ""), fields.get("summary", "")))
        if entry_language and not entry_language.startswith("en"):
            continue
        if not entry_language and not english_likely(text_hint):
            continue
        candidates.append(
            Candidate(
                clean_url,
                feed_url,
                feed_title,
                title,
                entry_language,
                fields.get("published", fields.get("pubdate", fields.get("updated", ""))),
            )
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--per-domain", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "article_urls.txt",
    )
    parser.add_argument("--manifest", type=Path, help="Optional JSONL provenance output")
    args = parser.parse_args()
    if args.count < 1 or args.per_domain < 1:
        raise SystemExit("--count and --per-domain must be positive")

    try:
        catalog = json.loads(fetch(CATALOG_API).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise SystemExit(f"Could not load public RSS catalog: {error}") from error

    category_files = [
        item for item in catalog
        if item.get("name", "").lower().endswith(".opml") and item.get("download_url")
    ]
    feed_map: dict[str, str] = {}
    for item in category_files:
        try:
            opml = ET.fromstring(fetch(item["download_url"]))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as error:
            print(f"Skip category {item.get('name')}: {error}", file=sys.stderr)
            continue
        for outline in opml.iter("outline"):
            feed_url = outline.attrib.get("xmlUrl")
            feed_title = outline.attrib.get("title") or outline.attrib.get("text") or ""
            if feed_url:
                feed_map.setdefault(feed_url, feed_title)

    print(f"Fetching {len(feed_map)} unique candidate feeds", file=sys.stderr)
    candidates: list[Candidate] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(feed_candidates, url, title) for url, title in feed_map.items()]
        for future in concurrent.futures.as_completed(futures):
            candidates.extend(future.result())

    # Shuffle a stable candidate order so one category or hostname range does not
    # dominate the URL list. Feed recency order is retained only as a source hint.
    candidates.sort(key=lambda item: item.url)
    random.Random(42).shuffle(candidates)
    chosen: list[Candidate] = []
    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}
    for candidate in candidates:
        if candidate.url in seen_urls:
            continue
        domain = domain_key(candidate.url)
        if not domain or domain_counts.get(domain, 0) >= args.per_domain:
            continue
        seen_urls.add(candidate.url)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        chosen.append(candidate)
        if len(chosen) >= args.count:
            break

    if len(chosen) < args.count:
        raise SystemExit(
            f"Found only {len(chosen)} qualifying URLs from {len(domain_counts)} domains; "
            "no output file was written. Add more English feed sources and retry."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(f"{item.url}\n" for item in chosen), encoding="utf-8")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest.open("w", encoding="utf-8") as output:
            for item in chosen:
                record = {
                    "url": item.url,
                    "domain": domain_key(item.url),
                    "feed": item.feed_url,
                    "feed_title": item.feed_title,
                    "article_title": item.entry_title,
                    "feed_language": item.language,
                    "published": item.timestamp,
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"Saved {len(chosen)} URLs across {len(domain_counts)} domains to {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
