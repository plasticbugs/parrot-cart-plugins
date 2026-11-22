"""build_dev -- the Parrot Cart developer portal: the docs, examples and tools
for making plugins, a site of its own beside the plugins site.

    python3 tools/build_dev.py [--kit PATH] [--out _site/developers]

The plugins site (tools/build_site.py) lists plugins for the people who use
them; the portal is for the people who make them. They share one Pages site
and one look, and nothing else: the portal's words are developers/copy.toml,
its pages are made here, and the plugins site only links to it.

The docs are the starter kit's own Markdown (plasticbugs/parrot-plugin-
template), so they're written once, where the code is. Pass the kit's
checkout as --kit; without it the build looks for kit/ in this repo (where
the Pages workflow checks it out) and then for a checkout beside this repo.
PAGES below says which kit file becomes which page.

Writes OUT/index.html, a page a doc (OUT/start/, OUT/hardware/, ...),
OUT/claude/ (the kit's Claude skill, and a zip of its folder made from the
kit's checkout), OUT/examples/, OUT/packaging/ (what a release needs: the
README, the screenshots and the icons), OUT/tools/ (the icon editor and the
ready-made icons) and OUT/assets/. The pages load the plugins site's assets/site.css
from one folder up, so build the plugins site first, into OUT's parent.
Standard library only; links are relative.
"""
import argparse
import html
import os
import re
import shutil
import io
import subprocess
import sys
import tomllib
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site  # noqa: E402  (the frame's shared parts, and the plugins the menu pictures show)
import cvp  # noqa: E402
import markdown  # noqa: E402
import png  # noqa: E402
import registry  # noqa: E402
import sitecopy  # noqa: E402
import tvscreen  # noqa: E402
from build_site import FONTS, doc_section, e_, li_rows, screen_card, spec_table, typeset  # noqa: E402

ROOT = registry.ROOT
DEV = os.path.join(ROOT, "developers")
T = sitecopy.Copy(path=os.path.join(DEV, "copy.toml"))
GALLERY = os.path.join(DEV, "icons.toml")
KIT_SHOT = "screenshots/screenshot-1.png"       # the kit's own plugin on the TV, the home page's picture

# The pages, in reading order. A doc page is a kit file; the rest are made here.
#   kit file                           page         group      its name (developers/copy.toml)
PAGES = (
    ("docs/getting-started.md",          "start",     "start",   "nav.start"),
    (None,                               "claude",    "start",   "nav.claude"),
    ("docs/hardware.md",                 "hardware",  "start",   "nav.hardware"),
    ("sdk/firmware/revc/sdk/README.md",  "sdk",       "build",   "nav.sdk"),
    ("docs/features.md",                 "features",  "build",   "nav.features"),
    (None,                               "examples",  "build",   "nav.examples"),
    ("docs/simulator.md",                "simulator", "build",   "nav.simulator"),
    ("docs/lua.md",                      "lua",       "build",   "nav.lua"),
    ("docs/testing.md",                  "testing",   "build",   "nav.testing"),
    ("docs/plugin-rules.md",             "rules",     "publish", "nav.rules"),
    (None,                               "packaging", "publish", "nav.packaging"),
    ("docs/release-checklist.md",        "release",   "publish", "nav.release"),
    (None,                               "tools",     "tools",   "nav.tools"),
)
OPTIONAL = {"docs/features.md", "docs/simulator.md", "docs/lua.md"}         # a kit without one of these just has no such page or link
GROUPS = ("start", "build", "publish", "tools")         # side.<group> names them
TOP_NAV = ("start", "hardware", "sdk", "examples", "tools")     # the header's menu, before Plugins
# kit docs the Packaging page covers: a link to one goes to its part there
COVERED = {"docs/readme-spec.md": "packaging/#readme", "docs/screenshots.md": "packaging/#screenshots",
           "docs/icons.md": "packaging/#icons"}
SKILL = ".claude/skills/parrot-cart-plugin"     # the kit's Claude skill: the claude/ page, if the kit has it
SKILL_ZIP = "parrot-cart-plugin.zip"            # its folder as a zip, beside that page
ZIP_TIME = (2026, 1, 1, 0, 0, 0)                # every file's date in the zip, so a build makes the same bytes


# ---- the starter kit --------------------------------------------------------------------

class Kit:
    """the starter kit's checkout, and where its files are on GitHub"""

    def __init__(self, path, repo):
        self.path, self.repo = path, repo
        self.home = f"https://github.com/{repo}"
        self.files = self._git_files()

    def _git_files(self):
        """what's in the kit's repo (tracked, or new and not ignored), with its folders: so a
        local build/ folder never becomes a link to GitHub. None outside git: then any file counts."""
        try:
            r = subprocess.run(["git", "-C", self.path, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        out = set()
        for name in r.stdout.decode("utf-8", "replace").split("\0"):
            while name:
                out.add(name)
                name = os.path.dirname(name)
        return out

    def has(self, rel):
        if self.files is not None and rel not in self.files:
            return False
        return os.path.exists(os.path.join(self.path, rel))

    def read(self, rel):
        with open(os.path.join(self.path, rel), encoding="utf-8") as f:
            return f.read()

    def url(self, rel):
        """a file (blob) or folder (tree) on GitHub, at main"""
        kind = "tree" if os.path.isdir(os.path.join(self.path, rel)) else "blob"
        return f"{self.home}/{kind}/main/{rel}".rstrip("/")


def find_kit(path=None):
    """--kit, else kit/ in this repo (the Pages workflow's checkout), else a checkout beside this repo"""
    if path:
        tries = [path]
    else:
        up = os.path.dirname(ROOT)
        tries = [os.path.join(ROOT, "kit"), os.path.join(up, "parrot-plugin-template"),
                 os.path.join(up, "parrotcart-plugin-template")]
    for t in tries:
        if os.path.isfile(os.path.join(t, "docs", "getting-started.md")):
            return os.path.abspath(t)
    raise SystemExit(f"error: no starter kit at {' or '.join(tries)}. Clone "
                     "https://github.com/plasticbugs/parrot-plugin-template and pass --kit PATH")


def present(kit):
    """the pages this kit makes: every page whose file it has; a missing optional doc drops out"""
    out = []
    for f, slug, group, label in PAGES:
        if slug == "claude" and not kit.has(f"{SKILL}/SKILL.md"):
            continue
        if f and not kit.has(f):
            if f in OPTIONAL:
                continue
            raise SystemExit(f"error: the starter kit at {kit.path} has no {f}")
        out.append((f, slug, group, label))
    return out


def portal_map(kit, pages):
    """kit path -> the portal page that shows it (from the portal's root)"""
    here = {f: f"{slug}/" for f, slug, _, _ in pages if f}
    here.update(COVERED)
    here["examples/README.md"] = here["examples"] = "examples/"
    if any(slug == "claude" for _, slug, _, _ in pages):
        here[SKILL] = "claude/"
    for name in example_names(kit):
        here["src" if name == "src" else f"examples/{name}"] = f"examples/#{name}"
    return here


# ---- a doc: the kit's Markdown as a page -------------------------------------------------

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def split_doc(text):
    """a doc's title (its first "# " line) and the rest, every heading a level up, so its
    "## " sections are the page's h2s; code blocks are left alone"""
    title, out, fence = None, [], None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
        elif m:
            fence = m.group(1)
        elif title is None and re.match(r"^ {0,3}# +\S", line):
            title = line.strip()[1:].strip().strip("#").strip()
            continue
        elif re.match(r"^ {0,3}#{2,6}([ \t]|$)", line):
            line = line.replace("#", "", 1)
        out.append(line)
    return (title or "").replace("`", ""), "\n".join(out)


def anchor_headings(body):
    """ids on the h2s and h3s (as GitHub makes them), and the h2s for the page's list"""
    seen, toc = set(), []

    def sub(m):
        level, inner = m.group(1), m.group(2)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner))
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "part"
        sid, n = base, 2
        while sid in seen:
            sid, n = f"{base}-{n}", n + 1
        seen.add(sid)
        if level == "2":
            toc.append((sid, re.sub(r"</?a\b[^>]*>", "", inner)))
        return f'<h{level} id="{sid}">{inner}</h{level}>'
    return re.sub(r"<h([23])>(.*?)</h\1>", sub, body), toc


