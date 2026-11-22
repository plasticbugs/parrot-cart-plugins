"""tools/validate.py and the jobs around it, end to end against replayed
GitHub responses (tests/scenarios.py, built when the tests start): no network"""
import contextlib
import io
import json
import os
import shutil
import unittest
import unittest.mock

from helpers import CVP_DIR, GH_DIR, ROOT, fixture, make_cvp, image, shot, tmp, SRAM_IMAGE
import png
import scenarios
import apply_entries
import find_updates
import ghapi
import registry
import validate
import verify_entries

CONFIG = registry.load_config(ROOT)
TODAY = "2026-11-14"
NES_URL = "https://github.com/fixture-dev/nes-plugin/releases/download/v0.4.6/NES-0.4.6.CVP"


def gh(scenario, token="test-token-not-real", extra=None):
    return ghapi.GitHub(token=token, transport=ghapi.RecordedTransport(os.path.join(GH_DIR, scenario), extra))


class Root:
    """a registry checkout in a temporary folder, with some entries"""

    def __init__(self, *entries):
        self.dir = tmp()
        os.makedirs(os.path.join(self.dir, "plugins"))
        for e in entries:
            registry.write_json(registry.entry_path(self.dir, e["id"]), e)
            if e["id"] == "parrotcart.nes":                   # its files, as the release has them
                d = registry.files_dir(self.dir, e["id"])
                os.makedirs(d)
                for name, data in NES_FILES.items():
                    if name in registry.entry_files(e):
                        with open(os.path.join(d, name), "wb") as f:
                            f.write(data)

    def __enter__(self):
        return self.dir

    def __exit__(self, *a):
        shutil.rmtree(self.dir)


def run(scenario, repo, tag=None, desc="A plugin.", root=None, **kw):
    return validate.validate(gh(scenario, extra=kw.pop("extra", None)), repo, tag, desc,
                             root=root or tmp(), config=CONFIG, today=TODAY, **kw)


def nes_entry(**over):
    res = run("nes-good", "fixture-dev/nes-plugin")
    e = dict(res["plugins"][0]["entry"])
    e.update(over)
    if "version" in over or "release" in over:               # an older listing: its history says so too
        e["release"] = dict(e["release"], **over.get("release", {"tag": "v" + e["version"]}))
        e["history"] = [dict(e["release"], version=e["version"], notes="Older notes.")]
    return e


NES_FILES = run("nes-good", "fixture-dev/nes-plugin")["plugins"][0]["files"]


def custom(build, *args, **kw):
    """a scenario of its own, in a new folder: gh() takes its path"""
    d = os.path.join(tmp(), "s")
    build(d, CVP_DIR, *args, **kw)
    return d


