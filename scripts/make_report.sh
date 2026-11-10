#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"

python3 "$REPO_ROOT/scripts/summarize_results.py"
python3 "$REPO_ROOT/scripts/make_report.py"

log "Report ready — open results/index.html in a browser."
