"""Tests for the blog placeholder (blog/index.html).  Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

import make_images
from test_build_seo import PROJECT

PAGE = PROJECT / "blog" / "index.html"


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: List[Tuple[str, Dict[str, Optional[str]]]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.tags.append((tag, dict(attrs)))


class BlogPlaceholderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = PAGE.read_text(encoding="utf-8")
        self.parser = Collector()
        self.parser.feed(self.html)

    def attrs(self, tag: str) -> List[Dict[str, Optional[str]]]:
        return [attrs for name, attrs in self.parser.tags if name == tag]

    def test_kept_out_of_search_until_the_real_blog(self) -> None:
        self.assertIn({"name": "robots", "content": "noindex"}, self.attrs("meta"))

    def test_bilingual_with_a_link_home(self) -> None:
        self.assertEqual(self.attrs("html"), [{"lang": "en"}])
        self.assertIn({"lang": "es"}, self.attrs("section"))
        self.assertEqual(self.html.count("<h1>"), 1)
        self.assertIn({"class": "back", "href": "https://johnny.com.mx/"}, self.attrs("a"))

    def test_works_under_the_root_csp(self) -> None:
        # No scripts; only inline styles, data: images and jsDelivr fonts, which the root .htaccess allows.
        self.assertEqual(self.attrs("script"), [])
        self.assertEqual(self.attrs("img"), [])
        for icon in self.attrs("link"):
            self.assertTrue((icon["href"] or "").startswith("data:image/svg+xml"), icon)
        for url in re.findall(r'url\("([^"]+)"\)', self.html):
            self.assertIn(url, make_images.FONTS.values(), "same font files as the page")

    def test_light_like_the_main_site(self) -> None:
        self.assertIn("--base:#eff1f5", self.html)
        self.assertIn("color-scheme:light", self.html)
        self.assertIn({"name": "theme-color", "content": "#eff1f5"}, self.attrs("meta"))


if __name__ == "__main__":
    unittest.main()
