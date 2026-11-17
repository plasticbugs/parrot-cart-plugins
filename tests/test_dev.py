"""the developer portal: it builds from a starter kit (tests/fixtures/kit, a small
stand-in), its doc pages are the kit's own Markdown with their links kept inside the
portal, and every link on the Pages site, the plugins site and the portal together,
goes somewhere"""
import copy
import glob
import os
import re
import shutil
import unittest

from helpers import ROOT, shot, tmp
import build_dev
import build_site
import cvp
import registry
import sitecopy

KIT = os.path.join(ROOT, "tests", "fixtures", "kit")
REPO = "https://github.com/plasticbugs/parrot-plugin-template"
DOCS = {"start", "hardware", "sdk", "testing", "rules", "release"}
MADE = {"examples", "packaging", "tools"}


def kit_copy():
    """the fixture kit in a folder of its own, outside git, to change"""
    d = os.path.join(tmp(), "kit")
    shutil.copytree(KIT, d)
    return d


def hrefs(text):
    return re.findall(r'(?:href|src)="([^"]*)"', text)


class Portal(unittest.TestCase):
    def build(self, kit=KIT, with_site=False):
        """the portal alone (in OUT/developers), or the whole Pages site; {path: html}"""
        out = os.path.join(tmp(), "_site")
        if with_site:
            build_site.build(out)
        build_dev.build(os.path.join(out, "developers"), kit)
        pages = {}
        for p in glob.glob(os.path.join(out, "**", "*.html"), recursive=True):
            with open(p) as f:
                pages[os.path.relpath(p, out)] = f.read()
        return out, pages

    def test_the_pages_site_links_up(self):
        out, pages = self.build(with_site=True)
        dev = {n for n in pages if n.startswith("developers/")}
        want = {"developers/index.html"} | {f"developers/{s}/index.html" for s in DOCS | MADE}
        self.assertEqual(dev, want)
        for name, text in pages.items():
            if name.startswith("converter/"):
                continue
            self.assertIn('<html lang="en">', text, name)
            for h in hrefs(text):
                if h.startswith(("https://", "#")):
                    continue
                self.assertFalse(re.match(r"^[a-z]+:", h) or h.startswith("/"), (name, h))
                path = h.split("#")[0]
                target = os.path.normpath(os.path.join(out, os.path.dirname(name), path))
                if path.endswith("/") or path == "":
                    target = os.path.join(target, "index.html")
                self.assertTrue(os.path.exists(target), (name, h))
        # the authors' old addresses land on the portal
        for name, to in build_site.MOVED.items():
            target = os.path.normpath(os.path.join(out, os.path.dirname(name), to.split("#")[0], "index.html"))
            self.assertTrue(target.startswith(os.path.join(out, "developers")) and os.path.exists(target), name)
        # each site's header names the other
        self.assertIn('<a href="developers/">Developers</a>', pages["index.html"])
        self.assertIn('<a href="../index.html">Plugins</a>', pages["developers/index.html"])
        self.assertIn('href="../../assets/site.css"', pages["developers/start/index.html"])

    def test_a_doc_is_the_kits_markdown(self):
        _, pages = self.build()
        page = pages["developers/start/index.html"]
        self.assertIn('<h1 id="hero-title">Getting started</h1>', page)
        self.assertEqual(page.count("<h1"), 1)
        # its headings a level up, with ids, and the h2s listed beside it; code stays code
        self.assertIn('<h2 id="1-tools">1. Tools</h2>', page)
        self.assertIn('<h3 id="a-smaller-part">A smaller part</h3>', page)
        self.assertIn('<pre><code># not a heading', page)
        self.assertIn('<ul class="side__toc" aria-label="On this page"><li><a href="#1-tools">1. Tools</a></li></ul>', page)
        self.assertIn('<a href="../start/" aria-current="page">Get started</a>', page)
        # links to the kit's docs go to their pages here, the rest to GitHub, and a path that isn't there stays text
        self.assertIn('<a href="../rules/#the-id">the plugin rules</a>', page)
        self.assertIn('<a href="../sdk/">SDK</a>', page)
        self.assertIn('<a href="../hardware/"><code>docs/hardware.md</code></a>', page)
        self.assertIn('<a href="../packaging/#icons"><code>docs/icons.md</code></a>', page)
        self.assertIn('<a href="../examples/#sound"><code>examples/sound</code></a>', page)
        self.assertIn(f'<a href="{REPO}/blob/main/tools/check.sh"><code>tools/check.sh</code></a>', page)
        self.assertIn("<code>docs/nothing.md</code> isn", page)
        self.assertIn(" <code>build/HELLO.CVP</code>", page)
        self.assertIn(f'href="{REPO}/blob/main/docs/getting-started.md"', page)
        self.assertIn("“The rules”", page)
        self.assertIn('<a class="pager__next" href="../hardware/">', page)
        # the same heading twice gets two ids; the SDK's relative paths are its own folder's
        self.assertIn('<h2 id="the-id-2">', pages["developers/rules/index.html"])
        sdk = pages["developers/sdk/index.html"]
        self.assertIn(f'<a href="{REPO}/blob/main/sdk/firmware/revc/sdk/cvplugin.cmake"><code>../sdk/cvplugin.cmake</code></a>', sdk)
        self.assertIn("<code>cvplugin.cmake</code>,", sdk)
        self.assertIn('class="warn doc__note"', sdk)
        self.assertNotIn('class="warn doc__note"', page)

    def test_an_optional_doc_comes_and_goes_with_the_kit(self):
        _, pages = self.build()
        for name, text in pages.items():
            self.assertNotIn("features/", text, name)
        kit = kit_copy()
        with open(os.path.join(kit, "docs", "features.md"), "w") as f:
            f.write("# Features\n\nEach USB feature.\n\n## USB host\n\nPads.\n")
        _, pages = self.build(kit)
        page = pages["developers/features/index.html"]
        self.assertIn('<h1 id="hero-title">Features</h1>', page)
        at = page.index('<nav class="side"')
        side = page[at:page.index("</nav>", at)]
        self.assertLess(side.index('href="../sdk/"'), side.index('href="../features/"'))
        self.assertLess(side.index('href="../features/"'), side.index('href="../examples/"'))
        self.assertIn('<a href="features/"><span class="group__name">Features</span>', pages["developers/index.html"])

    def test_a_kit_without_a_doc_stops_the_build(self):
        kit = kit_copy()
        os.remove(os.path.join(kit, "docs", "testing.md"))
        with self.assertRaises(SystemExit) as cm:
            self.build(kit)
        self.assertIn("docs/testing.md", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            build_dev.find_kit(os.path.join(tmp(), "nowhere"))
        self.assertIn("--kit", str(cm.exception))

    def test_the_examples(self):
        _, pages = self.build()
        page = pages["developers/examples/index.html"]
        self.assertLess(page.index('<li class="ex" id="src">'), page.index('<li class="ex" id="sound">'))
        self.assertIn('<h2 class="ex__title">Sound Example</h2>', page)
        self.assertIn("<code>cvk_sound</code>", page)
        self.assertIn(f'href="{REPO}/tree/main/examples/sound"', page)
        self.assertIn(f'href="{REPO}/tree/main/src"', page)
        self.assertIn('<h2 id="two-kinds-of-plugin">Two kinds of plugin</h2>', page)
        self.assertIn('<h2 id="building-them">Building them</h2>', page)
        self.assertNotIn("<table", page)                   # the kit's list of examples is the cards
        self.assertIn("never both (<code>sound</code>)", page)      # a bare name isn't a path: no link
        self.assertEqual(page.count('<path class="tv-m" d="'), 2)      # each one's icon

    def test_packaging_and_the_icon_editor(self):
        out, pages = self.build()
        page = pages["developers/packaging/index.html"]
        for part in ("readme", "screenshots", "icons"):
            self.assertIn(f'<li><h2><a href="#{part}">', page)
            self.assertIn(f'<section class="part" id="{part}"', page)
        self.assertIn('href="../../submit/"', page)
        self.assertIn('href="../hardware/"', page)
        self.assertIn(f'<a class="link" href="{REPO}/blob/main/docs/icons.md"><code class="code">docs/icons.md</code></a>', page)
        self.assertNotIn("docs/readme-spec.md", page)       # the fixture kit hasn't one: no line for it
        for f in ("icon-template.txt", "sample-icon.txt", "sample-file-icon.txt"):
            self.assertIn(f'href="files/{f}" download', page)
            self.assertTrue(os.path.isfile(os.path.join(out, "developers", "packaging", "files", f)))
        tools = pages["developers/tools/index.html"]
        icons = build_dev.gallery_icons()
        self.assertGreaterEqual(len(icons), 30)
        for slug, _, _, hx in icons:
            self.assertIn(f'href="#p={hx}" data-use hidden', tools)
            with open(os.path.join(out, "developers", "tools", "icons", slug + ".txt")) as f:
                self.assertEqual(f.read(), "\n".join(cvp.icon_rows(hx)) + "\n")
        self.assertIn("<noscript>", tools)
        self.assertEqual(tools.count('class="px__c"'), 128)
        self.assertEqual(tools.count('tabindex=-1'), 126)        # one tab stop a grid
        self.assertIn('<path id="ed-plugin"', tools)
        self.assertIn('<path id="ed-file"', tools)
        self.assertIn('<script src="../assets/icon-editor.js" defer>', tools)
        for name in ("icon-editor.js", "dev.js"):
            with open(os.path.join(out, "developers", "assets", name)) as f:
                js = f.read()
            for call in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "import(", "http://", "https://"):
                self.assertNotIn(call, js, (name, call))

    def test_the_kits_screenshot(self):
        _, pages = self.build()
        self.assertNotIn("kit-screenshot.png", pages["developers/index.html"])
        kit = kit_copy()
        os.makedirs(os.path.join(kit, "screenshots"))
        with open(os.path.join(kit, "screenshots", "screenshot-1.png"), "wb") as f:
            f.write(shot(1))
        out, pages = self.build(kit)
        self.assertIn('<img src="assets/kit-screenshot.png" width="256" height="192"', pages["developers/index.html"])
        self.assertIn('src="../assets/kit-screenshot.png"', pages["developers/packaging/index.html"])
        with open(os.path.join(out, "developers", "assets", "kit-screenshot.png"), "rb") as f:
            self.assertEqual(f.read(), shot(1))

    def test_the_css_is_tokens_only(self):
        with open(os.path.join(ROOT, "developers", "assets", "dev.css")) as f:
            css = f.read()
        self.assertTrue(css.startswith("/* Hallmark · "))
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|oklch\(|font-family:(?!\s*var\()", css))
        self.assertIn("prefers-reduced-motion", css)


class Words(unittest.TestCase):
    """developers/copy.toml holds every word the portal's pages use"""

    def test_every_key_the_code_reads_is_there(self):
        with open(os.path.join(ROOT, "tools", "build_dev.py")) as f:
            used = set(re.findall(r'\bT\.\w+\(\s*"([a-z0-9_.]+)"', f.read()))
        used |= {label for _, _, _, label in build_dev.PAGES} | {f"map.{slug}" for _, slug, _, _ in build_dev.PAGES}
        used |= {f"side.{g}" for g in build_dev.GROUPS}
        slugs = {slug: label for _, slug, _, label in build_dev.PAGES}
        for slug in build_dev.TOP_NAV:
            self.assertEqual(slugs[slug], f"nav.{slug}")
        for _, _, group, label in build_dev.PAGES:
            self.assertIn(group, build_dev.GROUPS)
            self.assertTrue(label.startswith("nav."))
        have = set(build_dev.T.keys())
        self.assertEqual(sorted(used - have), [], "read by the code but missing from developers/copy.toml")
        self.assertEqual(sorted(have - used), [], "in developers/copy.toml but nothing reads it")
        # a missing key stops the build, and says which
        data = copy.deepcopy(build_dev.T.data())
        del data["home"]["hero"]["lead"]
        old, build_dev.T = build_dev.T, sitecopy.Copy(path=build_dev.T.path, data=data)
        try:
            with self.assertRaises(sitecopy.CopyError) as cm:
                build_dev.build(os.path.join(tmp(), "developers"), KIT)
        finally:
            build_dev.T = old
        self.assertIn("home.hero.lead is missing", str(cm.exception))
        self.assertIn("developers/copy.toml", str(cm.exception))

    def test_the_two_sites_keep_their_own_words(self):
        site = set(sitecopy.COPY.keys())
        self.assertFalse({k for k in site if k.startswith(("authors.", "packaging.", "editor.", "tools."))})
        self.assertEqual(registry.load_config(ROOT)["template_repo"], "plasticbugs/parrot-plugin-template")


if __name__ == "__main__":
    unittest.main()
