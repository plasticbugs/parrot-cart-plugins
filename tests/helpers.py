"""helpers for the tests: synthetic RP2350 images and .CVP files, written
the way the SDK's mkcvp.py writes them, synthetic screenshots, and the
GitHub scenarios the validator's tests replay (tests/scenarios.py).

Nothing here is a real plugin: every image is a few words of vector table
and one picobin block, and every file is made when the tests start, in a
temporary folder. To run tools/cvp.py over real builds too, point
PARROTCART_CVP_DIR at a folder of them (tests/test_cvp.py RealBuilds)."""
import atexit
import hashlib
import os
import shutil
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import cvp  # noqa: E402
import png  # noqa: E402

_BASE = tempfile.mkdtemp(prefix="registry-tests-")
atexit.register(shutil.rmtree, _BASE, True)
CVP_DIR = os.path.join(_BASE, "cvp")
GH_DIR = os.path.join(_BASE, "github")


def tmp():
    """a new empty folder, removed when the tests end"""
    return tempfile.mkdtemp(dir=_BASE)


def fixture(name):
    with open(os.path.join(CVP_DIR, name), "rb") as f:
        return f.read()


def image(load_map=None, absolute=False, reset=0x10000101, size=4096):
    """a minimal RP2350 image: a vector table, then one block (IMAGE_TYPE,
    an optional LOAD_MAP of (storage, runtime, size) entries, LAST) that
    links to itself"""
    w = [0x20082000, reset]
    w += [cvp.PICOBIN_START, 0x42 | 1 << 8 | 0x1021 << 16]
    if load_map:
        k = len(load_map)
        w.append(cvp.PICOBIN_LOAD_MAP | (1 + 3 * k) << 8 | k << 24 | (1 << 31 if absolute else 0))
        for st, rt, z in load_map:
            w += [st, rt, rt + z if absolute else z]
    items = len(w) - 3
    w += [cvp.PICOBIN_LAST | items << 8, 0, cvp.PICOBIN_END]
    raw = struct.pack(f"<{len(w)}I", *w)
    return raw + b"\0" * (size - len(raw))


def field(s, n):
    b = s.encode("latin1")
    return b + b"\0" * (n - len(b))


def make_cvp(img, id="tester.thing", name="Thing", version="1.0.0", by="Tester", home="/THING", opens=(),
             flags=0, icon=bytes(8), file_icon=bytes(8), api=1, hdr=512, sha=None, image_size=None,
             readme=None, readme_off=None, readme_len=None, gap=b""):
    """mkcvp.py's header (with any field overridden) and the image; readme
    (bytes or str) goes after the image (and gap), as the SDK stores it"""
    h = bytearray(hdr)
    h[0:8] = b"CVPLUG\0\0"
    struct.pack_into("<III", h, 8, hdr, api, len(img) if image_size is None else image_size)
    h[20:52] = sha if sha is not None else hashlib.sha256(img).digest()
    h[52:84] = field(id, 32)
    h[84:116] = field(name, 32)
    h[116:132] = field(version, 16)
    h[132:164] = field(by, 32)
    h[164:196] = field(home, 32)
    h[196:260] = b"".join(field(e, 8) for e in opens) + bytes(8 * (8 - len(opens)))
    struct.pack_into("<I", h, 260, flags)
    h[264:272] = icon
    h[272:280] = file_icon
    tail = b""
    if readme is not None:
        text = readme.encode("latin1") if isinstance(readme, str) else readme
        tail = gap + text
        struct.pack_into("<II", h, 280, hdr + len(img) + len(gap) if readme_off is None else readme_off,
                         len(text) if readme_len is None else readme_len)
    elif readme_off is not None or readme_len is not None:
        struct.pack_into("<II", h, 280, readme_off or 0, readme_len or 0)
    return bytes(h) + img + tail


def shot(seed=0, width=png.WIDTH, height=png.HEIGHT):
    """a synthetic screenshot: bars in four colours"""
    rows = [bytes(((x // 16 + y // 16 + seed) % 4) for x in range(width)) for y in range(height)]
    return png.write(rows, [(0, 0, 0), (255, 255, 255), (200, 80, 190), (90, 200, 120)])


SRAM_IMAGE = dict(load_map=[(0x10000000 + 0x100, 0x20000000, 0x800)])


import scenarios  # noqa: E402

scenarios.build(CVP_DIR, GH_DIR)
