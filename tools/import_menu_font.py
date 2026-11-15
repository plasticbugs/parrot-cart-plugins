"""import_menu_font -- the cart menu's font and icons, for the site's
drawings of the TV screen.

    python3 tools/import_menu_font.py PATH/TO/coleco/firmware/revc/sdplayer

Reads font.asm (the menu font: Empty Windows Unboxed by VEXED, CC BY 4.0,
8x8 cells for ASCII 32-127) and icons.h (the menu's own icons), and writes
site/data/menu.json. Its output is committed; run it again only when the
menu's font or icons change.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rows_to_hex(rows):
    return "".join(f"{int(r.replace('#', '1').replace('.', '0'), 2):02x}" for r in rows)


def main():
    src = sys.argv[1]
    with open(os.path.join(src, "font.asm")) as f:
        rows = re.findall(r'DG\s+"([.#]{8})"', f.read())
    if len(rows) != 96 * 8:
        sys.exit(f"font.asm: {len(rows)} rows, not 768")
    glyphs = {str(32 + i): rows_to_hex(rows[8 * i:8 * i + 8]) for i in range(96)}
    with open(os.path.join(src, "icons.h")) as f:
        text = f.read()
    icons = {}
    for name, body in re.findall(r"\{ ICON_(\w+), \{(.*?)\} \}", text, re.S):
        art = re.findall(r'"([.#]{8})"', body)
        if len(art) == 8:
            icons[name.lower()] = rows_to_hex(art)
    out = {
        "source": "the cart's menu: firmware/revc/sdplayer/font.asm and icons.h",
        "font": "Empty Windows Unboxed by VEXED, CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
        "glyphs": glyphs,
        "icons": icons,
    }
    path = os.path.join(ROOT, "site", "data", "menu.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {path}: {len(glyphs)} glyphs, icons {', '.join(sorted(icons))}")


if __name__ == "__main__":
    main()
