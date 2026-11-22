"""tools/cvp.py on synthetic plugin files: ones shaped as the SDK writes them, and ones made to
break each rule. With PARROTCART_CVP_DIR set to a folder of real builds, those are checked too."""
import glob
import os
import hashlib
import struct
import unittest

from helpers import SRAM_IMAGE, fixture, image, make_cvp
import cvp
import registry
import scenarios

class Builds(unittest.TestCase):
    """the synthetic plugins the scenarios use (tests/scenarios.py): each header reads back"""

    def test_fields(self):
        for name, want in scenarios.PLUGINS.items():
            with self.subTest(name):
                data = fixture(name)
                code, p = cvp.parse(data)
                self.assertEqual(code, cvp.OK)
                self.assertEqual(p["hdr_size"], 512)
                self.assertEqual(p["api"], 1)
                info, errors, warnings = cvp.check(data)
                self.assertEqual(errors, [])
                self.assertEqual(warnings, [])
                for k in ("id", "name", "version", "by", "home", "opens", "uses", "icon", "file_icon"):
                    self.assertEqual(info[k], want[k], k)
                self.assertEqual(info["image"]["kind"], want["kind"])
                self.assertEqual(info["readme"], want.get("readme"))
                self.assertEqual(info["file"]["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(info["image"]["sha256"],
                                 hashlib.sha256(data[512:512 + info["image"]["size"]]).hexdigest())

    def test_icon_rows(self):
        self.assertEqual(cvp.icon_rows("007e81a5eba5817e"),
                         ["........", ".######.", "#......#", "#.#..#.#", "###.#.##", "#.#..#.#", "#......#",
                          ".######."])

    def test_needs(self):
        self.assertEqual(cvp.needs(5), "USB host, PSRAM")
        self.assertEqual(cvp.needs(0), "")
        self.assertEqual(cvp.needs(8 | 1), "USB host")            # standalone isn't something it uses
        self.assertEqual(cvp.uses(8 | 1), ["usb-host", "standalone"])
        self.assertTrue(cvp.standalone([], 0))
        self.assertFalse(cvp.standalone([".txt"], 0))
        self.assertTrue(cvp.standalone([".txt"], 8))


class MenuRules(unittest.TestCase):
    """cvp_parse()'s result codes, as plugins.c returns them"""

    def setUp(self):
        self.img = image(**SRAM_IMAGE)

    def test_synthetic_ok(self):
        info, errors, warnings = cvp.check(make_cvp(self.img, opens=[".thg"]))
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(info["image"]["kind"], "sram")

    def test_too_short(self):
        self.assertEqual(cvp.parse(b"CVPLUG\0\0" + bytes(100))[0], cvp.ESIZE)

    def test_magic(self):
        data = bytearray(make_cvp(self.img))
        data[0:6] = b"CVPLUX"
        self.assertEqual(cvp.parse(bytes(data))[0], cvp.EMAGIC)
        info, errors, _ = cvp.check(bytes(data))
        self.assertIsNone(info)
        self.assertIn("not a plugin", errors[0])

    def test_cut_short(self):
        data = make_cvp(self.img)
        self.assertEqual(cvp.parse(data[:-1])[0], cvp.ESIZE)
        self.assertEqual(cvp.parse(make_cvp(self.img, hdr=512)[:279] + b"\0")[0], cvp.ESIZE)
        small = bytearray(data)
        struct.pack_into("<I", small, 8, 100)              # a header smaller than the fields
        self.assertEqual(cvp.parse(bytes(small))[0], cvp.ESIZE)

    def test_id_ok_as_the_menu(self):
        for s, ok in [("a.b", True), ("vexed.nes", True), ("a..b", True), ("a.b.", True), (".a", False),
                      ("a.", False), ("a", False), ("A.b", False), ("a b.c", False), ("", False)]:
            self.assertEqual(cvp.id_ok(s), ok, s)

    def test_bad_id(self):
        code, _ = cvp.parse(make_cvp(self.img, id="Vexed.NES"))
        self.assertEqual(code, cvp.EID)

    def test_sdk_id_stricter(self):
        _, errors, _ = cvp.check(make_cvp(self.img, id="a..b"))
        self.assertTrue(any("The SDK writes it as" in e for e in errors))

    def test_fallbacks(self):
        _, p = cvp.parse(make_cvp(self.img, name="", version=""))
        self.assertEqual(p["name"], "tester.thing")              # an empty name is the ID
        self.assertEqual(p["version"], "?")
        _, errors, _ = cvp.check(make_cvp(self.img, name="", version=""))
        self.assertTrue(any("no name" in e for e in errors))
        self.assertTrue(any("major.minor.patch" in e for e in errors))

    def test_text_outside_ascii(self):
        _, p = cvp.parse(make_cvp(self.img, name="Caf\xe9"))
        self.assertEqual(p["name"], "Caf?")                      # plugins.c text()
        _, errors, _ = cvp.check(make_cvp(self.img, name="Caf\xe9"))
        self.assertTrue(any("printable ASCII" in e for e in errors))

    def test_vercmp(self):
        self.assertEqual(cvp.vercmp("1.0.10", "1.0.9"), 1)
        self.assertEqual(cvp.vercmp("0.4.6", "0.4.6"), 0)
        self.assertEqual(cvp.vercmp("1.2", "1.2.0"), 0)
        self.assertEqual(cvp.vercmp("0.3.9", "0.4.0"), -1)
        self.assertEqual(cvp.vercmp("2", "10"), -1)


class LaterRules(unittest.TestCase):
    """what the menu finds when it installs or starts a plugin, and the SDK's rules"""

    def setUp(self):
        self.img = image(**SRAM_IMAGE)

    def errors(self, data):
        return cvp.check(data)[1]

    def test_newer_api(self):
        self.assertTrue(any("newer cart firmware" in e for e in self.errors(make_cvp(self.img, api=2))))
        self.assertEqual(cvp.check(make_cvp(self.img, api=2), api_max=2)[1], [])

    def test_sha(self):
        self.assertTrue(any("SHA-256" in e for e in self.errors(make_cvp(self.img, sha=bytes(32)))))
        real = bytearray(fixture("PADTEST-0.1.2.CVP"))
        real[2000] ^= 1
        self.assertTrue(any("SHA-256" in e for e in self.errors(bytes(real))))

    def test_header_sectors(self):
        data = make_cvp(self.img, hdr=600)
        self.assertTrue(any("whole 512-byte sectors" in e for e in self.errors(data)))

    def test_too_big_for_a_slot(self):
        exact = image(**SRAM_IMAGE, size=cvp.SLOT_ROOM)
        self.assertEqual(cvp.check(make_cvp(exact))[1:], ([], []))
        two = image(size=cvp.SLOT_ROOM + 4)                       # over one slot: two side by side
        info, errors, warnings = cvp.check(make_cvp(two))
        self.assertEqual(errors, [])
        self.assertEqual(info["image"]["kind"], "xip")
        self.assertTrue(any("takes two" in w for w in warnings))
        self.assertEqual(self.errors(make_cvp(image(size=cvp.IMAGE_MAX))), [])
        big = image(size=cvp.IMAGE_MAX + 4)
        self.assertTrue(any("two flash slots hold" in e for e in self.errors(make_cvp(big))))
        self.assertEqual((cvp.span(cvp.SLOT_ROOM), cvp.span(cvp.SLOT_ROOM + 1)), (1, 2))
        self.assertEqual(cvp.IMAGE_MAX, 2 * 1024 * 1024 - 4096)
        # the registry reads a .CVP that big, with its header and the longest README
        limit = registry.load_config(registry.ROOT)["limits"]["asset_max_bytes"]
        self.assertGreaterEqual(limit, cvp.HDR_WRITTEN + cvp.IMAGE_MAX + cvp.README_MAX)

    def test_no_image(self):
        self.assertTrue(any("no image" in e for e in self.errors(make_cvp(b""))))

    def test_not_rp2350(self):
        self.assertTrue(any("isn't an RP2350 image" in e for e in self.errors(make_cvp(bytes(4096)))))

    def test_absolute_load_map_from_outside(self):
        img = image(load_map=[(0x10E00100, 0x20000000, 0x800)], absolute=True)
        self.assertTrue(any("only starts where it was built" in e for e in self.errors(make_cvp(img))))

    def test_xip(self):
        info, errors, _ = cvp.check(make_cvp(image()))
        self.assertEqual(errors, [])
        self.assertEqual(info["image"]["kind"], "xip")
        _, errors, _ = cvp.check(make_cvp(image(reset=0x20000101)))
        self.assertTrue(any("doesn't load into RAM" in e for e in errors))

    def test_extensions(self):
        self.assertTrue(any("1-7 letters" in e for e in self.errors(make_cvp(self.img, opens=["nes"]))))
        _, _, warnings = cvp.check(make_cvp(self.img, opens=[".col"]))
        self.assertTrue(any("ColecoVision header" in w for w in warnings))
        info, _, _ = cvp.check(make_cvp(self.img, opens=[".NES"]))
        self.assertEqual(info["opens"], [".nes"])                # the menu lower-cases them

    def test_folder(self):
        self.assertTrue(any("/PLUGINS" in e for e in self.errors(make_cvp(self.img, home="/PLUGINS"))))
        _, _, warnings = cvp.check(make_cvp(self.img, home="NES"))
        self.assertTrue(any("doesn't start with /" in w for w in warnings))

    def test_flags_and_tail(self):
        _, errors, warnings = cvp.check(make_cvp(self.img, flags=0x11) + b"extra")
        self.assertEqual(errors, [])
        self.assertTrue(any("mean nothing" in w for w in warnings))
        self.assertTrue(any("after the image" in w for w in warnings))

    def test_standalone(self):
        info, errors, warnings = cvp.check(make_cvp(self.img, opens=[".txt"], flags=0x9))
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(info["uses"], ["usb-host", "standalone"])


class Readme(unittest.TestCase):
    """the README section: header offsets 280 and 284, text after the image"""

    def setUp(self):
        self.img = image(**SRAM_IMAGE)

    def check(self, **kw):
        return cvp.check(make_cvp(self.img, **kw))

    def test_none_is_allowed(self):
        info, errors, warnings = self.check()
        self.assertEqual((info["readme"], errors, warnings), (None, [], []))

    def test_read_as_it_is(self):
        text = "MY PLUGIN\n\nCredits: me.\n" + "x" * 30 + "\n~ !\n"
        info, errors, warnings = self.check(readme=text)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(info["readme"], text)

    def test_the_image_sha_doesnt_cover_it(self):
        a, _, _ = self.check(readme="One.\n")
        b, _, _ = self.check(readme="Another.\n")
        self.assertEqual(a["image"]["sha256"], b["image"]["sha256"])
        self.assertNotEqual(a["file"]["sha256"], b["file"]["sha256"])

    def test_a_short_header_has_no_readme_fields(self):
        data = bytearray(make_cvp(self.img, hdr=280))
        code, p = cvp.parse(bytes(data))
        self.assertEqual((code, p["readme_off"], p["readme_len"]), (cvp.OK, 0, 0))

    def test_bounds(self):
        end = 512 + len(self.img)
        for kw, what in [(dict(readme="Hi.\n", readme_off=end + 1), "runs past the end"),
                         (dict(readme="Hi.\n", readme_off=100), "inside the header or the image"),
                         (dict(readme="Hi.\n", readme_off=end - 1), "inside the header or the image"),
                         (dict(readme="Hi.\n", readme_len=5), "runs past the end"),
                         (dict(readme="Hi.\n", readme_off=0xFFFFFFF0), "runs past the end"),
                         (dict(readme_off=end, readme_len=0), "don't agree"),
                         (dict(readme_off=0, readme_len=9), "don't agree")]:
            with self.subTest(kw):
                info, errors, _ = self.check(**kw)
                self.assertTrue(any(what in e for e in errors), errors)
                self.assertIsNone(info["readme"])

    def test_length(self):
        most = ("x" * 30 + "\n") * 528 + "x" * 16
        self.assertEqual(len(most), cvp.README_MAX)
        self.assertEqual(self.check(readme=most)[1], [])
        _, errors, _ = self.check(readme=most + "\n")
        self.assertTrue(any("16384 at most" in e for e in errors), errors)

    def test_charset(self):
        for bad in ("Caf\xe9\n", "tab\there\n", "dos\r\n", "nul\0\n", "del\x7f\n"):
            with self.subTest(bad):
                _, errors, _ = self.check(readme=bad)
                self.assertTrue(any("printable ASCII" in e for e in errors), errors)
        _, errors, _ = self.check(readme="ok\nok\nbad\x01\n")
        self.assertTrue(any("line 3" in e for e in errors), errors)

    def test_width(self):
        _, errors, _ = self.check(readme="fine\n" + "x" * 31 + "\n")
        self.assertTrue(any("line 2 is 31 characters" in e for e in errors), errors)

    def test_other_bytes_after_the_image(self):
        _, errors, warnings = self.check(readme="Hi.\n", gap=b"\0" * 12)
        self.assertEqual(errors, [])
        self.assertTrue(any("12 bytes after the image besides the README" in w for w in warnings), warnings)


@unittest.skipUnless(os.environ.get("PARROTCART_CVP_DIR"), "PARROTCART_CVP_DIR isn't set: no real builds to read")
class RealBuilds(unittest.TestCase):
    def test_each_passes(self):
        files = sorted(glob.glob(os.path.join(os.environ["PARROTCART_CVP_DIR"], "*.[Cc][Vv][Pp]")))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path), open(path, "rb") as f:
                info, errors, _ = cvp.check(f.read())
                self.assertEqual(errors, [])
                self.assertIsNotNone(info)


if __name__ == "__main__":
    unittest.main()
