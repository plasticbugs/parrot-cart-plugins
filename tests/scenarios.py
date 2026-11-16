"""scenarios -- the GitHub scenarios the validator's tests replay, and the
synthetic plugin files in them. Built when the tests start (helpers.py),
into a temporary folder; nothing is committed and nothing is real.

Each scenario folder has index.json (URL -> response) and the response
bodies, in the shapes GitHub's REST API returns (fields the registry
doesn't read are trimmed). The repositories and owners are made up. The
.CVP files have real-looking headers and a made-up image. To record a real
repository the same way: tools/record_fixture.py.
"""
import base64
import json
import os

import helpers

API = "https://api.github.com"

CART_README = """NES FOR PARROT CART

Plays .nes games from the /NES
folder.

CONTROLS
- Pad 1: the left controller
- * and #: Select and Start

CREDITS
QuickNES by Shay Green.
"""

# file -> its header (tests/test_cvp.py checks cvp.py reads each back)
PLUGINS = {
    "NES-0.4.6.CVP": dict(id="parrotcart.nes", name="NES", version="0.4.6", by="Parrot Cart", home="/NES",
                          opens=[".nes"], uses=["usb-host", "psram"], icon="007e81a5eba5817e",
                          file_icon="7e42427e7e5a7e00", kind="sram", readme=CART_README),
    "GB-0.1.2.CVP": dict(id="parrotcart.gameboy", name="Game Boy", version="0.1.2", by="Parrot Cart", home="/gb",
                         opens=[".gb", ".gbc"], uses=["usb-host", "psram"], icon="7e4242427e567e3c",
                         file_icon="007c44447c547c00", kind="sram"),
    "SMS-0.2.3.CVP": dict(id="parrotcart.mastersystem", name="Master System", version="0.2.3", by="Parrot Cart",
                          home="/SMS", opens=[".sms", ".gg", ".sg"], uses=["usb-host", "psram"],
                          icon="00ff207520ff0000", file_icon="7e42427e7e7e3c00", kind="sram"),
    "PADTEST-0.1.2.CVP": dict(id="parrotcart.padtest", name="Pad Test", version="0.1.2", by="Parrot Cart", home="",
                              opens=[], uses=["usb-host"], icon="3c4299819999423c", file_icon="0000000000000000",
                              kind="sram"),
    "PADTEST18.CVP": dict(id="parrotcart.padtest18", name="Pad Test 0.18", version="0.1.1", by="Parrot Cart", home="",
                          opens=[], uses=["usb-host"], icon="3c4299819999423c", file_icon="0000000000000000",
                          kind="sram"),
    "SCUMM-0.2.7.CVP": dict(id="parrotcart.scumm", name="SCUMM", version="0.2.7", by="Parrot Cart", home="/SCUMM",
                            opens=[".lfl", ".000"], uses=[], icon="3c42a581bda5423c", file_icon="7e81ad81b981b57e",
                            kind="xip"),
    "NESINFO-1.0.0.CVP": dict(id="parrotcart.nesinfo", name="NES Info", version="1.0.0", by="Parrot Cart", home="/NES",
                              opens=[".nes"], uses=[], icon="3c4299819999423c", file_icon="7e42427e7e5a7e00",
                              kind="sram"),
    "PSGSYNTH-1.0.0.CVP": dict(id="parrotcart.psgsynth", name="PSG Synth", version="1.0.0", by="Parrot Cart", home="",
                               opens=[], uses=["usb-host"], icon="003e222222eeee00", file_icon="0000000000000000",
                               kind="sram"),
}
FLAG = {"usb-host": 1, "usb-device": 2, "psram": 4}


def plugin_file(name):
    f = PLUGINS[name]
    img = helpers.image(**helpers.SRAM_IMAGE) if f["kind"] == "sram" else helpers.image()
    return helpers.make_cvp(img, id=f["id"], name=f["name"], version=f["version"], by=f["by"], home=f["home"],
                            opens=f["opens"], flags=sum(FLAG[u] for u in f["uses"]),
                            icon=bytes.fromhex(f["icon"]), file_icon=bytes.fromhex(f["file_icon"]),
                            readme=f.get("readme"))


