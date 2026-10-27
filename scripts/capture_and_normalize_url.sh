#!/usr/bin/env bash

# Fetch one URL, normalize its HTML into text blocks, and advance current_id.txt.
#
# Setup from the project root:
#   uv sync
#   cp scripts/current_id.txt.example scripts/current_id.txt
#
# Run:
#   ./scripts/capture_and_normalize_url.sh https://example.com/article

set -euo pipefail

if [[ $# -ne 1 || "$1" == "--help" || "$1" == "-h" ]]; then
  echo "Usage: $(basename "$0") URL" >&2
  exit 64
fi

url="$1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$script_dir/.." && pwd)"
normalizer="$script_dir/normalize_html_to_blocks.py"
id_file="$script_dir/current_id.txt"
id_lock="${id_file}.lock"
output_dir="$project_dir/data/pages"
html_temp=""
json_temp=""
lock_held=0

if [[ ! -x "$normalizer" && ! -f "$normalizer" ]]; then
  echo "Normalizer not found: $normalizer" >&2
  exit 66
fi

if [[ ! -f "$id_file" ]]; then
  echo "Missing ID file: $id_file" >&2
  exit 66
fi

cleanup() {
  local exit_status=$?
  [[ -n "$html_temp" && -e "$html_temp" ]] && rm -f "$html_temp"
  [[ -n "$json_temp" && -e "$json_temp" ]] && rm -f "$json_temp"
  if [[ "$lock_held" -eq 1 ]]; then
    rmdir "$id_lock" 2>/dev/null || true
  fi
  exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

while ! mkdir "$id_lock" 2>/dev/null; do
  sleep 0.05
done
lock_held=1

current_id="$(tr -d '[:space:]' < "$id_file")"
if [[ ! "$current_id" =~ ^[0-9]+$ ]]; then
  rmdir "$id_lock"
  lock_held=0
  echo "Invalid ID in $id_file: $current_id" >&2
  exit 65
fi

printf -v next_id "%0${#current_id}d" "$((10#$current_id + 1))"
printf '%s\n' "$next_id" > "$id_file"
rmdir "$id_lock"
lock_held=0

mkdir -p "$output_dir"
html_path="$output_dir/$current_id.html"
json_path="$output_dir/$current_id.json"

if [[ -e "$html_path" || -e "$json_path" ]]; then
  echo "Refusing to overwrite existing capture for ID $current_id" >&2
  exit 73
fi

html_temp="$(mktemp "$output_dir/.${current_id}.html.XXXXXX")"
json_temp="$(mktemp "$output_dir/.${current_id}.json.XXXXXX")"

echo "Fetching $url as ID $current_id"
curl \
  --location \
  --fail \
  --compressed \
  --retry 2 \
  --connect-timeout 20 \
  --max-time 60 \
  --user-agent 'Mozilla/5.0 (compatible; COWL/1.0; Content-Only Web Labeler)' \
  --output "$html_temp" \
  "$url"

mv "$html_temp" "$html_path"
html_temp=""

python3 "$normalizer" \
  "$html_path" \
  --page-id "$current_id" \
  --url "$url" \
  --output "$json_temp"

mv "$json_temp" "$json_path"
json_temp=""

echo "Saved HTML: $html_path"
echo "Saved blocks: $json_path"
echo "Reserved next ID: $next_id"
