"""Tests for static_page.py.  Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import html
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Tuple

import build_seo
import bundle
import check_content
import make_images
import static_page

PROJECT = Path(__file__).resolve().parent.parent
VOID_TAGS = {"br", "meta", "link", "img", "input", "hr"}


def load_real(lang: str) -> Dict[str, Any]:
    data, errors = check_content.parse_yaml((PROJECT / "content" / f"{lang}.yaml").read_text(encoding="utf-8"), lang)
    assert data is not None and not errors, errors
    return data


class TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: List[str] = []
        self.problems: List[Tuple[str, str]] = []
        self.text: List[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            self.problems.append(("unexpected", tag))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parse(markup: str) -> TagBalance:
    parser = TagBalance()
    parser.feed(markup)
    parser.close()
    return parser


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.en, self.es = load_real("en"), load_real("es")

    def test_markup_is_balanced(self) -> None:
        for content, lang in ((self.en, "en"), (self.es, "es")):
            parser = parse(static_page.render(content, lang))
            self.assertEqual((parser.problems, parser.stack), ([], []), lang)

    def test_every_piece_of_content_is_in_the_text(self) -> None:
        text = " ".join(parse(static_page.render(self.es, "es")).text)
        expected = [self.es["about"]["summary"], self.es["contact"]["title"], self.es["footer"]["copyright"]]
        expected += [bullet for company in self.es["experience"] for role in company["roles"] for bullet in role["bullets"]]
        expected += [role["role"] for company in self.es["experience"] for role in company["roles"]]
        expected += [item for group in self.es["skills"] for item in group["items"]]
        expected += [project["description"] for project in self.es["projects"]["items"]]
        expected += list(self.es["now"]["items"].values()) + list(self.es["about"]["facts"].keys())
        for piece in expected:
            self.assertIn(piece, text)

    def test_structure(self) -> None:
        page = static_page.render(self.en, "en")
        self.assertEqual(page.count("<h1>"), 1)
        self.assertIn("<h1>Juan “Johnny” Guzmán</h1>", page)
        for section_id in static_page.SECTIONS:
            self.assertIn(f'<section id="{section_id}">', page)
        self.assertIn('<a href="es/" hreflang="es" lang="es">Cambiar a español</a>', page)
        self.assertIn('<a href="../" hreflang="en" lang="en">Switch to English</a>', static_page.render(self.es, "es"))
        self.assertNotIn('id="writing"', page)
        self.assertIn('<a href="https://blog.johnny.com.mx/" rel="noopener noreferrer">~/johnny/blog</a>', page)
        self.en["blog"]["url"] = ""
        self.assertNotIn('href="https://blog.johnny.com.mx/"', static_page.render(self.en, "en"))

    def test_dates_use_the_language_months(self) -> None:
        self.assertIn('<time datetime="2024-05">May 2024</time> — Present', static_page.render(self.en, "en"))
        self.assertIn('<time datetime="2022-08">Ago 2022</time> — <time datetime="2023-12">Dic 2023</time>',
                      static_page.render(self.es, "es"))

    def test_experience_is_grouped_by_company(self) -> None:
        page = static_page.render(self.en, "en")
        section = page[page.index('<section id="experience">'):page.index('<section id="skills">')]
        self.assertEqual(section.count("<article>"), 5)
        self.assertEqual(section.count("<h4>"), 8)
        self.assertEqual(section.count("<h3>Wizeline</h3>"), 1)
        self.assertIn('<h3>Wizeline</h3>\n<p><time datetime="2018-05">May 2018</time> — <time datetime="2021-11">Nov 2021</time></p>\n'
                      '<h4>Sr. Engineering Manager / Lead of Software Engineering Discipline</h4>', section)
        self.assertIn('<h3>Capital One</h3>\n<p><time datetime="2024-05">May 2024</time> — Present</p>', section)
        self.assertNotIn("yr", section)  # no build-date-dependent durations

    def test_company_span(self) -> None:
        roles = [{"from": "2020-01", "to": "2021-11"}, {"from": "2018-05", "to": "2018-08"}]
        self.assertEqual(static_page.company_span(roles), ("2018-05", "2021-11"))
        roles[1]["to"] = None
        self.assertEqual(static_page.company_span(roles), ("2018-05", None))

    def test_empty_urls_are_not_links(self) -> None:
        page = static_page.render(self.en, "en")
        self.assertNotIn('href=""', page)
        self.assertIn('<a href="mailto:johnny@johnny.com.mx">johnny@johnny.com.mx</a>', page)
        self.en["projects"]["items"][0]["code"] = "https://github.com/x/y"
        page = static_page.render(self.en, "en")
        self.assertIn('<a href="https://github.com/x/y" rel="noopener noreferrer">code</a>', page)

    def test_project_images_are_relative_to_each_page(self) -> None:
        self.assertIn('<img src="img/projects/finsanity-1280.jpg" alt="Finsanity banner: a piggy bank', static_page.render(self.en, "en"))
        self.assertIn('<img src="../img/projects/juanderful-1280.jpg" alt="Banner de Juanderful', static_page.render(self.es, "es"))
        self.assertTrue(static_page.PROJECT_IMAGE.format(slug="x").endswith(make_images.project_file_names("x")[-1].split("/")[-1]))
        del self.en["projects"]["items"][0]["image"]
        self.assertEqual(static_page.render(self.en, "en").count("<img "), 1)

    def test_placeholder_urls_are_not_links(self) -> None:
        page = static_page.render(self.en, "en")
        self.assertNotIn('href="#"', page)
        self.assertIn("<h3>Finsanity (2026)</h3>", page)
        self.assertIn("<h3>Juanderful (2026)</h3>", page)
        self.en["contact"]["links"][0]["url"] = "#"
        self.assertNotIn('href="#"', static_page.render(self.en, "en"))

    def test_text_is_escaped(self) -> None:
        self.en["experience"][0]["roles"][0]["bullets"] = ["<script>alert(1)</script> & co"]
        page = static_page.render(self.en, "en")
        self.assertNotIn("<script>", page)
        self.assertIn(html.escape("<script>alert(1)</script> & co"), page)


class PageIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_html = (PROJECT / "index.html").read_text(encoding="utf-8")

    def test_static_page_is_in_the_outer_body_only(self) -> None:
        page = build_seo.build_page(self.bundle_html, load_real("es"), "es")
        head, body = page.split("</head>")
        self.assertEqual(page.count('<div id="static-page">'), 1)
        self.assertRegex(body, r'<div id="__bundler_loading">[^<]*</div>\n  <!-- static:start[^\n]*\n<div id="static-page">')
        self.assertNotIn("static-page", bundle.read_template(page).split("<style>")[0])
        self.assertNotIn("requires JavaScript", head)
        self.assertIn("<noscript><style>#__bundler_thumbnail,#__bundler_loading{display:none}", head)
        self.assertIn("background:#eff1f5;color:#4c4f69", head, "no-JS page uses Latte, like the default theme")


if __name__ == "__main__":
    unittest.main()
