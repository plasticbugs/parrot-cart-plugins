"""the issue form's parser, the registry's files, and the workflow lint"""
import glob
import json
import os
import unittest

from helpers import ROOT, tmp
import issue_form
import registry
import sitecopy

BODY = """### Repository

{repo}

### Release tag

{tag}

### Short description

{desc}

### Type

{types}

### Works with

{works}

### Rules

- [{a}] The repository is public and has a LICENSE file.
- [X] No commercial game art.
- [X] The registry may copy.
"""


WORKS = """- [X] USB gamepad
- [ ] USB keyboard
- [ ] USB mouse
- [x] MIDI keyboard
- [ ] MIDI out to a computer"""


def body(repo="someone/thing", tag="_No response_", desc="Does a thing.", a="X", types="Arcade, Music",
         works=WORKS):
    return BODY.format(repo=repo, tag=tag, desc=desc, a=a, types=types, works=works)


def names():
    """the form's labels for registry.config.json's tags and works_with: {label: value}"""
    n = sitecopy.names(registry.load_config(ROOT))
    return {v: k for k, v in n["tags"].items()}, {v: k for k, v in n["works_with"].items()}


class Form(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(issue_form.parse(body()), {"repo": "someone/thing", "tag": "", "description": "Does a thing.",
                                                    "tags": [], "works_with": [], "rules_ok": True})
        f = issue_form.parse(body(), 160, *names())
        self.assertEqual((f["tags"], f["works_with"]), (["arcade", "music"], ["gamepad", "midi-in"]))
        f = issue_form.parse(body(repo="https://github.com/someone/thing.git", tag="v1.2.0"))
        self.assertEqual((f["repo"], f["tag"]), ("someone/thing", "v1.2.0"))

    def test_rules(self):
        self.assertFalse(issue_form.parse(body(a=" "))["rules_ok"])

    def test_rejects(self):
        for kw in (dict(repo="someone/thing; rm -rf /"), dict(repo="$(id)/x"), dict(repo=""),
                   dict(tag="v1 && echo"), dict(tag="`x`"), dict(desc="x" * 161), dict(desc="_No response_")):
            with self.subTest(kw), self.assertRaises(issue_form.FormError):
                issue_form.parse(body(**kw))

    def test_type_and_works_with(self):
        types, works = names()
        parse = lambda **kw: issue_form.parse(body(**kw), 160, types, works)
        self.assertEqual(parse(types="tools")["tags"], ["tools"])                   # a value is fine too
        self.assertEqual(parse(types="Tools, Tools")["tags"], ["tools"])
        self.assertEqual(parse(types="_No response_")["tags"], [])                  # an issue from the old form
        self.assertEqual(parse(works="_No response_")["works_with"], [])
        old = body().split("### Type")[0] + "### Rules\n\n- [X] a\n- [X] b\n- [X] c\n"
        self.assertEqual(issue_form.parse(old, 160, types, works)["tags"], [])
        f = parse(works="- [x] MIDI out to a computer\n- [X] USB keyboard")
        self.assertEqual(f["works_with"], ["keyboard", "midi-out"])                   # in the form's order
        for kw in (dict(types="Arcade, Music, Tools"), dict(types="Toasters"), dict(types="<b>x</b>"),
                   dict(works="- [x] A toaster")):
            with self.subTest(kw), self.assertRaises(issue_form.FormError):
                parse(**kw)

    def test_description_is_one_clean_line(self):
        f = issue_form.parse(body(desc="Two\u202e words\u200b\there"))
        self.assertEqual(f["description"], "Two words here")


class Files(unittest.TestCase):
    def test_examples_are_well_formed(self):
        files = glob.glob(os.path.join(ROOT, "examples", "plugins", "*.json"))
        self.assertTrue(files)
        for p in files:
            with open(p) as f:
                e = json.load(f)
            self.assertEqual(registry.check_entry(e, p), [], p)
            self.assertIs(e["example"], True)

    def test_tags_and_works_with(self):
        e = registry.load_entries(ROOT)["parrotcart.msx"]
        self.assertEqual((e["tags"], e["works_with"]), (["computers"], ["gamepad", "keyboard", "mouse"]))
        old = {k: v for k, v in e.items() if k not in ("tags", "works_with")}      # an entry from before them
        self.assertEqual(registry.check_entry(old), [])
        self.assertEqual(list(registry.labelled(old, ["tools"], ["mouse"])), list(e))   # where the entries keep them
        for key, value in (("tags", []), ("tags", ["arcade", "music", "tools"]), ("tags", ["arcade", "arcade"]),
                           ("tags", ["emulators"]), ("tags", "arcade"), ("tags", [{"x": 1}]),
                           ("works_with", []), ("works_with", ["joystick"]), ("works_with", ["mouse", "mouse"]),
                           ("works_with", None)):
            with self.subTest(key=key, value=value):
                bad = registry.check_entry(dict(e, **{key: value}))
                self.assertTrue(any(p.startswith(key) for p in bad), bad)
        # the words come from the config: one that lists another tag allows it
        config = dict(registry.load_config(ROOT), tags=["emulators"])
        self.assertEqual(registry.check_entry(dict(e, tags=["emulators"]), config=config), [])
        self.assertTrue(registry.check_entry(e, config=config))

    def test_every_tag_has_a_name(self):
        config = registry.load_config(ROOT)
        n = sitecopy.names(config)
        for k, key in sitecopy.NAMES.items():
            self.assertEqual(list(n[k]), config[k])
            self.assertEqual(set(sitecopy.COPY.table(key)), set(config[k]), f"{key} names a word the config doesn't list")
        with self.assertRaises(sitecopy.CopyError) as cm:
            sitecopy.names(dict(config, tags=config["tags"] + ["emulators"]))
        self.assertIn("browse.types.emulators is missing", str(cm.exception))
        with self.assertRaises(ValueError):
            p = os.path.join(tmp(), "registry.config.json")
            registry.write_json(p, dict(config, tags=["Bad Word"]))
            registry.load_config(os.path.dirname(p))

    def test_index(self):
        config = registry.load_config(ROOT)
        ex = registry.load_entries(ROOT, examples=True)
        idx = registry.index(ex, config, now="2026-11-14T00:00:00Z")
        self.assertEqual(idx["format"], registry.INDEX_FORMAT)
        self.assertEqual(idx["plugins"], [])                     # examples never go in the index
        live = {k: dict(v, example=False) for k, v in ex.items()}
        idx = registry.index(live, config, now="2026-11-14T00:00:00Z")
        self.assertEqual([p["name"] for p in idx["plugins"]],
                         sorted((e["name"] for e in ex.values()), key=str.lower))
        self.assertNotIn("example", idx["plugins"][0])
        live = registry.load_entries(ROOT)
        idx = registry.index(live, config, now="2026-11-14T00:00:00Z")
        msx = next(p for p in idx["plugins"] if p["id"] == "parrotcart.msx")
        self.assertEqual((msx["tags"], msx["works_with"]), (["computers"], ["gamepad", "keyboard", "mouse"]))

    def test_pages_url(self):
        self.assertEqual(registry.pages_url({"registry_repo": "Someone/parrotcart-plugins"}),
                         "https://someone.github.io/parrotcart-plugins/")
        self.assertEqual(registry.pages_url({"registry_repo": "Parrot/parrot.github.io"}), "https://parrot.github.io/")

    def test_entry_paths(self):
        for bad in ("../x.y", "x", "X.y", "a/b.c"):
            with self.assertRaises(ValueError):
                registry.entry_path(ROOT, bad)


class Lint(unittest.TestCase):
    def test_workflows(self):
        import lint_workflows
        bad = []
        for p in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
            bad += lint_workflows.lint_workflow(p)
        self.assertEqual(bad + lint_workflows.lint_form(), [])

    def test_lint_catches(self):
        import lint_workflows
        p = os.path.join(tmp(), "bad.yml")
        with open(p, "w") as f:
            f.write("on:\n  pull_request_target:\npermissions: write-all\njobs:\n  x:\n    runs-on: ubuntu-24.04\n"
                    "    steps:\n      - uses: actions/checkout@v4\n      - run: echo \"${{ github.event.issue.title }}\"\n")
        bad = " ".join(lint_workflows.lint_workflow(p))
        for what in ("pinned", "pull_request_target", "top-level permissions", "no timeout", "expression inside run",
                     "event text", "keeps its credentials"):
            self.assertIn(what, bad)

    def test_reader_matches_pyyaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML isn't installed")
        import lint_workflows
        for p in glob.glob(os.path.join(ROOT, ".github", "**", "*.yml"), recursive=True):
            with open(p) as f:
                want = yaml.safe_load(f)
            if True in want:
                want["on"] = want.pop(True)
            self.assertEqual(lint_workflows.load(p), want, p)


if __name__ == "__main__":
    unittest.main()
