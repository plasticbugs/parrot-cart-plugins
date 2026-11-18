"""build_site -- the registry's static site, from plugins/ (and examples/, our own
plugins that have no release to download).

    python3 tools/build_site.py [--out _site]

Writes OUT/index.html (the catalogue), OUT/plugins/<id>/index.html (a page
a plugin, with its screenshots and the cart's README text beside it),
OUT/submit/index.html, OUT/registry.json (the index for installers),
OUT/assets/, and OUT/authors/, the old authors' addresses, which send you on
to the developer portal. The portal is its own site, built into
OUT/developers/ by tools/build_dev.py from developers/ and the starter kit;
this site only links to it. Every word on the pages comes from
site/copy.toml (tools/sitecopy.py); this file holds the markup. A plugin's
README.md and release notes are rendered by tools/markdown.py: no raw HTML,
no scripts, no pictures from other sites. The TV screens are drawn from
each plugin's header in the cart menu's own font (tools/tvscreen.py).
Standard library only; links are relative, so the site works from any
folder or host path.

Preview:  python3 tools/build_site.py && python3 -m http.server -d _site 8000
"""
import argparse
import html
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cvp  # noqa: E402
import markdown  # noqa: E402
import png  # noqa: E402
import registry  # noqa: E402
import sitecopy  # noqa: E402
import tvscreen  # noqa: E402

ROOT = registry.ROOT
ASSETS = os.path.join(ROOT, "site", "assets")
FLASH_SLOTS = 10            # the menu's plugin cache: sdplayer.c NSLOT (keep in step with the firmware)
NEEDS = {"usb-host": "USB host", "usb-device": "USB device", "psram": "PSRAM"}
FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Onest:wght@400;500"
         "&family=JetBrains+Mono:wght@500&display=swap")
SLOTS_JS = ("<script>window.hallmarkSlots = (m) => { for (const [k, v] of Object.entries(m)) { const s = "
            "document.querySelector(`[data-slot=\"${k}\"]`); if (!s) continue; const im = new Image(); im.src = "
            "typeof v === 'string' ? v : v.src; im.alt = (typeof v === 'object' && v.alt) || s.dataset.alt || ''; "
            "s.querySelectorAll(':scope > img').forEach((o) => o.remove()); s.prepend(im); } };\n"
            "document.querySelectorAll('[data-slot] img').forEach((i) => { if (i.complete && !i.naturalWidth) "
            "i.remove(); else i.addEventListener('error', () => i.remove(), { once: true }); });</script>")

e_ = html.escape
T = sitecopy.COPY


def kb(n):
    return f"{(n + 1023) // 1024}K"


def needs(e):
    return ", ".join(NEEDS[u] for u in e["uses"])


def opens(e):
    return " ".join(e["opens"])


_MDLINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def desc_text(e):
    """the one-line description as plain text: our own entries' may hold a Markdown link"""
    return _MDLINK.sub(r"\1", e["description"])


def desc_html(e, pre):
    """the description on the plugin's own page, where the links in one of our own entries
    (examples/) work, relative ones from the site's root. A listed plugin's description is always
    plain text."""
    d = e["description"]
    if not e.get("example"):
        return e_(d)
    out, at = [], 0
    for m in _MDLINK.finditer(d):
        href = m[2] if m[2].startswith("https://") else pre + m[2]
        out += [e_(d[at:m.start()]), f'<a class="link" href="{e_(href)}">{e_(m[1])}</a>']
        at = m.end()
    return "".join(out) + e_(d[at:])


def keep_together(s):
    """the last two words on one line: no word on its own under a big heading"""
    head, sep, tail = s.rpartition(" ")
    return f"{head}&nbsp;{tail}" if sep else s


# ---- the frame of every page --------------------------------------------------------

def shop_link(config, cls, text):
    """the link to the cart's own shop, if the config names one (text is html)"""
    url = config.get("shop_url")
    return f'<a class="{cls}" href="{e_(url)}">{text}</a>' if url else ""


