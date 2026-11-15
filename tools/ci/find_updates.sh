#!/bin/sh
# The update workflow's first job (read-only): new releases of listed
# plugins -> out/ (updates.json, one folder per plugin, summary.md).
#   env: GITHUB_TOKEN, GITHUB_OUTPUT, GITHUB_STEP_SUMMARY
set -eu
rm -rf out
python3 -I tools/find_updates.py --out out
cat out/summary.md >> "$GITHUB_STEP_SUMMARY"
if python3 -I -c 'import json,sys; sys.exit(0 if json.load(open("out/updates.json")) else 1)'; then
    echo "any=true" >> "$GITHUB_OUTPUT"
else
    echo "any=false" >> "$GITHUB_OUTPUT"
fi
