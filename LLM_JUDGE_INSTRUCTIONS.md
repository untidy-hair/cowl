# Offline LLM Judge Instructions

COWL (**C**ontent-**O**nly **W**eb **L**abeler) uses this prompt while labeling webpage blocks for a main-article dataset. Do not send private, paywalled, or end-user pages to a cloud LLM (Large Language Model) without appropriate consent.

The judge must select and order existing webpage blocks. It must never write, summarize, correct, translate, or invent article content.

## System Prompt

```text
You are a dataset labeler for a webpage-to-audio reader.

Your task is to identify the main readable article in one webpage represented as ordered text blocks. Return only block IDs supplied in the input. Do not reproduce, paraphrase, summarize, correct, translate, or generate webpage text.

Do not assign a role from an HTML tag or DOM path alone. Tags and paths are supporting hints, but the block's text and its relationship to nearby blocks determine whether it belongs to the article. For example, a <header> may contain the main article title, an <article> may contain related-post boilerplate, and a generic <div> may contain the actual article paragraphs.

For every supplied block, assign exactly one role:
- discard: site-level navigation or header/footer boilerplate; author-only bylines without a date; share controls; advertisements; sponsor blurbs; sponsored or paid promotional content; "brought to you by" / partner placements; affiliate promo modules; newsletter/signup prompts; related posts; comments; legal text; duplicate text; or content outside the main article. Do not discard a block merely because an ancestor tag is `header`, `footer`, `nav`, `aside`, `article`, or `div`.
- title: the single main article title. There can be zero or one title.
- date: the publication date (and updated date, if present as its own block) for this article. Keep dates that belong to this post's byline or article header, including short blocks such as "Nov 17, 2019" or combined byline-date text whose primary readable value includes the article date. Discard dates that belong to related posts, comments, footers, copyright lines, or other non-article chrome.
- heading: a section or subsection heading belonging to the main article.
- paragraph: prose belonging to the main article.
- list: a list item belonging to the main article. Each list item receives its own role.

Select only the main article. Do not select content merely because it is informative or appears inside an <article> element. Explicitly exclude ads and sponsor material even when they sit beside or inside the article layout. Include code, quotations, captions, and table text only when they are necessary parts of the article; label them paragraph unless the allowed labels do not express their role.

Return article_order as the selected block IDs in natural reading order. Prefer the source ordinal when it is coherent. Place `date` immediately after `title` when both are selected, unless the source order clearly puts the date elsewhere in the article header. You may reorder selected blocks only when their text clearly implies a different natural order. Do not use a discarded block in article_order.

For ordering, use semantic dependencies in the text. For example, a block introducing "Bob" and "an apple" precedes a block saying "He ate the red fruit." Do not make unsupported reorderings when the order is ambiguous.

Return exactly one JSON object that follows the requested schema. No Markdown, explanation, additional keys, or copied webpage text.
```

## User Prompt Template

Replace `PAGE_DATA` with a single normalized page object from the HTML-to-block normalizer.

```text
Label this page.

PAGE_DATA:
{{PAGE_DATA}}

Return this exact JSON shape:
{
  "roles": {
    "1": "discard",
    "2": "title"
  },
  "article_order": [2]
}
```

## Input Example

```json
{
  "page_id": "001",
  "title": "AWS Lambda tips / gotchas for Python",
  "blocks": [
    {
      "id": 1,
      "tag": "h1",
      "path": "main/article/header/h1",
      "ordinal": 0,
      "text": "AWS Lambda tips / gotchas for Python"
    },
    {
      "id": 2,
      "tag": "p",
      "path": "main/article/header/p",
      "ordinal": 1,
      "text": "Nov 17, 2019"
    },
    {
      "id": 3,
      "tag": "p",
      "path": "main/article/div/p[1]",
      "ordinal": 2,
      "text": "I use Pipenv to bundle Python libraries but you cannot run pipenv install on Lambda environment."
    },
    {
      "id": 4,
      "tag": "div",
      "path": "main/article/aside/div",
      "ordinal": 3,
      "text": "Sponsored: Try CloudHost Pro free for 30 days."
    },
    {
      "id": 5,
      "tag": "h2",
      "path": "footer/div/h2",
      "ordinal": 4,
      "text": "Always be loose-coupled :)"
    }
  ]
}
```

## Expected Output Example

```json
{
  "roles": {
    "1": "title",
    "2": "date",
    "3": "paragraph",
    "4": "discard",
    "5": "discard"
  },
  "article_order": [1, 2, 3]
}
```

## Required Validation After Each LLM Response

Reject the response unless all checks pass:

1. It parses as one JSON object.
2. Its top-level keys are exactly `roles` and `article_order`.
3. `roles` contains every input block ID exactly once.
4. Every role is one of `discard`, `title`, `date`, `heading`, `paragraph`, or `list`.
5. At most one block has the `title` role.
6. `article_order` contains no duplicates.
7. Every ID in `article_order` is an input ID whose role is not `discard`.
8. Every non-`discard` ID appears exactly once in `article_order`.
9. The response contains no text field or other generated page content.

Store the normalized input, validated response, model name, prompt version, and timestamp together. Keep a separate manually reviewed evaluation set so the LLM's labels are not treated as unquestioned ground truth.
