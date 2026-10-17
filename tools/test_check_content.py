"""Tests for check_content.py.  Run: python3 -m unittest discover tools"""
from __future__ import annotations

import contextlib
import copy
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

import yaml

import check_content as cc

REAL_CONTENT = cc.DEFAULT_CONTENT_DIR


def load_real(lang: str) -> Dict[str, Any]:
    data, errors = cc.parse_yaml((REAL_CONTENT / f"{lang}.yaml").read_text(encoding="utf-8"), lang)
    assert data is not None and not errors, errors
    return data


class ParseYamlTest(unittest.TestCase):
    def test_yaml_1_1_booleans_stay_text(self) -> None:
        data, _ = cc.parse_yaml("a: no\nb: on\nc: yes\nd: true\n", "x")
        self.assertEqual(data, {"a": "no", "b": "on", "c": "yes", "d": True})

    def test_dates_stay_text(self) -> None:
        data, _ = cc.parse_yaml("since: 2007-09-20\nfrom: 2024-05\n", "x")
        self.assertEqual(data, {"since": "2007-09-20", "from": "2024-05"})

    def test_duplicate_key_is_an_error(self) -> None:
        data, errors = cc.parse_yaml("title: a\ntitle: b\n", "en.yaml")
        self.assertIsNone(data)
        self.assertIn("duplicated key 'title'", errors[0])
        self.assertIn("line 2", errors[0])

    def test_syntax_error_reports_line(self) -> None:
        data, errors = cc.parse_yaml("a: [1, 2\nb: 3\n", "es.yaml")
        self.assertIsNone(data)
        self.assertRegex(errors[0], r"^es\.yaml \(line \d+, column \d+\): invalid YAML")

    def test_unquoted_colon_in_list_item_becomes_mapping(self) -> None:
        data, _ = cc.parse_yaml("bullets:\n  - Desarrollo profesional: implementé\n", "x")
        errors = cc.text_list()(data["bullets"], "bullets")
        self.assertEqual(len(errors), 1)
        self.assertIn("expected non-empty text", errors[0])

    def test_top_level_must_be_mapping(self) -> None:
        _, errors = cc.parse_yaml("- a\n- b\n", "en.yaml")
        self.assertIn("expected a mapping", errors[0])


class ValidatorTest(unittest.TestCase):
    def test_url(self) -> None:
        for good in ("", "https://github.com/x", "mailto:a@b.co", "files/notes%20v2.pdf", "#about"):
            self.assertEqual(cc.url(good, "u"), [], good)
        for bad in ("javascript:alert(1)", "https://x.com/a b", " https://x.com", None, 3):
            self.assertTrue(cc.url(bad, "u"), bad)

    def test_year_month(self) -> None:
        self.assertEqual(cc.year_month("2024-05", "p"), [])
        for bad in ("2024-5", "2024-13", "2024-00", 2024, "May 2024"):
            self.assertTrue(cc.year_month(bad, "p"), bad)
        self.assertEqual(cc.optional_year_month(None, "p"), [])

    def test_day(self) -> None:
        self.assertEqual(cc.day("2007-09-20", "p"), [])
        for bad in ("2007-9-20", "2007-02-30", "20070920", 2007):
            self.assertTrue(cc.day(bad, "p"), bad)
        self.assertIn("in the future", cc.day("2999-01-01", "p")[0])

    def test_year_and_count(self) -> None:
        self.assertEqual(cc.year(2026, "p") + cc.year("2025", "p"), [])
        self.assertTrue(cc.year(True, "p") and cc.year("26", "p"))
        self.assertEqual(cc.count(0, "p"), [])
        self.assertTrue(cc.count(-1, "p") and cc.count(True, "p") and cc.count("2", "p"))

    def test_label_map_rejects_digit_only_labels(self) -> None:
        self.assertEqual(cc.label_map({"since": "2009"}, "facts"), [])
        self.assertIn("only digits", cc.label_map({2009: "x"}, "facts")[0])
        self.assertIn("only digits", cc.label_map({"2009": "x"}, "facts")[0])
        self.assertTrue(cc.label_map({}, "facts"))

    def test_text_list_exact(self) -> None:
        self.assertIn("exactly 12", cc.text_list(exact=12)(["Jan"] * 11, "months")[0])


class CheckLanguageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.en = load_real("en")

    def test_real_files_are_valid(self) -> None:
        self.assertEqual(cc.check_language(self.en, "en"), [])
        self.assertEqual(cc.check_language(load_real("es"), "es"), [])

    def test_missing_and_unknown_keys(self) -> None:
        del self.en["identity"]["email"]
        self.en["identity"]["emial"] = "x@y.com"
        errors = cc.check_language(self.en, "en")
        self.assertIn("identity.email: missing", errors)
        self.assertIn("identity.emial: unknown key (typo?)", errors)

    def test_nested_list_paths(self) -> None:
        self.en["experience"][2]["roles"][0]["from"] = "2021-13"
        errors = cc.check_language(self.en, "en")
        self.assertEqual(errors, ["experience[2].roles[0].from: expected YYYY-MM (e.g. 2024-05), got '2021-13'"])

    def test_company_needs_roles(self) -> None:
        self.en["experience"][0]["roles"] = []
        self.en["experience"][1]["role"] = "flat entry from the old format"
        errors = cc.check_language(self.en, "en")
        self.assertIn("experience[0].roles: expected at least 1 item(s)", errors)
        self.assertIn("experience[1].role: unknown key (typo?)", errors)

    def test_to_before_from(self) -> None:
        self.en["experience"][1]["roles"][0]["to"] = "2020-01"
        self.assertIn("experience[1].roles[0]: `to` (2020-01) is before `from` (2022-08)",
                      cc.check_language(self.en, "en"))

    def test_lang_must_match_file(self) -> None:
        self.assertIn("meta.lang: is 'en' but the file is es.yaml", cc.check_language(self.en, "es"))

    def test_wrong_types_do_not_crash(self) -> None:
        self.en["meta"] = "oops"
        self.en["experience"] = ["oops"]
        errors = cc.check_language(self.en, "en")
        self.assertTrue(any(error.startswith("meta:") for error in errors))
        self.assertTrue(any(error.startswith("experience[0]:") for error in errors))

    def test_description_is_required(self) -> None:
        del self.en["meta"]["description"]
        self.assertIn("meta.description: missing", cc.check_language(self.en, "en"))

    def test_long_description_is_only_a_warning(self) -> None:
        self.assertEqual(cc.language_warnings(self.en), [])
        self.en["meta"]["description"] = "x" * (cc.DESCRIPTION_MAX + 1)
        self.assertEqual(cc.check_language(self.en, "en"), [])
        self.assertEqual(cc.language_warnings(self.en),
                         ["meta.description: 161 characters; search results cut it off after ~160"])

    def test_experience_order_is_only_a_warning(self) -> None:
        wizeline = self.en["experience"][3]["roles"]
        wizeline[0], wizeline[2] = wizeline[2], wizeline[0]
        self.en["experience"][1], self.en["experience"][2] = self.en["experience"][2], self.en["experience"][1]
        self.assertEqual(cc.check_language(self.en, "en"), [])
        self.assertEqual(cc.language_warnings(self.en), [
            "experience[3].roles: not newest first",
            "experience[2]: starts after the company above it; list companies newest first",
        ])

    def test_company_color_is_optional_hex_or_catppuccin_name(self) -> None:
        self.assertEqual(cc.color("#004977", "c"), [])
        self.assertEqual(cc.color("yellow", "c"), [])
        for bad in ("004977", "#04977", "Yellow", "golden", None, 4977):
            self.assertTrue(cc.color(bad, "c"), bad)
        del self.en["experience"][0]["color"]
        self.assertEqual(cc.check_language(self.en, "en"), [])
        self.en["experience"][1]["color"] = None  # `color:` left empty, or an unquoted hex (YAML reads it as a comment)
        self.assertEqual(cc.check_language(self.en, "en"),
                         ["experience[1].color: expected '#rrggbb' (quoted) or a Catppuccin color name like yellow, got None"])

    def test_optional_lists_may_be_empty(self) -> None:
        self.en["projects"]["items"] = []
        self.en["contact"]["links"] = []
        self.assertEqual(cc.check_language(self.en, "en"), [])

    def test_two_projects_with_images(self) -> None:
        items = self.en["projects"]["items"]
        self.assertEqual([(item["title"], item["year"], item["image"]) for item in items],
                         [("Finsanity", 2026, "finsanity"), ("Juanderful", 2026, "juanderful")])
        self.assertTrue(all(item["alt"] and item["code"] == "#" for item in items))
        self.assertEqual([item["live"] for item in items], ["https://finsanity.mx", "https://juanderful.mx"])

    def test_project_image_is_a_slug(self) -> None:
        for bad in ("Finsanity", "finsanity.jpg", "../x", "", 3):
            self.en["projects"]["items"][0]["image"] = bad
            self.assertEqual(len(cc.check_language(self.en, "en")), 1, bad)

    def test_image_and_alt_go_together(self) -> None:
        del self.en["projects"]["items"][0]["alt"]
        self.assertEqual(cc.check_language(self.en, "en"), ["projects.items[0]: `alt` is required when `image` is set"])
        del self.en["projects"]["items"][0]["image"]
        self.assertEqual(cc.check_language(self.en, "en"), [], "no image, no alt: the striped placeholder")
        self.en["projects"]["items"][1].pop("image")
        self.assertEqual(cc.check_language(self.en, "en"), ["projects.items[1]: `image` is required when `alt` is set"])
        self.en["projects"]["items"][1]["alt"] = ""
        self.assertIn("projects.items[1]: `image` is required when `alt` is set", cc.check_language(self.en, "en"))

    def test_placeholder_url_is_valid(self) -> None:
        self.en["projects"]["items"][0]["live"] = "#"
        self.assertEqual(cc.check_language(self.en, "en"), [])

    def test_blog_url_replaces_writing(self) -> None:
        self.assertEqual(self.en["blog"]["url"], "https://blog.johnny.com.mx/")
        self.assertNotIn("writing", self.en)
        self.en["blog"]["url"] = ""  # empty hides the link
        self.assertEqual(cc.check_language(self.en, "en"), [])
        self.en["blog"]["url"] = "ftp://blog"
        self.assertEqual(len(cc.check_language(self.en, "en")), 1)
        del self.en["blog"]
        self.assertTrue(any(error.startswith("blog") for error in cc.check_language(self.en, "en")))
        self.en["blog"], self.en["writing"] = {"url": ""}, []
        self.assertTrue(any("writing" in error for error in cc.check_language(self.en, "en")), "old section is reported")


class CompareLanguagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.en, self.es = load_real("en"), load_real("es")

    def test_real_files_match(self) -> None:
        self.assertEqual(cc.compare_structure(self.en, self.es), [])
        self.assertEqual(cc.compare_shared(self.en, self.es), [])

    def test_list_length_mismatch(self) -> None:
        self.es["experience"][0]["roles"][0]["bullets"].append("extra")
        self.assertEqual(cc.compare_structure(self.en, self.es),
                         ["experience[0].roles[0].bullets: 1 items in en.yaml but 2 in es.yaml"])
        self.es["experience"][3]["roles"].pop()
        self.assertIn("experience[3].roles: 3 items in en.yaml but 2 in es.yaml", cc.compare_structure(self.en, self.es))

    def test_key_only_in_one_file(self) -> None:
        self.es["hero"]["prompt"]["extra"] = "x"
        self.assertIn("hero.prompt.extra: only in es.yaml", cc.compare_structure(self.en, self.es))

    def test_label_maps_compared_by_count(self) -> None:
        self.assertEqual(cc.compare_structure(self.en["about"], self.es["about"], "about"), [])
        count = len(self.en["now"]["items"])
        self.es["now"]["items"]["extra"] = "x"
        self.assertIn(f"now.items: {count} entries in en.yaml but {count + 1} in es.yaml",
                      cc.compare_structure(self.en, self.es))

    def test_current_role_vs_ended_role_is_not_a_type_mismatch(self) -> None:
        self.es["experience"][0]["roles"][0]["to"] = "2025-01"
        self.assertEqual(cc.compare_structure(self.en, self.es), [])

    def test_company_color_must_match_across_languages(self) -> None:
        self.es["experience"][2]["color"] = "green"
        self.assertEqual(cc.compare_shared(self.en, self.es),
                         ["experience[2].color: en.yaml has '#95bf47' but es.yaml has 'green'"])
        del self.es["experience"][2]["color"]
        self.assertIn("experience[2].color: only in en.yaml", cc.compare_structure(self.en, self.es))

    def test_project_image_is_shared_and_alt_is_translated(self) -> None:
        self.assertNotEqual(self.en["projects"]["items"][0]["alt"], self.es["projects"]["items"][0]["alt"])
        self.assertEqual(cc.compare_shared(self.en, self.es), [])
        self.es["projects"]["items"][1]["image"] = "other"
        self.assertEqual(cc.compare_shared(self.en, self.es),
                         ["projects.items[1].image: en.yaml has 'juanderful' but es.yaml has 'other'"])
        del self.es["projects"]["items"][1]["alt"]
        self.assertIn("projects.items[1].alt: only in en.yaml", cc.compare_structure(self.en, self.es))

    def test_shared_value_drift_is_a_warning(self) -> None:
        self.es["experience"][3]["roles"][0]["from"] = "2020-02"
        self.es["contact"]["links"][0]["url"] = "https://github.com/x"
        self.assertEqual(cc.compare_shared(self.en, self.es), [
            "experience[3].roles[0].from: en.yaml has '2020-01' but es.yaml has '2020-02'",
            "contact.links[0].url: en.yaml has 'https://github.com/TheOneAndOnlyJohnny' but es.yaml has 'https://github.com/x'",
        ])


class CheckDirectoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        for lang in cc.LANGUAGES:
            shutil.copy(REAL_CONTENT / f"{lang}.yaml", self.directory)

    def tearDown(self) -> None:
        shutil.rmtree(self.directory)

    def run_main(self) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return cc.main(["check", str(self.directory)])

    def write(self, lang: str, data: Dict[str, Any]) -> None:
        (self.directory / f"{lang}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    def test_real_directory_passes(self) -> None:
        report = cc.check_directory(self.directory)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, [])
        self.assertEqual(self.run_main(), 0)

    def test_missing_file(self) -> None:
        (self.directory / "es.yaml").unlink()
        report = cc.check_directory(self.directory)
        self.assertFalse(report.ok)
        self.assertIn("es.yaml: file not found", report.errors[0])

    def test_errors_are_prefixed_and_fail(self) -> None:
        es = copy.deepcopy(load_real("es"))
        es["identity"]["email"] = "not-an-email"
        self.write("es", es)
        report = cc.check_directory(self.directory)
        self.assertIn("es.yaml › identity.email: expected an email address, got 'not-an-email'", report.errors)
        self.assertEqual(self.run_main(), 1)

    def test_warnings_do_not_fail(self) -> None:
        es = copy.deepcopy(load_real("es"))
        es["fun"]["coffee"]["perWorkday"] = 3
        self.write("es", es)
        report = cc.check_directory(self.directory)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, ["en/es differ › fun.coffee.perWorkday: en.yaml has 2 but es.yaml has 3"])

    def test_long_description_warns_with_file_prefix(self) -> None:
        es = copy.deepcopy(load_real("es"))
        es["meta"]["description"] = "x" * 200
        self.write("es", es)
        report = cc.check_directory(self.directory)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, ["es.yaml › meta.description: 200 characters; search results cut it off after ~160"])


if __name__ == "__main__":
    unittest.main()
