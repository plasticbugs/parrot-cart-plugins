"""build_site -- the registry's static site, from plugins/ (and the examples).

    python3 tools/build_site.py [--out _site]

Writes OUT/index.html (the catalogue), OUT/plugins/<id>/index.html (a page
a plugin, with its screenshots and the cart's README text beside it),
OUT/authors/ (what a release needs: the README, screenshot and icon pages,
and the icon editor), OUT/submit/index.html, OUT/registry.json (the index
for installers) and OUT/assets/. A plugin's README.md and release notes are
rendered by tools/markdown.py: no raw HTML, no scripts, no pictures from
other sites. The TV screens are drawn from each plugin's
header in the cart menu's own font (tools/tvscreen.py). Standard library
only; links are relative, so the site works from any folder or host path.

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


def kb(n):
    return f"{(n + 1023) // 1024}K"


def needs(e):
    return ", ".join(NEEDS[u] for u in e["uses"])


def opens(e):
    return " ".join(e["opens"])


# ---- the frame of every page --------------------------------------------------------

def slab(pre, current):
    def link(href, text, key):
        cur = ' aria-current="page"' if key == current else ""
        return f'<li><a href="{href}"{cur}>{text}</a></li>'
    return (f'<header class="slab"><div class="container">'
            f'<a class="wordmark" href="{pre}index.html" aria-label="Parrot Cart plugins, the catalogue" '
            f'><img src="{pre}assets/parrot-cart-mark.svg" width="24" height="28" alt="">Parrot Cart plugins</a>'
            f'<nav aria-label="The registry"><ul>'
            + link(f"{pre}index.html#plugins", "Plugins", "plugins")
            + link(f"{pre}index.html#install", "Install", "install")
            + link(f"{pre}authors/", "For authors", "authors")
            + link(f"{pre}submit/", "Submit a plugin", "submit")
            + "</ul></nav></div></header>")


def placeholder(config):
    """the registry's repository is still the OWNER/... stand-in: nothing on GitHub to link to yet"""
    return config["registry_repo"].split("/")[0] == "OWNER"


