"""build_site -- the registry's static site, from plugins/ (and the examples).

    python3 tools/build_site.py [--out _site]

Writes OUT/index.html (the catalogue), OUT/plugins/<id>/index.html (a page
a plugin, with its screenshots and the cart's README text beside it),
OUT/authors/ (what a release needs: the README, screenshot and icon pages,
and the icon editor), OUT/submit/index.html, OUT/registry.json (the index
for installers) and OUT/assets/. Every word on the pages comes from
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


def keep_together(s):
    """the last two words on one line: no word on its own under a big heading"""
    head, sep, tail = s.rpartition(" ")
    return f"{head}&nbsp;{tail}" if sep else s


# ---- the frame of every page --------------------------------------------------------

def slab(pre, current):
    def link(href, text, key):
        cur = ' aria-current="page"' if key == current else ""
        return f'<li><a href="{href}"{cur}>{text}</a></li>'
    return (f'<header class="slab"><div class="container">'
            f'<a class="wordmark" href="{pre}index.html" aria-label="{T.attr("header.home_label")}" '
            f'><img src="{pre}assets/parrot-cart-mark.svg" width="24" height="28" alt="">{T.html("header.wordmark")}</a>'
            f'<nav aria-label="{T.attr("header.nav_label")}"><ul>'
            + link(f"{pre}index.html#plugins", T.html("header.nav_plugins"), "plugins")
            + link(f"{pre}index.html#install", T.html("header.nav_install"), "install")
            + link(f"{pre}authors/", T.html("header.nav_authors"), "authors")
            + link(f"{pre}submit/", T.html("header.nav_submit"), "submit")
            + "</ul></nav></div></header>")


def placeholder(config):
    """the registry's repository is still the OWNER/... stand-in: nothing on GitHub to link to yet"""
    return config["registry_repo"].split("/")[0] == "OWNER"