class Submissions(unittest.TestCase):
    def test_nes_passes(self):
        t = gh("nes-good")
        res = validate.validate(t, "fixture-dev/nes-plugin", None, "Plays NES games.", root=tmp(),
                                config=CONFIG, today=TODAY, submission=12)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["changed"], ["parrotcart.nes"])
        e = res["plugins"][0]["entry"]
        self.assertEqual(registry.check_entry(e), [])
        self.assertEqual((e["name"], e["version"], e["by"], e["repo"], e["owner"], e["repo_id"]),
                         ("NES", "0.4.6", "Parrot Cart", "fixture-dev/nes-plugin", "fixture-dev", 880001))
        self.assertEqual(e["opens"], [".nes"])
        self.assertEqual(e["uses"], ["usb-host", "psram"])
        self.assertEqual(e["license"]["spdx"], "LGPL-2.1")
        self.assertEqual(e["download"]["url"], NES_URL)
        self.assertEqual(e["download"]["size"], len(fixture("NES-0.4.6.CVP")))
        self.assertEqual(e["release"], {"tag": "v0.4.6", "published": "2026-11-14",
                                        "url": "https://github.com/fixture-dev/nes-plugin/releases/tag/v0.4.6"})
        self.assertEqual(e["source_url"], "https://github.com/fixture-dev/nes-plugin/tree/v0.4.6")
        self.assertEqual(e["submission"], 12)
        self.assertEqual((e["added"], e["updated"]), (TODAY, TODAY))
        self.assertIn("QuickNES", e["credits"])

    def test_token_stays_on_the_api(self):
        t = gh("nes-good", token="secret-for-the-api")
        validate.validate(t, "fixture-dev/nes-plugin", None, "x", root=tmp(), config=CONFIG)
        hosts = {}
        for url, headers in t.t.asked:
            hosts.setdefault(url.split("/")[2], set()).add("Authorization" in headers)
        self.assertEqual(hosts["api.github.com"], {True})
        self.assertEqual(hosts["github.com"], {False})
        self.assertEqual(hosts["release-assets.githubusercontent.com"], {False})

    def test_two_plugins_in_a_release(self):
        res = run("pads-two", "fixture-dev/pad-tools", "v0.1.2")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["changed"], ["parrotcart.padtest", "parrotcart.padtest18"])
        self.assertEqual([p["file"] for p in res["plugins"]], ["PADTEST-0.1.2.CVP", "PADTEST18.CVP"])
        self.assertTrue(any("isn't in the release tag" in w for w in res["plugins"][1]["warnings"]))

    def test_missing_license_and_readme(self):
        res = run("gb-missing", "other-dev/gb-plugin")
        self.assertFalse(res["ok"])
        text = " ".join(res["errors"])
        self.assertIn("no LICENSE", text)
        self.assertNotIn("credits", text)                  # credits and a source link aren't required
        self.assertNotIn("source", text)
        self.assertTrue(any("no README inside" in e for e in res["plugins"][0]["errors"]))
        self.assertIsNone(res["plugins"][0]["entry"])

    def test_prerelease(self):
        res = run("sms-prerelease", "fixture-dev/sms-plugin")
        self.assertIn("no published release", res["errors"][0])
        res = run("sms-prerelease", "fixture-dev/sms-plugin", "v0.2.3-rc1")
        self.assertTrue(any("pre-release" in e for e in res["errors"]))
        self.assertFalse(res["ok"])

    def test_unnamed_licence_and_xip(self):
        res = run("scumm-noassert", "fixture-dev/scumm-plugin")
        self.assertTrue(res["ok"], res)
        e = res["plugins"][0]["entry"]
        self.assertIsNone(e["license"]["spdx"])
        self.assertEqual(e["image"]["kind"], "xip")
        self.assertTrue(any("couldn't tell which license" in w for w in res["warnings"]))

    def test_too_big_isnt_downloaded(self):
        t = gh("too-big")
        res = validate.validate(t, "fixture-dev/big-plugin", None, "x", root=tmp(), config=CONFIG)
        self.assertFalse(res["ok"])
        self.assertTrue(any("at most" in e for e in res["plugins"][0]["errors"]))
        self.assertFalse(any("releases/download" in u for u, _ in t.t.asked))

    def test_redirect_off_github(self):
        res = run("evil-redirect", "fixture-dev/odd-plugin")
        self.assertFalse(res["ok"])
        self.assertIn("went somewhere else", res["plugins"][0]["errors"][0])

    def test_rate_limit_is_a_retry(self):
        with self.assertRaises(ghapi.GitHubError):
            run("rate-limited", "fixture-dev/nes-plugin")

    def test_private_or_missing(self):
        res = run("private", "fixture-dev/nes-plugin")
        self.assertIn("no public repository", res["errors"][0])

    def test_bad_repo_names(self):
        for repo in ("fixture-dev", "fixture-dev/..", "a/b/c", "-x/y", "x/y z"):
            self.assertFalse(run("private", repo)["ok"], repo)

    def test_rules_must_be_ticked(self):
        res = run("nes-good", "fixture-dev/nes-plugin", rules_ok=False)
        self.assertFalse(res["ok"])
        self.assertIn("rule", res["errors"][0])

    def test_tampered_file(self):
        d = tmp()
        bad = bytearray(fixture("NES-0.4.6.CVP"))
        bad[600] ^= 0xFF
        path = os.path.join(d, "NES-0.4.6.CVP")
        with open(path, "wb") as f:
            f.write(bad)
        store = ("https://release-assets.githubusercontent.com/github-production-release-asset/880001/8800010"
                 "?sp=r&sv=2018-11-09&sr=b")
        res = run("nes-good", "fixture-dev/nes-plugin", extra={store: {"file": path}})
        self.assertFalse(res["ok"])
        self.assertTrue(any("SHA-256" in e for e in res["plugins"][0]["errors"]))