def footer(pre, entries, config):
    repo = ("" if placeholder(config) else
            f'\n<li><a href="https://github.com/{e_(config["registry_repo"])}">Its source on GitHub</a></li>')
    names = "".join(f'<li><a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a></li>'
                    for e in sorted(entries, key=lambda e: e["name"].lower()))
    return f"""<footer class="foot"><div class="container">
<div class="cols">
<div><h2>Parrot Cart plugins</h2><p>Free plugins for your Parrot Flash cartridge, all in one place.</p></div>
<div><h2>Plugins</h2><ul>{names}</ul></div>
<div><h2>The registry</h2><ul><li><a href="{pre}submit/">Submit a plugin</a></li><li><a href="{pre}submit/#rules">The rules</a></li>
<li><a href="{pre}authors/">For plugin authors</a></li><li><a href="{pre}authors/icon-editor/">The icon editor</a></li>
<li><a href="{pre}index.html#install">Install a plugin</a></li><li><a href="{pre}registry.json">registry.json</a></li>{repo}</ul></div>
</div>
<p class="fine">The TV screens use the cart menu's font, Empty Windows Unboxed by VEXED,
<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.</p>
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
<a class="skip" href="#main">Skip to content</a>
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
            part = part.replace("&#x27;", "\u2019").replace("'", "\u2019")
        out.append(part)
    return "".join(out)


def screen_card(screen, caption, code, slot=None, alt=None, extra=""):
    slot_attr = f' data-slot="{slot}" data-alt="{e_(alt)}"' if slot else ""
    return (f'<figure class="card{extra}"><div class="screen"{slot_attr} data-kind="product">{screen.svg()}</div>'
            f'<figcaption><span>{caption}</span><span class="code">{e_(code)}</span></figcaption></figure>')


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
    for e in sorted(entries, key=lambda e: e["name"].lower()):
        text = " ".join([e["name"], e["id"], opens(e), needs(e), e["by"], e["owner"], e["description"]]).lower()
        who = "Example" if e.get("example") else "By " + e_(e["by"] or e["owner"])
        rows.append(
            f'<tr data-text="{e_(text)}">'
            f'<td class="first"><div class="plugin">{thumb(e, pre)}'
            f'<div><a href="{pre}plugins/{e_(e["id"])}/">{e_(e["name"])}</a><small>{who}</small></div></div></td>'
            f'<td data-label="ID"><span class="code code--id">{e_(e["id"])}</span></td>'
            f'<td data-label="Opens">{f"<span class=code>{e_(opens(e))}</span>" if e["opens"] else "<span class=muted>An app</span>"}</td>'
            f'<td data-label="Needs">{e_(needs(e)) or "<span class=muted>None</span>"}</td>'
            f'<td data-label="Version" class="num"><span class="code">{e_(e["version"])}</span></td>'
            f'<td data-label="Size" class="num"><span class="code">{kb(e["download"]["size"])}</span></td></tr>')
    return "".join(rows)


def home(entries, config):
    examples = [e for e in entries if e.get("example")]
    plugins_screen = tvscreen.plugins_page(entries)
    screens = [plugins_screen]
    if len(examples) == len(entries):
        line = f"{len(entries)} examples from the cart's own plugins, shown until the first submissions."
    else:
        line = f"{len(entries) - len(examples)} plugins, each a free download from its author's release."
    body = [f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">Plugins for your Parrot&nbsp;Cart</h1>
<p class="lead">Emulators, utilities and more to enhance your ColecoVision.</p>
<div class="actions"><a class="btn" href="#plugins">See the plugins</a><a class="btn btn--secondary" href="submit/">Submit a plugin</a></div>
</div>
{screen_card(plugins_screen, "The cart's Plugins page", "/PLUGINS", "hero-screen",
             "A photograph of a TV showing the cart's Plugins page with these plugins")}
</div></section>""",
            f"""<section class="section" id="plugins" aria-labelledby="plugins-title"><div class="container">
<div class="headblock"><h2 id="plugins-title">Browse Plugins</h2><p class="lead">{e_(line)}</p></div>
<div class="finder" data-finder="catalogue" data-empty="catalogue-empty" hidden>
<label for="q">Search by name or file type<input id="q" type="search" autocomplete="off" spellcheck="false"></label>
<p role="status" aria-live="polite"></p></div>
<table class="spec" id="catalogue">
<thead><tr><th scope="col">Plugin</th><th scope="col">ID</th><th scope="col">Opens</th><th scope="col">Needs</th>
<th scope="col" class="num">Version</th><th scope="col" class="num">Size</th></tr></thead>
<tbody>{catalogue_rows(entries)}</tbody></table>
<p class="empty" id="catalogue-empty" hidden>No plugin matches that. Try a file type such as .nes, or clear the search.</p>
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
            ("before", "Before", f"Three {e_(ext)} files in {e_(folder)}, and the menu hides them.",
             before, folder),
            ("copied", "Copied", f"{f} in /PLUGINS: the Plugins page lists it.", listed,
             "/PLUGINS"),
            ("after", "After", "The files show, with its icon. A opens one.",
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
<div class="headblock"><h2 id="change-title">How plugins work with files</h2><p class="lead">The card only shows files
that are associated with a plugin.</p></div>
<div class="switch" data-switch>
<div class="switch__tabs" role="tablist" aria-label="The card, a step at a time" aria-orientation="vertical">{tabs}</div>
<div class="switch__panels">{panels}</div>
</div></div></section>""")

    body.append("""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">No installer. Manage your plugins on the cartridge.</h2><p class="lead">Three
easy steps.</p></div>
<ol class="steps">
<li><h3>Download its .CVP</h3><p>From its page here.</p></li>
<li><h3>Copy it to /PLUGINS</h3><p>On the cart's microSD card.</p></li>
<li><h3>Start it from Plugins</h3><p>B for Home, then Plugins, the plugin and A.</p></li>
</ol></div></section>""")

    body.append(f"""<section class="band band--ink figure-band" id="flash" aria-labelledby="flash-title"><div class="container">
<div><p class="big" aria-hidden="true">{FLASH_SLOTS}</p><h2 id="flash-title"><span class="visually-hidden">{FLASH_SLOTS} </span>plugins
stay ready in the cart's flash</h2></div>
<ul class="ruled">
<li><b>The first start</b><span>copies it into a 1 MB slot, once a version.</span></li>
<li><b>A new version</b><span>reuses its old slot.</span></li>
<li><b>One plugin more</b><span>takes the slot used longest ago.</span></li>
<li><b>Removing it</b><span>frees its slot too.</span></li>
</ul></div></section>""")

    body.append("""<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Add your plugin by submitting a GitHub issue in the registry.</h2><p>A bot checks the release; a
maintainer merges.</p></div>
<div class="actions"><a class="btn" href="submit/">Submit a plugin</a>
<a class="btn btn--secondary" href="registry.json">registry.json</a></div>
</div></section>""")
    return page("Parrot Cart plugins", "Free plugins for Parrot Cart, the ColecoVision cart with a microSD slot: "
                "emulators and tools, each one .CVP file to copy to /PLUGINS.", "\n".join(body), "", "plugins",
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
        f'height="{png.HEIGHT}" alt="{e_(e["name"])} on the TV, picture {i} of {n}" loading="lazy" '
        f'decoding="async"></div><figcaption><span>Picture {i}</span>'
        f'<span class="code">{png.WIDTH} x {png.HEIGHT}</span></figcaption></figure>'
        for i, s in enumerate(e["screenshots"], 1))
    lead = ("Drawn by the cart's menu for this example; a listed plugin shows its author's own."
            if e.get("example") else "From its release, pixel for pixel as the console draws them.")
    return f"""<section class="section" id="screenshots" aria-labelledby="shots-title"><div class="container">
<div class="headblock"><h2 id="shots-title">On the TV</h2><p class="lead">{lead}</p></div>
<div class="shots" data-n="{n}">{figs}</div>
</div></section>"""


def cart_readme_section(e, text, pre):
    """the .CVP's README text as it is, in the menu's font, and the same text to read or copy"""
    if text is None:
        return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">No README on the cart</h2><p class="lead">This plugin's .CVP has no
