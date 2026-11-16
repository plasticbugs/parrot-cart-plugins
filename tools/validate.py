"""validate -- check a plugin repository's release and make its registry
entries.

    python3 tools/validate.py OWNER/REPO [--tag TAG] [--description TEXT]
        [--out DIR] [--write] [--fixtures DIR] [--today YYYY-MM-DD]
    ISSUE_BODY=... python3 tools/validate.py --from-issue [--submission N] --out DIR

It reads, and never runs, what the repository holds: the repository's
details, its LICENSE and README at the release's tag, and the release's
.CVP assets (each downloaded with a size cap and checked as the cart's
menu checks it, tools/cvp.py). Then the registry's rules: a public
repository with a LICENSE, a README inside each .CVP, an ID nobody else
has, a version newer than the one listed. The repository's README.md is
shown when there is one; credits and a source link aren't required.

What the plugin's page shows is copied into the entry, so the site stays
static and hotlinks nothing: the release's notes, the README.md at the tag,
the .CVP's README section (the text the cart shows) and up to three
screenshots (screenshot-1.png to screenshot-3.png on the release, each a
256 x 192 PNG of 100 KB at most).

--out DIR writes DIR/report.md (the issue comment), DIR/result.json and,
for each new or changed entry, DIR/plugins/<id>.json with its files in
DIR/plugins/<id>/. --write puts those
entries in this checkout's plugins/ instead. --fixtures DIR replays
recorded GitHub responses (tests/fixtures/github/<scenario>) instead of
the network.

Exit status: 0 it passed, 1 it didn't, 2 GitHub couldn't be read (try
again later), 3 a usage mistake.

Standard library only.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cvp  # noqa: E402
import ghapi  # noqa: E402
import issue_form  # noqa: E402
import png  # noqa: E402
import registry  # noqa: E402
import sitecopy  # noqa: E402

MARK = "<!-- parrotcart-registry-report -->"
T = sitecopy.COPY
CREDITS = re.compile(r"^[ \t]{0,3}(?:#{1,6}[ \t]+|\*\*|__|<h[1-6][^>]*>)?[ \t]*(?:credits?|acknowledge?ments?|thanks|"
                     r"authors?|attributions?)\b", re.I | re.M)
URL = re.compile(r"https?://[^\s)>\]\"']+")


def readme_checks(text, full):
    """(has credits, has a source link)"""
    credits = bool(CREDITS.search(text))
    own = re.compile(r"https?://github\.com/" + re.escape(full) + r"(?:[/#?)\s\]]|\.git|$)", re.I)
    source = bool(own.search(text)) or any("source" in line.lower() and URL.search(line)
                                            for line in text.splitlines())
    return credits, source


def credits_text(text, n=300):
    """the README's credits, as one line of plain text (at most n characters)"""
    m = CREDITS.search(text)
    if not m:
        return ""
    lines = text[m.start():].splitlines()
    first = re.sub(r"^[ \t]*(?:#{1,6}[ \t]+|\*\*|__|<h[1-6][^>]*>)?[ \t]*", "", lines[0])
    first = re.sub(r"^(?:credits?|acknowledge?ments?|thanks|authors?|attributions?)\b\W*", "", first, flags=re.I)
    body = [first]
    for line in lines[1:]:
        if re.match(r"[ \t]{0,3}(#{1,6}[ \t]|<h[1-6])", line):
            break
        body.append(line)
    s = " ".join(body)
    s = re.sub(r"<[^>]*>", " ", s)                       # no HTML
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)     # links: their text
    s = re.sub(r"[`*_>#|]", "", s)
    s = re.sub(r"^\s*[-+]\s+", "", s)
    s = re.sub(r"\s+[-+]\s+", "; ", s)
    s = "".join(c for c in s if c.isprintable())
    s = re.sub(r"\s+", " ", s).strip(" ;:")
    return s if len(s) <= n else s[:n - 1].rstrip() + "\u2026"


SHOT = re.compile(r"screenshot-([0-9]+)\.png")


