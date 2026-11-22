"""the static site: every page builds, links stay inside the site or go to
https, and an entry's text can never become markup"""
import copy
import glob
import hashlib
import json
import os
import re
import unittest

import html.parser

from helpers import GH_DIR, ROOT, make_cvp, image, shot, tmp, SRAM_IMAGE
import build_site
import cvp
import ghapi
import markdown
import registry
import sitecopy
import tvscreen
import validate

CONVERTER = {"converter/index.html"}     # the movie converter, copied in as built
MOVED = build_site.MOVED                # the authors' old addresses, which send you on to the developer portal
AUTHORS = set(MOVED)


def listed(root, description="Plays NES games.", **over):
    """the nes-good scenario's plugin, listed in root as the bot would list it"""
    gh = ghapi.GitHub(token="", transport=ghapi.RecordedTransport(os.path.join(GH_DIR, "nes-good")))
    config = registry.load_config(ROOT)
    res = validate.validate(gh, "fixture-dev/nes-plugin", None, description, root=root, config=config,
                            today="2026-11-14")
    assert res["ok"], res
    res["plugins"][0]["entry"].update(over)
    validate.write_entries(res, root)
    config["show_examples"] = False
    registry.write_json(os.path.join(root, "registry.config.json"), config)
    return res["plugins"][0]["entry"]


class Tags(html.parser.HTMLParser):
    """every tag and attribute in a piece of HTML"""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.seen = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.seen.append((tag, dict(attrs)))


def hrefs(text):
    return re.findall(r'(?:href|src)="([^"]*)"', text)


