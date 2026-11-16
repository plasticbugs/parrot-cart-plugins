"""png -- check a plugin's screenshot, and write small PNGs.

A screenshot is the console's picture: a PNG of exactly 256 x 192 pixels,
100 KB at most (docs: the site's "Screenshots" page). check() reads the
file's structure and never hands it to an image library: the signature,
every chunk's length and CRC, the IHDR's fields, the pixel data inflated
(with a cap) to the size the header promises, and IEND at the very end.
Animated PNGs are refused.

write() makes an indexed PNG from rows of palette indexes: the examples'
screens (tools/seed_examples.py) and the tests' files.

Standard library only.
"""
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
WIDTH, HEIGHT = 256, 192
MAX_BYTES = 100 * 1024
# colour type -> (channels, the bit depths it may have)
TYPES = {0: (1, (1, 2, 4, 8, 16)), 2: (3, (8, 16)), 3: (1, (1, 2, 4, 8)), 4: (2, (8, 16)), 6: (4, (8, 16))}


def _chunks(data):
    """[(type, body)] or raises ValueError saying what is wrong"""
    if data[:8] != SIGNATURE:
        raise ValueError("it isn't a PNG file")
    out, at = [], 8
    while at < len(data):
        if at + 12 > len(data):
            raise ValueError("it's cut short")
        (n,) = struct.unpack_from(">I", data, at)
        kind = data[at + 4:at + 8]
        if n > len(data) - at - 12:
            raise ValueError("it's cut short")
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            raise ValueError("it has a chunk with a bad name")
        body = data[at + 8:at + 8 + n]
        (crc,) = struct.unpack_from(">I", data, at + 8 + n)
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f"the {kind.decode()} chunk is damaged (its CRC is wrong)")
        out.append((kind, body))
        at += 12 + n
        if kind == b"IEND":
            break
    if at != len(data):
        raise ValueError("it has bytes after the end of the picture")
    return out


def _pass_sizes(w, h, interlace):
    if not interlace:
        return [(w, h)]
    out = []
    for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2),
                           (0, 1, 1, 2)):
        pw, ph = (w - x0 + dx - 1) // dx, (h - y0 + dy - 1) // dy
        if pw and ph:
            out.append((pw, ph))
    return out


def check(data, width=WIDTH, height=HEIGHT, max_bytes=MAX_BYTES):
    """why data isn't an acceptable screenshot, or None"""
    if len(data) > max_bytes:
        return f"it's {len(data)} bytes, but a screenshot can be {max_bytes} at most"
    try:
        chunks = _chunks(data)
    except ValueError as e:
        return str(e)
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        return "it isn't a PNG file (no IHDR)"
    if chunks[-1][0] != b"IEND":
        return "it's cut short (no IEND)"
    w, h, depth, ctype, comp, filt, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
    if (w, h) != (width, height):
        return f"it's {w} x {h} pixels, but a screenshot has to be exactly {width} x {height}"
    if ctype not in TYPES or depth not in TYPES[ctype][1] or comp or filt or interlace > 1:
        return "the header doesn't describe any kind of PNG"
    names = [k for k, _ in chunks]
    if b"acTL" in names or b"fcTL" in names or b"fdAT" in names:
        return "it's an animated PNG, but a screenshot has to be one still picture"
    if ctype == 3 and b"PLTE" not in names:
        return "it has no palette"
    idat = [i for i, k in enumerate(names) if k == b"IDAT"]
    if not idat or idat != list(range(idat[0], idat[-1] + 1)):
        return "it has no picture data" if not idat else "the picture data is out of order"
    bits = TYPES[ctype][0] * depth
    want = sum(ph * (1 + (pw * bits + 7) // 8) for pw, ph in _pass_sizes(w, h, interlace))
    z = zlib.decompressobj()
    try:
        raw = z.decompress(b"".join(b for k, b in chunks if k == b"IDAT"), want + 1)
    except zlib.error:
        return "the picture data is damaged"
    if len(raw) != want or not z.eof:
        return "the picture data isn't the size the header says"
    return None


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def write(rows, palette):
    """an 8-bit indexed PNG: rows of palette indexes (bytes), palette a list of (r, g, b)"""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + _chunk(b"PLTE", b"".join(bytes(c) for c in palette))
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))