def kit_path(kit, text, docdir):
    """a code span that names a file or folder in the kit: its path from the kit's root, or None"""
    if not re.fullmatch(r"(?:\.{1,2}/)*[\w.-]+(?:/[\w.-]+)+/?|[\w.-]+/", text):
        return None
    for base in ((docdir, "") if docdir else ("",)):
        rel = os.path.normpath(os.path.join(base, text))
        if not rel.startswith("..") and not os.path.isabs(rel) and kit.has(rel):
            return rel
    return None


def link_kit(body, kit, here, docdir, pre):
    """links to the kit's own files go to their pages here when the portal has one: the
    Markdown's links (made absolute on GitHub by markdown.render), and code spans that name
    a file, which become links to it"""
    blob = re.escape(kit.home) + r"/(?:blob|tree)/main/([^\"#]*)(#[^\"]*)?"

    def href(m):
        rel, frag = html.unescape(m.group(1)).rstrip("/"), m.group(2) or ""
        if rel in here:
            to = pre + here[rel]
            return f'href="{e_(to if "#" in to else to + html.unescape(frag))}"'
        return m.group(0)
    body = re.sub(r'href="' + blob + '"', href, body)
    body = re.sub(r'(<a href="(?!https://)[^"]*") rel="nofollow noopener"', r"\1", body)    # ours, not another site's
    parts, out, i, depth = re.split(r"(<[^>]*>)", body), [], 0, 0
    while i < len(parts):
        p = parts[i]
        if re.match(r"<(a|pre)\b", p):
            depth += 1
        elif re.match(r"</(a|pre)>", p):
            depth -= 1
        elif p == "<code>" and not depth and i + 2 < len(parts) and parts[i + 2] == "</code>":
            rel = kit_path(kit, html.unescape(parts[i + 1]), docdir)
            if rel:
                to = pre + here[rel] if rel in here else kit.url(rel)
                out += [f'<a href="{e_(to)}">', p, parts[i + 1], "</code>", "</a>"]
                i += 3
                continue
        out.append(p)
        i += 1
    return "".join(out)


def curl_quotes(body):
    """typographic double quotes in a doc's text, never inside code (typeset() does the apostrophes)"""
    out, skip, last = [], 0, " "
    for part in re.split(r"(<[^>]*>)", body):
        if part.startswith("<"):
            m = re.match(r"<(/?)(pre|code)\b", part)
            if m:
                skip += -1 if m.group(1) else 1
                last = "x"
        elif part:
            if not skip:
                bits = re.split(r'&quot;|"', part)
                text = bits[0]
                for bit in bits[1:]:
                    before = (text or last)[-1:]
                    text += ("\u201c" if before in " \n([—–-" else "\u201d") + bit
                part = text
            last = html.unescape(part)[-1:] or last
        out.append(part)
    return "".join(out)


def render_doc(kit, rel, here, pre, text=None):
    """(title, body html, its h2s) for a kit Markdown file"""
    title, md = split_doc(kit.read(rel) if text is None else text)
    docdir = os.path.dirname(rel)
    base = f"{kit.home}/blob/main/{docdir + '/' if docdir else ''}"
    body = markdown.render(md, base, level=2, anchor="./")
    body = curl_quotes(link_kit(body, kit, here, docdir, pre))
    body, toc = anchor_headings(body)
    return title, body, toc


# ---- the frame of every page --------------------------------------------------------------

def slab(pre, current, config):
    site = pre + "../"

    def link(href, text, key=None):
        cur = ' aria-current="page"' if key == current else ""
        return f'<li><a href="{href}"{cur}>{text}</a></li>'
    return (f'<header class="slab"><div class="container">'
            f'<a class="wordmark" href="{pre}index.html" aria-label="{T.attr("header.home_label")}" '
            f'><img src="{site}assets/parrot-cart-mark.svg" width="24" height="28" alt="">{T.html("header.wordmark")}</a>'
            f'<nav aria-label="{T.attr("header.nav_label")}"><ul>'
            + "".join(link(f"{pre}{slug}/", T.html(f"nav.{slug}"), slug) for slug in TOP_NAV)
            + link(f"{site}index.html", T.html("header.nav_plugins"))
            + "</ul></nav>" + build_site.shop_link(config, "slab__shop", T.html("header.shop")) + "</div></header>")