README inside, so the cart has none to show for it.</p></div>
<p class="warn"><b>For its author:</b> build it with the SDK from a README.md and the next release puts its
instructions and credits on the TV. <a class="link" href="{pre}authors/readme/">How the README works</a></p>
</div></section>""", None
    strip = tvscreen.readme_strip(text)
    meta = e["readme"]["cart"]
    return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">Its README, on the cart</h2><p class="lead">The text inside the .CVP, as it
is: {meta["lines"]} lines of 30 columns in the menu's font.</p></div>
<div class="cartreadme">
<figure class="card"><div class="scroll" tabindex="0" role="region" aria-label="The README in the cart's font; the same text follows">{strip.svg()}</div>
<figcaption><span>From the plugin's details on the cart</span><span class="code">{meta["size"]:,} bytes</span></figcaption></figure>
<div class="cartreadme__text"><h3>The same text</h3>
<pre class="plain">{e_(text)}</pre>
<p><a class="link" href="{registry.CART_README}">{registry.CART_README}</a></p></div>
</div></div></section>""", strip


def web_readme_section(e, text, live):
    tag = e["release"]["tag"]
    where = e["readme"]["web"]["url"] if e["readme"]["web"] else e["credits_url"]
    if text is None:
        body = (f'<p class="warn">Its README isn\'t shown here (it isn\'t Markdown, or it is over 64K). '
                f'{link_or_text(where, "Read it on GitHub", live)}.</p>')
        lead = "Kept in its repository."
    else:
        base = f"https://github.com/{e['repo']}/blob/{tag}/" if live else None
        body = f'<div class="prose">{markdown.render(text, base, 3, where if live else None)}</div>'
        lead = (f'README.md at <span class="code">{e_(tag)}</span>. Its pictures are links: this site loads '
                "nothing from anywhere else.")
    return f"""<section class="section" id="readme" aria-labelledby="readme-title"><div class="container">
<div class="headblock"><h2 id="readme-title">Its README</h2><p class="lead">{lead}</p></div>
{body}
</div></section>"""


def notes_section(e, live):
    """each listed version's release notes, newest first"""
    base = f"https://github.com/{e['repo']}/blob/{e['release']['tag']}/" if live else None
    items = []
    for h in e["history"]:
        notes = (f'<div class="prose">{markdown.render(h["notes"], base, 4)}</div>' if h["notes"].strip()
                 else '<p class="muted">This release has no notes.</p>')
        items.append(f'<li><div><h3>{e_(h["version"])}</h3><p class="muted">{e_(h["published"])}, '
                     f'{link_or_text(h["url"], f"""<span class="code">{e_(h["tag"])}</span>""", live)}</p></div>'
                     f"{notes}</li>")
    return f"""<section class="section" id="notes" aria-labelledby="notes-title"><div class="container">
<div class="headblock"><h2 id="notes-title">Release notes</h2><p class="lead">From each release listed here,
newest first.</p></div>
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
        action = (f'<div class="actions"><a class="btn" href="{e_(e["download"]["url"])}">Download '
                  f'{e_(e["download"]["name"])}</a>'
                  f'<a class="btn btn--secondary" href="{e_(e["source_url"])}">Its source</a></div>')
    else:
        action = ('<div class="actions"><a class="btn" href="#install">Put it on your cart</a></div>'
                  '<p class="note">An example: its repository isn\'t public yet, so nothing downloads.</p>')
    hero = f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{e_(e["name"])}</h1>
<p class="lead">{e_(e["description"])}</p>
{action}
</div>
{screen_card(details, "Its details page on the cart", e["download"]["name"], "details",
             f"A photograph of a TV showing the cart's details page for {e['name']}")}
</div></section>"""

    kind = "loaded into RAM" if e["image"]["kind"] == "sram" else "run in place from flash"
    # the details screen above already shows the header; these are what the check read in the release
    rows = [
        ("Release", f'<span class="code">{e_(e["release"]["tag"])}</span>, {e_(e["release"]["published"])}'),
        ("Image", f'{e["image"]["size"]:,} bytes, {kind}'),
        ("Plugin API", f'<span class="code">{e["api"]}</span>'),
        ("GitHub", link_or_text(f"https://github.com/{e['repo']}", e_(e["repo"]), True) if live
         else "Not public yet"),
        ("Licence", link_or_text(lic["url"], e_(lic["name"]), live)
         + (f'. {e_(lic["note"])}' if lic.get("note") else "")),
    ]
    rows.insert(4, ("Source", link_or_text(e["source_url"], f'At <span class="code">{e_(e["release"]["tag"])}</span>',
                                           live)))
    items = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
    if e.get("credits"):        # the long ones run the full width, so the two columns stay even
        items += f'<div class="wide"><dt>Credits</dt><dd>{e_(e["credits"])}</dd></div>'
    items += (f'<div class="wide"><dt>SHA-256</dt><dd><span class="code hash">{e_(e["download"]["sha256"])}</span>'
              "</dd></div>")
    specs = f"""<section class="section" aria-labelledby="specs-title"><div class="container">
<div class="headblock"><h2 id="specs-title">Its release, as checked</h2><p class="lead">As read from GitHub
when it was listed.</p></div>
<dl class="specs">{items}</dl>
</div></section>"""

    fname = e_(e["download"]["name"])
    steps = [f"<li><h3>Download {fname}</h3><p>Its SHA-256 is above.</p></li>",
             "<li><h3>Copy it to /PLUGINS</h3><p>On the cart's microSD card.</p></li>"]
    if e["opens"] and e["home"]:
        steps.append(f'<li><h3>Put files in {e_(e["home"])}</h3><p>Its {e_(opens(e))} files.</p></li>')
    steps.append(f'<li><h3>Start it</h3><p>Home, Plugins, {e_(e["name"])}, then A.</p></li>')
    install = f"""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">Put it on your cart</h2></div>
<ol class="steps{" steps--4" if len(steps) == 4 else ""}">{"".join(steps)}</ol>
</div></section>"""
    desc = f"{e['name']} {e['version']} for Parrot Cart: {e['description']}"
    return page(f"{e['name']}, a Parrot Cart plugin", desc, hero + extra + specs + notes_section(e, live) + install,
                pre, "plugins", [details] + ([strip] if strip else []), entries, config)


