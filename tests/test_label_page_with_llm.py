from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

BLOCKS = [
    {"id": 1, "tag": "h1", "text": "AWS Lambda tips"},
    {"id": 2, "tag": "p", "text": "Nov 17, 2019"},
    {"id": 3, "tag": "p", "text": "I use Pipenv."},
    {"id": 4, "tag": "div", "text": "Sponsored: CloudHost Pro"},
]


def test_extracts_system_prompt_from_instructions(label_mod):
    prompt = label_mod.extract_system_prompt(ROOT / "LLM_JUDGE_INSTRUCTIONS.md")
    assert "dataset labeler" in prompt
    assert "discard" in prompt
    assert "date:" in prompt
    assert "Do not reproduce" in prompt


def test_validate_page_requires_blocks(label_mod):
    with pytest.raises(SystemExit, match="non-empty blocks array"):
        label_mod.validate_page({"page_id": "001", "blocks": []})


def test_validate_labels_accepts_date_and_discards_sponsor(label_mod):
    result = {
        "roles": {
            "1": "title",
            "2": "date",
            "3": "paragraph",
            "4": "discard",
        },
        "article_order": [1, 2, 3],
    }
    assert label_mod.validate_labels(result, BLOCKS) == result


@pytest.mark.parametrize(
    ("result", "match"),
    [
        ({"roles": {"1": "title"}}, "top-level keys"),
        (
            {
                "roles": {"1": "title", "2": "date", "3": "paragraph"},
                "article_order": [1, 2, 3],
            },
            "every input block ID",
        ),
        (
            {
                "roles": {
                    "1": "title",
                    "2": "date",
                    "3": "paragraph",
                    "4": "ad",
                },
                "article_order": [1, 2, 3],
            },
            "roles must be one of",
        ),
        (
            {
                "roles": {
                    "1": "title",
                    "2": "title",
                    "3": "paragraph",
                    "4": "discard",
                },
                "article_order": [1, 2, 3],
            },
            "at most one block may have the title role",
        ),
        (
            {
                "roles": {
                    "1": "title",
                    "2": "date",
                    "3": "paragraph",
                    "4": "discard",
                },
                "article_order": [1, 2],
            },
            "every non-discard block exactly once",
        ),
        (
            {
                "roles": {
                    "1": "title",
                    "2": "date",
                    "3": "paragraph",
                    "4": "discard",
                },
                "article_order": [1, 2, 3, 3],
            },
            "duplicate IDs",
        ),
        (
            {
                "roles": {
                    "1": "title",
                    "2": "date",
                    "3": "paragraph",
                    "4": "discard",
                },
                "article_order": [1, 2, 4],
            },
            "every non-discard block exactly once",
        ),
    ],
)
def test_validate_labels_rejects_invalid_payloads(label_mod, result, match):
    with pytest.raises(ValueError, match=match):
        label_mod.validate_labels(result, BLOCKS)


def test_user_prompt_includes_block_ids_and_correction(label_mod):
    page = {"page_id": "001", "title": "AWS Lambda tips", "blocks": BLOCKS}
    prompt = label_mod.make_user_prompt(page)
    assert "[1, 2, 3, 4]" in prompt
    assert "PAGE_DATA:" in prompt
    assert "AWS Lambda tips" in prompt

    corrected = label_mod.make_user_prompt(page, "article_order must contain every non-discard block exactly once")
    assert "The previous response was invalid" in corrected
    assert "article_order must contain every non-discard block exactly once" in corrected


def test_write_json_atomically(label_mod, tmp_path):
    path = tmp_path / "labels" / "001.labels.json"
    label_mod.write_json_atomically(path, {"ok": True})
    assert path.read_text(encoding="utf-8").strip() == '{\n  "ok": true\n}'
