"""cvp -- read a Parrot Cart plugin file (.CVP) as the cart's menu reads it.

The layout and every rule here come from the cart's firmware, in the
coleco repository (firmware/revc/):

  sdplayer/plugins.c   cvp_parse(): the header fields, id_ok(), text()
  sdplayer/plugins.h   CVP_HDR_MIN, CVP_EXTS, the flag bits, CVP_API
  sdplayer/plugslot.c  ps_install(): image size and header size limits
  sdplayer/plugslot.h  PS_SLOT_SIZE, PS_REC (a slot less its 4K record)
  sdplayer/picobin.h   picobin_walk(): the image's block loop
  sdplayer/sdplayer.c  plug_chainable(): can it start from a flash slot
  sdplayer/mkcvp.py    what the SDK writes (stricter than the menu)
  docs/plugins.md      "The plugin file (.cvp)"

The README section is the text the menu shows as a plugin's README page:
two header fields at 280 and 284, and plain text after the image, which
the image's SHA-256 doesn't cover (the site's authors/readme page).

parse() gives the fields exactly as cvp_parse() fills cvp_t, and its result
code. check() then adds what the menu finds only later (installing into a
slot, starting it) and the registry's own rules, as errors and warnings.

Standard library only.
"""
import hashlib
import re
import struct

MAGIC = b"CVPLUG\0\0"
HDR_MIN = 280                  # plugins.h CVP_HDR_MIN: the fields end here
HDR_WRITTEN = 512              # mkcvp.py HDR: what the SDK writes
HDR_README = 288               # a header at least this long has the README fields
README_OFF, README_LEN = 280, 284      # u32 LE each: from the file's start (0: none), and its length
README_MAX = 16384             # the most text the menu's README page takes
README_COLS = 30               # its lines, wrapped by the SDK when it builds the plugin
EXTS = 8                       # plugins.h CVP_EXTS
API_MENU = 1                   # plugins.h CVP_API: the newest menu's API

# plugins.h result codes and cvp_err() texts
OK, EMAGIC, ESIZE, EID = 0, -1, -2, -3
ERR_TEXT = {OK: "ok", EMAGIC: "not a plugin", ESIZE: "cut short", EID: "its ID is bad"}

# plugins.h flags; the names are mkcvp.py's --uses words, the labels cvp_needs()'s
FLAGS = (
    (1, "usb-host", "USB host"),
    (2, "usb-device", "USB device"),
    (4, "psram", "PSRAM"),
)

# plugslot.h
SLOT_SIZE = 0x00100000
SECTOR = 4096
SLOT_ROOM = SLOT_SIZE - SECTOR             # PS_REC: the most an image can be
SLOTS = 10                                 # sdplayer.c NSLOT
SLOT_OFF = 0x00400000                      # sdplayer.c SLOT_OFF

# RP2350 addresses (picobin.h, sdplayer.c's SRAM_BASE/SRAM8_BASE/XIP_BASE)
XIP_BASE = 0x10000000
XIP_HI = 0x14000000
SRAM_BASE = 0x20000000
SRAM8_BASE = 0x20080000

PICOBIN_START = 0xFFFFDED3
PICOBIN_END = 0xAB123579
PICOBIN_IMAGE_TYPE = 0x42
PICOBIN_LOAD_MAP = 0x06
PICOBIN_LAST = 0xFF

# mkcvp.py's rules, which the SDK enforces when it builds a plugin
ID_SDK = re.compile(r"[a-z0-9_-]+(\.[a-z0-9_-]+)+")
VERSION_SDK = re.compile(r"\d+\.\d+\.\d+")
EXT_SDK = re.compile(r"\.[A-Za-z0-9]{1,7}")


def _u32(b, off):
    return struct.unpack_from("<I", b, off)[0]


def _text(b, off, n):
    """plugins.c text(): up to the first 0 of an n-byte field, '?' for a
    byte outside 32-126. Also says whether such a byte was there."""
    raw = b[off:off + n].split(b"\0", 1)[0]
    bad = any(c < 32 or c > 126 for c in raw)
    return "".join(chr(c) if 32 <= c <= 126 else "?" for c in raw), bad


def id_ok(s):
    """plugins.c id_ok(): a '.' with something before and after the first
    one; only a-z 0-9 . - _"""
    dot = s.find(".")
    if dot <= 0 or dot + 1 >= len(s):
        return False
    return all(c in "abcdefghijklmnopqrstuvwxyz0123456789.-_" for c in s)