def footer(pre, entries, config):
    repo = ("" if placeholder(config) else
            f'\n<li><a href="https://github.com/{e_(config["registry_repo"])}">{T.html("footer.source_code")}</a></li>')
    names = "".join(f'<li><a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a></li>'
                    for e in sorted(entries, key=lambda e: e["name"].lower()))
    return f"""<footer class="foot"><div class="container">
<div class="cols">
<div><h2>{T.html("footer.title")}</h2><p>{T.html("footer.tagline")}</p></div>
<div><h2>{T.html("footer.plugins_heading")}</h2><ul>{names}</ul></div>
<div><h2>{T.html("footer.links_heading")}</h2><ul><li><a href="{pre}submit/">{T.html("footer.submit")}</a></li><li><a href="{pre}submit/#rules">{T.html("footer.rules")}</a></li>
<li><a href="{pre}authors/">{T.html("footer.authors")}</a></li><li><a href="{pre}authors/icon-editor/">{T.html("footer.icon_editor")}</a></li>
<li><a href="{pre}index.html#install">{T.html("footer.install")}</a></li><li><a href="{pre}registry.json">{T.html("footer.registry_json")}</a></li>{repo}</ul></div>
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
{slab(pre, current)}
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
            f'<figcaption><span>{caption}</span><span class="code">{e_(code)}</span></figcaption></figure>')


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
           "needs": T.attr("home.browse.columns.needs"), "version": T.attr("home.browse.columns.version"),
           "size": T.attr("home.browse.columns.size")}
    no_files, nothing = T.html("home.browse.no_files"), T.html("home.browse.needs_nothing")
    for e in sorted(entries, key=lambda e: e["name"].lower()):
        text = " ".join([e["name"], e["id"], opens(e), needs(e), e["by"], e["owner"], e["description"]]).lower()
        who = (T.html("home.browse.example") if e.get("example")
               else T.html("home.browse.by", name=e_(e["by"] or e["owner"])))
        rows.append(
            f'<tr data-text="{e_(text)}">'
            f'<td class="first"><div class="plugin">{thumb(e, pre)}'
            f'<div><a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a><small>{who}</small></div></div></td>'
            f'<td data-label="{col["id"]}"><span class="code code--id">{e_(e["id"])}</span></td>'
            f'<td data-label="{col["opens"]}">{f"<span class=code>{e_(opens(e))}</span>" if e["opens"] else f"<span class=muted>{no_files}</span>"}</td>'
            f'<td data-label="{col["needs"]}">{e_(needs(e)) or f"<span class=muted>{nothing}</span>"}</td>'
            f'<td data-label="{col["version"]}" class="num"><span class="code">{e_(e["version"])}</span></td>'
            f'<td data-label="{col["size"]}" class="num"><span class="code">{kb(e["download"]["size"])}</span></td></tr>')
    return "".join(rows)


def home(entries, config):
    examples = [e for e in entries if e.get("example")]
    plugins_screen = tvscreen.plugins_page(entries)
    screens = [plugins_screen]
    if len(examples) == len(entries):
        line = T.html("home.browse.lead_examples", count=len(entries))
    else:
        line = T.html("home.browse.lead", count=len(entries) - len(examples))
    body = [f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{keep_together(T.html("home.hero.title"))}</h1>
<p class="lead">{T.html("home.hero.lead")}</p>
<div class="actions"><a class="btn" href="#plugins">{T.html("home.hero.browse_button")}</a><a class="btn btn--secondary" href="submit/">{T.html("home.hero.submit_button")}</a></div>
</div>
{screen_card(plugins_screen, T.html("home.hero.card_caption"), T.text("home.hero.card_code"), "hero-screen",
             T.text("home.hero.card_alt"))}
</div></section>""",
            f"""<section class="section" id="plugins" aria-labelledby="plugins-title"><div class="container">
<div class="headblock"><h2 id="plugins-title">{T.html("home.browse.title")}</h2><p class="lead">{line}</p></div>
<div class="finder" data-finder="catalogue" data-empty="catalogue-empty" hidden>
<label for="q">{T.html("home.browse.search_label")}<input id="q" type="search" autocomplete="off" spellcheck="false"></label>
<p role="status" aria-live="polite"></p></div>
<table class="spec" id="catalogue">
<thead><tr><th scope="col">{T.html("home.browse.columns.plugin")}</th><th scope="col">{T.html("home.browse.columns.id")}</th><th scope="col">{T.html("home.browse.columns.opens")}</th><th scope="col">{T.html("home.browse.columns.needs")}</th>
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
            f'<figcaption><span>{t}</span><span class="code">{e_(code)}</span></figcaption></figure>'
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
        f'<span class="code">{png.WIDTH} × {png.HEIGHT}</span></figcaption></figure>'
        for i, s in enumerate(e["screenshots"], 1))
    lead = T.html("plugin.shots.lead_example") if e.get("example") else T.html("plugin.shots.lead")
    return f"""<section class="section" id="screenshots" aria-labelledby="shots-title"><div class="container">
<div class="headblock"><h2 id="shots-title">{T.html("plugin.shots.title")}</h2><p class="lead">{lead}</p></div>
<div class="shots" data-n="{n}">{figs}</div>
</div></section>"""


def cart_readme_section(e, text, pre):
    """the .CVP's README text as it is, in the menu's font, and the same text to read or copy"""
    if text is None:
        return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">{T.html("plugin.no_cart_readme.title")}</h2><p class="lead">{T.html("plugin.no_cart_readme.lead")}</p></div>
<p class="warn">{T.html("plugin.no_cart_readme.author_note", readme_page=f"{pre}authors/readme/")}</p>
</div></section>""", None
    strip = tvscreen.readme_strip(text)
    meta = e["readme"]["cart"]
    return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">{T.html("plugin.cart_readme.title")}</h2><p class="lead">{T.html("plugin.cart_readme.lead", lines=meta["lines"])}</p></div>