class PageContent(unittest.TestCase):
    """what the plugin's page shows: the README in the .CVP, README.md, the notes, screenshots"""

    def test_copied_from_the_release(self):
        res = run("nes-good", "fixture-dev/nes-plugin")
        self.assertTrue(res["ok"], res)
        p = res["plugins"][0]
        e, files = p["entry"], p["files"]
        self.assertEqual(files["cart-readme.txt"].decode(), scenarios.CART_README)
        self.assertEqual(e["readme"]["cart"]["lines"], scenarios.CART_README.count("\n"))
        self.assertIn(b"| Button | Does |", files["README.md"])
        self.assertEqual(e["readme"]["web"]["url"], "https://github.com/fixture-dev/nes-plugin/blob/v0.4.6/README.md")
        self.assertEqual([s["file"] for s in e["screenshots"]], ["screenshot-1.png", "screenshot-2.png"])
        self.assertEqual(files["screenshot-2.png"], shot(2))
        self.assertEqual(e["history"], [dict(e["release"], version="0.4.6", notes=scenarios.NOTES.strip("\n"))])
        self.assertEqual(p["warnings"], [])
        self.assertEqual(res["warnings"], [])
        self.assertIn("2 screenshots", validate.report(res))

    def test_none_of_it_is_required(self):
        res = run("pads-two", "fixture-dev/pad-tools", "v0.1.2")
        self.assertTrue(res["ok"], res)
        p = res["plugins"][0]
        self.assertEqual(p["entry"]["screenshots"], [])
        self.assertEqual(p["entry"]["history"][0]["notes"], "")
        self.assertTrue(any("no screenshots" in w for w in res["warnings"]))
        self.assertTrue(any("no notes" in w for w in res["warnings"]))

    def test_a_bad_readme_section_fails(self):
        d = tmp()
        path = os.path.join(d, "NES-0.4.6.CVP")
        with open(path, "wb") as f:
            f.write(make_cvp(image(**SRAM_IMAGE), id="parrotcart.nes", name="NES", version="0.4.6",
                             readme="A line that is far too long for the cart's page\n"))
        s = custom(scenarios.nes_good)
        store = ("https://release-assets.githubusercontent.com/github-production-release-asset/880001/8800010"
                 "?sp=r&sv=2018-11-09&sr=b")
        with open(os.path.join(s, "release.json")) as f:
            rel = json.load(f)
        rel["assets"][0]["size"] = os.path.getsize(path)
        res = validate.validate(ghapi.GitHub(token="", transport=ghapi.RecordedTransport(s, {
            store: {"file": path}, "https://api.github.com/repos/fixture-dev/nes-plugin/releases/latest": {"body": rel}})),
            "fixture-dev/nes-plugin", None, "x", root=tmp(), config=CONFIG, today=TODAY)
        self.assertFalse(res["ok"])
        self.assertTrue(any("in the README, line 1 is 47 characters" in e for e in res["plugins"][0]["errors"]), res)

    def shots(self, shots, **kw):
        s = custom(scenarios.nes_good, shots=shots, **kw)
        return validate.validate(ghapi.GitHub(token="", transport=ghapi.RecordedTransport(s)),
                                 "fixture-dev/nes-plugin", None, "x", root=tmp(), config=CONFIG, today=TODAY)

    def test_screenshots_refused(self):
        big = png.write([os.urandom(256) for _ in range(192)], [(i, i, i) for i in range(256)]) + b""
        cases = [
            ({"screenshot-1.png": shot(width=280, height=216)}, "280 x 216 pixels"),
            ({"screenshot-1.png": b"\xff\xd8\xff\xe0" + bytes(900)}, "isn't a PNG"),
            ({"screenshot-1.png": shot()[:-20]}, "cut short"),
            ({"screenshot-1.png": shot() + b"<script>"}, "bytes after the end"),
            ({"screenshot-1.png": shot(), "screenshot-4.png": shot()}, "three screenshots at most"),
            ({"screenshot-2.png": big + bytes(0)}, None),
        ]
        for shots, what in cases:
            with self.subTest(what):
                res = self.shots(shots)
                if what is None:                             # a noisy picture of the right size is fine
                    self.assertTrue(len(big) < png.MAX_BYTES and res["ok"], res["errors"])
                    continue
                self.assertFalse(res["ok"])
                self.assertTrue(any(what in e for e in res["errors"]), res["errors"])
                self.assertEqual(res["changed"], [])

    def test_a_heavy_screenshot_isnt_downloaded(self):
        s = custom(scenarios.nes_good, shots={"screenshot-1.png": shot()},
                   sizes={"screenshot-1.png": png.MAX_BYTES + 1})
        t = ghapi.GitHub(token="", transport=ghapi.RecordedTransport(s))
        res = validate.validate(t, "fixture-dev/nes-plugin", None, "x", root=tmp(), config=CONFIG)
        self.assertTrue(any("102400 at most" in e for e in res["errors"]), res["errors"])
        self.assertFalse(any(u.endswith("screenshot-1.png") for u, _ in t.t.asked))

    def test_other_names_are_only_mentioned(self):
        res = self.shots({"Screenshot 1.PNG".replace(" ", "_"): shot(), "screenshot-1.png": shot()})
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(len(res["plugins"][0]["entry"]["screenshots"]), 1)
        self.assertTrue(any("isn't shown" in w for w in res["warnings"]))

    def test_readme_that_isnt_markdown_is_linked(self):
        res = run("scumm-noassert", "fixture-dev/scumm-plugin")
        self.assertTrue(res["ok"], res)
        self.assertIsNone(res["plugins"][0]["entry"]["readme"]["web"])
        self.assertTrue(any("isn't Markdown" in w for w in res["warnings"]))

    def test_notes_are_cleaned_and_capped(self):
        text, cut = validate.clean_notes("One\r\ntwo\x00\x1b[31m three \n" + "x" * 9000)
        self.assertTrue(cut)
        self.assertEqual(len(text), registry.NOTES_MAX)
        self.assertTrue(text.startswith("One\ntwo[31m three\nxxx"))
        self.assertEqual(validate.clean_notes(None), ("", False))

    def test_an_update_keeps_the_older_notes(self):
        old = nes_entry(version="0.4.5", added="2026-10-01")
        with Root(old) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", desc=None, root=root)
        h = res["plugins"][0]["entry"]["history"]
        self.assertEqual([(x["version"], x["tag"]) for x in h], [("0.4.6", "v0.4.6"), ("0.4.5", "v0.4.5")])
        self.assertEqual(h[1]["notes"], "Older notes.")
        self.assertEqual(registry.check_entry(res["plugins"][0]["entry"]), [])