def vercmp(a, b):
    """plugins.c cvp_vercmp(): the first three numbers, -1 0 1"""
    def nums(s):
        out, i = [], 0
        for _ in range(3):
            x = 0
            while i < len(s) and s[i].isdigit() and s[i] in "0123456789":
                x = x * 10 + ord(s[i]) - 48
                i += 1
            out.append(x)
            if i < len(s) and s[i] == ".":
                i += 1
        return out
    x, y = nums(a), nums(b)
    return (x > y) - (x < y)


def parse(data):
    """cvp_parse(), for a whole file's bytes: (code, fields). The fields are
    filled as far as they could be, as the C fills cvp_t, plus the raw
    bytes the checks need."""
    p = {
        "hdr_size": 0, "api": 0, "image_size": 0, "sha256": "", "id": "", "name": "",
        "version": "", "dev": "", "home": "", "ext": [""] * EXTS, "flags": 0,
        "icon": "00" * 8, "file_icon": "00" * 8, "nonascii": [], "readme_off": 0, "readme_len": 0,
    }
    size = len(data)
    if size < HDR_MIN:
        return ESIZE, p
    if data[:8] != MAGIC:
        return EMAGIC, p
    p["hdr_size"] = _u32(data, 8)
    p["api"] = _u32(data, 12)
    p["image_size"] = _u32(data, 16)
    p["sha256"] = data[20:52].hex()
    for key, off, n in (("id", 52, 32), ("name", 84, 32), ("version", 116, 16), ("dev", 132, 32), ("home", 164, 32)):
        p[key], bad = _text(data, off, n)
        if bad:
            p["nonascii"].append(key)
    for i in range(EXTS):
        p["ext"][i], bad = _text(data, 196 + 8 * i, 8)
        if bad:
            p["nonascii"].append("opens")
    p["flags"] = _u32(data, 260)
    p["icon"] = data[264:272].hex()
    p["file_icon"] = data[272:280].hex()
    if p["hdr_size"] >= HDR_README and size >= HDR_README:
        p["readme_off"], p["readme_len"] = _u32(data, README_OFF), _u32(data, README_LEN)
    # (the C's display fallbacks; the registry keeps what the file says too)
    p["name_raw"], p["version_raw"] = p["name"], p["version"]
    if not p["name"]:
        p["name"] = p["id"]
    if not p["version"]:
        p["version"] = "?"
    if p["hdr_size"] < HDR_MIN or p["hdr_size"] + p["image_size"] > size:
        return ESIZE, p
    if not id_ok(p["id"]):
        return EID, p
    return OK, p


def picobin_walk(w, at, ram_lo=SRAM_BASE, ram_hi=SRAM8_BASE):
    """picobin.h picobin_walk() over the 32-bit words w, at XIP address at:
    None if it isn't a closed block loop starting with IMAGE_TYPE in the
    first 4K, else (ram_end, moves)."""
    nw = len(w)
    lim = min(nw, 1024)
    first = 0
    while first + 1 < lim and not (w[first] == PICOBIN_START and (w[first + 1] & 0xFF) == PICOBIN_IMAGE_TYPE):
        first += 1
    if first + 1 >= lim:
        return None
    b, end, moves = first, ram_lo, True
    for _ in range(8):
        i = b + 1
        while True:
            if i + 2 >= nw:
                return None
            h = w[i]
            t = h & 0xFF
            sz = (h >> 8 & 0xFFFF) if t & 0x80 else (h >> 8 & 0xFF)
            if t == PICOBIN_LAST:
                break
            if not sz or i + sz + 2 >= nw:
                return None
            if t == PICOBIN_LOAD_MAP:
                k = ((h << 1) & 0xFFFFFFFF) >> 25
                if 1 + 3 * k > sz:
                    return None
                for e in range(k):
                    st, rt, z = w[i + 1 + 3 * e], w[i + 2 + 3 * e], w[i + 3 + 3 * e]
                    if h >> 31:
                        z = (z - rt) & 0xFFFFFFFF
                        if XIP_BASE <= st < XIP_HI and (st < at or st + z > at + 4 * nw):
                            moves = False
                    if ram_lo <= rt < ram_hi and rt + z > end:
                        end = rt + z
            i += sz
        link = w[i + 1] - (1 << 32 if w[i + 1] >> 31 else 0)
        if w[i + 2] != PICOBIN_END or link % 4:
            return None
        b = b + int(link / 4)
        if b == first:
            return end, moves
        if not 0 <= b < nw or w[b] != PICOBIN_START:
            return None
    return None