def slab(pre, current, config):
    def link(href, text, key):
        cur = ' aria-current="page"' if key == current else ""
        return f'<li><a href="{href}"{cur}>{text}</a></li>'
    return (f'<header class="slab"><div class="container">'
            f'<a class="wordmark" href="{pre}index.html" aria-label="{T.attr("header.home_label")}" '
            f'><img src="{pre}assets/parrot-cart-mark.svg" width="24" height="28" alt="">{T.html("header.wordmark")}</a>'
            f'<nav aria-label="{T.attr("header.nav_label")}"><ul>'
            + link(f"{pre}index.html#plugins", T.html("header.nav_plugins"), "plugins")
            + link(f"{pre}index.html#install", T.html("header.nav_install"), "install")
            + link(f"{pre}converter/", T.html("header.nav_converter"), "converter")
            + link(f"{pre}developers/", T.html("header.nav_developers"), "developers")
            + link(f"{pre}submit/", T.html("header.nav_submit"), "submit")
            + "</ul></nav>" + shop_link(config, "slab__shop", T.html("header.shop")) + "</div></header>")


def footer(pre, entries, config):
    repo = f'\n<li><a href="https://github.com/{e_(config["registry_repo"])}">{T.html("footer.source_code")}</a></li>'
    names = "".join(f'<li><a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a></li>'
                    for e in sorted(entries, key=lambda e: e["name"].lower()))
    return f"""<footer class="foot"><div class="container">
<div class="cols">
<div><h2>{T.html("footer.title")}</h2><p>{T.html("footer.tagline")}</p><p class="foot__shop">{shop_link(config, "link", T.html("footer.shop"))}</p></div>
<div><h2>{T.html("footer.plugins_heading")}</h2><ul>{names}</ul></div>
<div><h2>{T.html("footer.links_heading")}</h2><ul><li><a href="{pre}submit/">{T.html("footer.submit")}</a></li><li><a href="{pre}submit/#rules">{T.html("footer.rules")}</a></li>
<li><a href="{pre}developers/">{T.html("footer.developers")}</a></li><li><a href="{pre}developers/tools/">{T.html("footer.icon_editor")}</a></li>
<li><a href="{pre}index.html#install">{T.html("footer.install")}</a></li><li><a href="{pre}converter/">{T.html("footer.converter")}</a></li><li><a href="{pre}registry.json">{T.html("footer.registry_json")}</a></li>{repo}</ul></div>
</div>
<p class="fine">{T.html("footer.font_credit", _link=None)}</p>
</div></footer>"""


def page(title, description, body, pre, current, screens, entries, config, scripts=()):
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
<link rel="stylesheet" href="{pre}assets/site.css">
<link rel="icon" href="{pre}assets/parrot-cart-icon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">{T.html("header.skip")}</a>
{tvscreen.glyph_defs(screens)}
{slab(pre, current, config)}
<main id="main">
{body}
</main>
{footer(pre, entries, config)}
<script src="{pre}assets/site.js" defer></script>
{"".join(f'<script src="{pre}assets/{n}" defer></script>' + chr(10) for n in scripts)}{SLOTS_JS}
</body>
</html>
""")


def typeset(doc):
    """typographic apostrophes in the page's text, never inside tags, code or scripts"""
    out, skip = [], 0
    for part in re.split(r"(<[^>]*>)", doc):
        if part.startswith("<"):
            m = re.match(r"<(/?)(script|pre|code|style)\b", part)
            if m:
                skip += -1 if m.group(1) else 1
        elif not skip:
            part = part.replace("&#x27;", "’").replace("'", "’")
        out.append(part)
    return "".join(out)


def screen_card(screen, caption, code, slot=None, alt=None, extra=""):
    """caption is html; code and alt are plain text"""
    slot_attr = f' data-slot="{slot}" data-alt="{e_(alt)}"' if slot else ""
    return (f'<figure class="card{extra}"><div class="screen"{slot_attr} data-kind="product">{screen.svg()}</div>'
            f'<figcaption><span>{caption}</span><code class="code">{e_(code)}</code></figcaption></figure>')


def li_rows(rows, sep=""):
    """[(title, text)] as <li><h3>title</h3><p>text</p></li>"""
    return sep.join(f"<li><h3>{t}</h3><p>{s}</p></li>" for t, s in rows)


# ---- the catalogue ------------------------------------------------------------------

