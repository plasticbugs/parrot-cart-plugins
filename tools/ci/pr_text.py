"""pr_text -- a registry pull request's title, body and commit message.

    python3 tools/ci/pr_text.py SRC_DIR OUT_DIR ID ...

SRC_DIR is the validator's --out folder (report.md, plugins/). Names and
versions come from entries that tools/apply_entries.py has checked; the
report's untrusted text was escaped by tools/validate.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import registry  # noqa: E402
import sitecopy  # noqa: E402

T = sitecopy.COPY


def checklist():
    """the reviewer's checklist: site/copy.toml's [bot.pr]"""
    items = "".join(f"- [ ] {c}\n" for c in T.texts("bot.pr.checklist"))
    return "\n" + T.text("bot.pr.checklist_intro") + "\n\n" + items


def main():
    src, out, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
    es = []
    for pid in ids:
        with open(registry.entry_path(src, pid)) as f:
            es.append(json.load(f))
    os.makedirs(out, exist_ok=True)
    names = ", ".join(f"{e['name']} {e['version']}" for e in es)
    issue = os.environ.get("ISSUE_NUMBER", "")
    title = (T.text("bot.pr.title_new", plugins=names) if issue
             else T.text("bot.pr.title_update", plugins=names))[:200]
    with open(os.path.join(src, "report.md")) as f:
        report = f.read()
    body = [report, checklist()]
    for e in es:
        body.append(T.text("bot.pr.source_line", id=e["id"], repo_url=f"https://github.com/{e['repo']}",
                           tag=e["release"]["tag"], download_url=e["download"]["url"],
                           sha256=e["download"]["sha256"]))
    if issue.isdigit():
        body.append(f"\nCloses #{issue}")
    with open(os.path.join(out, "title.txt"), "w") as f:
        f.write(title.replace("\n", " "))
    with open(os.path.join(out, "body.md"), "w") as f:
        f.write("\n".join(body) + "\n")
    with open(os.path.join(out, "commit.txt"), "w") as f:
        f.write(f"{title}\n\n" + "\n".join(f"{e['id']} {e['version']} from {e['repo']} {e['release']['tag']}"
                                           for e in es) + "\n")


if __name__ == "__main__":
    main()