def footer(pre, pages, config, kit):
    site = pre + "../"
    cols = []
    for g in GROUPS:
        items = "".join(f'<li><a href="{pre}{slug}/">{T.html(label)}</a></li>'
                        for _, slug, group, label in pages if group == g)
        cols.append(f'<div><h2>{T.html(f"side.{g}")}</h2><ul>{items}</ul></div>')
    shop = build_site.shop_link(config, "link", T.html("footer.shop"))
    return f"""<footer class="foot"><div class="container">
<div class="cols dev-cols">
<div><h2>{T.html("footer.title")}</h2><p>{T.html("footer.tagline")}</p>{f'<p class="foot__shop">{shop}</p>' if shop else ""}</div>
{"".join(cols)}
<div><h2>{T.html("footer.links_heading")}</h2><ul><li><a href="{e_(kit.home)}">{T.html("footer.kit")}</a></li>
<li><a href="{site}index.html">{T.html("footer.plugins")}</a></li><li><a href="{site}submit/">{T.html("footer.submit")}</a></li></ul></div>
</div>
<p class="fine">{T.html("footer.font_credit", _link=None)}</p>
<p class="fine">{T.html("footer.trademarks", _link=None)}</p>
</div></footer>"""


def page(title, description, body, pre, current, ctx, screens=(), scripts=()):
    site = pre + "../"
    return typeset(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e_(title)}</title>
<meta name="description" content="{e_(description)}">
<script>document.documentElement.classList.add('js');</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{site}assets/site.css">
<link rel="stylesheet" href="{pre}assets/dev.css">
<link rel="icon" href="{site}assets/parrot-cart-icon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">{T.html("header.skip")}</a>
{tvscreen.glyph_defs(screens)}
{slab(pre, current, ctx["config"])}
<main id="main">
{body}
</main>
{footer(pre, ctx["pages"], ctx["config"], ctx["kit"])}
<script src="{pre}assets/dev.js" defer></script>
{"".join(f'<script src="{pre}assets/{n}" defer></script>' + chr(10) for n in scripts)}</body>
</html>
""")


def side(pre, pages, current, toc):
    """the list of every page beside a doc, grouped, with the open page's sections under it"""
    groups = []
    for g in GROUPS:
        items = []
        for _, slug, group, label in pages:
            if group != g:
                continue
            if slug == current:
                sub = "".join(f'<li><a href="#{sid}">{inner}</a></li>' for sid, inner in toc)
                sub = f'<ul class="side__toc" aria-label="{T.attr("side.this_page")}">{sub}</ul>' if sub else ""
                items.append(f'<li><a href="{pre}{slug}/" aria-current="page">{T.html(label)}</a>{sub}</li>')
            else:
                items.append(f'<li><a href="{pre}{slug}/">{T.html(label)}</a></li>')
        groups.append(f'<div class="side__group"><p class="side__head">{T.html(f"side.{g}")}</p><ul>{"".join(items)}</ul></div>')
    return (f'<nav class="side" aria-label="{T.attr("side.label")}"><details class="side__fold" open data-fold>'
            f'<summary>{T.html("side.toggle")}</summary>{"".join(groups)}</details></nav>')


def pager(pre, pages, slug):
    """Previous and Next, in reading order"""
    slugs = [p[1] for p in pages]
    i = slugs.index(slug)
    out = []
    for j, cls, word in ((i - 1, "pager__prev", T.html("doc.previous")), (i + 1, "pager__next", T.html("doc.next"))):
        if 0 <= j < len(pages):
            out.append(f'<a class="{cls}" href="{pre}{pages[j][1]}/"><span>{word}</span>'
                       f'<b>{T.html(pages[j][3])}</b></a>')
        else:
            out.append("<span></span>")
    return f'<nav class="pager" aria-label="{T.attr("doc.pager_label")}">{"".join(out)}</nav>'


def source_line(kit, rel):
    link = f'<a class="link" href="{e_(kit.url(rel))}"><code class="code">{e_(rel)}</code></a>'
    return f'<p class="doc__source">{T.html("doc.source", file=link)}</p>'


def doc_layout(pre, ctx, slug, title_html, body, toc, rel, intro=""):
    return f"""<div class="container docs">
{side(pre, ctx["pages"], slug, toc)}
<article class="doc" aria-labelledby="hero-title">
<h1 id="hero-title">{title_html}</h1>
{intro}<div class="prose doc__body">
{body}
</div>
{source_line(ctx["kit"], rel)}
{pager(pre, ctx["pages"], slug)}
</article>
</div>"""


def doc_page(ctx, rel, slug, label):
    kit, pre = ctx["kit"], "../"
    title, body, toc = render_doc(kit, rel, ctx["here"], pre)
    title = title or T.text(label)
    intro = ""
    if slug == "sdk":
        intro = f'<p class="warn doc__note">{T.html("doc.sdk_note")}</p>\n'
    elif slug == "start" and any(p[1] == "claude" for p in ctx["pages"]):
        intro = f'<p class="docnote doc__note">{T.html("doc.start_claude", claude_page="../claude/")}</p>\n'
    first = re.search(r"<p>(.*?)</p>", body, re.S)
    desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", first.group(1)))).strip() if first else title
    return page(f"{title}: {T.text('header.wordmark')}", desc[:300],
                doc_layout(pre, ctx, slug, e_(title), body, toc, rel, intro), pre, slug, ctx)


# ---- the home page ----------------------------------------------------------------------

def kit_shot(alt, caption, code, cls=""):
    """the kit's own plugin on the TV, a TV pixel two screen pixels on a big screen"""
    return (f'<figure class="card shot {cls}"><div class="shot__tv"><img src="assets/kit-screenshot.png" '
            f'width="{png.WIDTH}" height="{png.HEIGHT}" alt="{alt}"></div><figcaption><span>{caption}</span>'
            f'<code class="code">{e_(code)}</code></figcaption></figure>')