def thumb(e, pre=""):
    """the catalogue's picture of a plugin: its first screenshot, a TV pixel a pixel (half
    that on a phone), or its icon on the TV's black"""
    if e["screenshots"]:
        src = f'{pre}plugins/{e_(e["id"])}/{e["screenshots"][0]["file"]}'
        return (f'<span class="thumb"><img src="{src}" width="{png.WIDTH}" height="{png.HEIGHT}" alt="" '
                f'loading="lazy" decoding="async"></span>')
    return f'<span class="thumb">{tvscreen.icon_svg(e["icon"])}</span>'


def catalogue_rows(entries, pre=""):
    rows = []
    col = {"id": T.attr("home.browse.columns.id"), "opens": T.attr("home.browse.columns.opens"),
           "version": T.attr("home.browse.columns.version"), "size": T.attr("home.browse.columns.size")}
    no_files = T.html("home.browse.no_files")
    for e in sorted(entries, key=lambda e: e["name"].lower()):
        text = " ".join([e["name"], e["id"], opens(e), needs(e), e["by"], e["owner"], desc_text(e)]).lower()
        rows.append(
            f'<tr data-text="{e_(text)}">'
            f'<td class="first"><div class="plugin">{thumb(e, pre)}'
            f'<div><span class="plugin__title">{tvscreen.icon_svg(e["icon"], "m")}'
            f'<a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a></span><small>{e_(desc_text(e))}</small></div></div></td>'
            f'<td data-label="{col["id"]}"><span class="code code--id">{e_(e["id"])}</span></td>'
            f'<td data-label="{col["opens"]}">{f"<span class=code>{e_(opens(e))}</span>" if e["opens"] else f"<span class=muted>{no_files}</span>"}</td>'
            f'<td data-label="{col["version"]}" class="num"><code class="code">{e_(e["version"])}</code></td>'
            f'<td data-label="{col["size"]}" class="num"><code class="code">{kb(e["download"]["size"])}</code></td></tr>')
    return "".join(rows)


def about(config):
    """what Parrot Cart is, under the hero: a few plain lines, the way to get one, and the hardware for the technical"""
    shop = shop_link(config, "btn", T.html("home.about.shop_button"))
    rows = "".join(f"<div><dt>{n}</dt><dd>{v}</dd></div>" for n, v in T.rows("home.about.specs", ("name", "value")))
    return f"""<section class="section about" id="about" aria-labelledby="about-title"><div class="container">
<div class="about__text">
<h2 id="about-title">{T.html("home.about.title")}</h2>
<p class="about__big">{T.html("home.about.big")}</p>
<p class="lead">{T.html("home.about.text")}</p>
{f'<div class="actions">{shop}</div>' if shop else ""}
</div>
<div class="about__specs"><h3>{T.html("home.about.specs_title")}</h3><dl class="specs specs--one">{rows}</dl></div>
</div></section>"""


