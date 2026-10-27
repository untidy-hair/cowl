# COWL

**C**ontent-**O**nly **W**eb **L**abeler.

Offline tools to **collect article URLs**, **capture HTML into text blocks**, and **label the main readable article** with an LLM (Large Language Model), so you can train or evaluate a model that keeps the article and drops page chrome.

The judge assigns roles to existing blocks and an `article_order`. It does not rewrite or summarize the page. Ads, sponsors, nav, and related-post chrome are `discard`. This article's publication date is `date`. This repo stops at labels.

## Intended use

This is a **dataset tool**, not a production reader and not a general web scraper.

Use it to label **public** article pages so you can train or fine-tune a model that keeps the main text (title, date, headings, body, lists) and drops chrome (nav, ads, sponsors, related posts, footers).

It is **not** permission to fetch paywalled, private, or personal pages, or to ignore a site's terms. Captured HTML and labels stay on your machine (`data/` is gitignored). Labeling sends block text to a third-party LLM API (xAI or OpenAI), so do not feed confidential pages into the judge. Treat LLM labels as a first pass; review a sample before calling them ground truth.

## Setup

Needs `uv`, `curl`, and `python3` on `PATH`.

```bash
uv sync
cp scripts/current_id.txt.example scripts/current_id.txt
```

`scripts/current_id.txt` is gitignored. Start at `001` on a fresh clone.

## 1. Collect article URLs

Reads public RSS feeds from the Plenary curated catalog, prefers English-looking items, skips some paywall and podcast hosts, and caps URLs per domain.

```bash
uv run python scripts/collect_article_urls.py \
  --count 500 \
  --per-domain 3 \
  --output data/article_urls.txt \
  --manifest data/article_urls.manifest.jsonl
```

Re-running produces a **new** URL list, not a copy of a previous run.

## 2. Capture and normalize pages

`curl` saves HTML. `normalize_html_to_blocks.py` turns it into ordered blocks (id, tag, DOM path, ordinal, original text). Normalization does not decide what is article content.

```bash
./scripts/capture_and_normalize_url.sh 'https://example.com/article'
```

Many URLs in parallel:

```bash
cat data/article_urls.txt |
  xargs -n 1 -P 6 ./scripts/capture_and_normalize_url.sh
```

Failed fetches still consume an ID, so numbering can have gaps. Failed captures leave no JSON, so labeling can skip them.

Already-downloaded HTML:

```bash
uv run python scripts/normalize_html_to_blocks.py page.html \
  --page-id page-001 \
  --url 'https://example.com/article' \
  --output data/pages/page-001.json
```

## 3. Label with the LLM judge

Instructions: `LLM_JUDGE_INSTRUCTIONS.md`. Roles: `discard`, `title`, `date`, `heading`, `paragraph`, `list`.

```bash
export XAI_API_KEY='your-key'
uv run python scripts/label_page_with_llm.py data/pages/001.json
```

OpenAI GPT-6 Luna:

```bash
export OPENAI_API_KEY='your-key'
uv run python scripts/label_page_with_llm.py \
  data/pages/001.json \
  --provider openai \
  --model gpt-6-luna
```

Inspect the prompt without an API call:

```bash
uv run python scripts/label_page_with_llm.py data/pages/001.json --dry-run
```

Invalid JSON is retried up to three times; the error is sent back to the model. API timeouts count as failed attempts. Outputs: `data/labels/<page_id>.labels.json`.

Label a zero-padded ID range (the trailing `_` is `$0` for `sh -c` so the path is `$1`):

```bash
printf 'data/pages/%03d.json\n' $(seq 1 50) |
  xargs -n 1 -P 3 sh -c 'test -f "$1" && uv run python scripts/label_page_with_llm.py "$1"' _
```

Remaining unlabeled pages:

```bash
comm -23 \
  <(ls data/pages/*.json | xargs -n1 basename | sed 's/\.json$//' | sort) \
  <(ls data/labels/*.labels.json | xargs -n1 basename | sed 's/\.labels\.json$//' | sort) |
  while read id; do echo "data/pages/$id.json"; done |
  xargs -n 1 -P 3 uv run python scripts/label_page_with_llm.py
```

Review a sample before treating labels as ground truth. Re-labeling the same page can yield a different valid answer. `data/` is gitignored.

## Tests

```bash
uv run pytest
```

Tests cover HTML normalization, URL filters, and label validation. They do not call the LLM API.

## Layout

```text
LLM_JUDGE_INSTRUCTIONS.md
README.md
pyproject.toml
data/                  # gitignored artifacts
scripts/
  collect_article_urls.py
  capture_and_normalize_url.sh
  normalize_html_to_blocks.py
  label_page_with_llm.py
  current_id.txt.example
tests/
```

## License

[MIT](LICENSE). Use, copy, modify, and sell the software, including commercially. The license does not grant rights in other people's webpage content.
