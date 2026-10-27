from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_and_normalize_url.sh"


def test_help_exits_with_usage():
    result = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 64
    assert "Usage:" in result.stderr


def test_missing_id_file_is_a_setup_error(tmp_path, monkeypatch):
    # Run from a copy without current_id.txt so we do not mutate the real counter.
    work = tmp_path / "proj"
    scripts = work / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "capture_and_normalize_url.sh").write_text(SCRIPT.read_text())
    (scripts / "normalize_html_to_blocks.py").write_text("#!/usr/bin/env python3\n")
    copied = scripts / "capture_and_normalize_url.sh"
    copied.chmod(0o755)
    result = subprocess.run(
        ["bash", str(copied), "https://example.com/post"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 66
    assert "Missing ID file" in result.stderr
