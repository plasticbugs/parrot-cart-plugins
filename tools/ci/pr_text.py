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

CHECKLIST = """
Before merging, check that:

- [ ] The repo and the release have no commercial game art, ROMs or other files the author can't share.
- [ ] The README credits the work the plugin uses, and the licence fits. GPL and LGPL code needs the full source linked.
- [ ] The plugin is free. Nothing in the repo sells it or bundles it with hardware.
- [ ] The description is accurate.
- [ ] The screenshots in `plugins/<id>/` show the plugin itself, with no commercial game art.
- [ ] The README and release notes are fine to show on the site.
"""


def main():
    src, out, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
    es = []
    for pid in ids:
        with open(registry.entry_path(src, pid)) as f:
            es.append(json.load(f))
    os.makedirs(out, exist_ok=True)
    names = ", ".join(f"{e['name']} {e['version']}" for e in es)
    issue = os.environ.get("ISSUE_NUMBER", "")
    kind = "Add" if issue else "Update"
    title = f"{kind} {names}"[:200]
    with open(os.path.join(src, "report.md")) as f:
        report = f.read()
    body = [report, CHECKLIST]
    for e in es:
        body.append(f"`{e['id']}` from https://github.com/{e['repo']} at `{e['release']['tag']}`: "
                    f"{e['download']['url']} (SHA-256 `{e['download']['sha256']}`).")
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
