"""registry -- the registry's files: its config, plugins/<id>.json, and
registry.json, the index a future installer reads.

    python3 tools/registry.py check          every entry against the schema
    python3 tools/registry.py index OUT      write registry.json to OUT

Standard library only.
"""
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cvp  # noqa: E402
import png  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = 2                     # an entry's layout (plugins/<id>.json)
INDEX_FORMAT = 1               # registry.json's layout

ID_RE = re.compile(r"[a-z0-9_-]+(\.[a-z0-9_-]+)+")
REPO_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")
HEX16 = re.compile(r"[0-9a-f]{16}")
HEX64 = re.compile(r"[0-9a-f]{64}")
DATE = re.compile(r"\d{4}-\d\d-\d\d")
USES = ("usb-host", "usb-device", "psram")

# the files an entry keeps beside it, in plugins/<id>/ (copies: a release can disappear)
CART_README = "cart-readme.txt"            # the .CVP's README section, byte for byte
WEB_README = "README.md"                   # the repository's README at the release's tag
SHOTS = tuple(f"screenshot-{i}.png" for i in (1, 2, 3))
WEB_README_MAX = 64 * 1024
NOTES_MAX = 8000                           # characters of one release's notes
HISTORY_MAX = 20                           # versions an entry remembers
ENTRY_MAX = 256 * 1024                     # an entry's JSON


def files_dir(root, pid, examples=False):
    """plugins/<id>/, where an entry's files are"""
    return entry_path(root, pid, examples)[:-5]


def load_config(root=ROOT):
    with open(os.path.join(root, "registry.config.json")) as f:
        c = json.load(f)
    if not REPO_RE.fullmatch(c.get("registry_repo", "")):
        raise ValueError("registry.config.json: registry_repo must be owner/repo")
    return c


def pages_url(config):
    """https://owner.github.io/repo/, from the one config value"""
    owner, repo = config["registry_repo"].split("/")
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner.lower()}.github.io/"
    return f"https://{owner.lower()}.github.io/{repo}/"


def entry_path(root, pid, examples=False):
    if not ID_RE.fullmatch(pid) or len(pid) > 32:
        raise ValueError(f"not a plugin ID: {pid!r}")
    return os.path.join(root, "examples" if examples else "", "plugins", pid + ".json")


def load_entries(root=ROOT, examples=False):
    """{id: entry} from plugins/ (or examples/plugins/)"""
    d = os.path.join(root, "examples" if examples else "", "plugins")
    out = {}
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name)) as f:
                e = json.load(f)
            out[e.get("id", name[:-5])] = e
    return out


def _https(s):
    return isinstance(s, str) and s.startswith("https://") and not re.search(r"[\s\"'<>`]", s)


def _file(v, name=None, extra=()):
    return (isinstance(v, dict) and isinstance(v.get("size"), int) and v["size"] > 0
            and isinstance(v.get("sha256"), str) and HEX64.fullmatch(v["sha256"])
            and (name is None or v.get("file") == name) and set(v) <= {"file", "size", "sha256", *extra})


def _readme_ok(v):
    if not isinstance(v, dict) or set(v) != {"cart", "web"}:
        return False
    c, w = v["cart"], v["web"]
    if c is not None and not (_file(c, CART_README, ("lines",)) and c["size"] <= cvp.README_MAX
                              and isinstance(c.get("lines"), int)):
        return False
    return w is None or (_file(w, WEB_README, ("url",)) and w["size"] <= WEB_README_MAX and _https(w.get("url")))


def _shots_ok(v):
    if not isinstance(v, list) or len(v) > len(SHOTS):
        return False
    names = [x.get("file") if isinstance(x, dict) else None for x in v]
    return (all(_file(x) and x["file"] in SHOTS and x["size"] <= png.MAX_BYTES for x in v)
            and names == sorted(set(names)))


def _history_ok(v, e):
    if not isinstance(v, list) or not 1 <= len(v) <= HISTORY_MAX:
        return False
    for h in v:
        if not (isinstance(h, dict) and set(h) == {"version", "tag", "url", "published", "notes"}
                and isinstance(h["version"], str) and re.fullmatch(r"\d+\.\d+\.\d+", h["version"])
                and isinstance(h["tag"], str) and h["tag"] and _https(h["url"])
                and isinstance(h["published"], str) and DATE.fullmatch(h["published"])
                and isinstance(h["notes"], str) and len(h["notes"]) <= NOTES_MAX):
            return False
    vs = [h["version"] for h in v]
    newest_first = all(cvp.vercmp(a, b) > 0 for a, b in zip(vs, vs[1:]))
    return newest_first and vs[0] == e.get("version") and v[0]["tag"] == (e.get("release") or {}).get("tag")


