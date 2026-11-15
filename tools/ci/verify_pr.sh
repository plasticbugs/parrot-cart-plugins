#!/bin/sh
# The tests workflow, on a pull request: every entry it adds or changes in
# plugins/ must match its release on GitHub (tools/verify_entries.py).
#   env: GITHUB_TOKEN, BASE_SHA
set -eu
ids=$(git diff --name-only --diff-filter=AM "$BASE_SHA" HEAD -- 'plugins/*.json' | sed -n 's|^plugins/\(.*\)\.json$|\1|p')
if [ -z "$ids" ]; then
    echo "no entries changed"
    exit 0
fi
python3 -I tools/verify_entries.py $ids
