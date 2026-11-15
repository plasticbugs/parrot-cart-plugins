"""apply_entries -- copy checked entries into this checkout's plugins/.

    python3 tools/apply_entries.py SRC_DIR [ID ...]

SRC_DIR is a validator's --out folder (from a workflow artifact). Only
SRC_DIR/plugins/<id>.json and the files that entry names in
SRC_DIR/plugins/<id>/ are read. Each entry must be well formed
(registry.check_entry) with a name matching its ID, and its files must be
exactly the ones it lists, with their sizes and SHA-256s, each passing its
own check again (registry.check_files), or nothing is copied. An entry's
old files are replaced. Prints the IDs copied, one a line.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    src, want = args[0], set(args[1:])
    d = os.path.join(src, "plugins")
    names = sorted(n for n in os.listdir(d) if n.endswith(".json")) if os.path.isdir(d) else []
    todo = []
    for n in names:
        pid = n[:-5]
        if want and pid not in want:
            continue
        path = os.path.join(d, n)
        if os.path.islink(path) or os.path.getsize(path) > registry.ENTRY_MAX:
            print(f"{n}: not a plain, small file", file=sys.stderr)
            return 1
        with open(path) as f:
            e = json.load(f)
        bad = registry.check_entry(e, n)
        if e.get("example"):
            bad.append("an example can't go in plugins/")
        if not bad:
            bad += registry.check_files(os.path.join(d, pid), e)
        if bad:
            print(f"{n}: " + "; ".join(bad), file=sys.stderr)
            return 1
        todo.append((pid, e))
    for pid, e in todo:
        registry.write_json(registry.entry_path(registry.ROOT, pid), e)
        dst = registry.files_dir(registry.ROOT, pid)
        shutil.rmtree(dst, ignore_errors=True)
        for name in registry.entry_files(e):
            os.makedirs(dst, exist_ok=True)
            shutil.copyfile(os.path.join(d, pid, name), os.path.join(dst, name))
        print(pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
