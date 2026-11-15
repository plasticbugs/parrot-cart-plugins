#!/bin/sh
# The submission workflow's comment job (issues: write): the check's report
# on the issue, editing the bot's last report rather than adding another.
#   env: ISSUE_NUMBER, GH_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, RUNNER_TEMP
set -eu
case "$ISSUE_NUMBER" in
    '' | *[!0-9]*) echo "not an issue number"; exit 1 ;;
esac
out="$RUNNER_TEMP/out"
gh run download "$GITHUB_RUN_ID" -n submission -D "$out"
[ -f "$out/skip" ] && { echo "not a submission: no comment"; exit 0; }
mark='<!-- parrotcart-registry-report -->'
old=$(gh api --paginate "repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER/comments" \
    --jq ".[] | select(.user.type == \"Bot\" and (.body | startswith(\"$mark\"))) | .id" | tail -n 1)
if [ -n "$old" ]; then
    gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$old" -F "body=@$out/report.md" > /dev/null
else
    gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$out/report.md"
fi