def home(ctx):
    kit, pages = ctx["kit"], ctx["pages"]
    card = ""
    if kit.has(KIT_SHOT):
        card = kit_shot(T.attr("home.hero.card_alt"), T.html("home.hero.card_caption"), T.text("home.hero.card_code"),
                        "shot--home")
    groups = []
    for g in GROUPS:
        items = "".join(f'<li><a href="{slug}/"><span class="group__name">{T.html(label)}</span>'
                        f'<span class="group__text">{T.html(f"map.{slug}")}</span></a></li>'
                        for _, slug, group, label in pages if group == g)
        groups.append(f'<div class="group"><h3>{T.html(f"side.{g}")}</h3><ul class="group__pages">{items}</ul></div>')
    claude = " " + T.html("home.map.claude") if any(p[1] == "claude" for p in pages) else ""
    body = f"""<section class="hero dev-hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{build_site.keep_together(T.html("home.hero.title"))}</h1>
<p class="lead">{T.html("home.hero.lead")}</p>
<div class="actions"><a class="btn" href="{e_(kit.home)}">{T.html("home.hero.kit_button")}</a><a class="btn btn--secondary" href="start/">{T.html("home.hero.start_button")}</a></div>
</div>
{card}
</div></section>
<section class="section" id="docs" aria-labelledby="docs-title"><div class="container">
<div class="headblock"><h2 id="docs-title">{T.html("home.map.title")}</h2><p class="lead">{T.html("home.map.lead")}{claude}</p></div>
<div class="groups">{"".join(groups)}</div>
</div></section>
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("home.close.title")}</h2><p>{T.html("home.close.text")}</p></div>
<div class="actions"><a class="btn" href="../submit/">{T.html("home.close.submit_button")}</a><a class="btn btn--secondary" href="../plugins/">{T.html("home.close.plugins_button")}</a></div>
</div></section>"""
    return page(T.text("home.page_title"), T.text("home.description"), body, "", "home", ctx)


# ---- the Claude skill ---------------------------------------------------------------------

def skill_files(kit):
    """the skill folder's files in the kit (tracked ones, as Kit.has counts them), by path from it"""
    base = os.path.join(kit.path, SKILL)
    out = []
    for d, dirs, files in os.walk(base):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/")
            if not f.startswith(".") and kit.has(f"{SKILL}/{rel}"):
                out.append(rel)
    return out


def skill_zip(kit):
    """the skill's folder as a zip, for Claude apps that take a skill that way: the same bytes
    from the same files (fixed dates and modes, the files in order)"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in skill_files(kit):
            path = os.path.join(kit.path, SKILL, rel)
            info = zipfile.ZipInfo(f"{os.path.basename(SKILL)}/{rel}", ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if os.access(path, os.X_OK) else 0o100644) << 16
            with open(path, "rb") as f:
                z.writestr(info, f.read())
    return buf.getvalue()


def claude_page(ctx):
    kit, pre, here = ctx["kit"], "../", ctx["here"]
    have = set(skill_files(kit))
    rows = "".join(
        f'<tr><td><a href="{e_(kit.url(f"{SKILL}/{path}"))}"><code>{e_(path)}</code></a></td><td>{text}</td></tr>'
        for path, text in T.rows("claude.files", ("path", "text")) if html.unescape(path) in have)
    table = (f'<table><thead><tr><th>{T.html("claude.files_columns.file")}</th><th>{T.html("claude.files_columns.what")}</th>'
             f'</tr></thead><tbody>{rows}</tbody></table>')
    download = (f'<div class="actions"><a class="btn" href="{SKILL_ZIP}" download>'
                f'{T.html("claude.download_button", file=SKILL_ZIP)}</a></div>')
    body = f"""<h2>{T.html("claude.use.title")}</h2>
<p>{T.html("claude.use.text")}</p>
<p>{T.html("claude.use.more")}</p>
<h2>{T.html("claude.have.title")}</h2>
<p>{T.html("claude.have.text")}</p>
<h2>{T.html("claude.files_title")}</h2>
{table}
<h2>{T.html("claude.elsewhere.title")}</h2>
<p>{T.html("claude.elsewhere.text")}</p>
{download}"""
    body = curl_quotes(link_kit(body, kit, here, "", pre))
    body, toc = anchor_headings(body)
    folder = f'<a class="link" href="{e_(kit.url(SKILL))}"><code class="code">{e_(SKILL)}</code></a>'
    html_ = f"""<div class="container docs">
{side(pre, ctx["pages"], "claude", toc)}
<article class="doc" aria-labelledby="hero-title">
<h1 id="hero-title">{T.html("claude.title")}</h1>
<p class="lead doc__lead">{T.html("claude.lead")}</p>
<div class="prose doc__body">
{body}
</div>
<p class="doc__source">{T.html("claude.source", folder=folder)}</p>
{pager(pre, ctx["pages"], "claude")}
</article>
</div>"""
    return page(T.text("claude.page_title"), T.text("claude.description"), html_, pre, "claude", ctx)


# ---- the examples ------------------------------------------------------------------------

def example_names(kit):
    """the kit's examples in the order examples/README.md lists them (src, the template's own
    plugin, first), then any others it has"""
    d = os.path.join(kit.path, "examples")
    have = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, "README.md"))) \
        if os.path.isdir(d) else []
    order = []
    if kit.has("examples/README.md"):
        for m in re.finditer(r"^\|\s*`([\w./-]+)`\s*\|", kit.read("examples/README.md"), re.M):
            name = "src" if m.group(1) == "../src" else m.group(1)
            if (name == "src" and kit.has("src/main.c")) or name in have:
                order.append(name)
    return order + [n for n in have if n not in order]


def icon_hex(rows, where):
    """eight lines of # and . (an icon's .txt, as the SDK reads it) as the header's hex"""
    rows = [r.strip() for r in rows if r.strip()]
    if len(rows) != 8 or any(len(r) != 8 or set(r) - set("#.") for r in rows):
        raise SystemExit(f"{where}: an icon is eight lines of eight # or .")
    return "".join(f"{int(r.replace('#', '1').replace('.', '0'), 2):02x}" for r in rows)


def first_paragraph(md):
    """the first paragraph of a README, under its title"""
    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if b and not b.startswith(("#", "|", "```", "-", "*", ">")):
            return b
    return ""