<div class="cartreadme">
<figure class="card"><div class="scroll" tabindex="0" role="region" aria-label="{T.attr("plugin.cart_readme.scroll_label")}">{strip.svg()}</div>
<figcaption><span>{T.html("plugin.cart_readme.caption")}</span><span class="code">{T.html("plugin.cart_readme.size", size=f"{meta['size']:,}")}</span></figcaption></figure>
<div class="cartreadme__text"><h3>{T.html("plugin.cart_readme.text_title")}</h3>
<pre class="plain">{e_(text)}</pre>
<p><a class="link" href="{registry.CART_README}">{registry.CART_README}</a></p></div>
</div></div></section>""", strip


def web_readme_section(e, text, live):
    tag = e["release"]["tag"]
    where = e["readme"]["web"]["url"] if e["readme"]["web"] else e["credits_url"]
    if text is None:
        link = link_or_text(where, T.html("plugin.readme.github_link"), live)
        body = f'<p class="warn">{T.html("plugin.readme.not_shown", link=link)}</p>'
        lead = T.html("plugin.readme.lead_not_shown")
    else:
        base = f"https://github.com/{e['repo']}/blob/{tag}/" if live else None
        body = f'<div class="prose">{markdown.render(text, base, 3, where if live else None)}</div>'
        lead = T.html("plugin.readme.lead", tag=e_(tag))
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
                     f'{link_or_text(h["url"], f"""<span class="code">{e_(h["tag"])}</span>""", live)}</p></div>'
                     f"{notes}</li>")
    return f"""<section class="section" id="notes" aria-labelledby="notes-title"><div class="container">
<div class="headblock"><h2 id="notes-title">{T.html("plugin.notes.title")}</h2><p class="lead">{T.html("plugin.notes.lead")}</p></div>
<ul class="rows rows--notes">{"".join(items)}</ul>
</div></section>"""


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
        action = (f'<div class="actions"><a class="btn" href="{e_(e["download"]["url"])}">'
                  f'{T.html("plugin.hero.download_button", file=e_(e["download"]["name"]))}</a>'
                  f'<a class="btn btn--secondary" href="{e_(e["source_url"])}">'
                  f'{T.html("plugin.hero.source_button")}</a></div>')
    else:
        action = (f'<div class="actions"><a class="btn" href="#install">{T.html("plugin.hero.example_button")}</a>'
                  f'</div><p class="note">{T.html("plugin.hero.example_note")}</p>')
    hero = f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{e_(e["name"])}</h1>
<p class="lead">{e_(e["description"])}</p>
{action}
</div>
{screen_card(details, T.html("plugin.hero.card_caption"), e["download"]["name"], "details",
             T.text("plugin.hero.card_alt", name=e["name"]))}
</div></section>"""

    size = f'{e["image"]["size"]:,}'
    image = (T.html("plugin.details.image_ram", size=size) if e["image"]["kind"] == "sram"
             else T.html("plugin.details.image_flash", size=size))
    # the details screen above already shows the header; these are what the check read in the release
    rows = [
        (T.html("plugin.details.release"), T.html("plugin.details.release_value", tag=e_(e["release"]["tag"]),
                                                  date=e_(e["release"]["published"]))),
        (T.html("plugin.details.image"), image),
        (T.html("plugin.details.api"), f'<span class="code">{e["api"]}</span>'),
        (T.html("plugin.details.github"), link_or_text(f"https://github.com/{e['repo']}", e_(e["repo"]), True) if live
         else T.html("plugin.details.not_public")),
        (T.html("plugin.details.license"), link_or_text(lic["url"], e_(lic["name"]), live)
         + (f'. {e_(lic["note"])}' if lic.get("note") else "")),
    ]
    rows.insert(4, (T.html("plugin.details.source"),
                    link_or_text(e["source_url"], T.html("plugin.details.source_value", tag=e_(e["release"]["tag"])),
                                 live)))
    items = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
    if e.get("credits"):        # the long ones run the full width, so the two columns stay even
        items += f'<div class="wide"><dt>{T.html("plugin.details.credits")}</dt><dd>{e_(e["credits"])}</dd></div>'
    items += (f'<div class="wide"><dt>{T.html("plugin.details.sha256")}</dt><dd><span class="code hash">'
              f'{e_(e["download"]["sha256"])}</span></dd></div>')
    specs = f"""<section class="section" aria-labelledby="specs-title"><div class="container">
<div class="headblock"><h2 id="specs-title">{T.html("plugin.details.title")}</h2><p class="lead">{T.html("plugin.details.lead")}</p></div>
<dl class="specs">{items}</dl>
</div></section>"""

    fname = e_(e["download"]["name"])
    steps = [(T.html("plugin.install.download_title", file=fname), T.html("plugin.install.download_text")),
             (T.html("plugin.install.copy_title"), T.html("plugin.install.copy_text"))]
    if e["opens"] and e["home"]:
        steps.append((T.html("plugin.install.files_title", folder=e_(e["home"])),
                      T.html("plugin.install.files_text", types=e_(opens(e)))))
    steps.append((T.html("plugin.install.start_title"), T.html("plugin.install.start_text", name=e_(e["name"]))))
    install = f"""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">{T.html("plugin.install.title")}</h2></div>
<ol class="steps{" steps--4" if len(steps) == 4 else ""}">{li_rows(steps)}</ol>
</div></section>"""
    desc = T.text("plugin.description", name=e["name"], version=e["version"], description=e["description"])
    return page(T.text("plugin.page_title", name=e["name"]), desc,
                hero + extra + specs + notes_section(e, live) + install,
                pre, "plugins", [details] + ([strip] if strip else []), entries, config)


