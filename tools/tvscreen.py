"""tvscreen -- the cart's menu pages as the TV shows them, drawn as SVG.

The menu runs the TMS9918 in Graphics I: 32 x 24 characters of 8 x 8
pixels, the font and icons in site/data/menu.json (from the menu's
font.asm and icons.h), white text on black, the selected row on a dark
blue bar, and each icon group in its colour (icons.h icon_colour: folders
light yellow, ROMs cyan, other systems' files light green, plugins
magenta). The pages below follow sdplayer.c: pub_plugins(), pub_details()
(tline/tpair), pub_card() and menu_help(); rows 3-21 hold the list (the
loader's LIST_ROW and ROWS), row 1 the head and row 23 the help line.

Glyphs are drawn once a page (glyph_defs) and placed with <use>, so a
screen is a few kilobytes. Colours are CSS classes the site's stylesheet
maps to tokens.
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "site", "data", "menu.json")) as _f:
    MENU = json.load(_f)

COLS, ROWS = 32, 24
HEAD_ROW, LIST_ROW, LIST_ROWS, MSG_ROW = 1, 3, 19, 23
BORDER = 12                                  # the backdrop around the picture, as MAME shows it
NAME_W = 28                                  # browse.h BR_NAME


def cvp_row(name, version, width=NAME_W):
    """plugins.c cvp_row(): the name, then the version at the right"""
    nv = min(len(version), width - 2)
    room = width - nv - 1
    out = list(name[:room].ljust(width))
    out[width - nv:] = version[len(version) - nv:]
    return "".join(out)


def tpair(label, v):
    """sdplayer.c tpair(): "Label     value", a long value on more lines"""
    lines, k = [], 0
    while k == 0 or k < len(v):
        lines.append(f"{'' if k else label:<10}{v[k:k + 20]}")
        k += 20
    return lines


# the TMS9918's colours as MAME shows them, for the PNGs (the site's SVGs take theirs from the stylesheet)
PALETTE = {"k": (0, 0, 0), "w": (255, 255, 255), "b": (84, 85, 237), "g": (94, 220, 120), "m": (201, 91, 186),
           "y": (230, 206, 128), "c": (66, 235, 245)}


class Screen:
    def __init__(self, label, rows=ROWS, border=BORDER, hidden=False):
        self.label = label
        self.rows = rows                     # 24 on the TV; a README's strip is as long as its text
        self.border = border
        self.hidden = hidden                 # its text is beside it on the page: no accessible name
        self.cells = {}                      # (row, col) -> (glyph id, colour)
        self.bar = None
        self.icons = {}                      # icon hex -> glyph id
        self.lines = []                      # the text, for the accessible name

    def text(self, row, col, s, colour="w"):
        for i, ch in enumerate(s):
            if col + i >= COLS:
                break
            c = ord(ch) if 32 <= ord(ch) <= 126 else ord("?")
            if c != 32:
                self.cells[(row, col + i)] = (f"tvg{c}", colour)
        if s.strip():
            self.lines.append(s.strip())

    def icon(self, row, col, hexstr, colour, gid=None):
        """gid: a name of its own for the glyph, so a page's script can redraw it (the icon editor)"""
        if hexstr == "00" * 8:
            return
        gid = gid or "tvi" + hexstr
        self.cells[(row, col)] = (gid, colour)
        self.icons[gid] = hexstr

    def pixels(self):
        """the picture alone, 256 x 192: rows of palette indexes, and the palette (for png.write)"""
        order = list(PALETTE)
        px = [bytearray(COLS * 8) for _ in range(self.rows * 8)]
        if self.bar is not None:
            for y in range(self.bar * 8, self.bar * 8 + 8):
                px[y][:] = bytes([order.index("b")]) * (COLS * 8)
        for (r, c), (gid, colour) in self.cells.items():
            bits = bytes.fromhex(MENU["glyphs"][gid[3:]] if gid.startswith("tvg") else self.icons[gid])
            for y, byte in enumerate(bits):
                for x in range(8):
                    if byte >> (7 - x) & 1:
                        px[r * 8 + y][c * 8 + x] = order.index(colour)
        return [bytes(r) for r in px], [PALETTE[k] for k in order]

    def svg(self, extra_class=""):
        """the screen as an inline SVG (the glyphs come from glyph_defs on the same page)"""
        w, h, BORDER = COLS * 8, self.rows * 8, self.border
        cls = ("tv " + extra_class).strip()
        name = html.escape(self.label + ": " + " / ".join(self.lines))
        a11y = 'aria-hidden="true" focusable="false"' if self.hidden else f'role="img" aria-label="{name}"'
        parts = [f'<svg class="{cls}" viewBox="{-BORDER} {-BORDER} {w + 2 * BORDER} {h + 2 * BORDER}" '
                 f'width="{w + 2 * BORDER}" height="{h + 2 * BORDER}" {a11y} shape-rendering="crispEdges">']
        parts.append(f'<rect class="tv-bg" x="{-BORDER}" y="{-BORDER}" width="{w + 2 * BORDER}" height="{h + 2 * BORDER}"/>')
        if self.bar is not None:
            parts.append(f'<rect class="tv-bar" x="0" y="{self.bar * 8}" width="{w}" height="8"/>')
        by_colour = {}
        for (r, c), (gid, colour) in sorted(self.cells.items()):
            by_colour.setdefault(colour, []).append(f'<use href="#{gid}" x="{c * 8}" y="{r * 8}"/>')
        for colour, uses in sorted(by_colour.items()):
            parts.append(f'<g class="tv-{colour}">' + "".join(uses) + "</g>")
        parts.append("</svg>")
        return "".join(parts)

    def glyph_ids(self):
        return {gid for gid, _ in self.cells.values()}