class AgainstTheRegistry(unittest.TestCase):
    def test_id_registered_to_another_repo(self):
        with Root(nes_entry(repo="someone/nes", owner="someone", repo_id=1)) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", root=root)
        self.assertFalse(res["ok"])
        self.assertIn("already registered to someone/nes", res["plugins"][0]["errors"][0])

    def test_developer_part_used_by_another_owner(self):
        other = nes_entry(id="parrotcart.gameboy", repo="someone/gb", owner="someone", repo_id=2)
        with Root(other) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", root=root)
        self.assertFalse(res["ok"])
        self.assertIn("'parrotcart' is already used by someone", res["plugins"][0]["errors"][0])

    def test_update(self):
        old = nes_entry(version="0.4.5", added="2026-10-01", submission=3, description="Old words.")
        with Root(old) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", desc=None, root=root)
        self.assertTrue(res["ok"], res)
        p = res["plugins"][0]
        self.assertEqual(p["change"], "update")
        self.assertEqual((p["entry"]["added"], p["entry"]["submission"], p["entry"]["description"]),
                         ("2026-10-01", 3, "Old words."))

    def test_tags_and_works_with(self):
        res = run("nes-good", "fixture-dev/nes-plugin", tags=["consoles"], works_with=["gamepad", "keyboard"])
        e = res["plugins"][0]["entry"]
        self.assertEqual((e["tags"], e["works_with"]), (["consoles"], ["gamepad", "keyboard"]))
        self.assertEqual(list(e)[list(e).index("uses") + 1:][:2], ["tags", "works_with"])
        self.assertNotIn("tags", run("nes-good", "fixture-dev/nes-plugin")["plugins"][0]["entry"])
        # a new version keeps the listed plugin's, unless the form gives new ones
        old = nes_entry(version="0.4.5", tags=["arcade", "music"], works_with=["mouse"])
        with Root(old) as root:
            e = run("nes-good", "fixture-dev/nes-plugin", desc=None, root=root)["plugins"][0]["entry"]
            self.assertEqual((e["tags"], e["works_with"]), (["arcade", "music"], ["mouse"]))
            e = run("nes-good", "fixture-dev/nes-plugin", root=root, tags=["tools"])["plugins"][0]["entry"]
            self.assertEqual((e["tags"], e["works_with"]), (["tools"], ["mouse"]))
        for kw in (dict(tags=["emulators"]), dict(tags=["arcade", "music", "tools"]), dict(works_with=["toaster"])):
            with self.subTest(kw):
                res = run("nes-good", "fixture-dev/nes-plugin", **kw)
                self.assertFalse(res["ok"])
                self.assertTrue(any(k in res["errors"][0] for k in ("can only be", "at most")), res["errors"])

    def test_same_file_again(self):
        with Root(nes_entry()) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", root=root)
        self.assertTrue(res["ok"])
        self.assertEqual(res["changed"], [])
        self.assertEqual(res["plugins"][0]["change"], "same")

    def test_same_version_other_file(self):
        e = nes_entry()
        e["download"] = dict(e["download"], sha256="0" * 64)
        with Root(e) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", root=root)
        self.assertFalse(res["ok"])
        self.assertIn("new version", res["plugins"][0]["errors"][0])

    def test_older(self):
        with Root(nes_entry(version="0.5.0")) as root:
            res = run("nes-good", "fixture-dev/nes-plugin", root=root)
        self.assertFalse(res["ok"])
        self.assertIn("older than the listed 0.5.0", res["plugins"][0]["errors"][0])

    def test_examples_hold_no_ids(self):
        with Root() as root:
            ex = nes_entry(repo="parrot-dev/parrotcart-nes", owner="parrot-dev", repo_id=None, example=True)
            registry.write_json(registry.entry_path(root, ex["id"], examples=True), ex)
            self.assertTrue(run("nes-good", "fixture-dev/nes-plugin", root=root)["ok"])


