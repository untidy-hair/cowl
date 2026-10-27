#!/usr/bin/env python3
"""Label one normalized webpage with xAI Grok or OpenAI GPT-6 Luna.

Setup from the project root::

    uv sync

Set the provider key, then run::

    XAI_API_KEY=... uv run python scripts/label_page_with_llm.py \\
        data/pages/001.json

OpenAI GPT-6 Luna example::

    OPENAI_API_KEY=... uv run python scripts/label_page_with_llm.py \\
        data/pages/001.json --provider openai --model gpt-6-luna

Use ``--dry-run`` to inspect the generated prompt without making an API call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ALLOWED_ROLES = {"discard", "title", "date", "heading", "paragraph", "list"}
DEFAULT_MODELS = {"xai": "grok-4.3", "openai": "gpt-6-luna"}


def parse_arguments() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Normalized page JSON file")
    parser.add_argument(
        "--provider",
        choices=("xai", "openai"),
        default="xai",
        help="API provider (default: xai)",
    )
    parser.add_argument("--model", help="Model ID; defaults to grok-4.3 or gpt-6-luna")
    parser.add_argument(
        "--output",
        type=Path,
        help="Label output path (default: data/labels/<page_id>.labels.json)",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=project_dir / "LLM_JUDGE_INSTRUCTIONS.md",
        help="Judge-instruction Markdown file",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=16_000,
        help="Maximum model output tokens (default: 16000)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="Maximum API attempts after invalid output (default: 3)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print the prompt without an API call")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SystemExit(f"Input file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {path}: {error}") from error

    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object in {path}")
    return value


def extract_system_prompt(path: Path) -> str:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise SystemExit(f"Judge instruction file not found: {path}") from error

    section = "## System Prompt"
    start = contents.find(section)
    if start == -1:
        raise SystemExit(f"Missing {section!r} section in {path}")

    fence_start = contents.find("```text", start)
    fence_end = contents.find("```", fence_start + len("```text"))
    if fence_start == -1 or fence_end == -1:
        raise SystemExit(f"Could not find the system-prompt code block in {path}")

    return contents[fence_start + len("```text") : fence_end].strip()


def validate_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = page.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise SystemExit("The normalized page must contain a non-empty blocks array")

    block_ids: set[int] = set()
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("id"), int):
            raise SystemExit("Every block must be an object with an integer id")
        if block["id"] in block_ids:
            raise SystemExit(f"Duplicate block ID: {block['id']}")
        if not isinstance(block.get("text"), str):
            raise SystemExit(f"Block {block['id']} is missing text")
        block_ids.add(block["id"])
    return blocks


def make_user_prompt(page: dict[str, Any], correction: str | None = None) -> str:
    block_ids = [block["id"] for block in page["blocks"]]
    prompt = (
        "Label the supplied webpage blocks according to the system instructions. "
        "Use the text and neighboring context as the primary evidence; tags and paths "
        "are hints only. Do not write or alter page text.\n\n"
        f"Every input block ID must appear exactly once as a string key in roles: {json.dumps(block_ids)}. "
        "Return article_order as integer IDs for every non-discard block, exactly once, "
        "in natural reading order.\n\n"
        "Return exactly this JSON structure, with no extra keys:\n"
        '{"roles":{"<block ID>":"discard|title|date|heading|paragraph|list"},'
        '"article_order":[<integer block IDs in natural reading order>]}\n\n'
        "PAGE_DATA:\n"
        + json.dumps(page, ensure_ascii=False, separators=(",", ":"))
    )
    if correction:
        prompt += (
            "\n\nThe previous response was invalid: "
            + correction
            + " Return a corrected JSON object only."
        )
    return prompt


def request_json(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
) -> tuple[str, dict[str, Any]]:
    if provider == "xai":
        api_key = os.environ.get("XAI_API_KEY")
        endpoint = "https://api.x.ai/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
        }
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        endpoint = "https://api.openai.com/v1/responses"
        payload = {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_output_tokens,
            "text": {"format": {"type": "json_object"}},
        }

    if not api_key:
        key_name = "XAI_API_KEY" if provider == "xai" else "OPENAI_API_KEY"
        raise SystemExit(f"Set {key_name} before calling the {provider} API")

    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{provider} API returned HTTP {error.code}: {body}") from error
    except TimeoutError as error:
        raise RuntimeError(f"{provider} API request timed out after 180s") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the {provider} API: {error.reason}") from error

    if provider == "xai":
        try:
            text = response_body["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as error:
            raise RuntimeError(f"Unexpected xAI API response: {response_body}") from error
    else:
        text = response_body.get("output_text")
        if not isinstance(text, str):
            text = extract_openai_output_text(response_body)

    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"The {provider} API returned no text output: {response_body}")
    return text, response_body


def extract_openai_output_text(response_body: dict[str, Any]) -> str | None:
    pieces: list[str] = []
    for output_item in response_body.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content in output_item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    return "".join(pieces) or None


def validate_labels(result: Any, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(result, dict) or set(result) != {"roles", "article_order"}:
        raise ValueError("top-level keys must be exactly roles and article_order")

    roles = result["roles"]
    order = result["article_order"]
    if not isinstance(roles, dict) or not isinstance(order, list):
        raise ValueError("roles must be an object and article_order must be an array")

    input_ids = {block["id"] for block in blocks}
    expected_role_ids = {str(block_id) for block_id in input_ids}
    if set(roles) != expected_role_ids:
        raise ValueError("roles must contain every input block ID exactly once")
    if any(role not in ALLOWED_ROLES for role in roles.values()):
        raise ValueError(f"roles must be one of: {', '.join(sorted(ALLOWED_ROLES))}")
    if sum(role == "title" for role in roles.values()) > 1:
        raise ValueError("at most one block may have the title role")
    if not all(isinstance(block_id, int) and not isinstance(block_id, bool) for block_id in order):
        raise ValueError("article_order must contain integer block IDs")
    if len(order) != len(set(order)):
        raise ValueError("article_order may not contain duplicate IDs")
    if not set(order).issubset(input_ids):
        raise ValueError("article_order contains an unknown block ID")

    selected_ids = {int(block_id) for block_id, role in roles.items() if role != "discard"}
    if set(order) != selected_ids:
        raise ValueError("article_order must contain every non-discard block exactly once")
    return result


def write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        json.dump(value, temporary_file, ensure_ascii=False, indent=2)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)


def main() -> None:
    arguments = parse_arguments()
    if arguments.attempts < 1 or arguments.max_output_tokens < 1:
        raise SystemExit("--attempts and --max-output-tokens must be positive")

    page = load_json(arguments.input)
    blocks = validate_page(page)
    system_prompt = extract_system_prompt(arguments.prompt_file)
    model = arguments.model or DEFAULT_MODELS[arguments.provider]
    page_id = str(page.get("page_id") or arguments.input.stem)
    output_path = arguments.output or (
        Path(__file__).resolve().parents[1] / "data" / "labels" / f"{page_id}.labels.json"
    )

    if output_path.exists() and not arguments.force:
        raise SystemExit(f"Output already exists: {output_path}. Use --force to overwrite it.")

    user_prompt = make_user_prompt(page)
    if arguments.dry_run:
        print("=== SYSTEM INSTRUCTIONS ===")
        print(system_prompt)
        print("\n=== USER INPUT AND REQUIRED OUTPUT ===")
        print(user_prompt)
        return

    last_error = ""
    for attempt in range(1, arguments.attempts + 1):
        try:
            raw_text, api_response = request_json(
                arguments.provider,
                model,
                system_prompt,
                make_user_prompt(page, last_error or None),
                arguments.max_output_tokens,
            )
            labels = validate_labels(json.loads(raw_text), blocks)
        except (json.JSONDecodeError, RuntimeError, ValueError) as error:
            last_error = str(error)
            print(f"Attempt {attempt}/{arguments.attempts} failed: {last_error}", file=sys.stderr)
            continue

        output = {
            "source_page": page,
            "judge": {
                "provider": arguments.provider,
                "model": model,
                "prompt_file": str(arguments.prompt_file),
                "labeled_at": datetime.now(timezone.utc).isoformat(),
                "attempt": attempt,
                "api_response_id": api_response.get("id"),
            },
            "labels": labels,
        }
        write_json_atomically(output_path, output)
        print(f"Saved validated labels: {output_path}")
        return

    raise SystemExit(f"No valid labels after {arguments.attempts} attempts: {last_error}")


if __name__ == "__main__":
    main()