def chainable(image):
    """sdplayer.c plug_chainable(), for the image in each of the menu's
    slots (the menu picks the slot, so it must work in all of them).
    (None, kind) with kind "sram" (a load map into SRAM: the bootrom copies
    it there) or "xip" (runs in place from its slot), or (why not, None)."""
    slot = image + b"\xff" * (SLOT_ROOM - len(image))      # past the image, as erased
    w = struct.unpack_from(f"<{SLOT_ROOM // 4}I", slot)
    kind = None
    for k in range(SLOTS):
        at = XIP_BASE + SLOT_OFF + k * SLOT_SIZE
        r = picobin_walk(w, at)
        if r is None:
            return "It isn't an RP2350 image", None
        ram_end, moves = r
        if ram_end <= SRAM_BASE:
            if w[1] < XIP_BASE or w[1] >= XIP_BASE + SLOT_ROOM:
                return "It doesn't load into RAM", None
            kind = "xip"
        elif not moves:
            return f"It only starts where it was built (not from slot {k})", None
        else:
            kind = "sram"
    return None, kind


def readme_text_problems(text):
    """what is wrong with a README's text (bytes) for the cart's page: [] if nothing"""
    bad = []
    if not text:
        return ["it's empty"]
    if len(text) > README_MAX:
        bad.append(f"it's {len(text)} bytes, but the menu's README page takes {README_MAX} at most")
    odd = sorted({c for c in text if c != 10 and not 32 <= c <= 126})
    if odd:
        at = next(i for i, c in enumerate(text) if c in odd)
        line = text.count(b"\n", 0, at) + 1
        bad.append("it has bytes that aren't printable ASCII or a line feed ("
                   + ", ".join(f"0x{c:02x}" for c in odd[:6]) + ("..." if len(odd) > 6 else "")
                   + f"), and the first one is on line {line}")
    lines = text.split(b"\n")
    wide = [i + 1 for i, ln in enumerate(lines) if len(ln) > README_COLS]
    if wide:
        bad.append(f"line {wide[0]} is {len(lines[wide[0] - 1])} characters, but the page is {README_COLS} wide"
                   + (f". {len(wide) - 1} other {'line is' if len(wide) == 2 else 'lines are'} too long as well"
                      if len(wide) > 1 else ""))
    return bad


def readme(data, p):
    """The README section of a parsed file: (text or None, errors).
    None with no errors: the plugin has none, which is allowed. The menu
    (plugins.c cvp_parse) quietly shows no README when the fields are wrong;
    the registry says what is wrong instead. The text's rules are the SDK's
    cvreadme.py check(): the length, the width, the characters."""
    off, n = p["readme_off"], p["readme_len"]
    if not off and not n:
        return None, []
    if not off or not n:
        return None, [f"the README fields don't agree. The offset is {off} and the length is {n}, but both are 0 when "
                      "there's no README"]
    end = p["hdr_size"] + p["image_size"]
    if off < end:
        return None, [f"the README starts at {off}, inside the header or the image, which end at {end}"]
    if off + n > len(data):
        return None, [f"the README ({n} bytes at {off}) runs past the end of the {len(data)}-byte file"]
    text = data[off:off + n]
    bad = readme_text_problems(text)
    if bad:
        return None, ["in the README, " + b for b in bad]
    return text.decode("ascii"), []


def icon_rows(hexstr):
    """an 8x8 icon, a byte a row, bit 7 the left pixel: 8 strings of # and ."""
    b = bytes.fromhex(hexstr)
    return ["".join("#" if v >> (7 - x) & 1 else "." for x in range(8)) for v in b]


def uses(flags):
    return [name for bit, name, _ in FLAGS if flags & bit]


def needs(flags):
    """cvp_needs(): "USB host, PSRAM" """
    return ", ".join(label for bit, _, label in FLAGS if flags & bit)