def check_entry(e, filename=None):
    """an entry's problems against the schema ([] if none)"""
    bad = []

    def need(key, ok, what):
        if key not in e:
            bad.append(f"{key}: missing")
        elif not ok(e[key]):
            bad.append(f"{key}: {what}")

    s = lambda v: isinstance(v, str)
    need("schema", lambda v: v == SCHEMA, f"must be {SCHEMA}")
    need("id", lambda v: s(v) and ID_RE.fullmatch(v) and len(v) <= 32, "developer.pluginname")
    need("name", lambda v: s(v) and 0 < len(v) <= 32, "1-32 characters")
    need("version", lambda v: s(v) and re.fullmatch(r"\d+\.\d+\.\d+", v), "major.minor.patch")
    need("by", lambda v: s(v) and len(v) <= 32, "at most 32 characters")
    need("description", lambda v: s(v) and len(v) <= 200 and "\n" not in v, "one line, 200 at most")
    need("repo", lambda v: s(v) and REPO_RE.fullmatch(v), "owner/repo")
    need("owner", lambda v: s(v) and v == e.get("repo", "").split("/")[0], "the repo's owner")
    need("repo_id", lambda v: v is None or isinstance(v, int), "a number or null")
    need("api", lambda v: isinstance(v, int) and v >= 1, "1 or more")
    need("home", lambda v: s(v) and len(v) <= 32, "at most 32 characters")
    need("opens", lambda v: isinstance(v, list) and len(v) <= 8
         and all(s(x) and re.fullmatch(r"\.[a-z0-9]{1,7}", x) for x in v), "up to 8 extensions like .nes")
    need("uses", lambda v: isinstance(v, list) and all(x in USES for x in v), "of " + ", ".join(USES))
    need("icon", lambda v: s(v) and HEX16.fullmatch(v), "16 hex digits")
    need("file_icon", lambda v: s(v) and HEX16.fullmatch(v), "16 hex digits")
    need("license", lambda v: isinstance(v, dict) and s(v.get("name")) and v.get("name")
         and (v.get("spdx") is None or s(v.get("spdx"))) and _https(v.get("url")), "{spdx, name, url}")
    need("source_url", _https, "an https URL")
    need("credits_url", _https, "an https URL")
    need("release", lambda v: isinstance(v, dict) and s(v.get("tag")) and v.get("tag")
         and _https(v.get("url")) and s(v.get("published")) and DATE.fullmatch(v["published"]),
         "{tag, url, published}")
    need("download", lambda v: isinstance(v, dict) and s(v.get("name")) and v["name"].lower().endswith(".cvp")
         and "/" not in v["name"] and _https(v.get("url")) and isinstance(v.get("size"), int)
         and s(v.get("sha256")) and HEX64.fullmatch(v["sha256"]), "{name, url, size, sha256}")
    need("image", lambda v: isinstance(v, dict) and isinstance(v.get("size"), int)
         and s(v.get("sha256")) and HEX64.fullmatch(v["sha256"]) and v.get("kind") in ("sram", "xip"),
         "{size, sha256, kind}")
    need("added", lambda v: s(v) and DATE.fullmatch(v), "YYYY-MM-DD")
    need("updated", lambda v: s(v) and DATE.fullmatch(v), "YYYY-MM-DD")
    need("submission", lambda v: v is None or isinstance(v, int), "an issue number or null")
    need("readme", _readme_ok, "{cart: null or {file, size, sha256, lines}, web: null or {file, size, sha256, url}}")
    need("screenshots", _shots_ok, "up to three of {file: screenshot-N.png, size, sha256}, in order")
    need("history", lambda v: _history_ok(v, e),
         "[{version, tag, url, published, notes}], newest first, starting with this version")
    if "credits" in e and not (isinstance(e["credits"], str) and len(e["credits"]) <= 400 and "\n" not in e["credits"]):
        bad.append("credits: one line, 400 at most")
    if "example" in e and not isinstance(e["example"], bool):
        bad.append("example: true or false")
    if "built_in" in e and not (e["built_in"] is True and e.get("example") is True):
        bad.append("built_in: it can only be true, and only on an example (one of the plugins we make)")
    if filename and e.get("id") and os.path.basename(filename) != e["id"] + ".json":
        bad.append(f"the file is {os.path.basename(filename)}, the ID {e['id']}")
    return bad


def entry_files(e):
    """{file name: {size, sha256}} for the files an entry says it has"""
    out = {}
    r = e.get("readme") or {}
    for k in ("cart", "web"):
        if r.get(k):
            out[r[k]["file"]] = r[k]
    for s in e.get("screenshots") or []:
        out[s["file"]] = s
    if not e.get("example") and isinstance(e.get("download"), dict):    # the site serves its own copy
        out[e["download"]["name"]] = e["download"]
    return out