def examples_page(ctx):
    kit, pre, here = ctx["kit"], "../", ctx["here"]
    cards = []
    for name in example_names(kit):
        folder = "src" if name == "src" else f"examples/{name}"
        readme = "README.md" if name == "src" else f"{folder}/README.md"
        title, md = split_doc(kit.read(readme))
        title = title or name
        icon = f"{folder}/icon.txt"
        hx = icon_hex(kit.read(icon).split("\n"), icon) if kit.has(icon) else "00" * 8
        para = markdown.render(first_paragraph(md), f"{kit.home}/blob/main/{folder}/", level=3)
        para = curl_quotes(link_kit(para, kit, here, folder, pre))
        cards.append(
            f'<li class="ex" id="{e_(name)}">{tvscreen.icon_svg(hx, "m")}<div class="ex__text">'
            f'<h2 class="ex__title">{e_(title)}</h2><p class="ex__dir"><code class="code">{e_(folder)}</code></p>'
            f'<div class="ex__about">{para}</div>'
            f'<p><a class="link" href="{e_(kit.url(folder))}" aria-label="{T.attr("examples.source_label", name=title)}">'
            f'{T.html("examples.source")}</a></p></div></li>')
    notes, toc = "", []
    if kit.has("examples/README.md"):
        text = kit.read("examples/README.md")
        cut = re.search(r"^\|.*\n(?!\|)", text, re.M)        # the notes start after the list's table
        rest = text[cut.end():] if cut else text.split("\n", 1)[-1]
        _, body, toc = render_doc(kit, "examples/README.md", here, pre, "# x\n\n## " + T.text("examples.notes_title") + "\n" + rest)
        notes = f'<div class="prose doc__body ex__notes">{body}</div>'
    cards_html = f'<ul class="examples">{"".join(cards)}</ul>'
    body = f"""<div class="container docs">
{side(pre, ctx["pages"], "examples", toc)}
<article class="doc" aria-labelledby="hero-title">
<h1 id="hero-title">{T.html("examples.title")}</h1>
<p class="lead doc__lead">{T.html("examples.lead")}</p>
{cards_html}
{notes}
{source_line(kit, "examples/README.md") if kit.has("examples/README.md") else ""}
{pager(pre, ctx["pages"], "examples")}
</article>
</div>"""
    return page(T.text("examples.page_title"), T.text("examples.description"), body, pre, "examples", ctx)


# ---- Packaging: what a release needs, the README, screenshots and icons -------------------

def template_link(ctx):
    return f'<a class="link" href="{e_(ctx["kit"].home)}">{T.html("packaging.starter_kit")}</a>'


def in_kit(ctx, rel):
    """the line under a part naming the kit's own copy of it, if the kit has one"""
    kit = ctx["kit"]
    if not kit.has(rel):
        return ""
    link = f'<a class="link" href="{e_(kit.url(rel))}"><code class="code">{e_(rel)}</code></a>'
    return f'<p class="part__top">{T.html("packaging.in_kit", file=link)}</p>'


def part(sid, num, title, lead, card, actions="", extra=""):
    """one numbered part of the Packaging page, with its picture; its sections (h3) follow it"""
    actions = f'<div class="actions">{actions}</div>' if actions else ""
    return f"""<section class="part" id="{sid}" aria-labelledby="{sid}-title"><div class="container">
<div class="part__text">
<p class="part__num" aria-hidden="true">{num}</p>
<h2 id="{sid}-title">{title}</h2>
<p class="lead">{lead}</p>
{actions}{extra}<p class="part__top"><a class="link" href="#hero-title">{T.html("packaging.back_to_top")}</a></p>
</div>
{card}
</div></section>"""


def check_band(ctx):
    repo = f'https://github.com/{ctx["config"]["registry_repo"]}'
    return f"""<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("packaging.check.title")}</h2><p>{T.html("packaging.check.text", registry=e_(repo))}</p></div>
<pre class="cmd"><code>{T.block("packaging.check.command")}</code></pre>
</div></section>"""


def readme_part(ctx):
    import cvreadme
    cart = cvreadme.convert(T.raw("packaging.readme.hero.sample"))
    screen = tvscreen.readme_page("Star Sweeper", cart)
    card = screen_card(screen, T.html("packaging.readme.hero.card_caption"), T.text("packaging.readme.hero.card_code"))
    body = f"""{part("readme", 1, T.html("packaging.readme.hero.title"), T.html("packaging.readme.hero.lead"), card,
                 extra=in_kit(ctx, "docs/readme-spec.md"))}
{doc_section("readme-write", T.html("packaging.readme.write.title"), T.html("packaging.readme.write.lead"),
             '<ul class="rows">' + li_rows(T.rows("packaging.readme.write.rows", ("title", "text"))) + '</ul>', 3)}
{doc_section("readme-cart", T.html("packaging.readme.convert.title"), T.html("packaging.readme.convert.lead"),
             spec_table(T.list("packaging.readme.convert.columns"),
                        T.rows("packaging.readme.convert.rows", ("markdown", "cart")))
             + f'<pre class="cmd"><code>{T.block("packaging.readme.convert.command")}</code></pre>'
             + f'<p class="docnote">{T.html("packaging.readme.convert.note", starter_kit=template_link(ctx))}</p>', 3)}
{doc_section("readme-format", T.html("packaging.readme.format.title"), T.html("packaging.readme.format.lead"),
             spec_table(T.list("packaging.readme.format.columns"),
                        T.rows("packaging.readme.format.rows", ("where", "type", "what"))), 3)}
{doc_section("readme-checks", T.html("packaging.readme.checks.title"), T.html("packaging.readme.checks.lead"),
             spec_table(T.list("packaging.readme.checks.columns"),
                        T.rows("packaging.readme.checks.rows", ("check", "rule", "result"))), 3)}
{doc_section("readme-web", T.html("packaging.readme.web.title"), T.html("packaging.readme.web.lead"),
             spec_table(T.list("packaging.readme.web.columns"), T.rows("packaging.readme.web.rows", ("part", "what"))), 3)}"""
    return body, [screen]