def check(data, api_max=API_MENU):
    """Everything the registry checks in one .CVP file's bytes.
    Returns (info, errors, warnings): info is the plugin's fields for the
    registry (None if the header can't be read at all)."""
    errors, warnings = [], []
    code, p = parse(data)
    if code == EMAGIC or (code == ESIZE and p["hdr_size"] == 0):
        errors.append(f"the menu would list it as a plain file, not a plugin. It would say \"{ERR_TEXT[code]}\"")
        return None, errors, warnings
    if code == ESIZE:
        errors.append(f"the menu would say \"{ERR_TEXT[code]}\". A {p['hdr_size']}-byte header and a "
                      f"{p['image_size']}-byte image don't fit in a {len(data)}-byte file")
        return None, errors, warnings
    if code == EID:
        errors.append(f"the menu would say \"{ERR_TEXT[code]}\". {p['id']!r} isn't developer.pluginname, written with "
                      "lowercase letters, digits, . - and _")
        return None, errors, warnings

    # the menu takes it from here; what it finds later
    if p["api"] > api_max:
        errors.append(f"it needs plugin API {p['api']}, and the cart's newest firmware has {api_max} "
                      "(the menu says \"It needs newer cart firmware\")")
    if p["api"] == 0:
        errors.append("the API version is 0, but the SDK writes 1 or more")
    hdr, isz = p["hdr_size"], p["image_size"]
    if hdr % 512:
        errors.append(f"the header is {hdr} bytes, not whole 512-byte sectors. The cart would say "
                      "\"its header isn't whole sectors\"")
    if not isz:
        errors.append("it has no image, so the cart would refuse it")
    elif isz > SLOT_ROOM:
        errors.append(f"the image is {isz} bytes, but a flash slot holds {SLOT_ROOM}. The cart would say "
                      "\"it's too big for a slot\"")
    readme_text, readme_errors = readme(data, p)
    errors += readme_errors
    if readme_text is not None and not readme_text.endswith("\n"):
        warnings.append("the README's last line doesn't end with a line feed. The SDK always ends it with one")
    tail = len(data) - hdr - isz - (p["readme_len"] if readme_text is not None else 0)
    if tail and not readme_errors:
        warnings.append(f"{tail} bytes after the image" + (" besides the README" if readme_text is not None else "")
                        + ", which the menu ignores")
    image = data[hdr:hdr + isz]
    if isz and hashlib.sha256(image).hexdigest() != p["sha256"]:
        errors.append("the image doesn't match the SHA-256 in the header, so the cart would refuse to copy it. "
                      "It would say \"the copy doesn't match its SHA-256\"")
    kind = None
    if isz and isz <= SLOT_ROOM:
        why, kind = chainable(image)
        if why:
            errors.append(f"the menu couldn't start it from a flash slot. It would say \"{why}\"")

    # the SDK's rules (mkcvp.py), which the registry holds every plugin to
    pid = p["id"]
    if not ID_SDK.fullmatch(pid):
        errors.append(f"the ID {pid!r} isn't developer.pluginname. The SDK writes it as parts of a-z 0-9 - _ "
                      "joined by single dots")
    if p["nonascii"]:
        errors.append("some fields have bytes outside printable ASCII, and the menu shows them as ?. They're in "
                      + ", ".join(sorted(set(p["nonascii"]))))
    if not p["name_raw"]:
        errors.append("it has no name, so the menu would show its ID instead")
    if not VERSION_SDK.fullmatch(p["version_raw"]):
        errors.append(f"the version {p['version_raw']!r} isn't major.minor.patch")
    if not p["dev"]:
        warnings.append("it has no developer (BY), so the menu shows \"By ?\"")
    exts = [e for e in p["ext"] if e]
    for e in exts:
        if not EXT_SDK.fullmatch(e):
            errors.append(f"it opens {e!r}, but an extension is a dot and 1-7 letters or digits")
    low = [e.lower() for e in exts]
    if len(set(low)) != len(low):
        warnings.append("it lists an extension twice")
    for e in sorted(set(low) & {".rom", ".col"}):
        warnings.append(f"it opens {e}, but the menu opens ColecoVision ROMs itself. The plugin only gets "
                        f"{e} files that aren't ROMs")
    home = p["home"]
    if home and not home.startswith("/"):
        warnings.append(f"the folder {home!r} doesn't start with /")
    if home.strip("/").upper() == "PLUGINS":
        errors.append("the folder is /PLUGINS, which the menu hides")
    known = sum(bit for bit, _, _ in FLAGS)
    if p["flags"] & ~known:
        warnings.append(f"flag bits {p['flags'] & ~known:#x} mean nothing to the menu")

    info = {
        "id": pid,
        "name": p["name_raw"],
        "version": p["version_raw"],
        "by": p["dev"],
        "api": p["api"],
        "home": home,
        "opens": low,
        "uses": uses(p["flags"]),
        "flags": p["flags"],
        "icon": p["icon"],
        "file_icon": p["file_icon"],
        "header_size": hdr,
        "readme": readme_text,
        "image": {"size": isz, "sha256": p["sha256"], "kind": kind},
        "file": {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    }
    return info, errors, warnings


def main(argv=None):
    """python3 tools/cvp.py FILE.CVP ...: each file's fields and verdict"""
    import json
    import sys
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(main.__doc__)
        return 2
    bad = 0
    for path in args:
        with open(path, "rb") as f:
            info, errors, warnings = check(f.read())
        print(json.dumps({"file": path, "plugin": info, "errors": errors, "warnings": warnings}, indent=2))
        bad += bool(errors)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