ISSUE_BODY = """### Repository

https://github.com/fixture-dev/nes-plugin

### Release tag

_No response_

### Short description

Plays NES games on the console.

### Type

Consoles

### Works with

- [X] USB gamepad
- [ ] USB keyboard
- [ ] USB mouse
- [ ] MIDI keyboard
- [ ] MIDI out to a computer

### Rules

- [X] The repository is public and has a LICENSE file.
- [X] No commercial game art.
- [X] The registry may copy.
"""


def cli(args, env=None):
    old = dict(os.environ)
    os.environ.update(env or {})
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = validate.main(args)
    finally:
        os.environ.clear()
        os.environ.update(old)
    return code, out.getvalue()


class Command(unittest.TestCase):
    def issue(self, **over):
        d = {"number": 7, "state": "open", "body": ISSUE_BODY, "labels": [{"name": "plugin-submission"}]}
        d.update(over)
        path = os.path.join(tmp(), "issue.json")
        with open(path, "w") as f:
            json.dump(d, f)
        return path

    def test_issue_end_to_end(self):
        out = tmp()
        # (the command reads this checkout's plugins/, where the fixture's ID is the real NES
        # plugin's: as on a registry that doesn't list it yet)
        with unittest.mock.patch.object(registry, "load_entries", return_value={}):
            code, text = cli(["--issue-json", self.issue(), "--out", out, "--fixtures",
                              os.path.join(GH_DIR, "nes-good"), "--today", TODAY])
        self.assertEqual(code, 0, text)
        self.assertTrue(text.startswith(validate.MARK))
        self.assertTrue(os.path.isfile(os.path.join(out, "plugins", "parrotcart.nes", "screenshot-1.png")))
        with open(os.path.join(out, "plugins", "parrotcart.nes.json")) as f:
            e = json.load(f)
        self.assertEqual((e["description"], e["submission"]), ("Plays NES games on the console.", 7))
        self.assertEqual((e["tags"], e["works_with"]), (["consoles"], ["gamepad"]))
        with open(os.path.join(out, "result.json")) as f:
            self.assertEqual(json.load(f)["changed"], ["parrotcart.nes"])
        with open(os.path.join(out, "report.md")) as f:
            self.assertIn("passed", f.read())

    def test_not_a_submission(self):
        for over in ({"labels": []}, {"state": "closed"}, {"pull_request": {"url": "x"}}):
            code, _ = cli(["--issue-json", self.issue(**over), "--fixtures", os.path.join(GH_DIR, "nes-good")])
            self.assertEqual(code, 3, over)

    def test_bad_form(self):
        out = tmp()
        code, text = cli(["--from-issue", "--out", out], {"ISSUE_BODY": "### Repository\n\nnot a repo\n"})
        self.assertEqual(code, 1)
        self.assertIn("owner/repo", text)

    def test_bad_type_on_the_form(self):
        out = tmp()
        body = ISSUE_BODY.replace("\nConsoles\n", "\nConsoles, Arcade, Tools\n")
        code, text = cli(["--from-issue", "--out", out], {"ISSUE_BODY": body})
        self.assertEqual(code, 1)
        self.assertIn("Pick 2 types at most", text)

    def test_tags_by_hand(self):
        out = tmp()
        with unittest.mock.patch.object(registry, "load_entries", return_value={}):
            code, text = cli(["fixture-dev/nes-plugin", "--description", "x", "--tags", "consoles, tools",
                              "--works-with", "gamepad", "--out", out, "--fixtures", os.path.join(GH_DIR, "nes-good")])
        self.assertEqual(code, 0, text)
        with open(os.path.join(out, "plugins", "parrotcart.nes.json")) as f:
            e = json.load(f)
        self.assertEqual((e["tags"], e["works_with"]), (["consoles", "tools"], ["gamepad"]))

    def test_rate_limit_exit(self):
        code, text = cli(["fixture-dev/nes-plugin", "--description", "x", "--fixtures",
                          os.path.join(GH_DIR, "rate-limited")])
        self.assertEqual(code, 2)
        self.assertIn("couldn't finish", text)

    def test_report_is_escaped(self):
        res = {"ok": False, "repo": "a/b", "tag": "`v1`", "release_url": None, "warnings": [], "changed": [],
               "errors": ["@someone [click](https://example.net) <b>x</b> | `code`"], "plugins": []}
        text = validate.report(res)
        self.assertNotIn("@someone", text)
        self.assertNotIn("[click]", text)
        self.assertNotIn("<b>", text)
        self.assertIn("\\`v1\\`", text)