def b64(text):
    raw = base64.b64encode(text.encode()).decode()
    return "\n".join(raw[i:i + 60] for i in range(0, len(raw), 60)) + "\n"


def repo(full, rid, oid, private=False, archived=False):
    owner, name = full.split("/")
    return {
        "id": rid, "node_id": f"R_kgDO{rid}", "name": name, "full_name": full, "private": private,
        "owner": {"login": owner, "id": oid, "type": "User", "html_url": f"https://github.com/{owner}"},
        "html_url": f"https://github.com/{full}", "description": "A Parrot Cart plugin", "fork": False,
        "url": f"{API}/repos/{full}", "created_at": "2026-10-02T09:00:00Z", "updated_at": "2026-11-14T19:50:00Z",
        "pushed_at": "2026-11-14T19:45:00Z", "default_branch": "main", "archived": archived, "disabled": False,
        "visibility": "private" if private else "public",
    }


def asset(full, tag, aid, name, size):
    return {
        "url": f"{API}/repos/{full}/releases/assets/{aid}", "id": aid, "node_id": f"RA_kwDO{aid}", "name": name,
        "label": "", "content_type": "application/octet-stream", "state": "uploaded", "size": size,
        "download_count": 0, "created_at": "2026-11-14T19:44:00Z", "updated_at": "2026-11-14T19:44:10Z",
        "browser_download_url": f"https://github.com/{full}/releases/download/{tag}/{name}",
    }


def release(full, rid, tag, assets, prerelease=False, draft=False, published="2026-11-14T19:45:00Z",
            body="Copy the .CVP to /PLUGINS on the SD card."):
    return {
        "url": f"{API}/repos/{full}/releases/{rid}", "html_url": f"https://github.com/{full}/releases/tag/{tag}",
        "id": rid, "tag_name": tag, "target_commitish": "main", "name": tag, "draft": draft,
        "prerelease": prerelease, "created_at": published, "published_at": published, "assets": assets,
        "tarball_url": f"{API}/repos/{full}/tarball/{tag}", "zipball_url": f"{API}/repos/{full}/zipball/{tag}",
        "body": body,
    }


def license_(full, tag, key, spdx, name):
    return {
        "name": "LICENSE", "path": "LICENSE", "sha": "4f3c" + "0" * 36, "size": 1100,
        "url": f"{API}/repos/{full}/contents/LICENSE?ref={tag}",
        "html_url": f"https://github.com/{full}/blob/{tag}/LICENSE",
        "download_url": f"https://raw.githubusercontent.com/{full}/{tag}/LICENSE", "type": "file",
        "content": b64("(licence text)\n"), "encoding": "base64",
        "license": {"key": key, "name": name, "spdx_id": spdx, "url": f"{API}/licenses/{key}" if key != "other" else None},
    }


def readme(full, tag, text, name="README.md"):
    return {
        "name": name, "path": name, "sha": "9a1b" + "0" * 36, "size": len(text.encode()),
        "url": f"{API}/repos/{full}/contents/{name}?ref={tag}",
        "html_url": f"https://github.com/{full}/blob/{tag}/{name}",
        "download_url": f"https://raw.githubusercontent.com/{full}/{tag}/{name}", "type": "file",
        "content": b64(text), "encoding": "base64",
    }


GOOD_README = """# {title}

A plugin for Parrot Cart. Copy the .CVP file to /PLUGINS on the cart's SD card.

| Button | Does |
|---|---|
| `*` | Select |
| `#` | Start |

- [x] USB pads
- [ ] Saves

<script>alert("not on the site")</script>

## Credits

{credits}

## Source

The full source, with the SDK it links: https://github.com/{full}
"""

