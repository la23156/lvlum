#!/usr/bin/env bash
# End-to-end pipeline: scrape Issuu -> extract entities -> export CSVs.
#
# Usage:
#   ./run_all.sh                 # full run (all 93 docs)
#   ./run_all.sh --limit 2       # smoke test: first 2 docs only
#
# Pass-through flags after --limit N go to the scraper/extractor where relevant.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
LIMIT_ARGS=()
EXTRA_EXTRACT=()

if [[ "${1:-}" == "--limit" ]]; then
  N="${2:?need a number after --limit}"
  LIMIT_ARGS=(--limit "$N")
  EXTRA_EXTRACT=(--limit-docs "$N")
  shift 2
fi

echo "==> [1/3] Scraping Issuu"
$PY scrape_issuu.py "${LIMIT_ARGS[@]}"

echo "==> [2/4] Extracting entities (vision OCR) + building people profiles"
$PY extract_entities.py "${EXTRA_EXTRACT[@]}" "$@"

echo "==> [3/4] Building semantic-search embeddings"
$PY embed_people.py

echo "==> [4/4] Exporting CSVs"
$PY export_csv.py

echo "==> Done. DB: data/db/alumni.sqlite  Exports: data/exports/"
echo "    Search:  python3 search.py \"climate policy\"   (keyword + semantic)"
echo "    Profile: python3 search.py --person \"Tsai\""
echo "    (optional) per-person bios: python3 build_summaries.py"
