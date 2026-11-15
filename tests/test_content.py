"""the pieces a plugin's page is made of: the cart's README text against the
SDK's own converter and check, screenshots (tools/png.py), and the files an
entry keeps beside it"""
import copy
import os
import struct
import unittest
import zlib

from helpers import ROOT, SRAM_IMAGE, image, make_cvp, shot, tmp
import cvp
import cvreadme
import png
import registry
import seed_examples
import tvscreen

DATA = os.path.join(ROOT, "tests", "data")


def read(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return f.read()


class CartReadme(unittest.TestCase):
    """the registry reads what the SDK writes, and refuses what its check refuses"""

    def test_the_sdks_sample(self):
        md, txt = read("readme_sample.md"), read("readme_sample.txt")
        self.assertEqual(cvreadme.convert(md), txt)              # this copy of the converter is the SDK's
        info, errors, warnings = cvp.check(make_cvp(image(**SRAM_IMAGE), readme=txt))
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(info["readme"], txt)                    # as it is: nothing converted again

    def test_the_same_verdict_as_the_sdk(self):
        texts = ["ok\n", "", "x" * 30 + "\n", "x" * 31 + "\n", "a\n\n\nb\n", "café\n", "tab\there\n",
                 "cr\r\n", "~ !\n", "\x7f\n", "no newline at the end", ("y" * 30 + "\n") * 528 + "z" * 16,
                 ("y" * 30 + "\n") * 529, " \n", "\n"]
        for t in texts:
            with self.subTest(t[:20]):
                sdk = cvreadme.check(t)
                ours = cvp.readme_text_problems(t.encode("utf-8"))
                if t == "":                                      # no text is "no README": both fields 0
                    self.assertTrue(ours)
                    continue
                self.assertEqual(sdk is None, ours == [], (sdk, ours))

    def test_a_cut_readme_passes(self):
        text = cvreadme.convert("word " * 6000)
        self.assertTrue(text.endswith(cvreadme.CUT_LINE + "\n"))
        self.assertEqual(cvp.readme_text_problems(text.encode()), [])

    def test_drawn_as_it_is(self):
        text = "TITLE\n\n- one\n  two\n"
        s = tvscreen.readme_strip(text)
        self.assertEqual(s.rows, 6)
        self.assertEqual(s.cells[(1, 1)], ("tvg84", "w"))        # T, at the page's first column
        self.assertEqual(s.cells[(4, 3)], ("tvg116", "w"))       # the hanging indent kept
        self.assertEqual(len(s.cells), len(text.replace(" ", "").replace("\n", "")))


class Png(unittest.TestCase):
    def test_a_screenshot(self):
        self.assertIsNone(png.check(shot()))

    def chunk(self, kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    def build(self, ihdr, idat, extra=b"", plte=True):
        return (png.SIGNATURE + self.chunk(b"IHDR", ihdr) + (self.chunk(b"PLTE", bytes(6)) if plte else b"") + extra
                + self.chunk(b"IDAT", idat) + self.chunk(b"IEND", b""))

    def test_refusals(self):
        good = shot()
        hdr = struct.pack(">IIBBBBB", 256, 192, 8, 3, 0, 0, 0)
        rows = zlib.compress(bytes(257 * 192))
        self.assertIsNone(png.check(self.build(hdr, rows)))
        crc = bytearray(good)
        crc[40] ^= 1
        cases = [
            (b"GIF89a" + bytes(100), "isn't a PNG"),
            (good[:60], "cut short"),
            (bytes(crc), "damaged"),
            (good + b"\0", "after the end"),
            (shot(width=512, height=384), "512 x 384"),
            (shot(width=192, height=256), "192 x 256"),
            (self.build(hdr, zlib.compress(bytes(257 * 100))), "isn't the size"),
            (self.build(hdr, zlib.compress(bytes(257 * 192 + 5))), "isn't the size"),
            (self.build(hdr, b"not zlib data"), "damaged"),
            (self.build(hdr, rows, plte=False), "no palette"),
            (self.build(hdr, rows, self.chunk(b"acTL", bytes(8))), "animated"),
            (self.build(struct.pack(">IIBBBBB", 256, 192, 3, 2, 0, 0, 0), rows), "no kind of PNG"),
            (png.SIGNATURE + self.chunk(b"IHDR", hdr) + self.chunk(b"PLTE", bytes(6)) + self.chunk(b"IEND", b""),
             "no picture data"),
            (png.SIGNATURE + self.chunk(b"IDAT", rows) + self.chunk(b"IEND", b""), "no IHDR"),
            (self.build(hdr, zlib.compress(os.urandom(257 * 192), 0)) + b"", None),
        ]
        for data, what in cases:
            with self.subTest(what):
                why = png.check(data)
                if what is None:
                    self.assertIsNone(why)
                else:
                    self.assertIn(what, why or "")
        heavy = self.build(hdr, rows, self.chunk(b"tEXt", bytes(png.MAX_BYTES)))
        self.assertIn("102400 at most", png.check(heavy))

    def test_a_bomb_isnt_inflated(self):
        hdr = struct.pack(">IIBBBBB", 256, 192, 8, 3, 0, 0, 0)
        bomb = zlib.compress(bytes(64 * 1024 * 1024), 9)         # 64 MB of zeros in about 64 KB
        self.assertLess(len(bomb), png.MAX_BYTES)
        self.assertIn("isn't the size", png.check(self.build(hdr, bomb)))

    def test_other_depths_and_interlace(self):
        for depth, ctype, bits in ((1, 0, 1), (8, 2, 24), (8, 6, 32), (16, 6, 64), (4, 3, 4)):
            raw = bytes((1 + (256 * bits + 7) // 8) * 192)
            data = self.build(struct.pack(">IIBBBBB", 256, 192, depth, ctype, 0, 0, 0), zlib.compress(raw))
            self.assertIsNone(png.check(data), (depth, ctype))
        sizes = png._pass_sizes(256, 192, 1)
        raw = bytes(sum(h * (1 + w) for w, h in sizes))
        self.assertIsNone(png.check(self.build(struct.pack(">IIBBBBB", 256, 192, 8, 3, 0, 0, 1), zlib.compress(raw))))

    def test_the_menus_pages_as_pictures(self):
        e = registry.load_entries(ROOT, examples=True)["moviecart.nes"]
        rows, palette = tvscreen.details_page(e).pixels()
        self.assertEqual((len(rows), len(rows[0])), (192, 256))
        self.assertIsNone(png.check(png.write(rows, palette)))
        self.assertEqual(rows[8][8 + 1:8 + 7], bytes(6))         # row 1 starts two characters in


class EntryFiles(unittest.TestCase):
    def setUp(self):
        self.entries = registry.load_entries(ROOT, examples=True)
        self.e = self.entries["moviecart.nes"]
        self.dir = registry.files_dir(ROOT, "moviecart.nes", examples=True)

    def test_examples_have_their_files(self):
        for pid, e in self.entries.items():
            self.assertEqual(registry.check_files(registry.files_dir(ROOT, pid, examples=True), e), [], pid)
        self.assertIsNone(self.entries["moviecart.nesinfo"]["readme"]["cart"])     # the page without one
        self.assertEqual(self.entries["moviecart.psgsynth"]["screenshots"], [])

    def test_examples_are_what_the_seeder_writes(self):
        for e, files in seed_examples.build(self.e["updated"]):
            self.assertEqual(e, self.entries[e["id"]], e["id"])
            for name, data in files.items():
                self.assertEqual(data, registry.read_file(ROOT, e, name), (e["id"], name))

    def test_schema(self):
        bad = [
            ("readme", {"cart": None}), ("readme", None),
            ("readme", dict(self.e["readme"], cart=dict(self.e["readme"]["cart"], file="../x.txt"))),
            ("readme", dict(self.e["readme"], cart=dict(self.e["readme"]["cart"], size=cvp.README_MAX + 1))),
            ("readme", dict(self.e["readme"], web=dict(self.e["readme"]["web"], url="javascript:x"))),
            ("screenshots", self.e["screenshots"] * 2),
            ("screenshots", [dict(self.e["screenshots"][0], file="screenshot-4.png")]),
            ("screenshots", [dict(self.e["screenshots"][0], file="shot.svg")]),
            ("screenshots", [dict(self.e["screenshots"][0], size=png.MAX_BYTES + 1)]),
            ("screenshots", list(reversed(self.e["screenshots"]))),
            ("history", []), ("history", [dict(self.e["history"][0], version="0.4.5")]),
            ("history", [dict(self.e["history"][0], notes="x" * (registry.NOTES_MAX + 1))]),
            ("history", self.e["history"] + [dict(self.e["history"][0], version="0.5.0")]),
            ("history", [dict(self.e["history"][0], url="http://example.com")]),
        ]
        self.assertEqual(registry.check_entry(self.e), [])
        for key, value in bad:
            with self.subTest(key=key, value=str(value)[:60]):
                e = copy.deepcopy(self.e)
                e[key] = value
                self.assertTrue(any(p.startswith(key) for p in registry.check_entry(e)))

    def test_files_must_be_the_entrys(self):
        d = os.path.join(tmp(), "moviecart.nes")
        os.makedirs(d)
        for name in registry.entry_files(self.e):
            with open(os.path.join(d, name), "wb") as f:
                f.write(registry.read_file(ROOT, self.e, name))
        self.assertEqual(registry.check_files(d, self.e), [])
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write("<script>")
        self.assertIn("index.html: the entry doesn't list it", registry.check_files(d, self.e))
        os.remove(os.path.join(d, "index.html"))
        os.remove(os.path.join(d, "screenshot-2.png"))
        os.symlink(os.path.join(self.dir, "screenshot-2.png"), os.path.join(d, "screenshot-2.png"))
        self.assertTrue(any("not a plain file" in p for p in registry.check_files(d, self.e)))
        os.remove(os.path.join(d, "screenshot-2.png"))
        with open(os.path.join(d, "screenshot-2.png"), "wb") as f:
            f.write(bytes(self.e["screenshots"][1]["size"]))
        self.assertTrue(any("SHA-256" in p for p in registry.check_files(d, self.e)))


if __name__ == "__main__":
    unittest.main()