def clean_notes(body, n=registry.NOTES_MAX):
    """a release's notes as stored: plain text lines, no control characters, at most n"""
    if not isinstance(body, str):
        return "", False
    s = body.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    s = "".join(c for c in s if c == "\n" or (c.isprintable() or c == " ")).strip("\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    if len(s) <= n:
        return s, False
    return s[:n - 1].rstrip() + "\u2026", True


def _meta(name, data, **more):
    return dict({"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}, **more)


def screenshots(gh, rel, full, err, warn):
    """the release's screenshot-N.png assets, checked: [(name, bytes)]"""
    prefix = f"https://github.com/{full}/releases/download/".lower()
    found = {}
    for a in rel.get("assets") or []:
        name = str(a.get("name", ""))
        m = SHOT.fullmatch(name)
        if not m:
            if name.lower().endswith(".png") and "screenshot" in name.lower():
                warn(f"{name} isn't shown. Name screenshots screenshot-1.png, screenshot-2.png and screenshot-3.png")
            continue
        if name not in registry.SHOTS:
            err(f"{name}: you can attach three screenshots at most, screenshot-1.png to screenshot-3.png")
            continue
        url, size = a.get("browser_download_url") or "", a.get("size")
        if not url.lower().startswith(prefix) or a.get("state", "uploaded") != "uploaded":
            err(f"{name}: it isn't a finished upload on this repository's release")
            continue
        if not isinstance(size, int) or size > png.MAX_BYTES:
            err(f"{name}: it's {size} bytes, and a screenshot can be {png.MAX_BYTES} at most")
            continue
        try:
            data = gh.download(url, png.MAX_BYTES)
        except ghapi.TooBig:
            err(f"{name}: it is over {png.MAX_BYTES} bytes")
            continue
        except ghapi.Refused as e:
            err(f"{name}: its download went somewhere else: {e}")
            continue
        why = png.check(data) if len(data) == size else f"GitHub says it's {size} bytes, but we got {len(data)}"
        if why:
            err(f"{name}: {why}")
            continue
        found[name] = data
    return sorted(found.items())


def _date(s):
    return (s or "")[:10] if re.match(r"\d{4}-\d\d-\d\d", s or "") else None


def validate(gh, repo, tag=None, description=None, root=registry.ROOT, config=None, today=None,
             submission=None, rules_ok=True, only_ids=None, entries=None):
    """Check repo's release. Returns a result dict:
    ok, repo, tag, errors, warnings, plugins [{file, id, version, change, entry, errors, warnings}],
    changed [ids]. only_ids: a scheduled update, for these registered plugins only."""
    config = config or registry.load_config(root)
    limits = config["limits"]
    today = today or datetime.date.today().isoformat()
    res = {"ok": False, "repo": repo, "tag": tag or "", "release_url": None, "errors": [], "warnings": [],
           "plugins": [], "changed": []}
    err, warn = res["errors"].append, res["warnings"].append
    if not issue_form.REPO.fullmatch(repo or "") or repo.split("/")[1] in (".", ".."):
        err("give the repository as owner/repo")
        return res
    if not rules_ok:
        err("tick every rule in the form")

    r = gh.repo(repo)
    if r is None:
        err(f"there's no public repository {repo} on GitHub")
        return res
    full = r.get("full_name") or repo
    res["repo"] = full
    if r.get("private") or r.get("visibility", "public") != "public":
        err(f"{full} isn't public. We only list plugins whose source anyone can read")
        return res
    if r.get("archived"):
        warn(f"{full} is archived")
    owner = (r.get("owner") or {}).get("login") or full.split("/")[0]
    repo_id = r.get("id") if isinstance(r.get("id"), int) else None

    rel = gh.release(full, tag or None)
    if rel is None:
        err(f"{full} has no release tagged {tag}" if tag else
            f"{full} has no published release. Drafts and pre-releases don't count")
        return res
    tag = rel.get("tag_name") or tag
    res["tag"], res["release_url"] = tag, rel.get("html_url")
    if rel.get("draft"):
        err(f"the release {tag} is a draft")
    if rel.get("prerelease"):
        err(f"the release {tag} is a pre-release. Publish it as a full release")

    lic = gh.license(full, ref=tag)
    license_ = None
    if lic is None:
        err(f"{full} has no LICENSE file at {tag}")
    else:
        l = lic.get("license") or {}
        spdx = l.get("spdx_id")
        name = l.get("name") or "Other"
        if not spdx or spdx == "NOASSERTION":
            spdx = None
            warn("GitHub couldn't tell which licence this is, so we'll read it ourselves")
        license_ = {"spdx": spdx, "name": name if spdx else "See the LICENSE file",
                    "url": lic.get("html_url") or f"https://github.com/{full}/blob/{tag}/LICENSE"}

    text, rd = gh.readme(full, ref=tag, cap=limits["readme_max_bytes"])
    credits_url, credits_line = f"https://github.com/{full}", ""
    if text is not None:                   # optional: shown on the plugin's page when there is one
        credits_url = (rd or {}).get("html_url") or f"https://github.com/{full}#readme"
        credits_line = credits_text(text) if readme_checks(text, full)[0] else ""
    # the README.md the plugin's page shows, as it is at the tag
    web_file = None
    if text is not None:
        rname = str((rd or {}).get("name") or "")
        raw = text.encode("utf-8")
        if not rname.lower().endswith((".md", ".markdown")):
            warn(f"the README ({rname or 'no name'}) isn't Markdown, so the plugin's page will link to it "
                 "instead of showing it. Name it README.md to show it")
        elif len(raw) > registry.WEB_README_MAX or (rd or {}).get("size", 0) > registry.WEB_README_MAX:
            warn(f"the README is over {registry.WEB_README_MAX} bytes, so the plugin's page will link to it "
                 "instead of showing it")
        elif raw.strip():
            web_file = raw
    notes, cut = clean_notes(rel.get("body"))
    if cut:
        warn(f"the release notes are long, so the plugin's page shows only the first {registry.NOTES_MAX} characters")
    if not notes:
        warn("the release has no notes")
    shots = screenshots(gh, rel, full, err, warn)
    if not shots and not any(SHOT.fullmatch(str(a.get("name", ""))) for a in rel.get("assets") or []):
        warn("the release has no screenshots. Attach screenshot-1.png (256 x 192) to show your plugin "
             "in the list")

    assets = [a for a in rel.get("assets") or [] if str(a.get("name", "")).lower().endswith(".cvp")]
    if not assets:
        err(f"the release {tag} has no .CVP file attached")
    elif len(assets) > limits["assets_per_release_max"]:
        err(f"the release has {len(assets)} .CVP files. We read {limits['assets_per_release_max']} at most")
        assets = []

    entries = registry.load_entries(root) if entries is None else entries
    seen = {}
    prefix = f"https://github.com/{full}/releases/download/".lower()
    for a in assets:
        name = str(a.get("name"))
        pr = {"file": name, "id": None, "name": None, "version": None, "change": None, "entry": None, "errors": [],
              "warnings": [], "files": {}}
        res["plugins"].append(pr)
        url, size = a.get("browser_download_url") or "", a.get("size")
        if not url.lower().startswith(prefix) or "/" in name:
            pr["errors"].append("it isn't a file on this repository's release")
            continue
        if a.get("state", "uploaded") != "uploaded":
            pr["errors"].append("it hasn't finished uploading")
            continue
        if not isinstance(size, int) or size > limits["asset_max_bytes"]:
            pr["errors"].append(f"it's {size} bytes, and we read {limits['asset_max_bytes']} at most")
            continue
        try:
            data = gh.download(url, limits["asset_max_bytes"])
        except ghapi.TooBig:
            pr["errors"].append(f"it is over {limits['asset_max_bytes']} bytes")
            continue
        except ghapi.Refused as e:
            pr["errors"].append(f"its download went somewhere else: {e}")
            continue
        if len(data) != size:
            pr["errors"].append(f"GitHub says it's {size} bytes, but we got {len(data)}")
            continue
        info, errs, warns = cvp.check(data, config["api_max"])
        pr["errors"] += errs
        pr["warnings"] += warns
        if info is None:
            continue
        pid = pr["id"] = info["id"]
        pr["version"], pr["name"] = info["version"], info["name"]
        if info["readme"] is None and not any("README" in e for e in errs):
            pr["errors"].append("It has no README inside. Build it with the SDK from a README.md "
                                "(README README.md in cvcart_plugin()) to add one")
        if pid in seen:
            pr["errors"].append(f"{seen[pid]} in this release has the same ID")
            continue
        seen[pid] = name
        if info["version"] and info["version"] not in tag:
            pr["warnings"].append(f"its version {info['version']} isn't in the release tag {tag}")
        why = registry.ownership(entries, pid, repo_id, full, config.get("shared_prefixes", ()))
        if why:
            pr["errors"].append(why)
            continue
        old = entries.get(pid)
        if only_ids is not None and pid not in only_ids:
            pr["change"] = "unlisted"
            pr["warnings"].append(f"{pid} isn't listed yet. Submit it with the form to add it")
            continue
        if old:
            c = cvp.vercmp(info["version"], old["version"])
            if c < 0:
                pr["errors"].append(f"{info['version']} is older than the listed {old['version']}")
                continue
            if c == 0:
                if old["download"]["sha256"] == info["file"]["sha256"]:
                    pr["change"] = "same"
                else:
                    pr["errors"].append(f"{info['version']} is already listed with a different file. "
                                        "Give the new build a new version number")
                continue
            pr["change"] = "update"
        else:
            pr["change"] = "new"
        if pr["errors"] or license_ is None or credits_url is None:
            continue
        desc = description if description else (old or {}).get("description", "")
        files = dict(shots)
        cart = web = None
        if info["readme"] is not None:
            files[registry.CART_README] = cb = info["readme"].encode("ascii")
            cart = _meta(registry.CART_README, cb, lines=cb.count(b"\n") + (not cb.endswith(b"\n")))
        if web_file is not None:
            files[registry.WEB_README] = web_file
            web = _meta(registry.WEB_README, web_file, url=credits_url)
        release = {"tag": tag, "url": rel.get("html_url") or f"https://github.com/{full}/releases/tag/{tag}",
                   "published": _date(rel.get("published_at")) or today}
        history = [dict(release, version=info["version"], notes=notes)]
        history += [h for h in (old or {}).get("history", []) if cvp.vercmp(h["version"], info["version"]) < 0]
        entry = {
            "schema": registry.SCHEMA,
            "id": pid,
            "name": info["name"],
            "version": info["version"],
            "by": info["by"],
            "description": desc,
            "repo": full,
            "repo_id": repo_id,
            "owner": owner,
            "api": info["api"],
            "home": info["home"],
            "opens": info["opens"],
            "uses": info["uses"],
            "icon": info["icon"],
            "file_icon": info["file_icon"],
            "license": license_,
            "source_url": f"https://github.com/{full}/tree/{tag}",
            "credits_url": credits_url,
            "release": release,
            "download": {"name": name, "url": url, "size": size, "sha256": info["file"]["sha256"]},
            "image": info["image"],
            "readme": {"cart": cart, "web": web},
            "screenshots": [_meta(n, d) for n, d in shots],
            "history": history[:registry.HISTORY_MAX],
            "added": (old or {}).get("added", today),
            "updated": today,
            "submission": submission if submission is not None else (old or {}).get("submission"),
        }
        if credits_line:
            entry["credits"] = credits_line
        problems = registry.check_entry(entry)
        if problems:
            pr["errors"] += ["the entry came out wrong: " + p for p in problems]
            continue
        pr["entry"], pr["files"] = entry, files

    if only_ids is None and description is not None and not description:
        err("the short description is empty")
    bad = res["errors"] or any(p["errors"] for p in res["plugins"])
    res["ok"] = not bad and bool(res["plugins"])
    if res["ok"]:
        res["changed"] = [p["id"] for p in res["plugins"] if p["entry"] and p["change"] in ("new", "update")]
    return res


def md(s):
    """untrusted text, safe in a GitHub comment: no mentions, links or markup"""
    s = re.sub(r"[\x00-\x1f]", " ", str(s))
    s = re.sub(r"([\\`*_\[\]<>|~#!])", r"\\\1", s)
    return s.replace("@", "@⁠")


def sentence(s):
    """a message as a list item: a full stop at the end, and a capital letter first unless it starts with
    a name (a repository, an ID, a file)"""
    s = str(s)
    if re.match(r"[a-z']+(?:\s|$)", s):
        s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "!", "?", "…")) else s + "."


def report(res, update=False):
    """the issue comment (or an update PR's body), as markdown; its words are site/copy.toml's [bot]"""
    where = (T.text("bot.repo_at_tag", repo=md(res["repo"]), tag=md(res["tag"])) if res["tag"]
             else md(res["repo"]))
    out = [MARK]
    if res.get("retry"):
        out.append(T.text("bot.checked_retry", where=where))
    else:
        if res["ok"] and res["changed"]:
            head = T.text("bot.passed") if not update else T.text("bot.new_version")
        elif res["ok"]:
            head = T.text("bot.nothing_new")
        else:
            head = T.text("bot.failed")
        out.append(T.text("bot.checked", where=where, result=head))
    out.append("")
    if res["plugins"]:
        cols = [T.text("bot.table.file"), T.text("bot.table.plugin"), T.text("bot.table.id"),
                T.text("bot.table.version"), T.text("bot.table.result")]
        out.append("| " + " | ".join(cols) + " |")
        out.append("|---|---|---|---|---|")
        words = {"new": T.text("bot.table.new"), "update": T.text("bot.table.update"),
                 "same": T.text("bot.table.same"), "unlisted": T.text("bot.table.unlisted")}
        for p in res["plugins"]:
            what = words.get(p["change"], "")
            verdict = (T.text("bot.table.fix") if p["errors"] else T.text("bot.table.hold") if not res["ok"]
                       else what or T.text("bot.table.ok"))
            out.append(f"| {md(p['file'])} | {md(p.get('name') or '')} | {md(p['id'] or '')} | "
                       f"{md(p['version'] or '')} | {verdict} |")
        out.append("")
    errs = [sentence(e) for e in res["errors"]] + [sentence(f"{p['file']}: {e}") for p in res["plugins"]
                                                   for e in p["errors"]]
    warns = [sentence(w) for w in res["warnings"]] + [sentence(f"{p['file']}: {w}") for p in res["plugins"]
                                                      for w in p["warnings"]]
    if errs:
        out.append(T.text("bot.errors_retry") if res.get("retry") else T.text("bot.errors"))
        out.append("")
        out += [f"- {md(e)}" for e in errs]
        out.append("")
    if warns:
        out.append(T.text("bot.warnings"))
        out.append("")
        out += [f"- {md(w)}" for w in warns]
        out.append("")
    shown = [p for p in res["plugins"] if p.get("entry") and p["id"] in res["changed"]]
    if res["ok"] and shown:
        out.append(T.text("bot.page_shows"))
        out.append("")
        for p in shown:
            e = p["entry"]
            n = len(e["screenshots"])
            parts = [T.text("bot.shows_cart_readme") if e["readme"]["cart"] else T.text("bot.shows_no_cart_readme"),
                     T.text("bot.shows_readme") if e["readme"]["web"] else T.text("bot.shows_readme_link"),
                     T.text("bot.shows_notes") if e["history"][0]["notes"] else T.text("bot.shows_no_notes"),
                     T.text("bot.shows_one_screenshot") if n == 1 else
                     T.text("bot.shows_screenshots", count=n) if n else T.text("bot.shows_no_screenshots")]
            out.append("- " + T.text("bot.page_shows_line", name=md(e["name"]), parts=", ".join(parts)))
        out.append("")
    if res["ok"] and res["changed"] and not update:
        out.append(T.text("bot.next_passed"))
    elif res.get("retry"):
        out.append(T.text("bot.next_retry"))
    elif not res["ok"] and not update:
        out.append(T.text("bot.next_failed"))
    return "\n".join(out).rstrip() + "\n"


def write_out(res, out, update=False):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "report.md"), "w") as f:
        f.write(report(res, update))
    slim = {k: v for k, v in res.items() if k != "plugins"}
    slim["plugins"] = [{k: v for k, v in p.items() if k not in ("entry", "files")} for p in res["plugins"]]
    registry.write_json(os.path.join(out, "result.json"), slim)
    write_entries(res, out)