def home(entries, config):
    plugins_screen = tvscreen.plugins_page(entries)
    screens = [plugins_screen]
    body = [f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{keep_together(T.html("home.hero.title"))}</h1>
<p class="lead">{T.html("home.hero.lead")}</p>
<div class="actions"><a class="btn" href="#plugins">{T.html("home.hero.browse_button")}</a><a class="btn btn--secondary" href="submit/">{T.html("home.hero.submit_button")}</a></div>
</div>
{screen_card(plugins_screen, T.html("home.hero.card_caption"), T.text("home.hero.card_code"), "hero-screen",
             T.text("home.hero.card_alt"))}
</div></section>""", about(config),
            f"""<section class="section" id="plugins" aria-labelledby="plugins-title"><div class="container">
<div class="headblock"><h2 id="plugins-title">{T.html("home.browse.title")}</h2></div>
<div class="finder" data-finder="catalogue" data-empty="catalogue-empty" hidden>
<label for="q">{T.html("home.browse.search_label")}<input id="q" type="search" autocomplete="off" spellcheck="false"></label>
<p role="status" aria-live="polite"></p></div>
<table class="spec" id="catalogue">
<thead><tr><th scope="col">{T.html("home.browse.columns.plugin")}</th><th scope="col">{T.html("home.browse.columns.id")}</th><th scope="col">{T.html("home.browse.columns.opens")}</th>
<th scope="col" class="num">{T.html("home.browse.columns.version")}</th><th scope="col" class="num">{T.html("home.browse.columns.size")}</th></tr></thead>
<tbody>{catalogue_rows(entries)}</tbody></table>
<p class="empty" id="catalogue-empty" hidden>{T.html("home.browse.no_match")}</p>
</div></section>"""]

    # what one file changes: a plugin that opens files, in its home folder
    pick = next((e for e in sorted(entries, key=lambda e: e["name"].lower()) if e["opens"] and e["home"]), None)
    if pick:
        ext, folder = pick["opens"][0], pick["home"]
        names = ["Sample 1", "Sample 2", "Sample 3"]
        before = tvscreen.folder_page(folder, [])
        listed = tvscreen.plugins_page([pick])
        after = tvscreen.folder_page(folder, names, pick["file_icon"])
        screens += [before, listed, after]
        f = e_(pick["download"]["name"])
        states = [
            ("before", T.html("home.files.before"), T.html("home.files.before_text", ext=e_(ext), folder=e_(folder)),
             before, folder),
            ("copied", T.html("home.files.copied"), T.html("home.files.copied_text", file=f), listed,
             T.text("home.files.copied_code")),
            ("after", T.html("home.files.after"), T.html("home.files.after_text"),
             after, folder),
        ]
        last = len(states) - 1          # it opens on After: the change itself
        tabs = "".join(
            f'<button type="button" role="tab" id="t-{k}" aria-controls="p-{k}" aria-selected="{str(i == last).lower()}"'
            f'{"" if i == last else " tabindex=-1"}><b>{t}</b><span>{s}</span></button>'
            for i, (k, t, s, _, _) in enumerate(states))
        panels = "".join(
            f'<figure class="card panel" role="tabpanel" id="p-{k}" aria-labelledby="t-{k}">'
            f'<div class="screen" data-kind="product">{sc.svg()}</div>'
            f'<figcaption><span>{t}</span><code class="code">{e_(code)}</code></figcaption></figure>'
            for k, t, s, sc, code in states)
        body.append(f"""<section class="section" aria-labelledby="change-title"><div class="container">
<div class="headblock"><h2 id="change-title">{T.html("home.files.title")}</h2><p class="lead">{T.html("home.files.lead")}</p></div>
<div class="switch" data-switch>
<div class="switch__tabs" role="tablist" aria-label="{T.attr("home.files.tabs_label")}" aria-orientation="vertical">{tabs}</div>
<div class="switch__panels">{panels}</div>
</div></div></section>""")

    body.append(f"""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">{T.html("home.install.title")}</h2><p class="lead">{T.html("home.install.lead")}</p></div>
<ol class="steps">
{li_rows(T.rows("home.install.steps", ("title", "text")), chr(10))}
</ol></div></section>""")

    ruled = "\n".join(f"<li><b>{t}</b><span>{s}</span></li>" for t, s in T.rows("home.flash.rows", ("bold", "text")))
    body.append(f"""<section class="band band--ink figure-band" id="flash" aria-labelledby="flash-title"><div class="container">
<div><p class="big" aria-hidden="true">{FLASH_SLOTS}</p><h2 id="flash-title"><span class="visually-hidden">{FLASH_SLOTS} </span>{T.html("home.flash.title")}</h2></div>
<ul class="ruled">
{ruled}
</ul></div></section>""")

    body.append(f"""<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("home.close.title")}</h2><p>{T.html("home.close.text")}</p></div>
<div class="actions"><a class="btn" href="submit/">{T.html("home.close.submit_button")}</a>
<a class="btn btn--secondary" href="registry.json">{T.html("home.close.json_button")}</a></div>
</div></section>""")
    return page(T.text("home.page_title"), T.text("home.description"), "\n".join(body), "", "plugins",
                screens, entries, config)


# ---- a plugin's page ----------------------------------------------------------------

def link_or_text(url, text, live):
    return f'<a class="link" href="{e_(url)}">{text}</a>' if live else text


def shots_section(e):
    """its screenshots, each in the TV's frame at a whole number of screen pixels a pixel"""
    n = len(e["screenshots"])
    if not n:
        return ""
    figs = "".join(
        f'<figure class="card shot"><div class="shot__tv"><img src="{s["file"]}" width="{png.WIDTH}" '
        f'height="{png.HEIGHT}" alt="{T.attr("plugin.shots.alt", name=e_(e["name"]), number=i, count=n)}" '
        f'loading="lazy" decoding="async"></div><figcaption><span>{T.html("plugin.shots.caption", number=i)}</span>'
        f'<code class="code">{png.WIDTH} × {png.HEIGHT}</code></figcaption></figure>'
        for i, s in enumerate(e["screenshots"], 1))
    lead = T.html("plugin.shots.lead_menu") if e.get("example") else T.html("plugin.shots.lead")
    return f"""<section class="section" id="screenshots" aria-labelledby="shots-title"><div class="container">
<div class="headblock"><h2 id="shots-title">{T.html("plugin.shots.title")}</h2><p class="lead">{lead}</p></div>
<div class="shots" data-n="{n}">{figs}</div>
</div></section>"""


