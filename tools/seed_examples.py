"""seed_examples -- the entry the site shows for our plugin that has no
release to download: Movies, which is built into the cart.

    python3 tools/seed_examples.py [--cvp-dir DIR] [--today YYYY-MM-DD]

Rewrites examples/plugins/<id>.json and the files beside each
(examples/plugins/<id>/). What a plugin's header gives (its name, ID,
version, icons, sizes and hashes) is kept from the entry already there, or,
with --cvp-dir, read again by tools/cvp.py from the real builds in DIR
(they aren't kept in this repository). The rest is written here:

  README.md        the plugin's own README (examples/readmes/<id>.md)
  cart-readme.txt  the text the cart shows (examples/readmes/<id>.cart.md
                   if there is one, else README.md) through the SDK's
                   converter (tools/cvreadme.py), as the build holds it
  screenshot-N.png the cart's menu pages for the plugin, drawn from its
                   header in the menu's font
  history          one line saying where the plugin stands

BUILT_IN ones are built into the cart: their page has no download, no
install steps and no repository. The others link their repository and say
that the first release is coming.

Each entry says "example": true, and the site shows it with no download.
They never go in registry.json, and they don't hold an ID. When a plugin
here gets its first release and is listed in plugins/, the site shows that
entry instead: take it out of SEEDS and run this again.
"""
import argparse
import datetime
import glob
import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cvp  # noqa: E402
import cvreadme  # noqa: E402
import png  # noqa: E402
import registry  # noqa: E402
import tvscreen  # noqa: E402

OWNER = "plasticbugs"
SITE_REPO = "plasticbugs/parrot-cart-plugins"
SITE = "https://plasticbugs.github.io/parrot-cart-plugins/"

# id: repository (None for a built-in), licence (spdx, name), description
SEEDS = {
    # the description may link, from the site's root; the list shows the words only
    "parrotcart.movies": (None, (None, "Parrot Cart firmware"),
                          "Player for movies made with the [movie converter](converter/)"),
}

CREDITS = {
    "parrotcart.movies": "TinyUSB by Ha Thach",
}
BUILT_IN = {"parrotcart.movies"}
NOTES = {
    "parrotcart.movies": "{name} {version} is built into the cart.",
}


def shots(e):
    """the menu's pages for the plugin, as 256 x 192 PNGs"""
    pages = [tvscreen.details_page(e)]
    if e["id"] in BUILT_IN:
        pass                            # it isn't on the Plugins page: the menu starts it
    elif e["opens"] and e["home"]:
        pages.append(tvscreen.folder_page(e["home"], ["Sample 1", "Sample 2", "Sample 3"], e["file_icon"]))
    else:
        pages.append(tvscreen.plugins_page([e]))
    pics = [png.write(*p.pixels()) for p in pages]
    return [(registry.SHOTS[i], data) for i, data in enumerate(pics[:len(registry.SHOTS)])]


def links(pid, name, version):
    """(repo, licence url, source, credits, release) for a plugin: its repository's, or, for a
    built-in, its page on this site (nothing shows them as links)"""
    tag = "v" + version
    if name is None:
        page = f"{SITE}plugins/{pid}/"
        return SITE_REPO, page, page, page, {"tag": tag, "url": page}
    full = f"{OWNER}/{name}"
    home = f"https://github.com/{full}"
    return full, f"{home}/blob/main/LICENSE", home, f"{home}#credits", {"tag": "main", "url": home}


def meta(name, data, **more):
    return dict({"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}, **more)


def from_cvp(path, today):
    """an example entry's header fields, read from a real build"""
    with open(path, "rb") as f:
        info, errors, _ = cvp.check(f.read())
    if errors:
        raise SystemExit(f"{path}: {errors}")
    if info["id"] not in SEEDS:
        return None
    fname = os.path.basename(path)
    return {
        "id": info["id"], "name": info["name"], "version": info["version"], "by": info["by"], "api": info["api"],
        "home": info["home"], "opens": info["opens"], "uses": info["uses"], "icon": info["icon"],
        "file_icon": info["file_icon"], "image": info["image"],
        "download": {"name": fname, "size": info["file"]["size"], "sha256": info["file"]["sha256"]},
        "added": today,
    }


def build(today, cvp_dir=None):
    have = registry.load_entries(registry.ROOT, examples=True)
    if cvp_dir:
        for path in sorted(glob.glob(os.path.join(cvp_dir, "*.[Cc][Vv][Pp]"))):
            h = from_cvp(path, today)
            if h:
                have[h["id"]] = dict(have.get(h["id"], {}), **h)
    out = []
    for pid, (name, (spdx, lname), desc) in SEEDS.items():
        old = have.get(pid)
        if old is None:
            raise SystemExit(f"{pid}: no entry to keep and no build for it in --cvp-dir")
        full, lic_url, source, credits, release = links(pid, name, old["version"])
        release["published"] = old.get("release", {}).get("published", today)
        e = {
            "schema": registry.SCHEMA, "id": pid, "name": old["name"], "version": old["version"], "by": old["by"],
            "description": desc, "repo": full, "repo_id": None, "owner": full.split("/")[0], "api": old["api"],
            "home": old["home"], "opens": old["opens"], "uses": old["uses"], "icon": old["icon"],
            "file_icon": old["file_icon"], "license": {"spdx": spdx, "name": lname, "url": lic_url},
            "source_url": source, "credits_url": credits, "release": release,
            "download": dict(old["download"], url=release["url"]), "image": old["image"],
        }
        if pid in CREDITS:
            e["credits"] = CREDITS[pid]
        files = dict(shots(e))
        d = os.path.join(registry.ROOT, "examples", "readmes")
        with open(os.path.join(d, pid + ".md"), "rb") as f:
            md = f.read()
        cart_md = os.path.join(d, pid + ".cart.md")
        if os.path.exists(cart_md):
            with open(cart_md, "rb") as f:
                text = cvreadme.convert(f.read().decode()).encode("ascii")
        else:
            text = cvreadme.convert(md.decode()).encode("ascii")
        files[registry.WEB_README] = md
        files[registry.CART_README] = text
        cart = meta(registry.CART_README, text, lines=text.count(b"\n"))
        e["readme"] = {"cart": cart, "web": meta(registry.WEB_README, md, url=credits)}
        e["screenshots"] = [meta(n, files[n]) for n in registry.SHOTS if n in files]
        notes = NOTES[pid].format(name=e["name"], version=e["version"])
        e["history"] = [dict(release, version=e["version"], notes=notes)]
        e.update(added=old.get("added", today), updated=today, submission=None, example=True)
        if pid in BUILT_IN:
            e["built_in"] = True
        bad = registry.check_entry(e)
        if bad:
            raise SystemExit(f"{pid}: {bad}")
        out.append((e, files))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cvp-dir", help="a folder of the real builds, to read their headers again")
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    for e, files in build(a.today, a.cvp_dir):
        path = registry.entry_path(registry.ROOT, e["id"], examples=True)
        registry.write_json(path, e)
        d = registry.files_dir(registry.ROOT, e["id"], examples=True)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        for name, data in files.items():
            with open(os.path.join(d, name), "wb") as f:
                f.write(data)
        bad = registry.check_files(d, e)
        if bad:
            raise SystemExit(f"{e['id']}: {bad}")
        print(os.path.relpath(path, registry.ROOT), "+", ", ".join(sorted(files)))


if __name__ == "__main__":
    main()