# ---- the submit page ----------------------------------------------------------------

def submit_page(entries, config):
    form = f"https://github.com/{config['registry_repo']}/issues/new?template=submit-plugin.yml"
    nodes = [
        ("Your release", "The .CVP, a LICENSE, credits."),
        ("An issue", "owner/repo and one line."),
        ("The check", "Reads it as the menu does."),
        ("A pull request", "Adds its entry."),
        ("A maintainer", "Checks credits, then merges."),
        ("This site", "Lists it in registry.json."),
        ("SD cards", "Owners copy it to /PLUGINS."),
        ("Your next release", "Found within a day."),
    ]
    items = "".join(f'<li{" class=loop" if i == len(nodes) - 1 else ""}><h2>{t}</h2><p>{s}</p></li>'
                    for i, (t, s) in enumerate(nodes))
    # one table: each rule, what it takes, and who checks it
    rules = [
        ("The .CVP", "Read as the menu reads it; it fits a 1 MB slot.", "Bot"),
        ("Its README", 'Inside the .CVP for the cart, if it has one: <a class="link" href="../authors/readme/">30 '
         "columns of plain text</a>.", "Bot"),
        ("Screenshots", 'Up to three, if any: <a class="link" href="../authors/screenshots/">256 x 192 PNGs</a>.',
         "Both"),
        ("The version", "Newer than the one listed.", "Bot"),
        ("The ID", "Yours alone.", "Bot"),
        ("Open source", "Public, with the full source and a LICENSE.", "Bot"),
        ("Credited", "A README crediting whose work it uses.", "Both"),
        ("Free", "Never sold, or bundled with anything sold.", "Maintainer"),
    ]
    rule_rows = "".join(f'<tr><th scope="row">{t}</th><td>{s}</td><td class="by" data-label="Checked by">{w}</td></tr>'
                        for t, s, w in rules)
    if placeholder(config):
        primary = ('<a class="btn" aria-disabled="true">Open a submission</a>')
        soon = '<p class="soon">Submissions open once the registry is on GitHub.</p>'
    else:
        primary, soon = f'<a class="btn" href="{e_(form)}">Open a submission</a>', ""
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Submit an Issue in the repository to add your Plugin</h1>
<p class="lead">Name the repository; a bot checks its release and opens a PR.</p>
<div class="actions">{primary}<a class="btn btn--secondary" href="#rules">Read the rules</a></div>
{soon}
</div>
<ol class="map" aria-label="From your release to the cart, in order">{items}</ol>
<p class="map-legend">Nothing in your repository runs.</p>
</div></section>
<section class="section" id="rules" aria-labelledby="rules-title"><div class="container">
<div class="headblock"><h2 id="rules-title">Free, open, credited</h2></div>
<table class="spec spec--rules"><thead><tr><th scope="col">Rule</th><th scope="col">What it takes</th>
<th scope="col">Checked by</th></tr></thead>
<tbody>{rule_rows}</tbody></table>
</div></section>
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Check a build before releasing it</h2><p>In a clone of this registry, it prints each
field and anything the cart would refuse.</p></div>
<pre class="cmd"><code>python3 tools/cvp.py YOURPLUGIN.CVP</code></pre>
</div></section>"""
    return page("Submit a plugin to Parrot Cart plugins",
                "How to list a Parrot Cart plugin: one GitHub issue naming its repository; a bot checks the "
                "release and opens the pull request.", body, "../", "submit", [], entries, config)


# ---- for authors: what a release needs, the three specs and the icon editor -----------

SAMPLE_README = """# Star Sweeper

A small game for Parrot Cart: clear the sky before the sun comes up.

## Controls

- Joystick: move
- Left button: sweep
- `*`: pause

## Credits