class Jobs(unittest.TestCase):
    def test_find_updates(self):
        old = nes_entry(version="0.4.5", release={"tag": "v0.4.5", "published": "2026-11-01",
                                                  "url": "https://github.com/fixture-dev/nes-plugin/releases/tag/v0.4.5"})
        with Root(old) as root:
            found = find_updates.find(gh("nes-good"), root=root, config=CONFIG, today=TODAY)
        self.assertEqual(len(found), 1)
        repo, tag, res = found[0]
        self.assertEqual((repo, tag, res["changed"]), ("fixture-dev/nes-plugin", "v0.4.6", ["parrotcart.nes"]))

    def test_no_update_when_the_tag_is_listed(self):
        with Root(nes_entry()) as root:
            self.assertEqual(find_updates.find(gh("nes-good"), root=root, config=CONFIG), [])

    def test_verify(self):
        e = nes_entry()
        with Root(e) as root:
            self.assertEqual(verify_entries.verify(gh("nes-good"), "parrotcart.nes", root=root, config=CONFIG), [])
        with Root(dict(e, name="Not NES", opens=[".zip"])) as root:
            bad = verify_entries.verify(gh("nes-good"), "parrotcart.nes", root=root, config=CONFIG)
        self.assertEqual(len(bad), 2)
        self.assertIn("name is 'Not NES'", bad[0])

    def test_verify_reads_the_files_and_the_notes(self):
        e = nes_entry()
        with Root(e) as root:
            with open(os.path.join(root, "plugins", "parrotcart.nes", "cart-readme.txt"), "ab") as f:
                f.write(b"An extra line.\n")
            bad = verify_entries.verify(gh("nes-good"), "parrotcart.nes", root=root, config=CONFIG)
        self.assertTrue(any("cart-readme.txt" in b for b in bad), bad)
        with Root(e) as root:                                # a screenshot swapped for another real PNG
            other = shot(7)
            with open(os.path.join(root, "plugins", "parrotcart.nes", "screenshot-1.png"), "wb") as f:
                f.write(other)
            e2 = dict(e, screenshots=[validate._meta("screenshot-1.png", other), e["screenshots"][1]])
            registry.write_json(registry.entry_path(root, e["id"]), e2)
            bad = verify_entries.verify(gh("nes-good"), "parrotcart.nes", root=root, config=CONFIG)
        self.assertTrue(any("screenshots is" in b for b in bad), bad)
        edited = dict(e, history=[dict(e["history"][0], notes="Not what the release says.")])
        with Root(edited) as root:
            bad = verify_entries.verify(gh("nes-good"), "parrotcart.nes", root=root, config=CONFIG)
        self.assertTrue(any("notes for 0.4.6 aren't the release's" in b for b in bad), bad)

    def test_apply_entries_copies_the_files(self):
        res = run("nes-good", "fixture-dev/nes-plugin")
        src, dst = tmp(), tmp()
        validate.write_out(res, src)
        self.assertEqual(sorted(os.listdir(os.path.join(src, "plugins", "parrotcart.nes"))),
                         ["NES-0.4.6.CVP", "README.md", "cart-readme.txt", "screenshot-1.png", "screenshot-2.png"])
        os.makedirs(os.path.join(dst, "plugins", "parrotcart.nes"))
        with open(os.path.join(dst, "plugins", "parrotcart.nes", "screenshot-3.png"), "wb") as f:
            f.write(shot(3))                                 # left from an older version: it must go
        old = registry.ROOT
        self.addCleanup(setattr, registry, "ROOT", old)
        registry.ROOT = dst                                  # (never this checkout's plugins/)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(apply_entries.main([src]), 0)
        self.assertEqual(out.getvalue().split(), ["parrotcart.nes"])
        e = registry.load_entries(dst)["parrotcart.nes"]
        self.assertEqual(registry.check_files(registry.files_dir(dst, e["id"]), e), [])
        # a file the entry doesn't list, or one changed on the way, stops it
        for name, data in (("extra.html", b"<script>"), ("screenshot-1.png", shot(3))):
            with self.subTest(name):
                src2 = tmp()
                validate.write_out(res, src2)
                with open(os.path.join(src2, "plugins", "parrotcart.nes", name), "wb") as f:
                    f.write(data)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(apply_entries.main([src2]), 1)
                self.assertIn(name, err.getvalue())

    def test_apply_entries(self):
        e = nes_entry()
        src = tmp()
        self.addCleanup(setattr, registry, "ROOT", registry.ROOT)
        registry.ROOT = tmp()
        validate.write_out(run("nes-good", "fixture-dev/nes-plugin"), src)
        self.assertEqual(registry.check_entry(e, "parrotcart.nes.json"), [])
        # a bad one stops the lot
        bad = dict(e, id="../../evil")
        with open(os.path.join(src, "plugins", "zzz.json"), "w") as f:
            json.dump(bad, f)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(apply_entries.main([src]), 1)
        self.assertIn("zzz.json", err.getvalue())


if __name__ == "__main__":
    unittest.main()