# ---- the submit page ----------------------------------------------------------------

def submit_page(entries, config):
    form = f"https://github.com/{config['registry_repo']}/issues/new?template=submit-plugin.yml"
    nodes = T.rows("submit.steps.boxes", ("title", "text"))
    items = "".join(f'<li{" class=loop" if i == len(nodes) - 1 else ""}><h2>{t}</h2><p>{s}</p></li>'
                    for i, (t, s) in enumerate(nodes))
    # what a plugin needs, in a few lines
    need_rows = "".join(f"<li><b>{t}</b><span>{s}</span></li>" for t, s in
                        T.rows("submit.requirements.rows", ("title", "text"), readme_page="../authors/readme/",
                               screenshots_page="../authors/screenshots/"))
    if placeholder(config):
        primary = f'<a class="btn" aria-disabled="true">{T.html("submit.hero.issue_button")}</a>'
        soon = f'<p class="soon">{T.html("submit.hero.not_open")}</p>'
    else:
        primary, soon = f'<a class="btn" href="{e_(form)}">{T.html("submit.hero.issue_button")}</a>', ""
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("submit.hero.title")}</h1>
<p class="lead">{T.html("submit.hero.lead")}</p>
<div class="actions">{primary}<a class="btn btn--secondary" href="#rules">{T.html("submit.hero.rules_button")}</a></div>
{soon}
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


# ---- for authors: what a release needs, the three specs and the icon editor -----------

def template_link(config):
    text = T.html("authors.starter_kit")
    repo = config.get("template_repo") or ""
    if repo and repo.split("/")[0] != "OWNER":
        return f'<a class="link" href="https://github.com/{e_(repo)}">{text}</a>'
    return T.html("authors.starter_kit_not_public", starter_kit=text)


def spec_table(heads, rows, caption=None):
    head = "".join(f'<th scope="col">{h}</th>' for h in heads)
    body = "".join(f'<tr><th scope="row">{r[0]}</th>' + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>"
                   for r in rows)
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f'<table class="spec spec--rules spec--doc">{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def doc_section(sid, title, lead, body):
    lead = f'<p class="lead">{lead}</p>' if lead else ""
    return (f'<section class="section" id="{sid}" aria-labelledby="{sid}-title"><div class="container">'
            f'<div class="headblock"><h2 id="{sid}-title">{title}</h2>{lead}</div>\n{body}\n</div></section>')


def doc_hero(title, lead, actions, card):
    return f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{title}</h1>
<p class="lead">{lead}</p>
<div class="actions">{actions}</div>
</div>
{card}
</div></section>"""


def authors_close(pre):
    return f"""<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("authors.check.title")}</h2><p>{T.html("authors.check.text")}</p></div>