Code and art by **A. Author**. Sound driver from the [Parrot Cart SDK](https://example.com/sdk).

## Source

https://github.com/author/star-sweeper
"""


def template_link(config, text="the starter kit"):
    repo = config.get("template_repo") or ""
    if repo and repo.split("/")[0] != "OWNER":
        return f'<a class="link" href="https://github.com/{e_(repo)}">{text}</a>'
    return f"{text} (not public yet)"


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
<div><h2 id="close-title">Check a build before releasing it</h2><p>In a clone of this registry, it prints each
field, the README it found and anything the cart would refuse.</p></div>
<pre class="cmd"><code>python3 tools/cvp.py YOURPLUGIN.CVP</code></pre>
</div></section>"""


def authors_index(entries, config):
    needs = [
        ("The .CVP", "Required", "Built with the SDK. The registry reads it as the cart's menu does."),
        ("LICENSE", "Required", "In the repository, at the release's tag."),
        ("README.md", "Required", 'Credits and a link to the source. The SDK also puts it <a class="link" '
         'href="readme/">inside the .CVP</a>, for the TV.'),
        ("Release notes", "Optional", "The release's own text on GitHub. Shown for each version listed."),
        ("Screenshots", "Optional", '<a class="link" href="screenshots/">Up to three PNGs</a>, 256 x 192, '
         "attached to the release."),
        ("Two icons", "Optional", '<a class="link" href="icons/">8 x 8, one bit a pixel</a>: the plugin\'s and '
         "its files'."),
    ]
    cards = [
        ("readme/", "The README", "One README.md: rendered on its page here, and as 30 columns of text on the cart."),
        ("screenshots/", "Screenshots", "The console's picture, 256 x 192, in the TV's frame."),
        ("icons/", "Icons", "Two 8 x 8 bitmaps in the header, coloured by the menu."),
        ("icon-editor/", "The icon editor", "Draw both, see them on the menu, save the .txt files."),
    ]
    tiles = "".join(f'<li><h2><a href="{h}">{t}</a></h2><p>{d}</p></li>' for h, t, d in cards)
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Packaging your plugin</h1>
<p class="lead">A .CVP, a licence and a README list a plugin. Screenshots and icons make it easy to find.</p>
<div class="actions"><a class="btn" href="../submit/">Submit a plugin</a><a class="btn btn--secondary" href="icon-editor/">Open the icon editor</a></div>
<p class="soon">Start from {template_link(config)}: a plugin that builds, with a README, icons and a release workflow.</p>
</div>
<ol class="map map--links" aria-label="The pages for authors">{tiles}</ol>
</div></section>
{doc_section("needs", "One release, read once", "The registry copies what its page shows, so nothing here depends on your release staying up.",
             spec_table(("In the release", "", "What it is"), needs))}
{authors_close("../")}"""
    return page("For plugin authors: Parrot Cart plugins",
                "What a Parrot Cart plugin's release needs to be listed: the .CVP, a licence, a README, and "
                "optional screenshots and icons.", body, "../", "authors", [], entries, config)


def readme_doc(entries, config):
    cart = cvreadme_text(SAMPLE_README)
    screen = tvscreen.readme_page("Star Sweeper", cart)
    card = screen_card(screen, "A README on the cart, converted by the SDK", "30 x 19")
    rules = [
        ("A heading", "In capitals, a blank line before and after."),
        ("A paragraph", "Reflowed to 30 columns."),
        ("A list", "<span class=code>-</span> or <span class=code>1.</span>, the text hanging under its first word."),
        ("A link", "Its text, then the URL. A long URL starts a line of its own."),
        ("Code", "Inline: its text. A block: as it is, each line cut at 30."),
        ("Emphasis", "Dropped: the cart has one weight."),
        ("An image", "<span class=code>[image: alt]</span>."),
        ("A table", "A <span class=code>header: value</span> line for each cell, row by row."),
        ("Raw HTML", "The tags dropped, their text kept."),
        ("Outside ASCII", "A look-alike (curly quotes, dashes, accents), or <span class=code>?</span>."),
    ]
    fmt = [
        ("Offset 280", "u32, little-endian", "Where the text starts, from the start of the file. 0: no README."),
        ("Offset 284", "u32, little-endian", "Its length in bytes, 16384 at most."),
        ("The text", "After the image", "Printable ASCII (0x20 to 0x7E) and line feeds only. No line over 30 "
         "characters. The last line ends with a line feed."),
        ("SHA-256", "Unchanged", "The image's hash doesn't cover the README, so editing it doesn't make the cart "
         "copy the plugin again."),
    ]
    checks = [
        ("In bounds", "The text starts after the image and ends inside the file.", "Refused"),
        ("Length", "16384 bytes at most.", "Refused"),
        ("Characters", "0x20 to 0x7E and line feeds. No tabs, no carriage returns.", "Refused"),
        ("Width", "30 characters a line at most.", "Refused"),
        ("No README at all", "Both fields 0, as in every plugin built before the README existed.",
         "Listed, with a note on its page"),
    ]
    web = [
        ("Shown", "Headings, lists, task lists, tables, code, quotes, links."),
        ("Pictures", "Become links. The site loads nothing from other hosts."),
        ("Raw HTML", "Dropped, with any script or style. Its text stays."),
        ("Links", "https only. A relative link goes to your repository at the release's tag."),
        ("Size", "64K at most, or the page links to it instead."),
    ]
    body = f"""{doc_hero("One README, on the web and on the TV", "Write README.md once. The registry renders it; "
                     "the SDK folds it into the .CVP for the cart.",
                     '<a class="btn" href="#write">What to write</a><a class="btn btn--secondary" href="#format">The format</a>',
                     card)}
{doc_section("write", "What to write", "Whoever has the cart in the console can read it there, with no computer near.",
             '<ul class="rows"><li><h3>What it does</h3><p>A line or two, first: the cart shows 19 lines a screen.</p></li>'
             '<li><h3>How to use it</h3><p>The controls, and which folder its files go in.</p></li>'
             '<li><h3>Credits</h3><p>Under a Credits heading: whose work it uses. The registry requires it.</p></li>'
             '<li><h3>Its source</h3><p>A line with the word source and a link. The registry requires it.</p></li></ul>')}
{doc_section("cart", "What the SDK makes of it", "The SDK converts README.md when it builds the plugin. The same input always gives the same text.",
             spec_table(("Markdown", "On the cart"), rules)
             + f'<pre class="cmd"><code>cvcart_plugin(sweeper ID author.sweeper NAME "Star Sweeper" VERSION 1.0.0\n'
               f'               README README.md)\n\npython3 cvreadme.py README.md    # prints what the cart will show</code></pre>'
             + f'<p class="docnote">Both come with {template_link(config)}. Text over 16384 bytes is cut at a line\'s end, '
               'and its last line says so.</p>')}
{doc_section("format", "The format in the .CVP", "For anyone building a .CVP without the SDK.",
             spec_table(("Where", "Type", "What"), fmt))}
{doc_section("checks", "What the registry checks", "It reads the text and never changes it: the page shows the .CVP's own bytes.",
             spec_table(("Check", "Rule", "If it fails"), checks))}
{doc_section("web", "On its page here", "README.md at the release's tag, as GitHub-flavoured Markdown.",
             spec_table(("Part", "What happens"), web))}
{authors_close("../../")}"""
    return page("The README: Parrot Cart plugins", "How a Parrot Cart plugin's README.md reaches the registry and "
                "the cart: what to write, the 30-column text in the .CVP, and what the registry checks.", body,
                "../../", "authors", [screen], entries, config)


def cvreadme_text(md):
    import cvreadme
    return cvreadme.convert(md)


def screenshots_doc(entries, config):
    pick = next((e for e in sorted(entries, key=lambda e: e["name"].lower()) if e["screenshots"]), None)
    if pick:
        src = f'../../plugins/{e_(pick["id"])}/{pick["screenshots"][0]["file"]}'
        card = (f'<figure class="card shot shot--hero"><div class="shot__tv"><img src="{src}" width="{png.WIDTH}" '
                f'height="{png.HEIGHT}" alt="A 256 by 192 picture in the TV frame, from {e_(pick["name"])}">'
                f'</div><figcaption><span>The picture alone; the site draws the frame</span>'
                f'<span class="code">{png.WIDTH} x {png.HEIGHT}</span></figcaption></figure>')
    else:
        card = screen_card(tvscreen.plugins_page(entries), "The console's picture is 256 x 192", "256 x 192")
    spec = [
        ("How many", "Up to three."),
        ("Format", "PNG, one still picture. No animation."),
        ("Size", f"Exactly {png.WIDTH} x {png.HEIGHT} pixels: the console's picture, without the border, "
         "not scaled or filtered."),
        ("Weight", f"{png.MAX_BYTES // 1024} KB each at most. A real screen is a few KB."),
        ("Names", "<span class=code>screenshot-1.png</span>, <span class=code>screenshot-2.png</span>, "
         "<span class=code>screenshot-3.png</span>, lower case."),
        ("Where", "Attached to the GitHub release, beside the .CVP."),
    ]
    refused = [
        ("Another size", "640 x 480, 280 x 216 with the border, a photo of the TV."),
        ("Not a PNG", "A JPEG renamed, a cut-off upload, an animated PNG."),
        ("Over 100 KB", "Usually a sign it was scaled up or saved in true colour from a photo."),
        ("A fourth", "<span class=code>screenshot-4.png</span> or higher."),
    ]
    used = [("Its page here", "Each in the TV's frame, at a whole number of screen pixels a pixel."),
            ("The catalogue", "The first one, as the plugin's thumbnail."),
            ("registry.json", "Their addresses on this site, for installers.")]
    body = f"""{doc_hero("Screenshots are the console's own picture", "Up to three PNGs, 256 x 192 each, attached "
                     "to the release.", '<a class="btn" href="#spec">The spec</a><a class="btn btn--secondary" href="#taking">Taking one</a>', card)}
{doc_section("spec", "256 x 192, and nothing else", "The TMS9918's picture is 32 x 24 characters of 8 x 8.", spec_table(("", "Rule"), spec))}
{doc_section("show", "What to show", None,
             '<ul class="rows"><li><h3>The plugin itself</h3><p>Its own screens, first the one a person will see most.</p></li>'
             '<li><h3>Nothing you can\'t share</h3><p>An emulator\'s pictures show homebrew or your own test files, '
             'not a commercial game.</p></li>'
             '<li><h3>One set a release</h3><p>A release with several .CVP files shares its screenshots.</p></li></ul>')}
{doc_section("taking", "Taking one", "Any ColecoVision emulator that saves the picture at its own size will do.",
             '<ul class="rows"><li><h3>Save at 1x</h3><p>Turn off scaling, filters and scanlines.</p></li>'
             '<li><h3>Crop the border</h3><p>If the file is larger than 256 x 192, the border is in it: crop to the picture.</p></li>'
             '<li><h3>Keep it indexed</h3><p>The console has 15 colours, so a palette PNG is exact and tiny.</p></li></ul>')}
{doc_section("refused", "What the check refuses", "A bad screenshot stops the submission, and the report says which and why.",
             spec_table(("Refused", "For example"), refused))}
{doc_section("used", "Where they go", "Copied into the registry when the plugin is listed, so they outlive the release.",
             spec_table(("Place", "How"), used))}
{authors_close("../../")}"""
    return page("Screenshots: Parrot Cart plugins", "The screenshot spec for Parrot Cart plugins: up to three "
                "256 x 192 PNGs of 100 KB at most, attached to the release as screenshot-1.png to screenshot-3.png.",
                body, "../../", "authors", [], entries, config)


def big_icon(hexstr, colour, label, caption):
    return (f'<figure class="iconfig">{tvscreen.icon_svg(hexstr, colour, label)}'
            f"<figcaption>{caption}</figcaption></figure>")


PAD_ICON = "3c4299819999423c"       # the Pad Test plugin's: firmware/revc/padtest/padtest_icon.txt


def icons_doc(entries, config):
    icons = tvscreen.MENU["icons"]
    with_icons = [e for e in entries if e["icon"] != "00" * 8] or entries
    screen = tvscreen.plugins_page(with_icons)
    card = screen_card(screen, "Each plugin's icon on the Plugins page", "/PLUGINS")
    spec = [
        ("Size", "8 x 8 pixels, one bit a pixel: on or off."),
        ("The plugin's icon", "Header offset 264, 8 bytes. Beside the plugin on the Plugins page and in Open with."),
        ("Its files' icon", "Header offset 272, 8 bytes. Beside each file the plugin opens."),
        ("A byte a row", "Top row first. Bit 7 is the left pixel."),
        ("Colour", "Not yours to pick: the menu draws a plugin's icon magenta and its files' light green, on black, "
         "or on dark blue under the selection bar."),
        ("All zeros", "No icon: the menu draws its own plug, or its plain file."),
        ("A screenful", "The menu shows seven plugins' own icons and six different file icons a page; any more "
         "get the plug and the plain file."),
    ]
    rows = cvp.icon_rows(PAD_ICON)
    txt = "\n".join(rows)
    hexs = " ".join(PAD_ICON[i:i + 2] for i in range(0, 16, 2))
    family = "".join([
        big_icon(icons["folder"], "y", "The menu's folder icon", "A folder"),
        big_icon(icons["cart"], "c", "The menu's cartridge icon", "A ROM"),
        big_icon(icons["file"], "g", "The menu's plain file icon", "A plugin's file, with no icon"),
        big_icon(icons["plugin"], "m", "The menu's plug icon", "A plugin, with no icon"),
        big_icon(PAD_ICON, "m", "The Pad Test plugin's icon", "Pad Test's own"),
    ])
    body = f"""{doc_hero("Two icons, 8 x 8, one bit a pixel", "One for the plugin, one for the files it opens. "
                     "The menu colours them.", '<a class="btn" href="../icon-editor/">Open the icon editor</a>'
                     '<a class="btn btn--secondary" href="#txt">The .txt file</a>', card)}
{doc_section("spec", "What an icon is", "Sixteen bytes of the .CVP's header.", spec_table(("", "Rule"), spec))}
{doc_section("txt", "The .txt file the SDK reads", "Eight lines of eight characters: # is a pixel, . is none.",
             f'<div class="pair"><div><h3>padtest_icon.txt</h3><pre class="cmd"><code>{txt}</code></pre></div>'
             f'<div><h3>In the header</h3><pre class="cmd"><code>{hexs}</code></pre>'
             f'<p class="docnote">Blank lines and spaces around a line are ignored. Anything else is an error when '
             f'the plugin is built.</p></div></div>'
             f'<pre class="cmd"><code>cvcart_plugin(padtest ID author.padtest NAME "Pad Test" VERSION 1.0.0\n'
             f'               ICON padtest_icon.txt FILE_ICON padtest_file_icon.txt)\n\n'
             f'mkcvp.py IN.uf2 OUT.cvp ... --icon padtest_icon.txt --file-icon padtest_file_icon.txt</code></pre>')}
{doc_section("design", "Drawing one that reads", "The menu's rows touch: there is no gap between one icon and the next.",
             f'<div class="iconrow">{family}</div>'
             '<ul class="rows"><li><h3>Leave an edge clear</h3><p>The menu\'s own icons keep the top row and the '
             'right column empty, so neighbours never join up.</p></li>'
             '<li><h3>Draw the shape, not the colour</h3><p>One colour, so the outline does the work. Solid shapes '
             'read better than thin lines on a TV.</p></li>'
             '<li><h3>Check it on the bar</h3><p>The selected row is dark blue. The editor shows both.</p></li></ul>')}
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Draw them in the browser</h2><p>Both icons, live on the menu, saved as the .txt files the SDK reads.</p></div>
<div class="actions"><a class="btn" href="../icon-editor/">Open the icon editor</a></div>
</div></section>"""
    return page("Icons: Parrot Cart plugins", "The icon spec for Parrot Cart plugins: two 8 x 8 one-bit icons in the "
                ".CVP header, how the menu colours them, and the .txt file the SDK reads.", body, "../../", "authors",
                [screen], entries, config)


def pad(kind, title, note, colour, name):
    cells = "".join(
        f'<button type="button" class="px__c" aria-pressed="false" aria-label="Row {y + 1}, column {x + 1}" '
        f'data-x="{x}" data-y="{y}"{"" if x == y == 0 else " tabindex=-1"}></button>'
        for y in range(8) for x in range(8))
    return f"""<fieldset class="pad" data-pad="{kind}">
<legend><b>{title}</b> <span>{note}</span></legend>
<div class="px px--{colour}" role="group" aria-label="{title}, 8 by 8 pixels" aria-describedby="keys">{cells}</div>
<div class="pad__tools" role="group" aria-label="Change the whole icon">
<button type="button" class="tool" data-do="clear">Clear</button>
<button type="button" class="tool" data-do="invert">Invert</button>
<button type="button" class="tool" data-do="left" aria-label="Move left">&larr;</button>
<button type="button" class="tool" data-do="right" aria-label="Move right">&rarr;</button>
<button type="button" class="tool" data-do="up" aria-label="Move up">&uarr;</button>
<button type="button" class="tool" data-do="down" aria-label="Move down">&darr;</button>
</div>
<label class="field">Hex, as in the header<input class="code" type="text" data-hex value="0000000000000000"
 maxlength="64" spellcheck="false" autocomplete="off" autocapitalize="off"></label>
<label class="field">{name}<textarea class="code" data-txt rows="8" cols="8" spellcheck="false"
 autocomplete="off" autocapitalize="off">{chr(10).join(["........"] * 8)}</textarea></label>
<div class="actions">
<button type="button" class="btn" data-save="{name}">Save {name}</button>
<label class="btn btn--secondary filebtn">Open a .txt<input class="visually-hidden" type="file" data-open accept=".txt,text/plain"></label>
<button type="button" class="btn btn--secondary" data-copy>Copy the hex</button>
</div>
<p class="pad__msg" role="status" aria-live="polite" data-msg></p>
</fieldset>"""


def icon_editor(entries, config):
    icons = tvscreen.MENU["icons"]
    a, b = tvscreen.editor_pages("ed-plugin", "ed-file")
    body = f"""<section class="banner banner--tool" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Draw your plugin's two icons</h1>
<p class="lead">Click or use the keys. The menu on the right redraws as you go; nothing leaves this page.</p>
</div>
<noscript><p class="warn"><b>Drawing needs JavaScript.</b> Without it, write each icon as a text file: eight
lines of eight characters, # for a pixel and . for none. <a class="link" href="../icons/#txt">The .txt file</a></p></noscript>
<div class="editor" data-editor data-plug="{icons["plugin"]}" data-file="{icons["file"]}">
<div class="editor__pads">
{pad("plugin", "The plugin's icon", "Magenta, header offset 264", "m", "icon.txt")}
{pad("file", "Its files' icon", "Light green, header offset 272", "g", "file_icon.txt")}
<p class="docnote" id="keys">Keys: the arrows move, Space or Enter turns a pixel on or off, and Shift with an
arrow carries the pixel's state along. An icon left empty is no icon: the menu draws its own.</p>
</div>
<div class="editor__preview" aria-label="Your icons on the cart's menu">
{screen_card(a, "The Plugins page: on the bar, and off it", "magenta")}
{screen_card(b, "A folder of its files", "light green")}
<p class="docnote">Give the files to the SDK: <span class="code">ICON icon.txt FILE_ICON file_icon.txt</span>.
The address of this page keeps your drawing, so a bookmark saves it.
<a class="link" href="../icons/">The icon spec</a></p>
</div>
</div>
</div></section>"""
    return page("The icon editor: Parrot Cart plugins", "Draw a Parrot Cart plugin's two 8 x 8 icons in the "
                "browser, see them on the cart's menu, and save the .txt files the SDK reads.", body, "../../",
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
    entries = build(a.out)
    if placeholder(registry.load_config(ROOT)):
        print("note: registry_repo is still OWNER/...: the Submit button stays off until it names the real repository")
    print(f"built {a.out}: the catalogue, {len(entries)} plugin pages, the authors' pages with the icon editor, "
          "the submit page and registry.json")


if __name__ == "__main__":
    main()