def cart_readme_section(e, text, pre):
    """the .CVP's README text as it is, in the menu's font, and the same text to read or copy"""
    if text is None:
        return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">{T.html("plugin.no_cart_readme.title")}</h2><p class="lead">{T.html("plugin.no_cart_readme.lead")}</p></div>
<p class="warn">{T.html("plugin.no_cart_readme.author_note", readme_page=f"{pre}developers/packaging/#readme")}</p>
</div></section>""", None
    strip = tvscreen.readme_strip(text)
    meta = e["readme"]["cart"]
    return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">{T.html("plugin.cart_readme.title")}</h2><p class="lead">{T.html("plugin.cart_readme.lead", lines=meta["lines"])}</p></div>
<div class="cartreadme">
<figure class="card"><div class="scroll" tabindex="0" role="region" aria-label="{T.attr("plugin.cart_readme.scroll_label")}">{strip.svg()}</div>
<figcaption><span>{T.html("plugin.cart_readme.caption")}</span><code class="code">{T.html("plugin.cart_readme.size", size=f"{meta['size']:,}")}</code></figcaption></figure>
<div class="cartreadme__text"><h3>{T.html("plugin.cart_readme.text_title")}</h3>
<pre class="plain">{e_(text)}</pre>
<p><a class="link" href="{registry.CART_README}">{registry.CART_README}</a></p></div>
</div></div></section>""", strip


def web_readme_section(e, text, live):
    """the README.md: a listed plugin's at its release's tag, a coming one's from its repository,
    a built-in's as we wrote it"""
    tag = e["release"]["tag"]
    linked = live or coming(e)
    where = e["readme"]["web"]["url"] if e["readme"]["web"] else e["credits_url"]
    if text is None:
        link = link_or_text(where, T.html("plugin.readme.github_link"), linked)
        body = f'<p class="warn">{T.html("plugin.readme.not_shown", link=link)}</p>'
        lead = T.html("plugin.readme.lead_not_shown")
    else:
        base = f"https://github.com/{e['repo']}/blob/{tag}/" if linked else None
        body = f'<div class="prose">{markdown.render(text, base, 3, where if linked else None)}</div>'
        lead = (T.html("plugin.readme.lead", tag=e_(tag)) if live else
                T.html("plugin.readme.lead_repo") if linked else T.html("plugin.readme.lead_built_in"))
    return f"""<section class="section" id="readme" aria-labelledby="readme-title"><div class="container">
<div class="headblock"><h2 id="readme-title">{T.html("plugin.readme.title")}</h2><p class="lead">{lead}</p></div>
{body}
</div></section>"""


def notes_section(e, live):
    """each listed version's release notes, newest first"""
    base = f"https://github.com/{e['repo']}/blob/{e['release']['tag']}/" if live else None
    items = []
    for h in e["history"]:
        notes = (f'<div class="prose">{markdown.render(h["notes"], base, 4)}</div>' if h["notes"].strip()
                 else f'<p class="muted">{T.html("plugin.notes.none")}</p>')
        items.append(f'<li><div><h3>{e_(h["version"])}</h3><p class="muted">{e_(h["published"])}, '
                     f'{link_or_text(h["url"], f"""<code class="code">{e_(h["tag"])}</code>""", live)}</p></div>'
                     f"{notes}</li>")
    return f"""<section class="section" id="notes" aria-labelledby="notes-title"><div class="container">
<div class="headblock"><h2 id="notes-title">{T.html("plugin.notes.title")}</h2><p class="lead">{T.html("plugin.notes.lead")}</p></div>
<ul class="rows rows--notes">{"".join(items)}</ul>
</div></section>"""


