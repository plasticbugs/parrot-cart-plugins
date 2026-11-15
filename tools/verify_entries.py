"""verify_entries -- check entries in plugins/ against GitHub as it is now.

    python3 tools/verify_entries.py [--fixtures DIR] ID ...

Each entry is made again from its repository's release (tools/validate.py,
at the entry's tag, as if it weren't listed) and compared field by field:
the file's SHA-256, the header's fields, the links, the licence, the
newest release's notes, and the README and screenshot files beside the
entry (plugins/<id>/), which must be the release's own, byte for byte.
Older versions' notes in the entry's history aren't read again. Run on
every pull request that changes plugins/, so an entry can't say what the
release doesn't (an edited bot PR, or one written by hand).

Exit status: 0 they match, 1 they don't, 2 GitHub couldn't be read.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghapi  # noqa: E402
import registry  # noqa: E402
import validate  # noqa: E402

SAME = ("id", "name", "version", "by", "repo", "repo_id", "owner", "api", "home", "opens", "uses", "icon",
        "file_icon", "source_url", "credits_url", "release", "download", "image", "readme", "screenshots")


def verify(gh, pid, root=registry.ROOT, config=None):
    """the differences between plugins/<pid>.json and its release ([] if none)"""
    config = config or registry.load_config(root)
    entries = registry.load_entries(root)
    e = entries.get(pid)
    if e is None:
        return [f"{pid}: no plugins/{pid}.json"]
    bad = [f"{pid}: {p}" for p in registry.check_entry(e, pid + ".json")]
    if bad:
        return bad
    bad += [f"{pid}: {p}" for p in registry.check_files(registry.files_dir(root, pid), e)]
    others = {k: v for k, v in entries.items() if k != pid}
    res = validate.validate(gh, e["repo"], e["release"]["tag"], e.get("description") or "-", root=root,
                            config=config, entries=others)
    got = next((p for p in res["plugins"] if p["id"] == pid), None)
    if not res["ok"] or got is None or got["entry"] is None:
        why = res["errors"] + [x for p in res["plugins"] for x in p["errors"]]
        return bad + [f"{pid}: its release doesn't pass: " + ("; ".join(why) or f"no {pid} in it")]
    fresh = got["entry"]
    for k in SAME:
        if e.get(k) != fresh.get(k):
            bad.append(f"{pid}: {k} is {e.get(k)!r}; the release says {fresh.get(k)!r}")
    if e["history"][0] != fresh["history"][0]:
        bad.append(f"{pid}: the notes for {e['version']} aren't the release's")
    for k in ("spdx", "url"):
        if e["license"].get(k) != fresh["license"].get(k):
            bad.append(f"{pid}: license.{k} is {e['license'].get(k)!r}; GitHub says {fresh['license'].get(k)!r}")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--fixtures")
    a = ap.parse_args(argv)
    gh = validate.gh_from(a.fixtures)
    bad = []
    try:
        for pid in a.ids:
            bad += verify(gh, pid)
    except ghapi.GitHubError as e:
        print(f"GitHub couldn't be read: {e}")
        return 2
    for b in bad:
        print(b)
    print(f"{len(a.ids)} entries match their releases" if not bad else f"{len(bad)} differences")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
