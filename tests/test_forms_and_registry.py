"""the issue form's parser, the registry's files, and the workflow lint"""
import glob
import json
import os
import unittest

from helpers import ROOT, tmp
import issue_form
import registry

BODY = """### Repository

{repo}

### Release tag

{tag}

### Short description

{desc}

### Rules

- [{a}] The plugin is a free download.
- [X] The repository is public.
- [X] The repository has a LICENSE file.
- [X] The README credits.
- [X] No commercial game art.
- [X] The registry may copy.
"""


def body(repo="someone/thing", tag="_No response_", desc="Does a thing.", a="X"):
    return BODY.format(repo=repo, tag=tag, desc=desc, a=a)


class Form(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(issue_form.parse(body()), {"repo": "someone/thing", "tag": "", "description": "Does a thing.",
                                                    "rules_ok": True})
        f = issue_form.parse(body(repo="https://github.com/someone/thing.git", tag="v1.2.0"))
        self.assertEqual((f["repo"], f["tag"]), ("someone/thing", "v1.2.0"))

    def test_rules(self):
        self.assertFalse(issue_form.parse(body(a=" "))["rules_ok"])

    def test_rejects(self):
        for kw in (dict(repo="someone/thing; rm -rf /"), dict(repo="$(id)/x"), dict(repo=""),
                   dict(tag="v1 && echo"), dict(tag="`x`"), dict(desc="x" * 161), dict(desc="_No response_")):
            with self.subTest(kw), self.assertRaises(issue_form.FormError):
                issue_form.parse(body(**kw))

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

    def test_pages_url(self):
        self.assertEqual(registry.pages_url({"registry_repo": "OWNER/parrotcart-plugins"}),
                         "https://owner.github.io/parrotcart-plugins/")
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