def screenshots_part(ctx):
    screens = []
    if ctx["kit"].has(KIT_SHOT):
        card = (f'<figure class="card shot shot--hero"><div class="shot__tv"><img src="../assets/kit-screenshot.png" '
                f'width="{png.WIDTH}" height="{png.HEIGHT}" alt="{T.attr("packaging.screenshots.hero.card_alt", name="Hello")}">'
                f'</div><figcaption><span>{T.html("packaging.screenshots.hero.card_caption")}</span>'
                f'<code class="code">{png.WIDTH} × {png.HEIGHT}</code></figcaption></figure>')
    else:
        screen = tvscreen.plugins_page(ctx["entries"])
        screens.append(screen)
        card = screen_card(screen, T.html("packaging.screenshots.hero.fallback_caption"),
                           T.text("packaging.screenshots.hero.fallback_code"))
    sizes = dict(width=png.WIDTH, height=png.HEIGHT, max_kb=png.MAX_BYTES // 1024)
    body = f"""{part("screenshots", 2, T.html("packaging.screenshots.hero.title"), T.html("packaging.screenshots.hero.lead"),
                 card, extra=in_kit(ctx, "docs/screenshots.md"))}
{doc_section("shots-spec", T.html("packaging.screenshots.spec.title"), T.html("packaging.screenshots.spec.lead"),
             spec_table(T.list("packaging.screenshots.spec.columns"),
                        T.rows("packaging.screenshots.spec.rows", ("name", "rule"), **sizes)), 3)}
{doc_section("shots-show", T.html("packaging.screenshots.show.title"), None,
             '<ul class="rows">' + li_rows(T.rows("packaging.screenshots.show.rows", ("title", "text"))) + '</ul>', 3)}
{doc_section("shots-taking", T.html("packaging.screenshots.taking.title"), T.html("packaging.screenshots.taking.lead"),
             '<ul class="rows">' + li_rows(T.rows("packaging.screenshots.taking.rows", ("title", "text"))) + '</ul>', 3)}
{doc_section("shots-refused", T.html("packaging.screenshots.refused.title"), T.html("packaging.screenshots.refused.lead"),
             spec_table(T.list("packaging.screenshots.refused.columns"),
                        T.rows("packaging.screenshots.refused.rows", ("what", "example"))), 3)}
{doc_section("shots-used", T.html("packaging.screenshots.used.title"), T.html("packaging.screenshots.used.lead"),
             spec_table(T.list("packaging.screenshots.used.columns"),
                        T.rows("packaging.screenshots.used.rows", ("place", "how"))), 3)}"""
    return body, screens


def big_icon(hexstr, colour, label, caption):
    """label is plain text (tvscreen escapes it), caption html"""
    return (f'<figure class="iconfig">{tvscreen.icon_svg(hexstr, colour, label)}'
            f"<figcaption>{caption}</figcaption></figure>")


PAD_ICON = "3c4299819999423c"       # the Pad Test plugin's: firmware/revc/padtest/padtest_icon.txt
BLANK_ICON = ('<svg class="tv-icon" viewBox="-2 -2 12 12" role="img" aria-label="{label}" shape-rendering="crispEdges">'
              '<rect class="tv-bg" x="-2" y="-2" width="12" height="12"/>'
              '<path class="tv-grid" d="M0 0h8v8h-8z"/></svg>')


def icon_txt(hexstr):
    """an icon as the .txt file the SDK reads"""
    return "\n".join(cvp.icon_rows(hexstr)) + "\n"


def starter_files():
    """the files the Icons part offers: name, hex, colour"""
    icons = tvscreen.MENU["icons"]
    return [("icon-template.txt", "00" * 8, "m"),
            ("sample-icon.txt", PAD_ICON, "m"),
            ("sample-file-icon.txt", icons["file"], "g")]


def icons_part(ctx):
    icons = tvscreen.MENU["icons"]
    entries = ctx["entries"]
    with_icons = [e for e in entries if e["icon"] != "00" * 8] or entries
    screen = tvscreen.plugins_page(with_icons)
    card = screen_card(screen, T.html("packaging.icons.hero.card_caption"), T.text("packaging.icons.hero.card_code"))
    rows = cvp.icon_rows(PAD_ICON)
    txt = "\n".join(rows)
    hexs = " ".join(PAD_ICON[i:i + 2] for i in range(0, 16, 2))
    family = "".join([
        big_icon(icons["folder"], "y", T.text("packaging.icons.family.folder_label"),
                 T.html("packaging.icons.family.folder_caption")),
        big_icon(icons["cart"], "c", T.text("packaging.icons.family.rom_label"),
                 T.html("packaging.icons.family.rom_caption")),
        big_icon(icons["file"], "g", T.text("packaging.icons.family.file_label"),
                 T.html("packaging.icons.family.file_caption")),
        big_icon(icons["plugin"], "m", T.text("packaging.icons.family.plug_label"),
                 T.html("packaging.icons.family.plug_caption")),
        big_icon(PAD_ICON, "m", T.text("packaging.icons.family.padtest_label"),
                 T.html("packaging.icons.family.padtest_caption")),
    ])
    (tname, _, _), (sname, shex, _), (fname, fhex, _) = starter_files()
    dl = lambda name: (f'<a class="btn btn--secondary" href="files/{name}" download>'  # noqa: E731
                       f'{T.html("packaging.icons.files.download", file=name)}</a>')
    starters = (
        f'<figure class="iconfig">{BLANK_ICON.format(label=T.attr("packaging.icons.files.template_label"))}'
        f'<figcaption><b>{T.html("packaging.icons.files.template_title")}</b> {T.html("packaging.icons.files.template_text")}'
        f'</figcaption>{dl(tname)}</figure>'
        f'<figure class="iconfig">{tvscreen.icon_svg(shex, "m", T.text("packaging.icons.files.sample_label"))}'
        f'<figcaption><b>{T.html("packaging.icons.files.sample_title")}</b> {T.html("packaging.icons.files.sample_text")}'
        f'</figcaption>{dl(sname)}</figure>'
        f'<figure class="iconfig">{tvscreen.icon_svg(fhex, "g", T.text("packaging.icons.files.file_sample_label"))}'
        f'<figcaption><b>{T.html("packaging.icons.files.file_sample_title")}</b> '
        f'{T.html("packaging.icons.files.file_sample_text")}</figcaption>{dl(fname)}</figure>')
    actions = (f'<a class="btn" href="../tools/#icon-editor">{T.html("packaging.icons.hero.editor_button")}</a>'
               f'<a class="btn btn--secondary" href="../tools/#gallery">{T.html("packaging.icons.hero.gallery_button")}</a>')
    body = f"""{part("icons", 3, T.html("packaging.icons.hero.title"), T.html("packaging.icons.hero.lead"), card, actions,
                 in_kit(ctx, "docs/icons.md"))}
{doc_section("icons-spec", T.html("packaging.icons.spec.title"), T.html("packaging.icons.spec.lead"),
             spec_table(T.list("packaging.icons.spec.columns"), T.rows("packaging.icons.spec.rows", ("name", "rule"))), 3)}
{doc_section("icons-files", T.html("packaging.icons.files.title"), T.html("packaging.icons.files.lead", gallery="../tools/#gallery"),
             f'<div class="iconrow iconrow--files">{starters}</div>', 3)}
{doc_section("icons-txt", T.html("packaging.icons.txt.title"), T.html("packaging.icons.txt.lead"),
             f'<div class="pair"><div><h4>{T.html("packaging.icons.txt.file_title")}</h4>'
             f'<pre class="cmd"><code>{txt}</code></pre></div>'
             f'<div><h4>{T.html("packaging.icons.txt.header_title")}</h4><pre class="cmd"><code>{hexs}</code></pre>'
             f'<p class="docnote">{T.html("packaging.icons.txt.note")}</p></div></div>'
             f'<pre class="cmd"><code>{T.block("packaging.icons.txt.command")}</code></pre>', 3)}
{doc_section("icons-design", T.html("packaging.icons.design.title"), T.html("packaging.icons.design.lead"),
             f'<div class="iconrow">{family}</div>'
             '<ul class="rows">' + li_rows(T.rows("packaging.icons.design.rows", ("title", "text"))) + '</ul>', 3)}"""
    return body, [screen]


def packaging_page(ctx):
    needs = T.rows("packaging.needs.rows", ("part", "status", "text"), readme_page="#readme",
                   screenshots_page="#screenshots", icons_page="#icons")
    cards = [
        ("#readme", T.html("packaging.pages.readme_title"), T.html("packaging.pages.readme_text")),
        ("#screenshots", T.html("packaging.pages.screenshots_title"), T.html("packaging.pages.screenshots_text")),
        ("#icons", T.html("packaging.pages.icons_title"), T.html("packaging.pages.icons_text")),
        ("../tools/", T.html("packaging.pages.tools_title"), T.html("packaging.pages.tools_text")),
    ]
    tiles = "".join(f'<li><h2><a href="{h}">{t}</a></h2><p>{d}</p></li>' for h, t, d in cards)
    hardware = f'<a class="link" href="../hardware/">{T.html("packaging.hardware_link")}</a>'
    readme, s1 = readme_part(ctx)
    shots, s2 = screenshots_part(ctx)
    icons, s3 = icons_part(ctx)
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("packaging.hero.title")}</h1>
<p class="lead">{T.html("packaging.hero.lead")}</p>
<div class="actions"><a class="btn" href="../../submit/">{T.html("packaging.hero.submit_button")}</a><a class="btn btn--secondary" href="../tools/">{T.html("packaging.hero.tools_button")}</a></div>
<p class="soon">{T.html("packaging.hero.starter_note", starter_kit=template_link(ctx), hardware=hardware)}</p>
</div>
<nav aria-label="{T.attr("packaging.pages.label")}"><ol class="map map--links">{tiles}</ol></nav>
</div></section>
{doc_section("needs", T.html("packaging.needs.title"), T.html("packaging.needs.lead"),
             spec_table(T.list("packaging.needs.columns"), needs))}
{readme}
{shots}
{icons}
<div class="container">{pager("../", ctx["pages"], "packaging")}</div>
{check_band(ctx)}"""
    return page(T.text("packaging.page_title"), T.text("packaging.description"), body, "../", "packaging",
                ctx, s1 + s2 + s3)


# ---- Tools: the icon editor and the ready-made icons --------------------------------------

def pad(kind, title, title_attr, note, colour, name):
    """an icon's drawing grid and tools; title and note are html, title_attr the title for attributes"""
    cells = "".join(
        f'<button type="button" class="px__c" aria-pressed="false" '
        f'aria-label="{T.attr("editor.cell_label", row=y + 1, column=x + 1)}" '
        f'data-x="{x}" data-y="{y}"{"" if x == y == 0 else " tabindex=-1"}></button>'
        for y in range(8) for x in range(8))
    arrow = ('<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"{turn}>'
             '<path d="M2 8h11M9 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.75"/></svg>')
    moves = "".join(
        f'<button type="button" class="tool" data-do="{d}" aria-label="{label}">{arrow.format(turn=turn)}</button>'
        for d, label, turn in (("left", T.attr("editor.move_left"), ' transform="rotate(180)"'),
                               ("right", T.attr("editor.move_right"), ""),
                               ("up", T.attr("editor.move_up"), ' transform="rotate(-90)"'),
                               ("down", T.attr("editor.move_down"), ' transform="rotate(90)"')))
    return f"""<fieldset class="pad" data-pad="{kind}">
<legend><b>{title}</b> <span>{note}</span></legend>
<div class="px px--{colour}" role="group" aria-label="{T.attr("editor.grid_label", icon=title_attr)}" aria-describedby="keys">{cells}</div>
<div class="pad__tools" role="group" aria-label="{T.attr("editor.tools_label")}">
<button type="button" class="tool" data-do="clear">{T.html("editor.clear")}</button>
<button type="button" class="tool" data-do="invert">{T.html("editor.invert")}</button>
{moves}
</div>
<label class="field">{T.html("editor.hex_label")}<input class="code" type="text" data-hex value="0000000000000000"
 maxlength="64" spellcheck="false" autocomplete="off" autocapitalize="off"></label>
<label class="field">{name}<textarea class="code" data-txt rows="8" cols="8" spellcheck="false"
 autocomplete="off" autocapitalize="off">{chr(10).join(["........"] * 8)}</textarea></label>
<div class="actions">
<button type="button" class="btn" data-save="{name}">{T.html("editor.save_button", file=name)}</button>
<label class="btn btn--secondary filebtn">{T.html("editor.open_button")}<input class="visually-hidden" type="file" data-open accept=".txt,text/plain"></label>
<button type="button" class="btn btn--secondary" data-copy>{T.html("editor.copy_button")}</button>
</div>
<p class="pad__msg" role="status" aria-live="polite" data-msg></p>
</fieldset>"""


