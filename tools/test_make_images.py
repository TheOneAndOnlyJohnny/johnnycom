"""Tests for make_images.py.  Run: python3 -m unittest discover -s tools

The rendering tests need Pillow and the cached fonts in tools/fonts/ (run
make_images.py once); without them they are skipped.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List

import bundle
import make_images
from test_build_seo import PROJECT, load_real

HAS_PILLOW = make_images.Image is not None
HAS_FONTS = all((make_images.FONT_DIR / url.rsplit("/", 1)[1]).is_file() for url in make_images.FONTS.values())


class FontCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.font_dir = Path(tempfile.mkdtemp()) / "fonts"
        self.fetched: List[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.font_dir.parent)

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        return b"woff2"

    def test_downloads_once_then_uses_the_cache(self) -> None:
        path = make_images.font_file("mono-400", self.font_dir, self.fetch)
        self.assertEqual(path.name, "iosevka-latin-400-normal.woff2")
        self.assertEqual(path.read_bytes(), b"woff2")
        make_images.font_file("mono-400", self.font_dir, self.fetch)
        self.assertEqual(self.fetched, [make_images.FONTS["mono-400"]])
        self.assertEqual([p.name for p in self.font_dir.iterdir()], [path.name])  # no leftover .part

    def test_project_widths_match_the_page(self) -> None:
        template = bundle.read_template((PROJECT / "index.html").read_text(encoding="utf-8"))
        widths = ", ".join(str(width) for width in make_images.PROJECT_WIDTHS)
        self.assertIn(f"static PROJECT_IMAGE_WIDTHS = [{widths}];", template)
        self.assertIn(f'width="{make_images.PROJECT_WIDTHS[-1]}" height="{make_images.PROJECT_WIDTHS[-1] * 9 // 16}"', template)

    def test_fonts_match_the_page(self) -> None:
        template = bundle.read_template((PROJECT / "index.html").read_text(encoding="utf-8"))
        for url in make_images.FONTS.values():
            self.assertIn(url, template)


class ContentTest(unittest.TestCase):
    def test_current_employer(self) -> None:
        content = load_real("en")
        self.assertEqual(make_images.build_seo.current_employer(content), "Capital One")
        content["experience"][0]["roles"][0]["to"] = "2026-01"
        self.assertIsNone(make_images.build_seo.current_employer(content))

    def test_project_slugs_follow_the_page_order(self) -> None:
        contents = {"en": load_real("en"), "es": load_real("es")}
        self.assertEqual(make_images.project_slugs(contents), ["finsanity", "juanderful"])
        del contents["en"]["projects"]["items"][0]["image"], contents["es"]["projects"]["items"][0]["image"]
        self.assertEqual(make_images.project_slugs(contents), ["juanderful"])

    def test_project_file_names(self) -> None:
        self.assertEqual(make_images.project_file_names("finsanity"), [
            "img/projects/finsanity-640.webp", "img/projects/finsanity-1280.webp", "img/projects/finsanity-1280.jpg"])

    def test_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(make_images.main(["make_images.py", "--force"]), 2)
        self.assertIn("Usage:", err.getvalue())


@unittest.skipUnless(HAS_PILLOW, "needs Pillow")
class ProjectImageTest(unittest.TestCase):
    def test_variants_are_16_9_and_small(self) -> None:
        files = make_images.project_images("finsanity", PROJECT / "content")
        self.assertEqual(list(files), make_images.project_file_names("finsanity"))
        for name, data in files.items():
            with make_images.Image.open(io.BytesIO(data)) as image:
                width = int(name.rsplit("-", 1)[1].split(".")[0])
                self.assertEqual(image.size, (width, width * 9 // 16), name)
                self.assertEqual(image.format, "WEBP" if name.endswith(".webp") else "JPEG")
                self.assertNotIn("exif", image.info, "metadata stripped")
            self.assertLess(len(data), 250_000, name)
        self.assertLess(len(files["img/projects/finsanity-640.webp"]), 80_000)

    def test_output_is_byte_stable(self) -> None:
        self.assertEqual(make_images.project_images("juanderful", PROJECT / "content"),
                         make_images.project_images("juanderful", PROJECT / "content"))

    def test_crop_keeps_the_center(self) -> None:
        wide = make_images.crop_to_ratio(make_images.Image.new("RGB", (2752, 1536)))
        self.assertEqual(wide.size, (2730, 1536))
        tall = make_images.crop_to_ratio(make_images.Image.new("RGB", (1000, 1000)))
        self.assertEqual(tall.size, (1000, 562))

    def test_missing_source_is_an_error(self) -> None:
        with self.assertRaises(make_images.MissingSource) as caught:
            make_images.project_images("nope", PROJECT / "content")
        self.assertIn("content/nope.jpg not found", str(caught.exception))


@unittest.skipUnless(HAS_PILLOW and HAS_FONTS, "needs Pillow and tools/fonts/ (run make_images.py once)")
class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        shutil.copytree(PROJECT / "content", self.root / "content")

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def run_main(self) -> str:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(make_images.main(["make_images.py"], self.root), 0)
        return out.getvalue()

    def test_writes_every_file_with_the_right_sizes(self) -> None:
        self.assertIn("✓ wrote og-en.png, og-es.png, apple-touch-icon.png, favicon.ico, favicon.svg, "
                      "img/projects/finsanity-640.webp", self.run_main())
        for name, size in (("og-en.png", (1200, 630)), ("og-es.png", (1200, 630)), ("apple-touch-icon.png", (180, 180))):
            with make_images.Image.open(self.root / name) as image:
                self.assertEqual(image.size, size, name)
        with make_images.Image.open(self.root / "favicon.ico") as image:
            self.assertEqual(sorted(image.info["sizes"]), [(16, 16), (32, 32), (48, 48)])

    def test_rerun_writes_nothing(self) -> None:
        self.run_main()
        self.assertIn("nothing written", self.run_main())

    def test_languages_get_different_cards(self) -> None:
        self.run_main()
        self.assertNotEqual((self.root / "og-en.png").read_bytes(), (self.root / "og-es.png").read_bytes())

    def test_missing_project_image_writes_nothing(self) -> None:
        (self.root / "content/juanderful.jpg").unlink()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(make_images.main(["make_images.py"], self.root), 1)
        self.assertIn("content/juanderful.jpg not found", err.getvalue())
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["content"])

    def test_matches_the_project_images(self) -> None:
        self.run_main()
        projects = [name for slug in ("finsanity", "juanderful") for name in make_images.project_file_names(slug)]
        for name in ("og-en.png", "og-es.png", "apple-touch-icon.png", "favicon.ico", "favicon.svg", *projects):
            self.assertEqual((self.root / name).read_bytes(), (PROJECT / name).read_bytes(), f"{name} is stale")


if __name__ == "__main__":
    unittest.main()
