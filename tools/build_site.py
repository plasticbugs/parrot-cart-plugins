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
            f'<a class="wordmark" href="{pre}index.html" aria-label="Parrot Cart plugins home" '
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
            f'\n<li><a href="https://github.com/{e_(config["registry_repo"])}">Source code on GitHub</a></li>')
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
<p class="fine">The TV screens use the cart menu's font, Empty Windows Unboxed by VEXED
(<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
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
        line = f"Showing {len(entries)} examples of the cart's own plugins until the first ones are submitted."
    else:
        line = f"{len(entries) - len(examples)} plugins. Each one is a free download from its author."
    body = [f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">Plugins for your Parrot&nbsp;Cart</h1>
<p class="lead">Emulators, utilities and more to enhance your ColecoVision.</p>
<div class="actions"><a class="btn" href="#plugins">Browse plugins</a><a class="btn btn--secondary" href="submit/">Submit a plugin</a></div>
</div>
{screen_card(plugins_screen, "The cart's Plugins page", "/PLUGINS", "hero-screen",
             "A photo of a TV showing the cart's Plugins page with these plugins")}
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
<p class="empty" id="catalogue-empty" hidden>No plugins match. Try a file type like .nes, or clear the search.</p>
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
            ("before", "Before", f"Three {e_(ext)} files in {e_(folder)}. The menu hides them.",
             before, folder),
            ("copied", "Copied", f"Copy {f} to /PLUGINS. It shows up on the Plugins page.", listed,
             "/PLUGINS"),
            ("after", "After", "The files show up with the plugin's icon. Press A to open one.",
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
<div class="switch__tabs" role="tablist" aria-label="Step by step" aria-orientation="vertical">{tabs}</div>
<div class="switch__panels">{panels}</div>
</div></div></section>""")

    body.append("""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">No installer. Manage your plugins on the cartridge.</h2><p class="lead">Three
easy steps.</p></div>
<ol class="steps">
<li><h3>Download the .CVP</h3><p>From the plugin's page on this site.</p></li>
<li><h3>Copy it to /PLUGINS</h3><p>On the cart's microSD card.</p></li>
<li><h3>Start it from Plugins</h3><p>Press B for Home, open Plugins, pick the plugin and press A.</p></li>
</ol></div></section>""")

    body.append(f"""<section class="band band--ink figure-band" id="flash" aria-labelledby="flash-title"><div class="container">
<div><p class="big" aria-hidden="true">{FLASH_SLOTS}</p><h2 id="flash-title"><span class="visually-hidden">{FLASH_SLOTS} </span>plugins
stay ready on the cart</h2></div>
<ul class="ruled">
<li><b>The first time you start one</b><span>it's copied into a 1 MB slot. That happens once per version.</span></li>
<li><b>A new version</b><span>uses the old version's slot.</span></li>
<li><b>When every slot is full</b><span>the next plugin takes the one used longest ago.</span></li>
<li><b>Removing a plugin</b><span>frees its slot.</span></li>
</ul></div></section>""")

    body.append("""<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Add your plugin by submitting a GitHub issue in the registry.</h2><p>We'll check your release
and list it here.</p></div>
<div class="actions"><a class="btn" href="submit/">Submit a plugin</a>
<a class="btn btn--secondary" href="registry.json">registry.json</a></div>
</div></section>""")
    return page("Parrot Cart plugins", "Free plugins for Parrot Cart, the ColecoVision cartridge with a microSD "
                "card. Download a .CVP file and copy it to /PLUGINS.", "\n".join(body), "", "plugins",
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
        f'<span class="code">{png.WIDTH} × {png.HEIGHT}</span></figcaption></figure>'
        for i, s in enumerate(e["screenshots"], 1))
    lead = ("Pictures of this example on the cart. A listed plugin shows its author's screenshots."
            if e.get("example") else "From the author's release, pixel for pixel.")
    return f"""<section class="section" id="screenshots" aria-labelledby="shots-title"><div class="container">
<div class="headblock"><h2 id="shots-title">On the TV</h2><p class="lead">{lead}</p></div>
<div class="shots" data-n="{n}">{figs}</div>
</div></section>"""


def cart_readme_section(e, text, pre):
    """the .CVP's README text as it is, in the menu's font, and the same text to read or copy"""
    if text is None:
        return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">No README on the cart</h2><p class="lead">This plugin's .CVP
doesn't include a README, so the cart has nothing to show.</p></div>
<p class="warn"><b>If you wrote this plugin:</b> build it with the SDK from a README.md. Your next release will
show its instructions and credits on the TV. <a class="link" href="{pre}authors/readme/">How the README works</a></p>
</div></section>""", None
    strip = tvscreen.readme_strip(text)
    meta = e["readme"]["cart"]
    return f"""<section class="section" id="on-the-cart" aria-labelledby="cart-title"><div class="container">
<div class="headblock"><h2 id="cart-title">README on the cart</h2><p class="lead">What the cart shows for this
plugin: {meta["lines"]} lines, 30 characters wide.</p></div>
<div class="cartreadme">
<figure class="card"><div class="scroll" tabindex="0" role="region" aria-label="The README in the cart's font. The same text follows as plain text.">{strip.svg()}</div>
<figcaption><span>From the details page on the cart</span><span class="code">{meta["size"]:,} bytes</span></figcaption></figure>
<div class="cartreadme__text"><h3>As plain text</h3>
<pre class="plain">{e_(text)}</pre>
<p><a class="link" href="{registry.CART_README}">{registry.CART_README}</a></p></div>
</div></div></section>""", strip


def web_readme_section(e, text, live):
    tag = e["release"]["tag"]
    where = e["readme"]["web"]["url"] if e["readme"]["web"] else e["credits_url"]
    if text is None:
        body = (f'<p class="warn">The README can\'t be shown here. It isn\'t Markdown, or it\'s over 64 KB. '
                f'{link_or_text(where, "Read it on GitHub", live)}.</p>')
        lead = "It's in the plugin's repository."
    else:
        base = f"https://github.com/{e['repo']}/blob/{tag}/" if live else None
        body = f'<div class="prose">{markdown.render(text, base, 3, where if live else None)}</div>'
        lead = f'README.md from <span class="code">{e_(tag)}</span>. Images show as links.'
    return f"""<section class="section" id="readme" aria-labelledby="readme-title"><div class="container">
<div class="headblock"><h2 id="readme-title">README</h2><p class="lead">{lead}</p></div>
{body}
</div></section>"""


def notes_section(e, live):
    """each listed version's release notes, newest first"""
    base = f"https://github.com/{e['repo']}/blob/{e['release']['tag']}/" if live else None
    items = []
    for h in e["history"]:
        notes = (f'<div class="prose">{markdown.render(h["notes"], base, 4)}</div>' if h["notes"].strip()
                 else '<p class="muted">No notes for this release.</p>')
        items.append(f'<li><div><h3>{e_(h["version"])}</h3><p class="muted">{e_(h["published"])}, '
                     f'{link_or_text(h["url"], f"""<span class="code">{e_(h["tag"])}</span>""", live)}</p></div>'
                     f"{notes}</li>")
    return f"""<section class="section" id="notes" aria-labelledby="notes-title"><div class="container">
<div class="headblock"><h2 id="notes-title">Release notes</h2><p class="lead">Newest first.</p></div>
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
                  f'<a class="btn btn--secondary" href="{e_(e["source_url"])}">Source code</a></div>')
    else:
        action = ('<div class="actions"><a class="btn" href="#install">Put it on your cart</a></div>'
                  '<p class="note">This is an example. Its source isn\'t public yet, so there\'s no download.</p>')
    hero = f"""<section class="hero" aria-labelledby="hero-title"><div class="container">
<div class="hero__text">
<h1 id="hero-title">{e_(e["name"])}</h1>
<p class="lead">{e_(e["description"])}</p>
{action}
</div>
{screen_card(details, "Its details page on the cart", e["download"]["name"], "details",
             f"A photo of a TV showing the cart's details page for {e['name']}")}
</div></section>"""

    kind = "loaded into RAM" if e["image"]["kind"] == "sram" else "runs from flash"
    # the details screen above already shows the header; these are what the check read in the release
    rows = [
        ("Release", f'<span class="code">{e_(e["release"]["tag"])}</span>, {e_(e["release"]["published"])}'),
        ("Image", f'{e["image"]["size"]:,} bytes, {kind}'),
        ("Plugin API", f'<span class="code">{e["api"]}</span>'),
        ("GitHub", link_or_text(f"https://github.com/{e['repo']}", e_(e["repo"]), True) if live
         else "Not public yet"),
        ("License", link_or_text(lic["url"], e_(lic["name"]), live)
         + (f'. {e_(lic["note"])}' if lic.get("note") else "")),
    ]
    rows.insert(4, ("Source", link_or_text(e["source_url"], f'Code at <span class="code">{e_(e["release"]["tag"])}</span>',
                                           live)))
    items = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
    if e.get("credits"):        # the long ones run the full width, so the two columns stay even
        items += f'<div class="wide"><dt>Credits</dt><dd>{e_(e["credits"])}</dd></div>'
    items += (f'<div class="wide"><dt>SHA-256</dt><dd><span class="code hash">{e_(e["download"]["sha256"])}</span>'
              "</dd></div>")
    specs = f"""<section class="section" aria-labelledby="specs-title"><div class="container">
<div class="headblock"><h2 id="specs-title">Release details</h2><p class="lead">From GitHub, when the plugin
was listed.</p></div>
<dl class="specs">{items}</dl>
</div></section>"""

    fname = e_(e["download"]["name"])
    steps = [f"<li><h3>Download {fname}</h3><p>Its SHA-256 is listed above.</p></li>",
             "<li><h3>Copy it to /PLUGINS</h3><p>On the cart's microSD card.</p></li>"]
    if e["opens"] and e["home"]:
        steps.append(f'<li><h3>Put your files in {e_(e["home"])}</h3><p>Your {e_(opens(e))} files go here.</p></li>')
    steps.append(f'<li><h3>Start it</h3><p>Press B for Home, open Plugins, pick {e_(e["name"])} and press A.</p></li>')
    install = f"""<section class="section" id="install" aria-labelledby="install-title"><div class="container">
<div class="headblock"><h2 id="install-title">Put it on your cart</h2></div>
<ol class="steps{" steps--4" if len(steps) == 4 else ""}">{"".join(steps)}</ol>
</div></section>"""
    desc = f"{e['name']} {e['version']}, a free Parrot Cart plugin. {e['description']}"
    return page(f"{e['name']}, a Parrot Cart plugin", desc, hero + extra + specs + notes_section(e, live) + install,
                pre, "plugins", [details] + ([strip] if strip else []), entries, config)


# ---- the submit page ----------------------------------------------------------------

def submit_page(entries, config):
    form = f"https://github.com/{config['registry_repo']}/issues/new?template=submit-plugin.yml"
    nodes = [
        ("Your release", "The .CVP, with its README inside."),
        ("An issue", "Your repo and a one-line description."),
        ("The check", "We read your files and reply on the issue."),
        ("Your listing", "Made from your release."),
        ("A review", "We look it over and approve it."),
        ("This site", "Your plugin gets its own page."),
        ("SD cards", "People copy it to /PLUGINS."),
        ("Your next release", "Picked up within a day."),
    ]
    items = "".join(f'<li{" class=loop" if i == len(nodes) - 1 else ""}><h2>{t}</h2><p>{s}</p></li>'
                    for i, (t, s) in enumerate(nodes))
    # what a plugin needs, in a few lines
    needs = [
        ("The .CVP", "Under 1 MB."),
        ("The README", 'Goes <a class="link" href="../authors/readme/">inside the .CVP</a>.'),
        ("Screenshots", 'Up to three, as <a class="link" href="../authors/screenshots/">256 × 192 PNGs</a>.'),
        ("Your repo", "Public, with a license."),
    ]
    need_rows = "".join(f"<li><b>{t}</b><span>{s}</span></li>" for t, s in needs)
    if placeholder(config):
        primary = ('<a class="btn" aria-disabled="true">Open an issue</a>')
        soon = '<p class="soon">Submissions open once the registry is on GitHub.</p>'
    else:
        primary, soon = f'<a class="btn" href="{e_(form)}">Open an issue</a>', ""
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Submit an Issue in the repository to add your Plugin</h1>
<p class="lead">Tell us your repo. We'll check your release and add your plugin.</p>
<div class="actions">{primary}<a class="btn btn--secondary" href="#rules">See the requirements</a></div>
{soon}
</div>
<ol class="map" aria-label="From your release to the cart">{items}</ol>
<p class="map-legend">We never run anything from your repo.</p>
</div></section>
<section class="section" id="rules" aria-labelledby="rules-title"><div class="container">
<div class="headblock"><h2 id="rules-title">Requirements</h2></div>
<ul class="ruled">{need_rows}</ul>
</div></section>
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Check your plugin before you release it</h2><p>Clone this repo and run this. It shows your
plugin's details and anything the cart would refuse.</p></div>
<pre class="cmd"><code>python3 tools/cvp.py YOURPLUGIN.CVP</code></pre>
</div></section>"""
    return page("Submit a plugin: Parrot Cart plugins",
                "Add your plugin to the Parrot Cart registry. Open a GitHub issue with your repo, and we'll check "
                "your release.", body, "../", "submit", [], entries, config)


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
<div><h2 id="close-title">Check your plugin before you release it</h2><p>Clone this repo and run this. It shows your
plugin's details, its README and anything the cart would refuse.</p></div>
<pre class="cmd"><code>python3 tools/cvp.py YOURPLUGIN.CVP</code></pre>
</div></section>"""


def authors_index(entries, config):
    needs = [
        ("The .CVP", "Required", "Your plugin, built with the SDK. Under 1 MB."),
        ("README", "Required", 'Goes <a class="link" href="readme/">inside the .CVP</a>, so the cart can show '
         "it. The SDK puts your README.md there."),
        ("LICENSE", "Required", "In your public repo, at the release's tag."),
        ("Release notes", "Optional", "The text of your GitHub release. Shown for each version."),
        ("Screenshots", "Optional", '<a class="link" href="screenshots/">Up to three PNGs</a>, 256 × 192, '
         "attached to the release."),
        ("Two icons", "Optional", '<a class="link" href="icons/">8 × 8, one colour</a>. One for the plugin and '
         "one for its files."),
    ]
    cards = [
        ("readme/", "The README", "One README.md for this site and the cart."),
        ("screenshots/", "Screenshots", "Up to three, 256 × 192 each."),
        ("icons/", "Icons", "Two 8 × 8 icons. The menu colours them."),
        ("icon-editor/", "The icon editor", "Draw your icons and save them as .txt files."),
    ]
    tiles = "".join(f'<li><h2><a href="{h}">{t}</a></h2><p>{d}</p></li>' for h, t, d in cards)
    body = f"""<section class="banner" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Packaging your plugin</h1>
<p class="lead">To be listed, a plugin needs a .CVP, a README and a license. Screenshots and icons help people find it.</p>
<div class="actions"><a class="btn" href="../submit/">Submit a plugin</a><a class="btn btn--secondary" href="icon-editor/">Open the icon editor</a></div>
<p class="soon">Start from {template_link(config)}. It's a working plugin with a README, icons and a release workflow.</p>
</div>
<ol class="map map--links" aria-label="Pages for plugin authors">{tiles}</ol>
</div></section>
{doc_section("needs", "What your release needs", "Three things are required. The rest are optional.",
             spec_table(("Part", "", "What it is"), needs))}
{authors_close("../")}"""
    return page("For plugin authors: Parrot Cart plugins",
                "What your Parrot Cart plugin's release needs: a .CVP, a README and a license. Screenshots and "
                "icons are optional.", body, "../", "authors", [], entries, config)


def readme_doc(entries, config):
    cart = cvreadme_text(SAMPLE_README)
    screen = tvscreen.readme_page("Star Sweeper", cart)
    card = screen_card(screen, "A README on the cart", "30 × 19")
    rules = [
        ("A heading", "Capitals, with a blank line before and after."),
        ("A paragraph", "Wrapped to 30 characters."),
        ("A list", "<span class=code>-</span> or <span class=code>1.</span>, with wrapped lines indented under the first word."),
        ("A link", "The text, then the URL. A long URL goes on its own line."),
        ("Code", "Inline code stays as text. A code block is kept as it is, with each line cut at 30."),
        ("Bold and italics", "Dropped. The cart has one style of text."),
        ("An image", "Shown as <span class=code>[image: alt]</span>."),
        ("A table", "One <span class=code>header: value</span> line for each cell, row by row."),
        ("Raw HTML", "Tags are dropped. Their text stays."),
        ("Non-ASCII characters", "Curly quotes, dashes and accented letters become plain look-alikes. Anything "
         "else becomes <span class=code>?</span>."),
    ]
    fmt = [
        ("Offset 280", "u32, little-endian", "Where the text starts, counted from the start of the file. 0 means no "
         "README."),
        ("Offset 284", "u32, little-endian", "The text's length in bytes, up to 16384."),
        ("The text", "After the image", "Printable ASCII (0x20 to 0x7E) and line feeds only. No line over 30 "
         "characters. The last line ends with a line feed."),
        ("SHA-256", "Unchanged", "The image's hash doesn't include the README. Changing the README won't make the "
         "cart copy the plugin again."),
    ]
    checks = [
        ("In bounds", "The text starts after the image and ends inside the file.", "Refused"),
        ("Length", "Up to 16384 bytes.", "Refused"),
        ("Characters", "0x20 to 0x7E and line feeds only. No tabs or carriage returns.", "Refused"),
        ("Width", "Up to 30 characters per line.", "Refused"),
        ("No README at all", "Both fields are 0, as in plugins built before the README existed.",
         "Listed, with a note on its page"),
    ]
    web = [
        ("Shown", "Headings, lists, task lists, tables, code, quotes and links."),
        ("Images", "Shown as links. This site doesn't load anything from other sites."),
        ("Raw HTML", "Dropped, along with any scripts or styles. The text stays."),
        ("Links", "Only https links work. Relative links point to your repo at the release's tag."),
        ("Size", "Up to 64 KB. A bigger README is linked instead of shown."),
    ]
    body = f"""{doc_hero("One README for the web and the TV", "Write README.md once. It shows on your plugin's "
                     "page here, and the SDK adds it to the .CVP for the cart.",
                     '<a class="btn" href="#write">What to write</a><a class="btn btn--secondary" href="#format">The format</a>',
                     card)}
{doc_section("write", "What to write", "People read it on the TV, often with no computer nearby.",
             '<ul class="rows"><li><h3>What it does</h3><p>Put a line or two first. The cart shows 19 lines at a time.</p></li>'
             '<li><h3>How to use it</h3><p>The controls, and which folder the files go in.</p></li>'
             '<li><h3>Credits</h3><p>Under a Credits heading, say whose work it uses. Required.</p></li>'
             '<li><h3>Source</h3><p>A line with the word “source” and a link. Required.</p></li></ul>')}
{doc_section("cart", "How the SDK converts it", "The SDK converts README.md when it builds your plugin.",
             spec_table(("Markdown", "On the cart"), rules)
             + f'<pre class="cmd"><code>cvcart_plugin(sweeper ID author.sweeper NAME "Star Sweeper" VERSION 1.0.0\n'
               f'               README README.md)\n\npython3 cvreadme.py README.md    # prints what the cart will show</code></pre>'
             + f'<p class="docnote">Both come with {template_link(config)}. Text over 16384 bytes is cut at the end of '
               'a line, and the last line says it was cut.</p>')}
{doc_section("format", "The format in the .CVP", "You only need this if you build a .CVP without the SDK.",
             spec_table(("Where", "Type", "What"), fmt))}
{doc_section("checks", "What we check", "We never change your text. Your page shows it exactly as it is in the .CVP.",
             spec_table(("Check", "Rule", "If it fails"), checks))}
{doc_section("web", "On your plugin's page", "We show README.md from the release's tag, as GitHub Markdown.",
             spec_table(("Part", "What happens"), web))}
{authors_close("../../")}"""
    return page("The README: Parrot Cart plugins", "How to write a README for your Parrot Cart plugin. It shows "
                "on this site and on the cart, 30 characters wide.", body,
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
                f'</div><figcaption><span>Just the picture. We add the TV frame.</span>'
                f'<span class="code">{png.WIDTH} × {png.HEIGHT}</span></figcaption></figure>')
    else:
        card = screen_card(tvscreen.plugins_page(entries), "The console's picture is 256 × 192", "256 × 192")
    spec = [
        ("How many", "Up to three."),
        ("Format", "PNG. No animation."),
        ("Size", f"Exactly {png.WIDTH} × {png.HEIGHT} pixels. No border, scaling or filters."),
        ("File size", f"{png.MAX_BYTES // 1024} KB max each. A real screen is usually a few KB."),
        ("Names", "<span class=code>screenshot-1.png</span>, <span class=code>screenshot-2.png</span> and "
         "<span class=code>screenshot-3.png</span>, in lower case."),
        ("Where", "Attach them to your GitHub release, next to the .CVP."),
    ]
    refused = [
        ("The wrong size", "640 × 480, 280 × 216 with the border, or a photo of the TV."),
        ("Not a PNG", "A renamed JPEG, a broken upload or an animated PNG."),
        ("Over 100 KB", "Usually it was scaled up, or saved in full colour from a photo."),
        ("A fourth screenshot", "<span class=code>screenshot-4.png</span> or higher."),
    ]
    used = [("Your plugin's page", "Each one in a TV frame, scaled up without blur."),
            ("The plugin list", "The first one, as a thumbnail."),
            ("registry.json", "Links to each one, for apps that install plugins.")]
    body = f"""{doc_hero("Screenshots at the console's real size", "Up to three PNGs, 256 × 192 each. Attach them "
                     "to your release.", '<a class="btn" href="#spec">Requirements</a><a class="btn btn--secondary" href="#taking">How to take one</a>', card)}
{doc_section("spec", "Requirements", "The console's picture is 256 × 192 pixels.", spec_table(("", "Rule"), spec))}
{doc_section("show", "What to show", None,
             '<ul class="rows"><li><h3>The plugin itself</h3><p>Show its own screens. Put the one people see most first.</p></li>'
             '<li><h3>Nothing you can\'t share</h3><p>For an emulator, show homebrew or your own test files, '
             'not a commercial game.</p></li>'
             '<li><h3>One set per release</h3><p>If a release has several .CVP files, they share the screenshots.</p></li></ul>')}
{doc_section("taking", "How to take one", "Use any ColecoVision emulator that can save the picture at its real size.",
             '<ul class="rows"><li><h3>Save at 1x</h3><p>Turn off scaling, filters and scanlines.</p></li>'
             '<li><h3>Crop the border</h3><p>If the file is bigger than 256 × 192, it includes the border. Crop it out.</p></li>'
             '<li><h3>Save an indexed PNG</h3><p>The console only has 15 colours, so an indexed PNG is exact and small.</p></li></ul>')}
{doc_section("refused", "What gets refused", "A bad screenshot stops your submission. We'll tell you which one and why.",
             spec_table(("Refused", "For example"), refused))}
{doc_section("used", "Where they show up", "Once your plugin is listed.",
             spec_table(("Place", "How"), used))}
{authors_close("../../")}"""
    return page("Screenshots: Parrot Cart plugins", "How to add screenshots to your Parrot Cart plugin. Up to three "
                "PNGs, 256 × 192, 100 KB max each, named screenshot-1.png to screenshot-3.png.",
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
        ("Size", "8 × 8 pixels. Each pixel is on or off."),
        ("The plugin's icon", "8 bytes at header offset 264. Shown next to the plugin on the Plugins page and in "
         "Open with."),
        ("The file icon", "8 bytes at header offset 272. Shown next to each file the plugin opens."),
        ("One byte per row", "Top row first. Bit 7 is the left pixel."),
        ("Colour", "The menu picks it. Plugin icons are magenta and file icons are light green. The background is "
         "black, or dark blue on the selected row."),
        ("All zeros", "No icon. The menu shows its own plug or plain file icon instead."),
        ("Per screen", "The menu shows up to seven plugin icons and six different file icons on a page. Any more "
         "get the plug and the plain file icon."),
    ]
    rows = cvp.icon_rows(PAD_ICON)
    txt = "\n".join(rows)
    hexs = " ".join(PAD_ICON[i:i + 2] for i in range(0, 16, 2))
    family = "".join([
        big_icon(icons["folder"], "y", "The menu's folder icon", "A folder"),
        big_icon(icons["cart"], "c", "The menu's cartridge icon", "A ROM"),
        big_icon(icons["file"], "g", "The menu's plain file icon", "A plugin's file with no icon"),
        big_icon(icons["plugin"], "m", "The menu's plug icon", "A plugin with no icon"),
        big_icon(PAD_ICON, "m", "The Pad Test plugin's icon", "Pad Test's icon"),
    ])
    body = f"""{doc_hero("Two 8 × 8 icons", "One for the plugin and one for the files it opens. Each pixel is on "
                     "or off, and the menu picks the colour.", '<a class="btn" href="../icon-editor/">Open the icon editor</a>'
                     '<a class="btn btn--secondary" href="#txt">The .txt file</a>', card)}
{doc_section("spec", "What an icon is", "Both icons together take 16 bytes of the .CVP's header.", spec_table(("", "Rule"), spec))}
{doc_section("txt", "The .txt file the SDK reads", "Eight lines of eight characters. # is a pixel and . is empty.",
             f'<div class="pair"><div><h3>padtest_icon.txt</h3><pre class="cmd"><code>{txt}</code></pre></div>'
             f'<div><h3>In the header</h3><pre class="cmd"><code>{hexs}</code></pre>'
             f'<p class="docnote">Blank lines and spaces around a line are ignored. Anything else stops the '
             f'build.</p></div></div>'
             f'<pre class="cmd"><code>cvcart_plugin(padtest ID author.padtest NAME "Pad Test" VERSION 1.0.0\n'
             f'               ICON padtest_icon.txt FILE_ICON padtest_file_icon.txt)\n\n'
             f'mkcvp.py IN.uf2 OUT.cvp ... --icon padtest_icon.txt --file-icon padtest_file_icon.txt</code></pre>')}
{doc_section("design", "Tips for a clear icon", "Menu rows touch, so there's no gap between one icon and the next.",
             f'<div class="iconrow">{family}</div>'
             '<ul class="rows"><li><h3>Leave an edge clear</h3><p>The menu\'s icons leave the top row and the '
             'right column empty, so they don\'t run into each other.</p></li>'
             '<li><h3>Use solid shapes</h3><p>There\'s only one colour, so the outline does the work. Solid shapes '
             'look better than thin lines on a TV.</p></li>'
             '<li><h3>Check it on the selected row</h3><p>The selected row is dark blue. The editor shows both '
             'backgrounds.</p></li></ul>')}
<section class="band band--paper close" aria-labelledby="close-title"><div class="container">
<div><h2 id="close-title">Draw them in your browser</h2><p>See them on the menu as you draw, then save the .txt files for the SDK.</p></div>
<div class="actions"><a class="btn" href="../icon-editor/">Open the icon editor</a></div>
</div></section>"""
    return page("Icons: Parrot Cart plugins", "How to make your Parrot Cart plugin's two 8 × 8 icons, and the .txt "
                "file the SDK reads.", body, "../../", "authors",
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
<label class="btn btn--secondary filebtn">Open a .txt file<input class="visually-hidden" type="file" data-open accept=".txt,text/plain"></label>
<button type="button" class="btn btn--secondary" data-copy>Copy hex</button>
</div>
<p class="pad__msg" role="status" aria-live="polite" data-msg></p>
</fieldset>"""


def icon_editor(entries, config):
    icons = tvscreen.MENU["icons"]
    a, b = tvscreen.editor_pages("ed-plugin", "ed-file")
    body = f"""<section class="banner banner--tool" aria-labelledby="hero-title"><div class="container">
<div class="banner__text">
<h1 id="hero-title">Draw your plugin's two icons</h1>
<p class="lead">Click the grid or use the keyboard. The menu preview updates as you draw. Nothing is uploaded.</p>
</div>
<noscript><p class="warn"><b>The editor needs JavaScript.</b> Without it, write each icon as a text file with
eight lines of eight characters. Use # for a pixel and . for an empty one. <a class="link" href="../icons/#txt">The .txt file</a></p></noscript>
<div class="editor" data-editor data-plug="{icons["plugin"]}" data-file="{icons["file"]}">
<div class="editor__pads">
{pad("plugin", "The plugin's icon", "Magenta, header offset 264", "m", "icon.txt")}
{pad("file", "The file icon", "Light green, header offset 272", "g", "file_icon.txt")}
<p class="docnote" id="keys">Keyboard: the arrows move. Space or Enter turns a pixel on or off. Hold Shift with
an arrow to copy the pixel as you move. An empty icon means the menu uses its own.</p>
</div>
<div class="editor__preview" aria-label="Your icons on the cart's menu">
{screen_card(a, "The Plugins page, selected and not selected", "magenta")}
{screen_card(b, "A folder of its files", "light green")}
<p class="docnote">Pass the files to the SDK with <span class="code">ICON icon.txt FILE_ICON file_icon.txt</span>.
Your drawing is saved in this page's address, so you can bookmark it.
<a class="link" href="../icons/">Icon requirements</a></p>
</div>
</div>
</div></section>"""
    return page("The icon editor: Parrot Cart plugins", "Draw your Parrot Cart plugin's two 8 × 8 icons and save "
                "them as .txt files for the SDK.", body, "../../",
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
