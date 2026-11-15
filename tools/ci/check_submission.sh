#!/bin/sh
# The submission workflow's first job (read-only token): the issue -> out/
# (report.md, result.json, plugins/<id>.json). Reads the plugin's repository
# through GitHub's API and runs nothing from it.
#   env: ISSUE_NUMBER, GH_TOKEN, GITHUB_REPOSITORY, GITHUB_OUTPUT, RUNNER_TEMP
set -eu
case "$ISSUE_NUMBER" in
    '' | *[!0-9]*) echo "not an issue number"; exit 3 ;;
esac
gh api "repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER" > "$RUNNER_TEMP/issue.json"
rm -rf out
set +e
python3 -I tools/validate.py --issue-json "$RUNNER_TEMP/issue.json" --out out
code=$?
set -e
echo "issue=$ISSUE_NUMBER" >> "$GITHUB_OUTPUT"
case $code in
    0) echo "ok=true" >> "$GITHUB_OUTPUT" ;;
    1 | 2) echo "ok=false" >> "$GITHUB_OUTPUT" ;;
    3) echo "skip=true" >> "$GITHUB_OUTPUT"; mkdir -p out; : > out/skip ;;
    *) exit "$code" ;;
esac
