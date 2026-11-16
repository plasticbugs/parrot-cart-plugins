"""seed_examples -- the example entries the site shows until real plugins
are listed.

    python3 tools/seed_examples.py [--cvp-dir DIR] [--today YYYY-MM-DD]

Rewrites examples/plugins/<id>.json and the files beside each
(examples/plugins/<id>/). What a plugin's header gives (its name, ID,
version, icons, sizes and hashes) is kept from the entry already there, or,
with --cvp-dir, read again by tools/cvp.py from the real builds in DIR
(they aren't kept in this repository). The rest is written here, and says
so on the page:

  README.md        from the entry's own facts: what it opens, its folder,
                   its credits
  cart-readme.txt  that README.md through the SDK's converter
                   (tools/cvreadme.py), as a build with a README would hold
  screenshot-N.png the cart's menu pages for the plugin, drawn from its
                   header in the menu's font; for a plugin in SCREENS, a
                   picture of it running comes first (examples/screens/:
                   PSG Synth's is coleco's midihello/test/ui_preview.c
                   "chord" screen, 1 pixel in 3)
  history          one line saying the release's notes will show there

NO_README and NO_SHOTS leave an example without, to show those pages too.
Each entry says "example": true, its links point at a placeholder owner,
and the site shows it as an unpublished example with no download. They
never go in registry.json, and they don't hold an ID: delete examples/ (or
set show_examples to false in registry.config.json) once real plugins are
listed.
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

OWNER = "OWNER"                # nobody: an example's repository isn't public

# id: repository name, licence (spdx, name, note), description
SEEDS = {
    "parrotcart.nes": ("parrotcart-nes", ("LGPL-2.1", "GNU Lesser General Public License v2.1", None),
                      "Plays NES games from /NES, with USB pads."),
    "parrotcart.gameboy": ("parrotcart-gameboy", ("MIT", "MIT License", None),
                          "Plays Game Boy games from /GB, with saves and USB pads."),
    "parrotcart.mastersystem": ("parrotcart-mastersystem", ("GPL-3.0", "GNU General Public License v3.0",
                                                           "Its Z80 core's notice allows non-commercial use only."),
                               "Plays Master System, Game Gear and SG-1000 games, with saves."),
    "parrotcart.scumm": ("parrotcart-scumm", ("GPL-3.0", "GNU General Public License v3.0", None),
                        "Plays SCUMM adventure games from /SCUMM, with saves."),
    "parrotcart.padtest": ("parrotcart-padtest", (None, "Not chosen yet", None),
                          "Shows a USB pad's buttons and sticks on the TV as they move."),
    "parrotcart.nesinfo": ("parrotcart-nesinfo", (None, "Not chosen yet", None),
                          "Shows a .nes file's header and CRC-32: the SDK's smallest example."),
    "parrotcart.psgsynth": ("parrotcart-psgsynth", (None, "Not chosen yet", None),
                           "Plays the console's sound chip from a USB MIDI keyboard."),
    "parrotcart.starwars": ("parrotcart-starwars", ("BSD-3-Clause", "BSD 3-Clause License", None),
                            "Plays the 1983 Star Wars arcade game from your own ROM files, with a USB pad as the yoke."),
    "parrotcart.esb": ("parrotcart-esb", ("BSD-3-Clause", "BSD 3-Clause License", None),
                       "Plays the 1985 Empire Strikes Back arcade game from your own ROM files, with a USB pad."),
}

CREDITS = {
    "parrotcart.nes": "QuickNES by Shay Green (blargg), via frank-nes; emu2413 by Mitsutaka Okazaki",
    "parrotcart.gameboy": "Peanut-GB and minigb_apu",
    "parrotcart.mastersystem": "SMS Plus by Charles MacDonald; pico-smsplus by Frank Hoedemakers; "
                              "the Z80 core by Juergen Buchmueller",
    "parrotcart.scumm": "ScummVM, via frank-quest",
    "parrotcart.starwars": "Parts ported from MAME (BSD-3-Clause): Steve Baines, Frank Palazzolo, Mathis Rosenhauer, "
                           "Aaron Giles and others. Star Wars is a trademark of Lucasfilm Ltd. The plugin contains "
                           "none of the game.",
    "parrotcart.esb": "Parts ported from MAME (BSD-3-Clause): Steve Baines, Frank Palazzolo, Mathis Rosenhauer, "
                      "Aaron Giles and others. Star Wars is a trademark of Lucasfilm Ltd. The plugin contains "
                      "none of the game.",
}
# a step of its own, for an app that needs files but opens none
ROMS = {
    "parrotcart.starwars": "Put your own Star Wars ROM files (MAME's `starwars` set) in `/STARWARS`, "
                           "loose or zipped, or as `/STARWARS.ZIP`.",
    "parrotcart.esb": "Put your own Empire Strikes Back ROM files (MAME's `esb` set) in `/ESB`, "
                      "loose or zipped, or as `/ESB.ZIP`.",
}
# pictures of the plugin running, before the menu pages (examples/screens/)
SCREENS = {"parrotcart.psgsynth": ["psgsynth-playing.png"]}
NO_README = {"parrotcart.nesinfo"}          # as a plugin built before the README existed
NO_SHOTS = set()
NEEDS = {"usb-host": "USB host", "usb-device": "USB device", "psram": "PSRAM"}


def readme_md(e):
    steps = [f"Copy `{e['download']['name']}` to `/PLUGINS` on the cart's microSD card."]
    if e["opens"] and e["home"]:
        steps.append(f"Put your {' '.join(e['opens'])} files in `{e['home']}`.")
    if e["id"] in ROMS:
        steps.append(ROMS[e["id"]])
    steps.append(f"On the cart: Home, Plugins, {e['name']}, then A.")
    facts = [("Opens", " ".join(f"`{x}`" for x in e["opens"]) or "No files: it is an app"),
             ("Folder", f"`{e['home']}`" if e["home"] else "None"),
             ("Uses", ", ".join(NEEDS[u] for u in e["uses"]) or "Nothing extra")]
    return "\n".join([
        f"# {e['name']} for Parrot Cart", "", e["description"], "",
        "## Install", "", *[f"{i}. {s}" for i, s in enumerate(steps, 1)], "",
        "## What it needs", "", "| " + " | ".join(k for k, _ in facts) + " |", "|---|---|---|",
        "| " + " | ".join(v for _, v in facts) + " |", "",
        "## Credits", "", e.get("credits") or "Written for Parrot Cart with its SDK.", "",
        "## Source", "", "An example entry: this plugin's repository isn't public yet.", ""])


def shots(e):
    """the plugin running (SCREENS), then the menu's pages for it, as 256 x 192 PNGs, three at most"""
    pics = []
    for name in SCREENS.get(e["id"], []):
        with open(os.path.join(registry.ROOT, "examples", "screens", name), "rb") as f:
            pics.append(f.read())
    pages = [tvscreen.details_page(e)]
    if e["opens"] and e["home"]:
        pages.append(tvscreen.folder_page(e["home"], ["Sample 1", "Sample 2", "Sample 3"], e["file_icon"]))
    else:
        pages.append(tvscreen.plugins_page([e]))
    pics += [png.write(*p.pixels()) for p in pages]
    return [(registry.SHOTS[i], data) for i, data in enumerate(pics[:len(registry.SHOTS)])]


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
    full, tag = f"{OWNER}/{SEEDS[info['id']][0]}", "v" + info["version"]
    fname = os.path.basename(path)
    return {
        "id": info["id"], "name": info["name"], "version": info["version"], "by": info["by"], "api": info["api"],
        "home": info["home"], "opens": info["opens"], "uses": info["uses"], "icon": info["icon"],
        "file_icon": info["file_icon"], "image": info["image"],
        "download": {"name": fname, "url": f"https://github.com/{full}/releases/download/{tag}/{fname}",
                     "size": info["file"]["size"], "sha256": info["file"]["sha256"]},
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
    for pid, (name, (spdx, lname, note), desc) in SEEDS.items():
        old = have.get(pid)
        if old is None:
            raise SystemExit(f"{pid}: no example entry to keep and no build for it in --cvp-dir")
        full, tag = f"{OWNER}/{name}", "v" + old["version"]
        lic = {"spdx": spdx, "name": lname, "url": f"https://github.com/{full}/blob/{tag}/LICENSE"}
        if note:
            lic["note"] = note
        release = {"tag": tag, "url": f"https://github.com/{full}/releases/tag/{tag}",
                   "published": old.get("release", {}).get("published", today)}
        e = {
            "schema": registry.SCHEMA, "id": pid, "name": old["name"], "version": old["version"], "by": old["by"],
            "description": desc, "repo": full, "repo_id": None, "owner": OWNER, "api": old["api"],
            "home": old["home"], "opens": old["opens"], "uses": old["uses"], "icon": old["icon"],
            "file_icon": old["file_icon"], "license": lic, "source_url": f"https://github.com/{full}/tree/{tag}",
            "credits_url": f"https://github.com/{full}#credits", "release": release, "download": old["download"],
            "image": old["image"],
        }
        if pid in CREDITS:
            e["credits"] = CREDITS[pid]
        files = {} if pid in NO_SHOTS else dict(shots(e))
        md = readme_md(e).encode()
        files[registry.WEB_README] = md
        cart = None
        if pid not in NO_README:
            text = cvreadme.convert(md.decode()).encode("ascii")
            files[registry.CART_README] = text
            cart = meta(registry.CART_README, text, lines=text.count(b"\n"))
        e["readme"] = {"cart": cart, "web": meta(registry.WEB_README, md, url=e["credits_url"])}
        e["screenshots"] = [meta(n, files[n]) for n in registry.SHOTS if n in files]
        e["history"] = [dict(release, version=e["version"],
                             notes=f"An example entry. When {e['name']} is listed, the notes of its "
                                   f"{e['version']} release on GitHub show here.")]
        e.update(added=old.get("added", today), updated=today, submission=None, example=True)
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
