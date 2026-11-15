#!/bin/sh
# Opens (or updates) a pull request with checked entries: the submission
# workflow's last job and the update workflow's (contents and
# pull-requests: write). The entries come from the read-only job's artifact
# and are checked again before they're copied (tools/apply_entries.py).
#   open_pr.sh ARTIFACT BRANCH [ID]
#   env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, RUNNER_TEMP, ISSUE_NUMBER (submissions)
set -eu
artifact=$1 branch=$2 only=${3:-}
case "$branch" in
    submission/[0-9]* | update/[a-z0-9]*) ;;
    *) echo "unexpected branch name"; exit 1 ;;
esac
out="$RUNNER_TEMP/$artifact"
[ -d "$out" ] || gh run download "$GITHUB_RUN_ID" -n "$artifact" -D "$out"
src="$out"
[ -n "$only" ] && src="$out/$only"
git fetch --no-tags origin main
git checkout -B "$branch" origin/main
ids=$(python3 -I tools/apply_entries.py "$src" $only)
[ -n "$ids" ] || { echo "nothing to add"; exit 0; }
python3 -I tools/ci/pr_text.py "$src" "$RUNNER_TEMP/pr" $ids
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add plugins
git commit -q -F "$RUNNER_TEMP/pr/commit.txt"
git push -q --force origin "$branch"
title=$(cat "$RUNNER_TEMP/pr/title.txt")
if [ -n "$(gh pr list --repo "$GITHUB_REPOSITORY" --head "$branch" --state open --json number --jq '.[].number')" ]; then
    gh pr edit "$branch" --repo "$GITHUB_REPOSITORY" --title "$title" --body-file "$RUNNER_TEMP/pr/body.md"
else
    gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" --title "$title" \
        --body-file "$RUNNER_TEMP/pr/body.md"
fi