def coming(e):
    """one of our plugins whose repository is public and whose first release isn't out yet"""
    return bool(e.get("example")) and not e.get("built_in")


def source_section(e, live):
    """where the plugin's code is: a card that links to its repo (none for the cart's built-in plugins)"""
    if e.get("built_in"):
        return ""
    owner, name = e["repo"].split("/", 1)
    release = (T.html("plugin.source.release", tag=e_(e["release"]["tag"])) if live else
               T.html("plugin.source.no_release"))
    body = (f'<a class="repo" href="https://github.com/{e_(e["repo"])}">'
            f'<span class="repo__host">{T.html("plugin.source.host")}</span>'
            f'<span class="repo__name">{e_(owner)}/<b>{e_(name)}</b></span>'
            f'<span class="repo__desc">{e_(desc_text(e))}</span>'
            f'<span class="repo__meta"><span>{e_(e["license"]["name"])}</span>'
            f'<span>{release}</span></span>'
            f'<span class="repo__go">{T.html("plugin.source.go")}</span></a>')
    return doc_section("source", T.html("plugin.source.title"), T.html("plugin.source.lead"), body)


def plugin_page(e, entries, config, root=ROOT):
    live = not e.get("example")
    pre = "../../"
    details = tvscreen.details_page(e)

    def text_of(name):
        raw = registry.read_file(root, e, name)
        return None if raw is None else raw.decode("utf-8", "replace")
    cart_html, strip = cart_readme_section(e, text_of(registry.CART_README), pre)
    extra = shots_section(e) + cart_html + web_readme_section(e, text_of(registry.WEB_README), live)
    lic = e["license"]
    if live:
        action = (f'<div class="actions"><a class="btn" href="{e_(e["download"]["name"])}" download>'
                  f'{T.html("plugin.hero.download_button", file=e_(e["download"]["name"]))}</a>'
                  f'<a class="btn btn--secondary" href="{e_(e["source_url"])}">'
                  f'{T.html("plugin.hero.source_button")}</a></div>')
    elif e.get("built_in"):
        action = f'<p class="note">{T.html("plugin.hero.built_in_note")}</p>'
    else:
        action = (f'<div class="actions"><a class="btn" href="{e_(e["source_url"])}">'
                  f'{T.html("plugin.hero.source_button")}</a></div>'
                  f'<p class="note">{T.html("plugin.hero.coming_note", name=e_(e["name"]))}</p>')
    hero = f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title" class="titled">{tvscreen.icon_svg(e["icon"], "m")}<span>{e_(e["name"])}</span></h1>
<p class="lead">{desc_html(e, pre)}</p>
{action}
</div>
{screen_card(details, T.html("plugin.hero.card_caption"), e["download"]["name"], "details",
             T.text("plugin.hero.card_alt", name=e["name"]))}
</div></section>"""

    size = f'{e["image"]["size"]:,}'
    image = (T.html("plugin.details.image_ram", size=size) if e["image"]["kind"] == "sram"
             else T.html("plugin.details.image_flash", size=size))
    # the details screen above already shows the header; these are what the check read in the release
    # (one of our own entries has no release: a coming plugin's rows link its repository, and a
    # built-in's are the build's alone)
    rows = [(T.html("plugin.details.image"), image),
            (T.html("plugin.details.api"), f'<code class="code">{e["api"]}</code>')]
    if live:
        rows.insert(0, (T.html("plugin.details.release"),
                        T.html("plugin.details.release_value", tag=e_(e["release"]["tag"]),
                               date=e_(e["release"]["published"]))))
    if not e.get("built_in"):
        rows += [
            (T.html("plugin.details.github"), link_or_text(f"https://github.com/{e['repo']}", e_(e["repo"]), True)),
            (T.html("plugin.details.source"),
             link_or_text(e["source_url"], T.html("plugin.details.source_value", tag=e_(e["release"]["tag"])), True)),
            (T.html("plugin.details.license"), link_or_text(lic["url"], e_(lic["name"]), True)
             + (f'. {e_(lic["note"])}' if lic.get("note") else "")),
        ]
    items = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
    if e.get("credits"):        # the long ones run the full width, so the two columns stay even
        items += f'<div class="wide"><dt>{T.html("plugin.details.credits")}</dt><dd>{e_(e["credits"])}</dd></div>'
    if live:
        items += (f'<div class="wide"><dt>{T.html("plugin.details.sha256")}</dt><dd><span class="code hash">'
                  f'{e_(e["download"]["sha256"])}</span></dd></div>')
    if live:
        title, lead = T.html("plugin.details.title"), T.html("plugin.details.lead")
    elif e.get("built_in"):
        title, lead = T.html("plugin.details.title_ours"), T.html("plugin.details.lead_built_in")
    else:
        title, lead = T.html("plugin.details.title_ours"), T.html("plugin.details.lead_coming")
    specs = f"""<section class="section" aria-labelledby="specs-title"><div class="container">
