from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def normalize_mod():
    return load_script("normalize_html_to_blocks")


@pytest.fixture(scope="session")
def label_mod():
    return load_script("label_page_with_llm")


@pytest.fixture(scope="session")
def collect_mod():
    return load_script("collect_article_urls")