def write_entries(res, root):
    """each changed entry and its files, under root/plugins/"""
    for p in res["plugins"]:
        if p["entry"] and p["id"] in res["changed"]:
            registry.write_json(registry.entry_path(root, p["id"]), p["entry"])
            d = registry.files_dir(root, p["id"])
            shutil.rmtree(d, ignore_errors=True)
            for name, data in p["files"].items():
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, name), "wb") as f:
                    f.write(data)


def gh_from(fixtures):
    if fixtures:
        return ghapi.GitHub(token="", transport=ghapi.RecordedTransport(fixtures))
    return ghapi.GitHub()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a plugin repository's release for the registry.")
    ap.add_argument("repo", nargs="?", help="owner/repo")
    ap.add_argument("--tag", default="")
    ap.add_argument("--description", default=None)
    ap.add_argument("--from-issue", action="store_true", help="read the issue form from $ISSUE_BODY")
    ap.add_argument("--issue-json", help="read the issue (GitHub's JSON for it) from this file")
    ap.add_argument("--submission", type=int, default=None, help="the issue's number")
    ap.add_argument("--out", help="write report.md, result.json and plugins/ here")
    ap.add_argument("--write", action="store_true", help="write changed entries into this checkout's plugins/")
    ap.add_argument("--fixtures", help="replay recorded GitHub responses from this folder")
    ap.add_argument("--today", help="YYYY-MM-DD (tests)")
    a = ap.parse_args(argv)
    config = registry.load_config()
    gh = gh_from(a.fixtures)
    rules_ok = True
    if a.issue_json:
        with open(a.issue_json) as f:
            issue = json.load(f)
        labels = [x.get("name") if isinstance(x, dict) else x for x in issue.get("labels") or []]
        why = ("it's a pull request, not an issue" if issue.get("pull_request") else
               "the issue is closed" if issue.get("state") != "open" else
               f"the issue doesn't have the {config['labels']['submission']} label"
               if config["labels"]["submission"] not in labels else None)
        if why:
            print(f"not a submission: {why}")
            return 3
        os.environ["ISSUE_BODY"] = issue.get("body") or ""
        a.from_issue = True
        if isinstance(issue.get("number"), int):
            a.submission = issue["number"]
    if a.from_issue:
        try:
            form = issue_form.parse(os.environ.get("ISSUE_BODY", ""), config["limits"]["description_max_chars"])
        except issue_form.FormError as e:
            res = {"ok": False, "repo": "the form", "tag": "", "release_url": None, "errors": [str(e)],
                   "warnings": [], "plugins": [], "changed": []}
            if a.out:
                write_out(res, a.out)
            print(report(res))
            return 1
        repo, tag, desc, rules_ok = form["repo"], form["tag"], form["description"], form["rules_ok"]
    elif a.repo:
        repo, tag, desc = a.repo, a.tag, a.description
    else:
        ap.print_usage()
        return 3
    try:
        res = validate(gh, repo, tag or None, desc, config=config, today=a.today, submission=a.submission,
                       rules_ok=rules_ok)
    except ghapi.GitHubError as e:
        res = {"ok": False, "repo": repo, "tag": tag, "release_url": None, "retry": True,
               "errors": [str(e)],
               "warnings": [], "plugins": [], "changed": []}
        if a.out:
            write_out(res, a.out)
        print(report(res))
        return 2
    if a.out:
        write_out(res, a.out)
    if a.write:
        write_entries(res, registry.ROOT)
    print(report(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