<div class="headblock"><h2 id="specs-title">{title}</h2><p class="lead">{lead}</p></div>
<dl class="specs">{items}</dl>
</div></section>"""

    fname = e_(e["download"]["name"])
    steps = [(T.html("plugin.install.download_title", file=fname), T.html("plugin.install.download_text")),
             (T.html("plugin.install.copy_title"), T.html("plugin.install.copy_text"))]
    if e["opens"] and e["home"]:
        steps.append((T.html("plugin.install.files_title", folder=e_(e["home"])),
                      T.html("plugin.install.files_text", types=e_(opens(e)))))
    steps.append((T.html("plugin.install.start_title"), T.html("plugin.install.start_text", name=e_(e["name"]))))
    install = "" if not live else f"""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">{T.html("plugin.install.title")}</h2></div>
<ol class="steps{" steps--4" if len(steps) == 4 else ""}">{li_rows(steps)}</ol>
</div></section>"""
    desc = T.text("plugin.description", name=e["name"], version=e["version"],
                  description=desc_text(e).rstrip(". "))
    return page(T.text("plugin.page_title", name=e["name"]), desc,
                hero + extra + specs + source_section(e, live) + ("" if coming(e) else notes_section(e, live))
                + install,
                pre, "plugins", [details] + ([strip] if strip else []), entries, config)


# ---- the submit page ----------------------------------------------------------------

def submit_page(entries, config):
    form = f"https://github.com/{config['registry_repo']}/issues/new?template=submit-plugin.yml"
    nodes = T.rows("submit.steps.boxes", ("title", "text"))
    items = "".join(f'<li{" class=loop" if i == len(nodes) - 1 else ""}><h2>{t}</h2><p>{s}</p></li>'
                    for i, (t, s) in enumerate(nodes))
    # what a plugin needs, in a few lines
    need_rows = "".join(f"<li><b>{t}</b><span>{s}</span></li>" for t, s in
                        T.rows("submit.requirements.rows", ("title", "text"), readme_page="../developers/packaging/#readme",
                               screenshots_page="../developers/packaging/#screenshots"))
    primary = f'<a class="btn" href="{e_(form)}">{T.html("submit.hero.issue_button")}</a>'
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("submit.hero.title")}</h1>
<p class="lead">{T.html("submit.hero.lead")}</p>
<div class="actions">{primary}<a class="btn btn--secondary" href="#rules">{T.html("submit.hero.rules_button")}</a></div>
</div>
<ol class="map" aria-label="{T.attr("submit.steps.label")}">{items}</ol>
<p class="map-legend">{T.html("submit.steps.note")}</p>
</div></section>
<section class="section" id="rules" aria-labelledby="rules-title"><div class="container">
<div class="headblock"><h2 id="rules-title">{T.html("submit.requirements.title")}</h2></div>
<ul class="ruled">{need_rows}</ul>
</div></section>
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("submit.check.title")}</h2><p>{T.html("submit.check.text")}</p></div>
<pre class="cmd"><code>{T.block("submit.check.command")}</code></pre>
</div></section>"""
    return page(T.text("submit.page_title"), T.text("submit.description"), body, "../", "submit", [], entries, config)


# ---- shared with the developer portal (tools/build_dev.py) ---------------------------