NOTES = """## What's new

- **USB pads** keep working after a reset.
- See [the guide](docs/pads.md).

<img src="https://example.net/tracker.png" onerror="alert(1)">
"""


def scenario(folder, index, files):
    os.makedirs(folder)
    for fname, body in files.items():
        mode = "wb" if isinstance(body, bytes) else "w"
        with open(os.path.join(folder, fname), mode) as f:
            if isinstance(body, bytes):
                f.write(body)
            else:
                json.dump(body, f, indent=2)
                f.write("\n")
    with open(os.path.join(folder, "index.json"), "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")


def plugin_scenario(folder, cvp_dir, full, rid, oid, tag, cvps, lic=("mit", "MIT", "MIT License"), text=None,
                    latest=True, prerelease=False, extra_assets=(), sizes=None, cvp_redirect=False,
                    shots=None, body=None, readme_name="README.md"):
    """shots: {asset name: bytes} attached to the release"""
    files, index = {}, {}
    files["repo.json"] = repo(full, rid, oid)
    index[f"{API}/repos/{full}"] = {"file": "repo.json"}

    def size_of(n):
        return os.path.getsize(os.path.join(cvp_dir, n))
    assets = [asset(full, tag, rid * 10 + i, n, (sizes or {}).get(n, size_of(n))) for i, n in enumerate(cvps)]
    assets += [asset(full, tag, rid * 10 + 9, n, 1234) for n in extra_assets]
    for i, (n, data) in enumerate(sorted((shots or {}).items())):
        a = asset(full, tag, rid * 100 + i, n, (sizes or {}).get(n, len(data)))
        assets.append(a)
        files[f"shot{i}.bin"] = data
        index[a["browser_download_url"]] = {"file": f"shot{i}.bin"}
    kw = {} if body is None else {"body": body}
    files["release.json"] = release(full, rid + 1, tag, assets, prerelease=prerelease, **kw)
    if latest:
        index[f"{API}/repos/{full}/releases/latest"] = {"file": "release.json"}
    index[f"{API}/repos/{full}/releases/tags/{tag}"] = {"file": "release.json"}
    if lic:
        files["license.json"] = license_(full, tag, *lic)
        index[f"{API}/repos/{full}/license?ref={tag}"] = {"file": "license.json"}
    if text is not None:
        files["readme.json"] = readme(full, tag, text, readme_name)
        index[f"{API}/repos/{full}/readme?ref={tag}"] = {"file": "readme.json"}
    for a in assets:
        if not a["name"].lower().endswith(".cvp"):
            continue
        path = os.path.join(cvp_dir, a["name"])
        if cvp_redirect:
            store = f"https://release-assets.githubusercontent.com/github-production-release-asset/{rid}/{a['id']}?sp=r&sv=2018-11-09&sr=b"
            index[a["browser_download_url"]] = {"status": 302, "location": store}
            index[store] = {"file": path}
        else:
            index[a["browser_download_url"]] = {"file": path}
    scenario(folder, index, files)


def nes_good(folder, cvp_dir, **over):
    """a plugin that passes: a README on the cart, GitHub-flavoured README.md,
    notes, two screenshots, its file behind GitHub's redirect to its asset store"""
    kw = dict(lic=("lgpl-2.1", "LGPL-2.1", "GNU Lesser General Public License v2.1"),
              text=GOOD_README.format(title="NES for Parrot Cart", full="fixture-dev/nes-plugin",
                                      credits="QuickNES by Shay Green and the frank-nes fork; "
                                              "the Parrot Cart SDK."),
              cvp_redirect=True, body=NOTES,
              shots={"screenshot-1.png": helpers.shot(1), "screenshot-2.png": helpers.shot(2)})
    kw.update(over)
    plugin_scenario(folder, cvp_dir, "fixture-dev/nes-plugin", 880001, 990001, "v0.4.6", ["NES-0.4.6.CVP"], **kw)