def gallery_icons():
    """the ready-made icons (developers/icons.toml): slug, emoji, name, hex"""
    with open(GALLERY, "rb") as f:
        icons = tomllib.load(f)["icon"]
    out, seen = [], set()
    for i in icons:
        if not re.fullmatch(r"[a-z0-9-]+", i["slug"]) or i["slug"] in seen:
            raise SystemExit(f"developers/icons.toml: {i.get('slug')!r} needs a new slug of a-z, 0-9 and -")
        seen.add(i["slug"])
        out.append((i["slug"], i["emoji"], i["name"], icon_hex(i["pixels"], f"developers/icons.toml: {i['slug']}")))
    return out


def tools_page(ctx):
    icons = tvscreen.MENU["icons"]
    a, b = tvscreen.editor_pages("ed-plugin", "ed-file")
    plugin_pad = pad("plugin", T.html("editor.plugin_icon"), T.attr("editor.plugin_icon"),
                     T.html("editor.plugin_icon_note"), "m", "icon.txt")
    file_pad = pad("file", T.html("editor.file_icon"), T.attr("editor.file_icon"),
                   T.html("editor.file_icon_note"), "g", "file_icon.txt")
    picks = "".join(
        f'<li class="pick">{tvscreen.icon_svg(hx, "m")}'
        f'<p class="pick__name">{e_(name)}</p>'
        f'<p class="pick__do"><a class="link" href="#p={hx}" data-use hidden '
        f'aria-label="{T.attr("tools.use_label", name=name)}">{T.html("tools.use")}</a>'
        f'<a class="link" href="icons/{slug}.txt" download="icon.txt" '
        f'aria-label="{T.attr("tools.save_label", name=name)}">{T.html("tools.save")}</a></p></li>'
        for slug, emoji, name, hx in gallery_icons())
    body = f"""<section class="banner banner--tool" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("tools.title")}</h1>
<p class="lead">{T.html("tools.lead")}</p>
<ul class="jump"><li><a class="link" href="#icon-editor">{T.html("editor.title")}</a></li><li><a class="link" href="#gallery">{T.html("tools.gallery_title")}</a></li></ul>
</div>
</div></section>
<section class="section" id="icon-editor" aria-labelledby="icon-editor-title"><div class="container">
<div class="headblock"><h2 id="icon-editor-title">{T.html("editor.title")}</h2><p class="lead">{T.html("editor.lead")}</p></div>
<noscript><p class="warn">{T.html("editor.no_script", txt_section="../packaging/#icons-txt")}</p></noscript>
<div class="editor" data-editor data-plug="{icons["plugin"]}" data-file="{icons["file"]}">
<div class="editor__pads">
{plugin_pad}
{file_pad}
<p class="docnote" id="keys">{T.html("editor.keys")}</p>
</div>
<div class="editor__preview" aria-label="{T.attr("editor.preview_label")}">
{screen_card(a, T.html("editor.plugins_caption"), T.text("editor.plugins_code"))}
{screen_card(b, T.html("editor.folder_caption"), T.text("editor.folder_code"))}
<p class="docnote">{T.html("editor.sdk_note", icons_page="../packaging/#icons")}</p>
</div>
</div>
</div></section>
{doc_section("gallery", T.html("tools.gallery_title"), T.html("tools.gallery_lead"),
             f'<ul class="picks">{picks}</ul><p class="docnote">{T.html("tools.gallery_note")}</p>')}
<div class="container">{pager("../", ctx["pages"], "tools")}</div>
{check_band(ctx)}"""
    return page(T.text("tools.page_title"), T.text("tools.description"), body, "../", "tools", ctx, [a, b],
                scripts=("icon-editor.js",))


