#!/bin/sh
# The update workflow's second job: one pull request a plugin, on update/<id>.
#   env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, RUNNER_TEMP
set -eu
out="$RUNNER_TEMP/updates"
gh run download "$GITHUB_RUN_ID" -n updates -D "$out"
for id in $(python3 -I -c 'import json,sys; print(" ".join(u["id"] for u in json.load(open(sys.argv[1]))))' "$out/updates.json"); do
    case "$id" in
        *[!a-z0-9._-]* | '') echo "skipping a bad ID"; continue ;;
    esac
    tools/ci/open_pr.sh updates "update/$id" "$id"
done
