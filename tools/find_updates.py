"""find_updates -- the scheduled job: new releases of listed plugins.

    python3 tools/find_updates.py --out DIR [--fixtures DIR] [--today YYYY-MM-DD]

For each plugin in plugins/, it asks GitHub for its repository's latest
release. A release with a new tag is checked in full (tools/validate.py),
for the plugins that repository already has listed. Each one that passes
and has a newer version goes in DIR/<id>/ (report.md, plugins/<id>.json),
ready for a pull request; DIR/updates.json lists them, and DIR/summary.md
says what was found, including releases that didn't pass.

Exit status: 0 (even with nothing new), 2 if GitHub couldn't be read.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghapi  # noqa: E402
import registry  # noqa: E402
import validate  # noqa: E402


def find(gh, root=registry.ROOT, config=None, today=None):
    """[(repo, tag, result)] for each repository with a new release"""
    config = config or registry.load_config(root)
    entries = registry.load_entries(root)
    by_repo = {}
    for e in entries.values():
        by_repo.setdefault(e["repo"], []).append(e)
    found = []
    for repo, es in sorted(by_repo.items()):
        rel = gh.release(repo)
        if rel is None:
            continue
        tag = rel.get("tag_name")
        if not tag or all(e["release"]["tag"] == tag for e in es):
            continue
        res = validate.validate(gh, repo, tag, None, root=root, config=config, today=today,
                                only_ids={e["id"] for e in es})
        found.append((repo, tag, res))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixtures")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    gh = validate.gh_from(a.fixtures)
    try:
        found = find(gh, today=a.today)
    except ghapi.GitHubError as e:
        print(f"GitHub couldn't be read: {e}")
        return 2
    os.makedirs(a.out, exist_ok=True)
    updates, lines = [], ["## New releases of listed plugins", ""]
    for repo, tag, res in found:
        ok_ids = [p["id"] for p in res["plugins"] if p["entry"] and p["change"] == "update" and not p["errors"]]
        if res["ok"] and ok_ids:
            for pid in ok_ids:
                one = dict(res, changed=[pid], plugins=[p for p in res["plugins"] if p["id"] == pid])
                validate.write_out(one, os.path.join(a.out, pid), update=True)
                entry = one["plugins"][0]["entry"]
                updates.append({"id": pid, "name": entry["name"], "version": entry["version"], "repo": repo,
                                "tag": tag})
            lines.append(f"- {validate.md(repo)} {validate.md(tag)}: update for " + ", ".join(ok_ids))
        else:
            why = res["errors"] + [e for p in res["plugins"] for e in p["errors"]]
            lines.append(f"- {validate.md(repo)} {validate.md(tag)}: not updated: "
                         + "; ".join(validate.md(w) for w in why[:5] or ["nothing new to list"]))
    if not found:
        lines.append("No new releases.")
    registry.write_json(os.path.join(a.out, "updates.json"), updates)
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