# ---- the build ---------------------------------------------------------------------------

def pages_of(kit, config, root=ROOT):
    """every file the portal is: {path under OUT: text}"""
    entries, _ = build_site.site_entries(config, root)
    pages = present(kit)
    ctx = {"kit": kit, "config": config, "entries": entries, "pages": pages, "here": portal_map(kit, pages)}
    out = {"index.html": home(ctx)}
    for rel, slug, _, label in pages:
        if rel:
            out[f"{slug}/index.html"] = doc_page(ctx, rel, slug, label)
    if any(slug == "claude" for _, slug, _, _ in pages):
        out["claude/index.html"] = claude_page(ctx)
        out[f"claude/{SKILL_ZIP}"] = skill_zip(kit)
    out["examples/index.html"] = examples_page(ctx)
    out["packaging/index.html"] = packaging_page(ctx)
    out["tools/index.html"] = tools_page(ctx)
    for name, hx, _ in starter_files():
        out[f"packaging/files/{name}"] = icon_txt(hx)
    for slug, _, _, hx in gallery_icons():
        out[f"tools/icons/{slug}.txt"] = icon_txt(hx)
    return out


def build(out, kit=None, config=None, root=ROOT):
    """the portal from the kit at kit (found as --kit would be if None), into out"""
    config = config or registry.load_config(root)
    repo = config.get("template_repo") or ""
    if not registry.REPO_RE.fullmatch(repo):
        raise SystemExit("error: registry.config.json template_repo must name the starter kit's repo, owner/repo")
    kit = Kit(find_kit(kit), repo)
    files = pages_of(kit, config, root)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "assets"))
    for name in ("dev.css", "dev.js", "icon-editor.js"):
        shutil.copy(os.path.join(DEV, "assets", name), os.path.join(out, "assets", name))
    if kit.has(KIT_SHOT):
        shutil.copy(os.path.join(kit.path, KIT_SHOT), os.path.join(out, "assets", "kit-screenshot.png"))
    for rel, text in files.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(text, bytes) else "w") as f:
            f.write(text)
    return kit, files


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the developer portal (the plugins site's developers/).")
    ap.add_argument("--kit", help="the starter kit's checkout (default: kit/ here, or one beside this repo)")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "developers"))
    a = ap.parse_args(argv)
    try:
        kit, files = build(a.out, a.kit)
    except sitecopy.CopyError as e:
        raise SystemExit(f"error: {e}") from None
    if not os.path.isfile(os.path.join(a.out, "..", "assets", "site.css")):
        print(f"note: the pages load ../assets/site.css: build the plugins site into {os.path.dirname(os.path.abspath(a.out))} too")
    n = sum(1 for r in files if r.endswith(".html"))
    print(f"built {a.out}: {n} pages from the starter kit at {kit.path}")


if __name__ == "__main__":
    main()
