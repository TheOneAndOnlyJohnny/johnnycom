"""Tests for build_seo.py.  Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import io
import json
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict

import yaml

import build_seo
import bundle
import check_content

PROJECT = Path(__file__).resolve().parent.parent
DAY_ONE, DAY_TWO = dt.date(2026, 10, 14), dt.date(2026, 11, 2)


def load_real(lang: str) -> Dict[str, Any]:
    data, errors = check_content.parse_yaml((PROJECT / "content" / f"{lang}.yaml").read_text(encoding="utf-8"), lang)
    assert data is not None and not errors, errors
    return data


def json_ld(document: str) -> Dict[str, Any]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', document, re.S)
    assert match is not None
    return json.loads(match.group(1))


def person(document: str) -> Dict[str, Any]:
    return next(node for node in json_ld(document)["@graph"] if node["@type"] == "Person")


class HeadTagsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.en, self.es = load_real("en"), load_real("es")

    def head(self, content: Dict[str, Any], lang: str, standalone: bool = True) -> str:
        return "\n".join(build_seo.head_tags(content, lang, standalone))

    def test_canonical_and_hreflang_per_language(self) -> None:
        es_head = self.head(self.es, "es")
        self.assertIn('<link rel="canonical" href="https://johnny.com.mx/es/">', es_head)
        self.assertIn('<link rel="canonical" href="https://johnny.com.mx/">', self.head(self.en, "en"))
        for code, url in (("en", "https://johnny.com.mx/"), ("es", "https://johnny.com.mx/es/"),
                          ("x-default", "https://johnny.com.mx/")):
            self.assertIn(f'<link rel="alternate" hreflang="{code}" href="{url}">', es_head)

    def test_open_graph_locale_and_image(self) -> None:
        es_head = self.head(self.es, "es")
        self.assertIn('<meta property="og:locale" content="es_MX">', es_head)
        self.assertIn('<meta property="og:locale:alternate" content="en_US">', es_head)
        self.assertIn('<meta property="og:image" content="https://johnny.com.mx/og-es.png">', es_head)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', es_head)

    def test_single_light_theme_color(self) -> None:
        head = self.head(self.en, "en")
        self.assertIn('<meta name="theme-color" content="#eff1f5">', head)
        self.assertEqual(head.count('name="theme-color"'), 1)
        self.assertNotIn("prefers-color-scheme", head)

    def test_own_files_are_linked_relatively(self) -> None:
        self.assertIn('<link rel="icon" href="favicon.ico" sizes="32x32">', self.head(self.en, "en"))
        es_head = self.head(self.es, "es")
        self.assertIn('<link rel="icon" href="../favicon.svg" type="image/svg+xml">', es_head)
        self.assertIn('<link rel="apple-touch-icon" href="../apple-touch-icon.png">', es_head)
        self.assertNotRegex(es_head, r'(href|src)="/[^/]')

    def test_title_and_viewport_only_in_the_outer_page(self) -> None:
        self.assertIn("<title>Johnny · Juan Guzmán</title>", self.head(self.en, "en", standalone=True))
        self.assertNotIn("<title>", self.head(self.en, "en", standalone=False))
        self.assertNotIn('name="viewport"', self.head(self.en, "en", standalone=False))

    def test_text_is_escaped(self) -> None:
        self.en["meta"]["description"] = 'Tags <b> & "quotes"'
        self.en["meta"]["title"] = "A </script><!-- B"
        head = self.head(self.en, "en")
        self.assertIn('content="Tags &lt;b&gt; &amp; &quot;quotes&quot;"', head)
        self.assertIn("<title>A &lt;/script&gt;&lt;!-- B</title>", head)
        script = re.search(r'<script type="application/ld\+json">(.*?)</script>', head, re.S).group(1)
        self.assertNotIn("</", script)
        self.assertNotIn("<!--", script)
        self.assertEqual(json.loads(script)["@graph"][1]["name"], "A </script><!-- B")


class StructuredDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.en = load_real("en")

    def test_person(self) -> None:
        graph = build_seo.structured_data(self.en, "en")["@graph"]
        self.assertEqual([node["@type"] for node in graph], ["WebSite", "ProfilePage", "Person"])
        found = graph[2]
        self.assertEqual((found["name"], found["alternateName"], found["jobTitle"]),
                         ("Juan Guzmán", "Johnny", "Senior Engineering Manager"))
        self.assertEqual(found["worksFor"], {"@type": "Organization", "name": "Capital One"})
        self.assertEqual(len(found["knowsAbout"]), len(set(found["knowsAbout"])))

    def test_same_as_lists_the_contact_profiles(self) -> None:
        self.assertEqual(build_seo.structured_data(self.en, "en")["@graph"][2]["sameAs"],
                         ["https://github.com/TheOneAndOnlyJohnny", "https://www.linkedin.com/in/theoneandonlyjohnny"])

    def test_same_as_only_lists_real_profile_urls(self) -> None:
        self.en["contact"]["links"] = [{"label": "GitHub", "url": ""}, {"label": "LinkedIn", "url": "#"}]
        self.assertNotIn("sameAs", build_seo.structured_data(self.en, "en")["@graph"][2])
        self.en["contact"]["links"][1]["url"] = "https://www.linkedin.com/in/example"
        self.en["contact"]["links"].append({"label": "Mail", "url": "mailto:a@b.co"})
        self.assertEqual(build_seo.structured_data(self.en, "en")["@graph"][2]["sameAs"],
                         ["https://www.linkedin.com/in/example"])

    def test_no_current_job_means_no_employer(self) -> None:
        self.en["experience"][0]["roles"][0]["to"] = "2026-01"
        self.assertNotIn("worksFor", build_seo.structured_data(self.en, "en")["@graph"][2])

    def test_employer_is_the_company_with_a_current_role(self) -> None:
        self.en["experience"][0]["roles"][0]["to"] = "2026-01"
        self.en["experience"][3]["roles"][0]["to"] = None
        self.assertEqual(build_seo.current_employer(self.en), "Wizeline")


class PageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_html = (PROJECT / "index.html").read_text(encoding="utf-8")
        self.en, self.es = load_real("en"), load_real("es")

    def test_outer_and_template_both_get_the_block_and_lang(self) -> None:
        page = build_seo.build_page(self.bundle_html, self.es, "es")
        template = bundle.read_template(page)
        for document in (page, template):
            self.assertEqual(document.count("<!-- seo:start"), 1)
            self.assertRegex(document, r'<html lang="es">')
            self.assertIn('href="https://johnny.com.mx/es/"', document)
            self.assertEqual(person(document)["name"], "Juan Guzmán")
        self.assertEqual(page.split("</head>")[0].count("<title>"), 1)
        self.assertNotIn("<title>", template.split("</head>")[0])
        self.assertIn('<script type="text/x-dc"', template)

    def test_block_comes_right_after_charset(self) -> None:
        page = build_seo.build_page(self.bundle_html, self.en, "en")
        self.assertRegex(page, r'<meta charset="utf-8">\n  <!-- seo:start[^\n]*-->\n  <title>')

    def test_rebuilding_is_stable_and_switches_language_cleanly(self) -> None:
        english = build_seo.build_page(self.bundle_html, self.en, "en")
        self.assertEqual(build_seo.build_page(english, self.en, "en"), english)
        spanish = build_seo.build_page(english, self.es, "es")
        self.assertNotIn("https://johnny.com.mx/og-en.png", spanish)
        self.assertEqual(build_seo.build_page(spanish, self.en, "en"), english)

    def test_set_html_lang_keeps_other_attributes(self) -> None:
        self.assertEqual(build_seo.set_html_lang('<html class="x" lang="en">', "es"), '<html lang="es" class="x">')
        self.assertEqual(build_seo.set_html_lang("<!DOCTYPE html><html>", "en"), '<!DOCTYPE html><html lang="en">')

    def test_unexpected_page_shape_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "</head>"):
            build_seo.apply_head("<html><head></head><head></head></html>", "", "en", strip_original=False)
        with self.assertRaisesRegex(ValueError, "charset"):
            build_seo.apply_head("<html><head></head></html>", "", "en", strip_original=False)


class BuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        shutil.copy(PROJECT / "index.html", self.root)
        shutil.copytree(PROJECT / "content", self.root / "content")

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def run_main(self, *options: str, today: dt.date = DAY_ONE) -> int:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = build_seo.main(["build_seo.py", *options], self.root, today)
        self.output = out.getvalue()
        return code

    def lastmods(self) -> Dict[str, str]:
        return build_seo.previous_lastmods((self.root / "sitemap.xml").read_text(encoding="utf-8"))

    def test_writes_every_file(self) -> None:
        self.assertEqual(self.run_main(), 0)
        for name in ("index.html", "es/index.html", "sitemap.xml", "robots.txt"):
            self.assertTrue((self.root / name).is_file(), name)
        self.assertIn('<html lang="es">', (self.root / "es/index.html").read_text(encoding="utf-8"))
        self.assertIn("Sitemap: https://johnny.com.mx/sitemap.xml", (self.root / "robots.txt").read_text(encoding="utf-8"))

    def test_sitemap_is_valid_with_alternates(self) -> None:
        self.run_main()
        tree = ElementTree.parse(self.root / "sitemap.xml").getroot()
        links = tree.findall(".//{http://www.w3.org/1999/xhtml}link")
        self.assertEqual(len(links), 6)
        self.assertEqual(self.lastmods(), {"https://johnny.com.mx/": "2026-10-14", "https://johnny.com.mx/es/": "2026-10-14"})

    def test_lastmod_only_moves_for_changed_pages(self) -> None:
        self.run_main()
        self.assertEqual(self.run_main(today=DAY_TWO), 0)
        self.assertIn("nothing written", self.output)
        self.assertEqual(set(self.lastmods().values()), {"2026-10-14"})
        es_file = self.root / "content" / "es.yaml"
        es_file.write_text(es_file.read_text(encoding="utf-8").replace("Ciudad de México.", "CDMX."), encoding="utf-8")
        self.run_main(today=DAY_TWO)
        self.assertEqual(self.lastmods(), {"https://johnny.com.mx/": "2026-10-14", "https://johnny.com.mx/es/": "2026-11-02"})

    def test_check_mode_reports_stale_files_and_writes_nothing(self) -> None:
        before = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertEqual(self.run_main("--check"), 1)
        self.assertIn("es/index.html, sitemap.xml, robots.txt", self.output)  # never built in this copy
        self.assertEqual((self.root / "index.html").read_text(encoding="utf-8"), before)
        self.run_main()
        self.assertEqual(self.run_main("--check", today=DAY_TWO), 0)
        en_file = self.root / "content" / "en.yaml"
        en_file.write_text(en_file.read_text(encoding="utf-8").replace("Mexico City.", "CDMX."), encoding="utf-8")
        self.assertEqual(self.run_main("--check", today=DAY_TWO), 1)
        self.assertIn("out of date: index.html, sitemap.xml\n", self.output)  # es page untouched

    def test_invalid_content_writes_nothing(self) -> None:
        es = copy.deepcopy(load_real("es"))
        del es["meta"]["description"]
        (self.root / "content" / "es.yaml").write_text(yaml.safe_dump(es, allow_unicode=True), encoding="utf-8")
        self.assertEqual(self.run_main(), 1)
        self.assertIn("es.yaml › meta.description: missing", self.output)
        self.assertFalse((self.root / "es").exists())

    def test_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.run_main("--force"), 2)
        self.assertIn("--check", err.getvalue())


if __name__ == "__main__":
    unittest.main()