<pre class="cmd"><code>{T.block("authors.check.command")}</code></pre>
</div></section>"""


def authors_index(entries, config):
    needs = T.rows("authors.needs.rows", ("part", "status", "text"), readme_page="readme/",
                   screenshots_page="screenshots/", icons_page="icons/")
    cards = [
        ("readme/", T.html("authors.pages.readme_title"), T.html("authors.pages.readme_text")),
        ("screenshots/", T.html("authors.pages.screenshots_title"), T.html("authors.pages.screenshots_text")),
        ("icons/", T.html("authors.pages.icons_title"), T.html("authors.pages.icons_text")),
        ("icon-editor/", T.html("authors.pages.editor_title"), T.html("authors.pages.editor_text")),
    ]
    tiles = "".join(f'<li><h2><a href="{h}">{t}</a></h2><p>{d}</p></li>' for h, t, d in cards)
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("authors.hero.title")}</h1>
<p class="lead">{T.html("authors.hero.lead")}</p>
<div class="actions"><a class="btn" href="../submit/">{T.html("authors.hero.submit_button")}</a><a class="btn btn--secondary" href="icon-editor/">{T.html("authors.hero.editor_button")}</a></div>
<p class="soon">{T.html("authors.hero.starter_note", starter_kit=template_link(config))}</p>
</div>
<ol class="map map--links" aria-label="{T.attr("authors.pages.label")}">{tiles}</ol>
</div></section>
{doc_section("needs", T.html("authors.needs.title"), T.html("authors.needs.lead"),
             spec_table(T.list("authors.needs.columns"), needs))}
{authors_close("../")}"""
    return page(T.text("authors.page_title"), T.text("authors.description"), body, "../", "authors", [],
                entries, config)


def readme_doc(entries, config):
    cart = cvreadme_text(T.raw("authors.readme.hero.sample"))
    screen = tvscreen.readme_page("Star Sweeper", cart)
    card = screen_card(screen, T.html("authors.readme.hero.card_caption"), T.text("authors.readme.hero.card_code"))
    body = f"""{doc_hero(T.html("authors.readme.hero.title"), T.html("authors.readme.hero.lead"),
                     f'<a class="btn" href="#write">{T.html("authors.readme.hero.write_button")}</a>'
                     f'<a class="btn btn--secondary" href="#format">{T.html("authors.readme.hero.format_button")}</a>',
                     card)}
{doc_section("write", T.html("authors.readme.write.title"), T.html("authors.readme.write.lead"),
             '<ul class="rows">' + li_rows(T.rows("authors.readme.write.rows", ("title", "text"))) + '</ul>')}
{doc_section("cart", T.html("authors.readme.convert.title"), T.html("authors.readme.convert.lead"),
             spec_table(T.list("authors.readme.convert.columns"),
                        T.rows("authors.readme.convert.rows", ("markdown", "cart")))
             + f'<pre class="cmd"><code>{T.block("authors.readme.convert.command")}</code></pre>'
             + f'<p class="docnote">{T.html("authors.readme.convert.note", starter_kit=template_link(config))}</p>')}
{doc_section("format", T.html("authors.readme.format.title"), T.html("authors.readme.format.lead"),
             spec_table(T.list("authors.readme.format.columns"),
                        T.rows("authors.readme.format.rows", ("where", "type", "what"))))}
{doc_section("checks", T.html("authors.readme.checks.title"), T.html("authors.readme.checks.lead"),
             spec_table(T.list("authors.readme.checks.columns"),
                        T.rows("authors.readme.checks.rows", ("check", "rule", "result"))))}
{doc_section("web", T.html("authors.readme.web.title"), T.html("authors.readme.web.lead"),
             spec_table(T.list("authors.readme.web.columns"), T.rows("authors.readme.web.rows", ("part", "what"))))}
{authors_close("../../")}"""
    return page(T.text("authors.readme.page_title"), T.text("authors.readme.description"), body,
                "../../", "authors", [screen], entries, config)


def cvreadme_text(md):
    import cvreadme
    return cvreadme.convert(md)