class Site(unittest.TestCase):
    def build(self, root=ROOT, config=None):
        out = os.path.join(tmp(), "_site")
        build_site.build(out, config, root)
        pages = {}
        for p in glob.glob(os.path.join(out, "**", "*.html"), recursive=True):
            with open(p) as f:
                pages[os.path.relpath(p, out)] = f.read()
        with open(os.path.join(out, "registry.json")) as f:
            return out, pages, json.load(f)

    def test_the_registry_builds(self):
        out, pages, idx = self.build()
        examples = registry.load_entries(ROOT, examples=True)
        live = registry.load_entries(ROOT)
        want = ({"index.html", "plugins/index.html", "submit/index.html"} | AUTHORS | CONVERTER
                | {f"plugins/{i}/index.html" for i in set(examples) | set(live)})
        self.assertEqual(set(pages), want)
        self.assertEqual([e["id"] for e in idx["plugins"]],
                         [e["id"] for e in sorted(live.values(), key=lambda e: (e["name"].lower(), e["id"]))])
        for e in idx["plugins"]:                # every listed plugin's download is a file on the site
            self.assertTrue(os.path.exists(os.path.join(out, "plugins", e["id"], e["download"]["name"])), e["id"])
            page = pages[f"plugins/{e['id']}/index.html"]
            self.assertIn(f'<a class="btn" href="{e["download"]["name"]}" download>', page)
        for name, text in pages.items():
            self.assertIn('<html lang="en">', text, name)
            self.assertNotIn("${{", text, name)
            for h in hrefs(text):
                if h.startswith(("https://", "#")):
                    continue
                self.assertFalse(re.match(r"^[a-z]+:", h) or h.startswith("/"), (name, h))
                target = os.path.normpath(os.path.join(out, os.path.dirname(name), h.split("#")[0]))
                if target.startswith(os.path.join(out, "developers")):
                    continue                    # the developer portal's: tests/test_dev.py builds both and follows them
                if h.split("#")[0].endswith("/"):
                    target = os.path.join(target, "index.html")
                self.assertTrue(os.path.exists(target), (name, h))

    def test_examples_can_be_hidden(self):
        config = dict(registry.load_config(ROOT), show_examples=False)
        _, pages, _ = self.build(config=config)
        self.assertEqual(set(pages), {"index.html", "plugins/index.html", "submit/index.html"} | AUTHORS | CONVERTER
                         | {f"plugins/{i}/index.html" for i in registry.load_entries(ROOT)})

    def test_a_built_in_plugin(self):
        _, pages, _ = self.build()
        page = pages["plugins/parrotcart.movies/index.html"]
        self.assertIn('<a class="link" href="../../converter/">movie converter</a>', page)
        self.assertNotIn('id="install"', page)
        for name in ("index.html", "plugins/index.html"):
            self.assertNotIn("[movie converter]", pages[name])
        self.assertIn('<p class="pcard__desc">Player for movies made with the movie converter</p>',
                      pages["plugins/index.html"])
        for name, text in pages.items():
            if not name.startswith("converter/") and name not in MOVED:
                self.assertIn('href="' + "../" * name.count("/") + 'converter/"', text, name)

    def test_the_shop_and_the_code(self):
        root = tmp()
        listed(root)
        _, pages, _ = self.build(root)
        for name, text in pages.items():
            if name not in MOVED:
                self.assertIn('<a class="slab__shop" href="https://parrotcart.com/">Get a Parrot Cart</a>', text, name)
        page = pages["plugins/parrotcart.nes/index.html"]
        self.assertIn('<a class="repo" href="https://github.com/fixture-dev/nes-plugin">', page)
        self.assertNotIn(">Needs<", pages["index.html"])
        _, pages, _ = self.build()
        self.assertNotIn('id="source"', pages["plugins/parrotcart.movies/index.html"])

    def test_one_of_ours_with_no_release_yet(self):
        examples = registry.load_entries(ROOT, examples=True)
        coming = [e for e in examples.values() if not e.get("built_in")]
        if not coming:
            self.skipTest("every plugin of ours has a release")
        _, pages, idx = self.build()
        for e in coming:
            page = pages[f"plugins/{e['id']}/index.html"]
            self.assertIn(f'<a class="repo" href="https://github.com/{e["repo"]}">', page)
            self.assertIn("No release yet", page)
            self.assertIn("has no release yet. The first one is coming", page)
            self.assertNotIn('id="install"', page)
            self.assertNotIn(" download>", page)
            self.assertNotIn(e["id"], [p["id"] for p in idx["plugins"]])

    def test_old_authors_pages_send_you_on(self):
        _, pages, _ = self.build()
        for name, to in MOVED.items():
            self.assertTrue(to.startswith("../" * name.count("/") + "developers/"), (name, to))
            self.assertIn(f'<meta http-equiv="refresh" content="0; url={to}">', pages[name])
        for name, text in pages.items():
            if name not in MOVED and name not in CONVERTER:
                self.assertNotIn("authors/", text, name)
                self.assertIn('href="' + "../" * name.count("/") + 'developers/"', text, name)

    def test_entry_text_is_escaped(self):
        root = tmp()
        evil = '<script>alert(1)</script>"\'><img src=x onerror=alert(2)>'
        e = listed(root, name="<b>NES</b>", by='"><svg onload=x>', description=evil, credits=evil, home="/<i>")
        e["license"]["name"] = evil
        e["history"][0]["notes"] += "\n\n" + evil + "\n\n[x](javascript:alert(3))"
        self.assertEqual(registry.check_entry(e), [])
        registry.write_json(registry.entry_path(root, e["id"]), e)
        _, pages, idx = self.build(root)
        self.assertEqual([p["id"] for p in idx["plugins"]], ["parrotcart.nes"])
        for name, text in pages.items():
            for bad in ("<script>alert", "<img src=x", "<b>NES", "<svg onload", "<i>", 'href="javascript', "<a onerror", " onerror=alert(2)>"):
                self.assertNotIn(bad, text, (name, bad))
        self.assertIn("&lt;b&gt;NES&lt;/b&gt;", pages["plugins/parrotcart.nes/index.html"])

    def test_a_plugins_page_shows_what_was_copied(self):
        root = tmp()
        e = listed(root)
        out, pages, idx = self.build(root)
        page = pages["plugins/parrotcart.nes/index.html"]
        here = os.path.join(out, "plugins", "parrotcart.nes")
        # the screenshots: copies beside the page, never the release's own address
        for i in (1, 2):
            with open(os.path.join(here, f"screenshot-{i}.png"), "rb") as f:
                self.assertEqual(f.read(), shot(i))
            self.assertIn(f'<img src="screenshot-{i}.png" width="256" height="192"', page)
        self.assertNotIn("releases/download/v0.4.6/screenshot", page)
        self.assertIn('src="plugins/parrotcart.nes/screenshot-1.png"', pages["index.html"])
        for t, a in Tags(page).seen + Tags(pages["index.html"]).seen:
            if t in ("img", "script", "source", "video", "iframe") and "src" in a:
                self.assertFalse(a["src"].startswith(("http", "//")), a)
        # the cart's README: the .CVP's text as it is, and drawn in the menu's font
        with open(os.path.join(here, "cart-readme.txt")) as f:
            cart = f.read()
        self.assertIn('<pre class="plain">' + build_site.e_(cart) + "</pre>", page)
        self.assertIn("README on the cart", page)
        self.assertEqual(page.count('<use href="#tvg'), len([c for c in cart if c not in " \n"])
                         + sum(1 for c in "".join(tvscreen.details_page(e).lines) if c != " "))
        # README.md, as safe GitHub-flavoured Markdown
        self.assertIn("<table><thead><tr><th>Button</th><th>Does</th></tr></thead>", page)
        self.assertIn('<input type="checkbox" disabled checked>', page)
        self.assertNotIn("not on the site", page)             # the README's <script>, with what it held
        # the release's notes
        self.assertIn("<strong>USB pads</strong> keep working", page)
        self.assertIn('href="https://github.com/fixture-dev/nes-plugin/blob/v0.4.6/docs/pads.md"', page)
        self.assertNotIn("tracker.png", page)
        self.assertEqual(idx["plugins"][0]["screenshots"],
                         [f"https://plasticbugs.github.io/parrot-cart-plugins/plugins/parrotcart.nes/screenshot-{i}.png"
                          for i in (1, 2)])
        self.assertTrue(idx["plugins"][0]["readme_url"].endswith("/plugins/parrotcart.nes/cart-readme.txt"))
        # the download: the site's own copy of the release's .CVP, so nobody has to go to GitHub for it
        with open(os.path.join(here, "NES-0.4.6.CVP"), "rb") as f:
            data = f.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), e["download"]["sha256"])
        self.assertIn('<a class="btn" href="NES-0.4.6.CVP" download>', page)
        self.assertNotIn('href="https://github.com/fixture-dev/nes-plugin/releases/download', page)
        d = idx["plugins"][0]["download"]
        self.assertEqual(d["url"], "https://plasticbugs.github.io/parrot-cart-plugins/plugins/parrotcart.nes/NES-0.4.6.CVP")
        self.assertEqual(d["from"], e["download"]["url"])
        # a copy that isn't the release's file stops the build
        with open(os.path.join(root, "plugins", "parrotcart.nes", "NES-0.4.6.CVP"), "r+b") as f:
            f.seek(600)
            f.write(b"\xff")
        self.assertTrue(any("NES-0.4.6.CVP" in b for b in registry.check_files(
            os.path.join(root, "plugins", "parrotcart.nes"), e)))

    def test_a_plugin_without_a_readme_says_so(self):
        root = tmp()
        e = listed(root)
        self.assertNotIn("No README on the cart", self.build(root)[1]["plugins/parrotcart.nes/index.html"])
        e["readme"]["cart"] = None              # as a plugin built before the README existed
        registry.write_json(registry.entry_path(root, e["id"]), e)
        os.remove(os.path.join(registry.files_dir(root, e["id"]), registry.CART_README))
        page = self.build(root)[1]["plugins/parrotcart.nes/index.html"]
        self.assertIn("No README on the cart", page)
        self.assertIn('href="../../developers/packaging/#readme"', page)

    def test_the_site_needs_no_script_and_calls_nobody(self):
        out, pages, _ = self.build()
        for name in ("site.js", "browse.js"):
            with open(os.path.join(out, "assets", name)) as f:
                js = f.read()
            for call in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "import(", "http://", "https://"):
                self.assertNotIn(call, js, (name, call))
        with open(os.path.join(out, "assets", "site.css")) as f:
            css = f.read()
        self.assertIn("image-rendering: pixelated", css)
        self.assertIn("prefers-reduced-motion", css)
        new = css[css.index("/* ---- screenshots"):css.index("/* ---- the footer")]
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|oklch\(|font-family:(?!\s*var\()", new))


def cards(page):
    """the ids of the cards on All plugins, in the page's order"""
    return re.findall(r'<li class="pcard" data-id="([^"]+)"', page)


def embedded(page):
    """the index All plugins carries"""
    return json.loads(re.search(r'<script type="application/json" id="browse-data">(.*?)</script>', page, re.S)[1])


class Browse(unittest.TestCase):
    """All plugins (plugins/), its index, and the home page's list of the newest"""

    def setUp(self):
        self.out, self.pages, self.idx = Site.build(self)
        self.page = self.pages["plugins/index.html"]
        with open(os.path.join(self.out, "plugins", "index.json")) as f:
            self.index = json.load(f)
        config = registry.load_config(ROOT)
        self.entries, _ = build_site.site_entries(config)

    def test_every_plugin_has_a_card(self):
        ids = sorted((e["id"] for e in self.entries), key=lambda i: next(
            (e["name"].lower(), e["id"]) for e in self.entries if e["id"] == i))
        self.assertEqual(cards(self.page), ids)                     # A to Z, all of them, with or without script
        self.assertEqual([p["id"] for p in self.index["plugins"]], ids)
        for e in self.entries:
            # (the page's text has typographic apostrophes: Dragon’s Lair)
            self.assertIn(f'<a href="{e["id"]}/">{build_site.typeset(build_site.e_(e["name"]))}</a>', self.page)
        more = re.findall(r'<li class="pcard" data-id="([^"]+)" data-more>', self.page)
        self.assertEqual(more, ids[build_site.PER_PAGE:])           # held back until the script pages them
        self.assertIn('<script src="../assets/browse.js" defer></script>', self.page)
        self.assertIn(f'data-per-page="{build_site.PER_PAGE}"', self.page)
        self.assertIn('<a href="../plugins/" aria-current="page">Plugins</a>', self.page)

    def test_the_index(self):
        self.assertEqual(embedded(self.page), self.index)          # the page carries the published file
        self.assertEqual(self.index["format"], build_site.BROWSE_FORMAT)
        self.assertEqual(self.index["url"], "https://plasticbugs.github.io/parrot-cart-plugins/plugins/index.json")
        config = registry.load_config(ROOT)
        self.assertEqual(list(self.index["names"]["tags"]), config["tags"])
        self.assertEqual(self.index["names"]["works_with"]["midi-out"], "MIDI out to a computer")
        by = {p["id"]: p for p in self.index["plugins"]}
        lua = by["parrotcart.lua"]
        self.assertEqual(set(lua), {"id", "name", "by", "made_by", "description", "version", "published", "size",
                                    "icon", "opens", "standalone", "built_in", "tags", "works_with", "page"})
        self.assertEqual((lua["tags"], lua["works_with"], lua["opens"], lua["standalone"], lua["made_by"]),
                         (["programming"], ["keyboard"], [".lua"], True, "parrotcart"))
        self.assertEqual(lua["page"], "https://plasticbugs.github.io/parrot-cart-plugins/plugins/parrotcart.lua/")
        self.assertFalse(by["parrotcart.nes"]["standalone"])
        self.assertTrue(by["parrotcart.movies"]["built_in"])
        self.assertEqual(by["parrotcart.movies"]["description"], "Player for movies made with the movie converter")
        for e in self.entries:
            self.assertEqual(by[e["id"]]["published"], e["release"]["published"])

    def test_the_filters(self):
        facets = dict(re.findall(r'<fieldset class="facet[^"]*" data-facet="(\w+)"><legend>([^<]+)</legend>', self.page))
        self.assertEqual(facets, {"type": "Type", "works": "Works with", "opens": "Opens"})      # Made by: all ours
        boxes = re.findall(r'<input type="checkbox" name="(\w+)" value="([^"]+)">', self.page)
        types = [v for k, v in boxes if k == "type"]
        self.assertEqual(types, [t for t in registry.load_config(ROOT)["tags"]
                                 if any(t in e.get("tags", []) for e in self.entries)])
        opens = [v for k, v in boxes if k == "opens"]
        self.assertEqual(opens[0], "app")
        self.assertEqual(opens[1:], sorted({x for e in self.entries for x in e["opens"]}))
        self.assertIn('<span class="facet__name">Runs on its own</span>', self.page)
        # the file types fold away under Runs on its own, closed, and say how many there are
        opens_set = self.page.split('data-facet="opens"')[1].split("</fieldset>")[0]
        shown, fold = opens_set.split("<details")
        self.assertIn('value="app"', shown)
        self.assertEqual(re.findall(r'value="([^"]+)"', fold), opens[1:])
        self.assertTrue(fold.startswith(' class="facet__fold" data-fold><summary>'))      # no "open"
        self.assertIn(f'<span class="facet__more">File types ({len(opens) - 1})</span>', fold)
        self.assertIn('data-ticked="{count} ticked"', self.page)
        self.assertIn('<span class="facet__name">MIDI out to a computer</span><span class="facet__n">1</span>', self.page)
        # the words the script puts on the page keep their placeholders
        self.assertIn('data-count-page="{first} to {last} of {count} plugins"', self.page)
        self.assertIn('data-list="Plugins, page {page} of {pages}"', self.page)
        n = len(self.entries)
        self.assertIn(f'aria-live="polite" aria-atomic="true">1 to {build_site.PER_PAGE} of {n} plugins</p>', self.page)
        self.assertIn('<ul class="tags" aria-label="Type"><li>Consoles</li></ul>', self.page)

    def test_community_plugins_get_made_by(self):
        root = tmp()
        listed(root, owner="fixture-dev")
        e = registry.load_entries(root)["parrotcart.nes"]
        self.assertEqual(build_site.made_by(e, registry.load_config(root)), "community")
        self.assertEqual(build_site.made_by(dict(e, owner="PlasticBugs"), registry.load_config(root)), "parrotcart")

    def test_the_home_page_shows_the_newest(self):
        home = self.pages["index.html"]
        rows = re.findall(r'<a href="plugins/([^/]+)/">', home.split('id="catalogue"')[1].split("</table>")[0])
        want = [e["id"] for e in build_site.newest(self.entries)][:build_site.HOME_LATEST]
        self.assertEqual(rows, want)
        dates = [next(e for e in self.entries if e["id"] == i)["release"]["published"] for i in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertIn('<a class="btn" href="plugins/">Browse all available plugins</a>', home)
        self.assertIn('<a class="btn" href="#plugins">Browse plugins</a>', home)          # the hero's button
        self.assertNotIn("data-finder", home)
        for name, text in self.pages.items():           # the menu's Plugins is All plugins
            if name not in MOVED and name not in CONVERTER:
                self.assertIn(f'<a href="{"../" * name.count("/")}plugins/"', text, name)

    def test_an_entry_cant_break_out_of_the_index(self):
        root = tmp()
        listed(root, name="</script><b>x", description='</script><script>alert(1)</script>&amp;')
        out, pages, _ = Site.build(self, root)
        page = pages["plugins/index.html"]
        data = page.split('id="browse-data">')[1].split("</script>")[0]
        self.assertNotIn("<", data)
        self.assertEqual(embedded(page)["plugins"][0]["description"], '</script><script>alert(1)</script>&amp;')


class Copy(unittest.TestCase):
    """site/copy.toml holds every word the pages and the bot use"""
    CODE = ("tools/build_site.py", "tools/validate.py", "tools/ci/pr_text.py")

    def test_every_key_the_code_reads_is_there(self):
        used = set()
        for name in self.CODE:
            with open(os.path.join(ROOT, name)) as f:
                used |= set(re.findall(r'\bT\.\w+\(\s*"([a-z0-9_.]+)"', f.read()))
        # the tables that name registry.config.json's words are read whole (sitecopy.names)
        tables = set(sitecopy.NAMES.values())
        have = {next((t for t in tables if k.startswith(t + ".")), k) for k in sitecopy.COPY.keys()}
        used |= tables
        self.assertEqual(sorted(used - have), [], "read by the code but missing from site/copy.toml")
        self.assertEqual(sorted(have - used), [], "in site/copy.toml but nothing reads it")
        # a missing key stops the build, and says which
        data = copy.deepcopy(sitecopy.COPY.data())
        del data["home"]["hero"]["lead"]
        old, build_site.T = build_site.T, sitecopy.Copy(data=data)
        try:
            with self.assertRaises(sitecopy.CopyError) as cm:
                build_site.build(os.path.join(tmp(), "_site"))
        finally:
            build_site.T = old
        self.assertIn("home.hero.lead is missing", str(cm.exception))
        # so does a placeholder the line can't take, and a row without a field
        data = copy.deepcopy(sitecopy.COPY.data())
        data["home"]["files"]["before_text"] = "Three {extt} files"
        del data["home"]["install"]["steps"][1]["text"]
        t = sitecopy.Copy(data=data)
        with self.assertRaises(sitecopy.CopyError) as cm:
            t.html("home.files.before_text", ext="x", folder="y")
        self.assertIn("home.files.before_text uses {extt}", str(cm.exception))
        with self.assertRaises(sitecopy.CopyError) as cm:
            t.rows("home.install.steps", ("title", "text"))
        self.assertIn("home.install.steps (block 2).text is missing", str(cm.exception))

    def test_what_you_type_stays_text(self):
        t = sitecopy.Copy(data={"a": "Tom & Jerry <b>x</b> 'q' \"r\" `<i>` **B** [l](../x/?a=1&b=2) {n}",
                                "bad": "[x](javascript:void)", "odd": "[x](javascript:alert(1))"})
        self.assertEqual(t.html("a", n="<v>"),
                         "Tom &amp; Jerry &lt;b&gt;x&lt;/b&gt; 'q' \"r\" <code class=\"code\">&lt;i&gt;</code> "
                         "<b>B</b> <a class=\"link\" href=\"../x/?a=1&amp;b=2\">l</a> <v>")
        self.assertNotIn('"r"', t.attr("a", n=""))
        with self.assertRaises(sitecopy.CopyError):
            t.html("bad")
        self.assertNotIn("<a", t.html("odd"))


class Markdown(unittest.TestCase):
    BASE = "https://github.com/a/b/blob/v1/"

    def test_github_flavoured(self):
        out = markdown.render("# T\n\nA *b* **c** ~~d~~ `e<f>`.\n\n- [ ] one\n- [x] two\n\n1. x\n2. y\n\n"
                              "| a | b |\n|---|--:|\n| 1 | 2 |\n\n```js\n<b>&\n```\n\n> q\n\n---\n")
        for want in ("<h3>T</h3>", "<em>b</em>", "<strong>c</strong>", "<del>d</del>", "<code>e&lt;f&gt;</code>",
                     '<li class="task"><input type="checkbox" disabled> one</li>',
                     '<input type="checkbox" disabled checked> two', "<ol><li>x</li><li>y</li></ol>",
                     '<th class="ta-r">b</th>', '<td class="ta-r">2</td>',
                     "<pre><code>&lt;b&gt;&amp;</code></pre>", "<blockquote><p>q</p></blockquote>", "<hr>"):
            self.assertIn(want, out)

    def test_links(self):
        r = lambda s: markdown.render(s, self.BASE, anchor="https://github.com/a/b/blob/v1/README.md")
        self.assertIn('<a href="https://example.com/x?a=1&amp;b=2" rel="nofollow noopener">t</a>',
                      r("[t](https://example.com/x?a=1&b=2)"))
        self.assertIn('href="https://github.com/a/b/blob/v1/docs/x.md"', r("[t](docs/x.md)"))
        self.assertIn('href="https://github.com/a/b/blob/v1/README.md#use"', r("[t](#use)"))
        self.assertIn('href="https://example.com/r"', r("[t][ref]\n\n[ref]: https://example.com/r"))
        self.assertIn('<a href="https://example.com/a" rel="nofollow noopener">https://example.com/a</a>.',
                      r("See https://example.com/a."))
        self.assertIn('rel="nofollow noopener">Image: a badge</a>', r("![a badge](https://example.com/b.svg)"))
        self.assertNotIn("<img", r("![a](https://example.com/b.png) <img src=https://example.com/c.png>"))
        for bad in ("[t](javascript:alert(1))", "[t](JaVaScRiPt:alert(1))", "[t](data:text/html,x)",
                    "[t](http://example.com)", "[t](//example.com)", "[t](../../../../evil)", "[t](vbscript:x)",
                    "[t](https://x\"onmouseover=\"y)", "<javascript:alert(1)>", "[t]( java\tscript:x)"):
            with self.subTest(bad):
                self.assertNotIn("<a", r(bad).replace("<a href=\"https://github.com/a/b/", "<a ok"), bad)

    def test_only_its_own_tags_come_out(self):
        with open(os.path.join(ROOT, "tests", "data", "readme_sample.md")) as f:
            sample = f.read()
        evil = [
            sample,
            "<script>alert(1)</script><img src=x onerror=alert(1)><svg/onload=alert(1)>",
            "<a href=\"javascript:alert(1)\" onclick=\"x\">a</a> <iframe src=//e></iframe> <style>*{}</style>",
            "<scr<script>ipt>alert(1)</scr</script>ipt> <<b>b>", "<!-- <script> --> x <!-- unclosed <b>",
            "`<script>` and ```\n<script>alert(1)</script>\n```", "    <script>indented</script>",
            "[<img src=x>](https://e.com) ![<b>](https://e.com/\"><script>)", "| <td onclick=x> | b |\n|---|---|\n| <i> | 2 |",
            "- [x] <input onfocus=x autofocus>\n> <details open ontoggle=x>", "&lt;script&gt;alert(1)&lt;/script&gt;",
            "\x00<\x00script>\x000\x00 a\x001\x00b", "<p\nonclick=x>multi\nline</p\n>", "*a **b* c** _d __e_ f__",
            "[a](https://e.com '\"><script>')", "<https://e.com/\"onx=\"1>", "# <h1 onclick=x>t</h1>\n\n=====\n",
        ]
        for text in evil:
            out = markdown.render(text, self.BASE)
            for tag, attrs in Tags(out).seen:
                self.assertIn(tag, markdown.TAGS, (text, out))
                self.assertLessEqual(set(attrs), markdown.ATTRS.get(tag, set()), (text, out))
                if "href" in attrs:
                    self.assertTrue(attrs["href"].startswith("https://"), (text, out))
            self.assertNotIn("\x00", out)
            self.assertFalse(re.search(r"<(script|img|svg|iframe|style)\b", out), (text, out))

    def test_heading_levels_stay_under_the_pages(self):
        out = markdown.render("# a\n## b\n###### c\n\nd\n===\n", level=4)
        self.assertEqual(re.findall(r"<(h\d)>", out), ["h4", "h5", "h6", "h4"])

if __name__ == "__main__":
    unittest.main()