def check_files(folder, e):
    """Problems with the files beside an entry ([] if none): each one the
    entry names is there, a plain file with that size and SHA-256 that still
    passes its own check, and nothing else is in the folder."""
    bad = []
    want = entry_files(e)
    have = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    for name in have:
        if name not in want and name != ".DS_Store":
            bad.append(f"{name}: the entry doesn't list it")
    for name, meta in sorted(want.items()):
        path = os.path.join(folder, name)
        if os.path.islink(path) or not os.path.isfile(path):
            bad.append(f"{name}: missing, or not a plain file")
            continue
        if os.path.getsize(path) != meta["size"]:
            bad.append(f"{name}: {os.path.getsize(path)} bytes, and the entry says {meta['size']}")
            continue
        with open(path, "rb") as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            bad.append(f"{name}: its SHA-256 isn't the entry's")
        elif name == CART_README:
            bad += [f"{name}: {p}" for p in cvp.readme_text_problems(data)]
            if data.count(b"\n") + (not data.endswith(b"\n")) != meta.get("lines"):
                bad.append(f"{name}: the entry's line count is wrong")
        elif name == WEB_README:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                bad.append(f"{name}: not UTF-8 text")
        elif name.lower().endswith(".cvp"):
            info, errs, _ = cvp.check(data, max(e.get("api") or 0, cvp.API_MENU))     # the API was checked when listed
            bad += [f"{name}: {p}" for p in errs]
            if info and (info["id"], info["version"]) != (e.get("id"), e.get("version")):
                bad.append(f"{name}: it's {info['id']} {info['version']}, and the entry says {e.get('id')} {e.get('version')}")
        else:
            why = png.check(data)
            if why:
                bad.append(f"{name}: {why}")
    return bad


def read_file(root, e, name):
    """one of an entry's files, as bytes (None if the entry doesn't have it)"""
    if name not in entry_files(e):
        return None
    with open(os.path.join(files_dir(root, e["id"], bool(e.get("example"))), name), "rb") as f:
        return f.read()


def same_repo(e, repo_id, full):
    """is entry e from this repository (by its number if both have one)"""
    if e.get("repo_id") is not None and repo_id is not None:
        return e["repo_id"] == repo_id
    return e.get("repo", "").lower() == full.lower()


def ownership(entries, pid, repo_id, full, shared=()):
    """why repository `full` can't register ID pid, or None: an ID belongs
    to the repository that registered it first; the developer part (before
    the first dot) to the first GitHub owner that used it"""
    owner = full.split("/")[0].lower()
    have = entries.get(pid)
    if have and not same_repo(have, repo_id, full):
        return f"the ID {pid} is already registered to {have['repo']}"
    prefix = pid.split(".")[0]
    if prefix not in shared:
        for e in entries.values():
            if e["id"].split(".")[0] == prefix and e.get("owner", "").lower() != owner:
                return (f"the developer part {prefix!r} is already used by {e['owner']} "
                        f"({e['id']}). Please pick a different one, such as your GitHub username")
    return None


def index(entries, config, now=None):
    """registry.json: format, when, where, the menu API, and the plugins"""
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = ("id", "name", "version", "by", "description", "repo", "owner", "api", "home", "opens", "uses",
            "icon", "file_icon", "license", "source_url", "credits_url", "credits", "release", "download",
            "image", "added", "updated")
    site = pages_url(config)
    plugins = []
    for e in sorted(entries.values(), key=lambda e: (e["name"].lower(), e["id"])):
        if e.get("example"):
            continue
        p = {k: e[k] for k in keep if k in e}
        here = f"{site}plugins/{e['id']}/"
        d = e["download"]                       # our copy, checked; the release's own file is "from"
        p["download"] = {"name": d["name"], "url": here + d["name"], "size": d["size"], "sha256": d["sha256"],
                         "from": d["url"]}
        p["page"] = here
        p["readme_url"] = here + CART_README if e["readme"]["cart"] else None
        p["screenshots"] = [here + s["file"] for s in e["screenshots"]]
        p["notes"] = e["history"][0]["notes"]
        plugins.append(p)
    return {
        "format": INDEX_FORMAT,
        "generated": now,
        "registry": config["registry_repo"],
        "url": pages_url(config) + "registry.json",
        "menu_api": config["api_max"],
        "install": "Copy the .CVP file to the /PLUGINS folder on the cart's SD card.",
        "plugins": plugins,
    }


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=True)
        f.write("\n")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    config = load_config()
    if args[:1] == ["check"]:
        bad = 0
        for ex in (False, True):
            d = os.path.join(ROOT, "examples" if ex else "", "plugins")
            for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                if not name.endswith(".json"):
                    continue
                with open(os.path.join(d, name)) as f:
                    e = json.load(f)
                problems = check_entry(e, name)
                if ex and e.get("example") is not True:
                    problems.append("example: an entry in examples/ must say example: true")
                if not ex and e.get("example"):
                    problems.append("example: an entry in plugins/ must not be an example")
                if not problems:
                    problems += check_files(os.path.join(d, name[:-5]), e)
                for p in problems:
                    print(f"{os.path.relpath(os.path.join(d, name), ROOT)}: {p}")
                bad += bool(problems)
        listed = load_entries(ROOT)
        for pid, e in listed.items():
            why = ownership({k: v for k, v in listed.items() if k != pid}, pid, e.get("repo_id"), e["repo"],
                            config.get("shared_prefixes", ()))
            if why:
                print(f"plugins/{pid}.json: {why}")
                bad += 1
        print("all entries are well formed" if not bad else f"{bad} entries have problems")
        return 1 if bad else 0
    if args[:1] == ["index"] and len(args) == 2:
        write_json(args[1], index(load_entries(), config))
        print(f"wrote {args[1]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