def screenshots_doc(entries, config):
    pick = next((e for e in sorted(entries, key=lambda e: e["name"].lower()) if e["screenshots"]), None)
    if pick:
        src = f'../../plugins/{e_(pick["id"])}/{pick["screenshots"][0]["file"]}'
        card = (f'<figure class="card shot shot--hero"><div class="shot__tv"><img src="{src}" width="{png.WIDTH}" '
                f'height="{png.HEIGHT}" alt="{T.attr("authors.screenshots.hero.card_alt", name=e_(pick["name"]))}">'
                f'</div><figcaption><span>{T.html("authors.screenshots.hero.card_caption")}</span>'
                f'<span class="code">{png.WIDTH} × {png.HEIGHT}</span></figcaption></figure>')
    else:
        card = screen_card(tvscreen.plugins_page(entries), T.html("authors.screenshots.hero.fallback_caption"),
                           T.text("authors.screenshots.hero.fallback_code"))
    sizes = dict(width=png.WIDTH, height=png.HEIGHT, max_kb=png.MAX_BYTES // 1024)
    body = f"""{doc_hero(T.html("authors.screenshots.hero.title"), T.html("authors.screenshots.hero.lead"),
                     f'<a class="btn" href="#spec">{T.html("authors.screenshots.hero.spec_button")}</a>'
                     f'<a class="btn btn--secondary" href="#taking">{T.html("authors.screenshots.hero.taking_button")}</a>',
                     card)}
{doc_section("spec", T.html("authors.screenshots.spec.title"), T.html("authors.screenshots.spec.lead"),
             spec_table(T.list("authors.screenshots.spec.columns"),
                        T.rows("authors.screenshots.spec.rows", ("name", "rule"), **sizes)))}
{doc_section("show", T.html("authors.screenshots.show.title"), None,
             '<ul class="rows">' + li_rows(T.rows("authors.screenshots.show.rows", ("title", "text"))) + '</ul>')}
{doc_section("taking", T.html("authors.screenshots.taking.title"), T.html("authors.screenshots.taking.lead"),
             '<ul class="rows">' + li_rows(T.rows("authors.screenshots.taking.rows", ("title", "text"))) + '</ul>')}
{doc_section("refused", T.html("authors.screenshots.refused.title"), T.html("authors.screenshots.refused.lead"),
             spec_table(T.list("authors.screenshots.refused.columns"),
                        T.rows("authors.screenshots.refused.rows", ("what", "example"))))}
{doc_section("used", T.html("authors.screenshots.used.title"), T.html("authors.screenshots.used.lead"),
             spec_table(T.list("authors.screenshots.used.columns"),
                        T.rows("authors.screenshots.used.rows", ("place", "how"))))}
{authors_close("../../")}"""
    return page(T.text("authors.screenshots.page_title"), T.text("authors.screenshots.description"),
                body, "../../", "authors", [], entries, config)


def big_icon(hexstr, colour, label, caption):
    """label is plain text (tvscreen escapes it), caption html"""
    return (f'<figure class="iconfig">{tvscreen.icon_svg(hexstr, colour, label)}'
            f"<figcaption>{caption}</figcaption></figure>")


PAD_ICON = "3c4299819999423c"       # the Pad Test plugin's: firmware/revc/padtest/padtest_icon.txt


def icons_doc(entries, config):
    icons = tvscreen.MENU["icons"]
    with_icons = [e for e in entries if e["icon"] != "00" * 8] or entries
    screen = tvscreen.plugins_page(with_icons)
    card = screen_card(screen, T.html("authors.icons.hero.card_caption"), T.text("authors.icons.hero.card_code"))
    rows = cvp.icon_rows(PAD_ICON)
    txt = "\n".join(rows)
    hexs = " ".join(PAD_ICON[i:i + 2] for i in range(0, 16, 2))
    family = "".join([
        big_icon(icons["folder"], "y", T.text("authors.icons.family.folder_label"),
                 T.html("authors.icons.family.folder_caption")),
        big_icon(icons["cart"], "c", T.text("authors.icons.family.rom_label"),
                 T.html("authors.icons.family.rom_caption")),
        big_icon(icons["file"], "g", T.text("authors.icons.family.file_label"),
                 T.html("authors.icons.family.file_caption")),
        big_icon(icons["plugin"], "m", T.text("authors.icons.family.plug_label"),
                 T.html("authors.icons.family.plug_caption")),
        big_icon(PAD_ICON, "m", T.text("authors.icons.family.padtest_label"),
                 T.html("authors.icons.family.padtest_caption")),
    ])
    body = f"""{doc_hero(T.html("authors.icons.hero.title"), T.html("authors.icons.hero.lead"),
                     f'<a class="btn" href="../icon-editor/">{T.html("authors.icons.hero.editor_button")}</a>'
                     f'<a class="btn btn--secondary" href="#txt">{T.html("authors.icons.hero.txt_button")}</a>', card)}
{doc_section("spec", T.html("authors.icons.spec.title"), T.html("authors.icons.spec.lead"),
             spec_table(T.list("authors.icons.spec.columns"), T.rows("authors.icons.spec.rows", ("name", "rule"))))}
{doc_section("txt", T.html("authors.icons.txt.title"), T.html("authors.icons.txt.lead"),
             f'<div class="pair"><div><h3>{T.html("authors.icons.txt.file_title")}</h3>'
             f'<pre class="cmd"><code>{txt}</code></pre></div>'
             f'<div><h3>{T.html("authors.icons.txt.header_title")}</h3><pre class="cmd"><code>{hexs}</code></pre>'
             f'<p class="docnote">{T.html("authors.icons.txt.note")}</p></div></div>'
             f'<pre class="cmd"><code>{T.block("authors.icons.txt.command")}</code></pre>')}
{doc_section("design", T.html("authors.icons.design.title"), T.html("authors.icons.design.lead"),
             f'<div class="iconrow">{family}</div>'
             '<ul class="rows">' + li_rows(T.rows("authors.icons.design.rows", ("title", "text"))) + '</ul>')}
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">{T.html("authors.icons.close.title")}</h2><p>{T.html("authors.icons.close.text")}</p></div>
<div class="actions"><a class="btn" href="../icon-editor/">{T.html("authors.icons.close.editor_button")}</a></div>
</div></section>"""
    return page(T.text("authors.icons.page_title"), T.text("authors.icons.description"), body, "../../", "authors",
                [screen], entries, config)


def pad(kind, title, title_attr, note, colour, name):
    """an icon's drawing grid and tools; title and note are html, title_attr the title for attributes"""
    cells = "".join(
        f'<button type="button" class="px__c" aria-pressed="false" '
        f'aria-label="{T.attr("authors.editor.cell_label", row=y + 1, column=x + 1)}" '
        f'data-x="{x}" data-y="{y}"{"" if x == y == 0 else " tabindex=-1"}></button>'
        for y in range(8) for x in range(8))
    return f"""<fieldset class="pad" data-pad="{kind}">
<legend><b>{title}</b> <span>{note}</span></legend>
<div class="px px--{colour}" role="group" aria-label="{T.attr("authors.editor.grid_label", icon=title_attr)}" aria-describedby="keys">{cells}</div>
<div class="pad__tools" role="group" aria-label="{T.attr("authors.editor.tools_label")}">
<button type="button" class="tool" data-do="clear">{T.html("authors.editor.clear")}</button>
<button type="button" class="tool" data-do="invert">{T.html("authors.editor.invert")}</button>
<button type="button" class="tool" data-do="left" aria-label="{T.attr("authors.editor.move_left")}">&larr;</button>
<button type="button" class="tool" data-do="right" aria-label="{T.attr("authors.editor.move_right")}">&rarr;</button>
<button type="button" class="tool" data-do="up" aria-label="{T.attr("authors.editor.move_up")}">&uarr;</button>
<button type="button" class="tool" data-do="down" aria-label="{T.attr("authors.editor.move_down")}">&darr;</button>
</div>
<label class="field">{T.html("authors.editor.hex_label")}<input class="code" type="text" data-hex value="0000000000000000"
 maxlength="64" spellcheck="false" autocomplete="off" autocapitalize="off"></label>
<label class="field">{name}<textarea class="code" data-txt rows="8" cols="8" spellcheck="false"
 autocomplete="off" autocapitalize="off">{chr(10).join(["........"] * 8)}</textarea></label>
<div class="actions">
<button type="button" class="btn" data-save="{name}">{T.html("authors.editor.save_button", file=name)}</button>
<label class="btn btn--secondary filebtn">{T.html("authors.editor.open_button")}<input class="visually-hidden" type="file" data-open accept=".txt,text/plain"></label>
<button type="button" class="btn btn--secondary" data-copy>{T.html("authors.editor.copy_button")}</button>
</div>
<p class="pad__msg" role="status" aria-live="polite" data-msg></p>
</fieldset>"""


def icon_editor(entries, config):
    icons = tvscreen.MENU["icons"]
    a, b = tvscreen.editor_pages("ed-plugin", "ed-file")
    plugin_pad = pad("plugin", T.html("authors.editor.plugin_icon"), T.attr("authors.editor.plugin_icon"),
                     T.html("authors.editor.plugin_icon_note"), "m", "icon.txt")
    file_pad = pad("file", T.html("authors.editor.file_icon"), T.attr("authors.editor.file_icon"),
                   T.html("authors.editor.file_icon_note"), "g", "file_icon.txt")
    body = f"""<section class="banner banner--tool" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">{T.html("authors.editor.title")}</h1>
<p class="lead">{T.html("authors.editor.lead")}</p>
</div>
<noscript><p class="warn">{T.html("authors.editor.no_script", txt_section="../icons/#txt")}</p></noscript>
<div class="editor" data-editor data-plug="{icons["plugin"]}" data-file="{icons["file"]}">
<div class="editor__pads">
{plugin_pad}
{file_pad}
<p class="docnote" id="keys">{T.html("authors.editor.keys")}</p>
</div>
<div class="editor__preview" aria-label="{T.attr("authors.editor.preview_label")}">
{screen_card(a, T.html("authors.editor.plugins_caption"), T.text("authors.editor.plugins_code"))}
{screen_card(b, T.html("authors.editor.folder_caption"), T.text("authors.editor.folder_code"))}
<p class="docnote">{T.html("authors.editor.sdk_note", icons_page="../icons/")}</p>
</div>
</div>
</div></section>"""
    return page(T.text("authors.editor.page_title"), T.text("authors.editor.description"), body, "../../",
                "authors", [a, b], entries, config, scripts=("icon-editor.js",))


def authors_pages(entries, config):
    return {
        "authors/index.html": authors_index(entries, config),
        "authors/readme/index.html": readme_doc(entries, config),
        "authors/screenshots/index.html": screenshots_doc(entries, config),
        "authors/icons/index.html": icons_doc(entries, config),
        "authors/icon-editor/index.html": icon_editor(entries, config),
    }


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 12 12" shape-rendering="crispEdges">
<rect x="-2" y="-2" width="12" height="12" fill="{bg}"/><path fill="{fg}" d="{d}"/></svg>
"""


def build(out, config=None, root=ROOT):
    """the site for the entries under root (the registry's own files by default)"""
    config = config or registry.load_config(root)
    live = registry.load_entries(root)
    entries = list(live.values())
    if config.get("show_examples"):
        entries += [e for e in registry.load_entries(root, examples=True).values() if e["id"] not in live]
    for e in entries:
        bad = registry.check_entry(e)
        bad = bad or registry.check_files(registry.files_dir(root, e["id"], bool(e.get("example"))), e)
        if bad:
            raise SystemExit(f"{e.get('id')}: {bad}")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "assets"))
    for name in ("tokens.css", "base.css", "site.css", "site.js", "icon-editor.js",
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
    for rel, text in authors_pages(entries, config).items():
        write(rel, text)
    registry.write_json(os.path.join(out, "registry.json"), registry.index(live, config))
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
    if placeholder(registry.load_config(ROOT)):
        print("note: registry_repo is still OWNER/...: the Submit button stays off until it names the real repository")
    print(f"built {a.out}: the catalogue, {len(entries)} plugin pages, the authors' pages with the icon editor, "
          "the submit page and registry.json")


if __name__ == "__main__":
    main()