def build(cvp_dir, gh_dir):
    os.makedirs(cvp_dir)
    for name in PLUGINS:
        with open(os.path.join(cvp_dir, name), "wb") as f:
            f.write(plugin_file(name))

    def at(name):
        return os.path.join(gh_dir, name)
    nes_good(at("nes-good"), cvp_dir)
    # two plugins in one release, a tag given, and an asset that isn't a plugin; no extras at all
    plugin_scenario(at("pads-two"), cvp_dir, "fixture-dev/pad-tools", 880002, 990001, "v0.1.2",
                    ["PADTEST-0.1.2.CVP", "PADTEST18.CVP"], latest=False, extra_assets=["pad-tools-src.zip"],
                    text=GOOD_README.format(title="Pad tools", full="fixture-dev/pad-tools",
                                            credits="TinyUSB (MIT) by Ha Thach."), body="")
    # no LICENSE, a README without credits or a source link
    plugin_scenario(at("gb-missing"), cvp_dir, "other-dev/gb-plugin", 880003, 990002, "v0.1.2", ["GB-0.1.2.CVP"],
                    lic=None, text="# Game Boy\n\nCopy GB.CVP to the card.\n")
    # only a pre-release: /releases/latest has nothing, the tag is a pre-release
    plugin_scenario(at("sms-prerelease"), cvp_dir, "fixture-dev/sms-plugin", 880004, 990001, "v0.2.3-rc1",
                    ["SMS-0.2.3.CVP"], latest=False, prerelease=True,
                    lic=("gpl-3.0", "GPL-3.0", "GNU General Public License v3.0"),
                    text=GOOD_README.format(title="Master System", full="fixture-dev/sms-plugin",
                                            credits="SMS Plus by Charles MacDonald; pico-smsplus."))
    # a licence GitHub can't name (non-commercial terms), an XIP plugin, and a README that isn't Markdown
    plugin_scenario(at("scumm-noassert"), cvp_dir, "fixture-dev/scumm-plugin", 880005, 990001, "v0.2.7",
                    ["SCUMM-0.2.7.CVP"], lic=("other", "NOASSERTION", "Other"), readme_name="README.txt",
                    text="# SCUMM\n\n### Acknowledgements\n\nThe ScummVM team.\n\n"
                         "Source code: https://github.com/fixture-dev/scumm-plugin/tree/main\n")
    # a release whose .CVP is far over the size cap (by its metadata)
    plugin_scenario(at("too-big"), cvp_dir, "fixture-dev/big-plugin", 880006, 990001, "v1.0.0",
                    ["NESINFO-1.0.0.CVP"], sizes={"NESINFO-1.0.0.CVP": 50 * 1024 * 1024},
                    text=GOOD_README.format(title="Big", full="fixture-dev/big-plugin", credits="Me."))
    # its download redirects off GitHub
    plugin_scenario(at("evil-redirect"), cvp_dir, "fixture-dev/odd-plugin", 880007, 990001, "v1.0.0",
                    ["PSGSYNTH-1.0.0.CVP"],
                    text=GOOD_README.format(title="Odd", full="fixture-dev/odd-plugin", credits="Me."))
    with open(os.path.join(at("evil-redirect"), "index.json")) as f:
        index = json.load(f)
    index["https://github.com/fixture-dev/odd-plugin/releases/download/v1.0.0/PSGSYNTH-1.0.0.CVP"] = {
        "status": 302, "location": "https://downloads.example.net/PSGSYNTH-1.0.0.CVP"}
    with open(os.path.join(at("evil-redirect"), "index.json"), "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    # GitHub's rate limit
    scenario(at("rate-limited"), {f"{API}/repos/fixture-dev/nes-plugin": {
        "status": 403, "headers": {"x-ratelimit-remaining": "0"},
        "body": {"message": "API rate limit exceeded"}}}, {})
    # a private repository looks like no repository at all
    scenario(at("private"), {}, {})