def _path(hexstr):
    """an 8x8 bitmap (a byte a row, bit 7 the left pixel) as one path of runs"""
    d = []
    for y, byte in enumerate(bytes.fromhex(hexstr)):
        x = 0
        while x < 8:
            if byte >> (7 - x) & 1:
                start = x
                while x < 8 and byte >> (7 - x) & 1:
                    x += 1
                d.append(f"M{start} {y}h{x - start}v1h{start - x}z")
            else:
                x += 1
    return "".join(d)


def glyph_defs(screens):
    """one hidden <svg> holding every glyph and icon the page's screens use"""
    ids, icons = set(), {}
    for s in screens:
        ids |= s.glyph_ids()
        icons.update(s.icons)
    defs = []
    for gid in sorted(ids):
        if gid.startswith("tvg"):
            defs.append(f'<path id="{gid}" d="{_path(MENU["glyphs"][gid[3:]])}"/>')
        else:
            defs.append(f'<path id="{gid}" d="{_path(icons[gid])}"/>')
    return ('<svg class="tv-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>'
            + "".join(defs) + "</defs></svg>")


def icon_svg(hexstr, colour="m", label=None):
    """one 8x8 icon on the TV's black, for the catalogue and the plugin pages"""
    hexstr = hexstr if hexstr != "00" * 8 else MENU["icons"]["plugin"]
    a = f'role="img" aria-label="{html.escape(label)}"' if label else 'aria-hidden="true" focusable="false"'
    return (f'<svg class="tv-icon" viewBox="-2 -2 12 12" {a} shape-rendering="crispEdges">'
            f'<rect class="tv-bg" x="-2" y="-2" width="12" height="12"/>'
            f'<path class="tv-{colour}" d="{_path(hexstr)}"/></svg>')


# ---- the pages ----------------------------------------------------------------------

def plugins_page(entries, selected=0):
    """pub_plugins(): /PLUGINS as the menu lists it, by file name"""
    s = Screen("The cart's Plugins page")
    es = sorted(entries, key=lambda e: e["download"]["name"].upper())
    s.text(HEAD_ROW, 2, "Plugins")
    for r, e in enumerate(es[:LIST_ROWS]):
        icon = e["icon"] if e["icon"] != "00" * 8 and r < 7 else MENU["icons"]["plugin"]
        s.icon(LIST_ROW + r, 2, icon, "m")
        s.text(LIST_ROW + r, 4, cvp_row(e["name"], e["version"]))
    if es:
        s.bar = LIST_ROW + min(selected, len(es) - 1)
    s.text(MSG_ROW, 2, "A details  B back")
    return s


NEEDS = {"usb-host": "USB host", "usb-device": "USB device", "psram": "PSRAM"}      # plugins.c cvp_needs()