def spec_table(heads, rows, caption=None):
    head = "".join(f'<th scope="col">{h}</th>' for h in heads)
    body = "".join(f'<tr><th scope="row">{r[0]}</th>' + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>"
                   for r in rows)
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f'<table class="spec spec--rules spec--doc">{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def doc_section(sid, title, lead, body, level=2):
    lead = f'<p class="lead">{lead}</p>' if lead else ""
    return (f'<section class="section" id="{sid}" aria-labelledby="{sid}-title"><div class="container">'
            f'<div class="headblock"><h{level} id="{sid}-title">{title}</h{level}>{lead}</div>\n{body}\n</div></section>')


# ---- old addresses -------------------------------------------------------------------

def moved(to):
    """a page that has moved: an old address that sends you on"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{T.html("moved.title")}</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={to}">
<link rel="canonical" href="{to}">
</head>
<body>
<p>{T.html("moved.text")} <a href="{to}">{T.html("moved.link")}</a></p>
</body>
</html>
"""


# the authors' pages, now the developer portal's Packaging and Tools pages
MOVED = {
    "authors/index.html": "../developers/packaging/",
    "authors/tools/index.html": "../../developers/tools/",
    "authors/readme/index.html": "../../developers/packaging/#readme",
    "authors/screenshots/index.html": "../../developers/packaging/#screenshots",
    "authors/icons/index.html": "../../developers/packaging/#icons",
    "authors/icon-editor/index.html": "../../developers/tools/#icon-editor",
}


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 12 12" shape-rendering="crispEdges">
<rect x="-2" y="-2" width="12" height="12" fill="{bg}"/><path fill="{fg}" d="{d}"/></svg>
"""


def site_entries(config, root=ROOT):
    """the listed plugins, and our own with no release (examples/) if the config shows them:
    (entries, the listed ones by ID)"""
    live = registry.load_entries(root)
    entries = list(live.values())
    if config.get("show_examples"):
        entries += [e for e in registry.load_entries(root, examples=True).values() if e["id"] not in live]
    for e in entries:
        bad = registry.check_entry(e)
        bad = bad or registry.check_files(registry.files_dir(root, e["id"], bool(e.get("example"))), e)
        if bad:
            raise SystemExit(f"{e.get('id')}: {bad}")
    return entries, live


def build(out, config=None, root=ROOT):
    """the site for the entries under root (the registry's own files by default)"""
    config = config or registry.load_config(root)
    entries, live = site_entries(config, root)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "assets"))
    for name in ("tokens.css", "base.css", "site.css", "site.js",       # site.css is the portal's too
                 "parrot-cart-mark.svg", "parrot-cart-icon.svg"):     # the logo, from the cart's own site
        shutil.copy(os.path.join(ASSETS, name), os.path.join(out, "assets", name))
    with open(os.path.join(out, "assets", "icon.svg"), "w") as f:     # the menu's plug, as on the TV
        f.write(ICON_SVG.format(bg="#22232e", fg="#c95bba", d=tvscreen._path(tvscreen.MENU["icons"]["plugin"])))

    def write(rel, text):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    write("index.html", home(entries, config))
    for e in entries:
        write(f"plugins/{e['id']}/index.html", plugin_page(e, entries, config, root))
        for name in registry.entry_files(e):                    # copies: the site hotlinks nothing
            with open(os.path.join(out, "plugins", e["id"], name), "wb") as f:
                f.write(registry.read_file(root, e, name))
    write("submit/index.html", submit_page(entries, config))
    for rel, to in MOVED.items():
        write(rel, moved(to))
    registry.write_json(os.path.join(out, "registry.json"), registry.index(live, config))
    conv = os.path.join(root, "converter")
    if os.path.isdir(conv):             # the movie converter: a built web app, copied as it is
        shutil.copytree(conv, os.path.join(out, "converter"))
    write(".nojekyll", "")
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the registry's static site.")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args(argv)
    try:
        entries = build(a.out)
    except sitecopy.CopyError as e:
        raise SystemExit(f"error: {e}") from None
    print(f"built {a.out}: the catalogue, {len(entries)} plugin pages, the submit page and registry.json "
          "(the developer portal: tools/build_dev.py --out " + os.path.join(a.out, "developers") + ")")


if __name__ == "__main__":
    main()
