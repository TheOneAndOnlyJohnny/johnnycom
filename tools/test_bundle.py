"""Tests for bundle.py.  Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import contextlib
import io
import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Tuple

import bundle

REAL_INDEX = Path(__file__).resolve().parent.parent / "index.html"
TINY = '<html><body><script>x</script>\n<script type="__bundler/template">"<p>old</p>"</script>\n<p>after</p></body></html>'

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
             "path", "circle", "rect", "line", "polyline", "polygon", "stop"}


class TagBalance(HTMLParser):
    """Records closing tags that don't match the innermost open tag, with their line numbers."""

    def __init__(self) -> None:
        super().__init__()
        self.open_tags: List[Tuple[str, int]] = []
        self.mismatches: List[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag not in VOID_TAGS:
            self.open_tags.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if self.open_tags and self.open_tags[-1][0] == tag:
            self.open_tags.pop()
            return
        innermost = self.open_tags[-1] if self.open_tags else ("nothing", 0)
        self.mismatches.append(f"line {self.getpos()[0]}: </{tag}> while <{innermost[0]}> (line {innermost[1]}) is open")


class BundleTest(unittest.TestCase):
    def test_real_index_round_trips_byte_for_byte(self) -> None:
        html = REAL_INDEX.read_text(encoding="utf-8")
        template = bundle.read_template(html)
        self.assertIn('<script type="text/x-dc"', template)
        self.assertEqual(bundle.write_template(html, template), html)

    def test_template_markup_is_balanced(self) -> None:
        """A stray closing tag silently breaks the layout (e.g. sections losing their centered container)."""
        parser = TagBalance()
        parser.feed(bundle.read_template(REAL_INDEX.read_text(encoding="utf-8")))
        parser.close()
        self.assertEqual(parser.mismatches, [])
        self.assertEqual(parser.open_tags, [])

    def test_template_colors_come_from_theme_variables(self) -> None:
        """Every color is var(--ctp-…) so both themes apply; hex values live only in the :root definitions.
        The Three.js scene reads the same variables (themeScene), so it has none either."""
        template = bundle.read_template(REAL_INDEX.read_text(encoding="utf-8"))
        template = re.sub(r"<!-- seo:start.*?<!-- seo:end -->", "", template, flags=re.S)  # generated, tested in test_build_seo
        template = re.sub(r":root(\[[^\]]*\])?\{[^}]*\}", "", template)  # the theme definitions themselves
        stray = re.findall(r"#[0-9a-fA-F]{6}\b|rgba?\((?!0,0,0)[^)]*\)|0x(?!000000)[0-9a-fA-F]{6}", template)
        self.assertEqual(stray, [])

    def test_write_replaces_only_the_template(self) -> None:
        packed = bundle.write_template(TINY, "<p>new $1 \\g<0></p>")
        self.assertEqual(bundle.read_template(packed), "<p>new $1 \\g<0></p>")
        self.assertTrue(packed.startswith("<html><body><script>x</script>"))
        self.assertTrue(packed.endswith("<p>after</p></body></html>"))

    def test_script_and_comment_markers_cannot_break_out(self) -> None:
        # Browsers end the script at the first `</script`; after `<!--<script` they ignore it.
        tricky = '<!-- seo:start --><script>a</script><!--x--></script><script>'
        payload = bundle.encode(tricky)
        self.assertNotIn("</", payload)
        self.assertNotIn("<!--", payload)
        self.assertEqual(bundle.read_template(bundle.write_template(TINY, tricky)), tricky)

    def test_missing_template_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "__bundler/template"):
            bundle.read_template("<html></html>")

    def test_cli_unpack_then_pack(self) -> None:
        directory = Path(tempfile.mkdtemp())
        try:
            index, template = directory / "index.html", directory / "template.html"
            shutil.copy(REAL_INDEX, index)
            self.assertEqual(bundle.main(["bundle.py", "unpack", str(index), str(template)]), 0)
            template.write_text(template.read_text(encoding="utf-8").replace("<title>", "<title>Edited "), encoding="utf-8")
            self.assertEqual(bundle.main(["bundle.py", "pack", str(index), str(template)]), 0)
            self.assertIn("<title>Edited ", bundle.read_template(index.read_text(encoding="utf-8")))
        finally:
            shutil.rmtree(directory)

    def test_cli_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(bundle.main(["bundle.py", "explode"]), 2)
        self.assertIn("unpack index.html", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