def details_page(e):
    """pub_details(): a plugin's details, as the text page shows them"""
    s = Screen(f"The cart's details page for {e['name']}")
    s.text(HEAD_ROW, 2, e["name"])
    lines = []
    lines += tpair("Version", e["version"])
    lines += tpair("By", e["by"] or "?")
    lines += tpair("ID", e["id"])
    lines += tpair("Opens", " ".join(e["opens"]) if e["opens"] else "no files: an app")
    lines += tpair("Folder", e["home"] or "none")
    lines += tpair("File", e["download"]["name"])
    lines += tpair("Size", f"{(e['download']['size'] + 1023) // 1024}K")
    needs = ", ".join(NEEDS[u] for u in e["uses"] if u in NEEDS)
    if needs:
        lines += tpair("Uses", needs)
    lines += tpair("In flash", "no: A copies it")
    for r, line in enumerate(lines[:LIST_ROWS]):
        s.text(LIST_ROW + r, 2, line)
    s.text(MSG_ROW, 2, "A start  # remove  B back")
    return s


def folder_page(path, names, file_icon=None, selected=0):
    """pub_card() inside a folder: the files a plugin opens, with its file icon;
    with none, the folder looks empty (the menu hides files nothing opens)"""
    s = Screen(f"The cart's {path} folder")
    s.text(HEAD_ROW, 2, path)
    icon = file_icon if file_icon and file_icon != "00" * 8 else MENU["icons"]["file"]
    for r, n in enumerate(names[:LIST_ROWS]):
        s.icon(LIST_ROW + r, 2, icon, "g")
        s.text(LIST_ROW + r, 4, n[:NAME_W])
    if names:
        s.bar = LIST_ROW + selected
        s.text(MSG_ROW, 2, "A open  B back")
    else:
        s.text(MSG_ROW, 2, "Nothing to play here. B: back")
    return s


README_COL = 1                               # 30 columns of text, a column clear each side


def readme_strip(text):
    """A plugin's README as the cart's README page sets it: the .CVP's text
    as it is, a line a row in the menu's font, 30 columns from column 1. One
    long strip, where the cart shows a screenful at a time."""
    lines = text.split("\n")
    if lines and not lines[-1]:
        lines.pop()
    s = Screen("The README on the cart", rows=len(lines) + 2, border=BORDER, hidden=True)
    for r, line in enumerate(lines):
        s.text(1 + r, README_COL, line)
    return s


def readme_page(name, text):
    """the first screenful of the cart's README page: the name, 19 lines, the help line"""
    lines = text.split("\n")
    s = Screen(f"The cart's README page for {name}")
    s.text(HEAD_ROW, README_COL, name)
    for r, line in enumerate(lines[:LIST_ROWS]):
        s.text(LIST_ROW + r, README_COL, line)
    s.text(MSG_ROW, README_COL, "Up/down scroll  B back")
    return s


def editor_pages(plugin_gid, file_gid):
    """the icon editor's two previews: the Plugins page with the icon being drawn on its
    selected row, and a folder of its files; the page's script redraws the two glyphs"""
    a = Screen("The Plugins page with your icon")
    a.text(HEAD_ROW, 2, "Plugins")
    a.icon(LIST_ROW, 2, MENU["icons"]["plugin"], "m", plugin_gid)
    a.text(LIST_ROW, 4, cvp_row("My Plugin", "1.0.0"))
    a.icon(LIST_ROW + 1, 2, MENU["icons"]["plugin"], "m", plugin_gid)
    a.text(LIST_ROW + 1, 4, cvp_row("My Plugin (off the bar)", "1.0.0"))
    a.icon(LIST_ROW + 2, 2, MENU["icons"]["plugin"], "m")
    a.text(LIST_ROW + 2, 4, cvp_row("Another plugin", "0.2.0"))
    a.bar = LIST_ROW
    a.text(MSG_ROW, 2, "A details  B back")
    b = Screen("A folder of your plugin's files")
    b.text(HEAD_ROW, 2, "/MYFILES")
    b.icon(LIST_ROW, 2, MENU["icons"]["folder"], "y")
    b.text(LIST_ROW, 4, "More")
    for r, n in enumerate(["First file", "Second file", "Third file"]):
        b.icon(LIST_ROW + 1 + r, 2, MENU["icons"]["file"], "g", file_gid)
        b.text(LIST_ROW + 1 + r, 4, n)
    b.bar = LIST_ROW + 1
    b.text(MSG_ROW, 2, "A open  B back")
    return a, b
