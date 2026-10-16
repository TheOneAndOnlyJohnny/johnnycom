#!/usr/bin/env python3
"""Generate the SEO files from content/*.yaml.

Usage:
    python3 tools/build_seo.py           # check content/*.yaml, then write the files below
    python3 tools/build_seo.py --check   # exit 1 if any generated file is out of date

Writes (index.html is both the input bundle and the English output):
    index.html       head tags (description, canonical, hreflang, Open Graph, JSON-LD), lang="en",
                     and the whole page as plain HTML for crawlers (tools/static_page.py)
    es/index.html    the same bundle in Spanish; lang="es"
    sitemap.xml      both URLs with hreflang alternates
    robots.txt       allow everything, point to the sitemap

The tags go into the outer page (what crawlers and link previews read) and into
the bundled template, which replaces the whole document when the page unpacks.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bundle
import check_content
import static_page

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = check_content.LANGUAGES
PAGE_PATHS: Dict[str, str] = {"en": "", "es": "es/"}
PAGE_FILES: Dict[str, str] = {"en": "index.html", "es": "es/index.html"}
LOCALES: Dict[str, str] = {"en": "en_US", "es": "es_MX"}
# Links to the site's own files are relative, so the site also works under a subpath (dev servers).
TO_SITE_ROOT = static_page.TO_SITE_ROOT
THEME_COLOR = "#eff1f5"  # Latte base: light is the default; the page updates it when the visitor picks dark
OG_IMAGE_WIDTH, OG_IMAGE_HEIGHT = 1200, 630
BLOCK = re.compile(r"[ \t]*<!-- seo:start.*?<!-- seo:end -->\n", re.S)
STATIC_BLOCK = re.compile(r"[ \t]*<!-- static:start.*?<!-- static:end -->\n", re.S)
LOADING_DIV = re.compile(r'[ \t]*<div id="__bundler_loading">[^<]*</div>\n')
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

Content = Dict[str, Any]


# ── URLs ────────────────────────────────────────────────────────────────────

def site_url(content: Content) -> str:
    return f"https://{content['identity']['domain']}/"


def page_url(content: Content, lang: str) -> str:
    return site_url(content) + PAGE_PATHS[lang]


def og_image_url(content: Content, lang: str) -> str:
    return f"{site_url(content)}og-{lang}.png"


def profile_urls(content: Content) -> List[str]:
    return [link["url"] for link in content["contact"]["links"] if link["url"].startswith(("https://", "http://"))]


def current_employer(content: Content) -> Optional[str]:
    """The company with a role that has no end date."""
    return next((company["company"] for company in content["experience"]
                 if any(not role.get("to") for role in company["roles"])), None)


# ── Head tags ───────────────────────────────────────────────────────────────

def esc(value: str) -> str:
    return html.escape(value, quote=True)


def meta(attribute: str, key: str, value: str) -> str:
    return f'<meta {attribute}="{key}" content="{esc(value)}">'


def script_json(data: Dict[str, Any]) -> str:
    """JSON that cannot end its <script> early (same rules as bundle.encode)."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def structured_data(content: Content, lang: str) -> Dict[str, Any]:
    identity, base, url = content["identity"], site_url(content), page_url(content, lang)
    person: Dict[str, Any] = {
        "@type": "Person", "@id": f"{base}#person", "url": base,
        "name": f"{identity['firstName']} {identity['lastName']}",
        "givenName": identity["firstName"], "familyName": identity["lastName"],
        "alternateName": identity["alias"], "jobTitle": identity["role"],
        "knowsAbout": list(dict.fromkeys(item for group in content["skills"] for item in group["items"])),
    }
    employer = current_employer(content)
    if employer:
        person["worksFor"] = {"@type": "Organization", "name": employer}
    if profile_urls(content):
        person["sameAs"] = profile_urls(content)
    website = {"@type": "WebSite", "@id": f"{base}#website", "url": base, "name": identity["domain"]}
    page = {
        "@type": "ProfilePage", "@id": f"{url}#page", "url": url, "inLanguage": lang,
        "name": content["meta"]["title"], "description": content["meta"]["description"],
        "isPartOf": {"@id": website["@id"]}, "mainEntity": {"@id": person["@id"]},
    }
    return {"@context": "https://schema.org", "@graph": [website, page, person]}


def social_tags(content: Content, lang: str) -> List[str]:
    identity, title, description = content["identity"], content["meta"]["title"], content["meta"]["description"]
    image, image_alt = og_image_url(content, lang), f"{identity['firstName']} {identity['lastName']} · {identity['role']}"
    return [
        meta("property", "og:type", "profile"),
        meta("property", "og:site_name", identity["domain"]),
        meta("property", "og:title", title),
        meta("property", "og:description", description),
        meta("property", "og:url", page_url(content, lang)),
        meta("property", "og:locale", LOCALES[lang]),
        *[meta("property", "og:locale:alternate", LOCALES[other]) for other in LANGUAGES if other != lang],
        meta("property", "og:image", image),
        meta("property", "og:image:width", str(OG_IMAGE_WIDTH)),
        meta("property", "og:image:height", str(OG_IMAGE_HEIGHT)),
        meta("property", "og:image:alt", image_alt),
        meta("property", "profile:first_name", identity["firstName"]),
        meta("property", "profile:last_name", identity["lastName"]),
        meta("name", "twitter:card", "summary_large_image"),
        meta("name", "twitter:title", title),
        meta("name", "twitter:description", description),
        meta("name", "twitter:image", image),
        meta("name", "twitter:image:alt", image_alt),
    ]


def head_tags(content: Content, lang: str, standalone: bool) -> List[str]:
    """standalone = the outer page; the template already has a viewport and sets <title> itself."""
    tags = [f"<title>{esc(content['meta']['title'])}</title>",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<style>{static_page.STYLE}</style>",
            f"<noscript><style>{static_page.NOSCRIPT_STYLE}</style></noscript>"] if standalone else []
    return tags + [
        meta("name", "description", content["meta"]["description"]),
        f'<link rel="canonical" href="{esc(page_url(content, lang))}">',
        *[f'<link rel="alternate" hreflang="{code}" href="{esc(page_url(content, code))}">' for code in LANGUAGES],
        f'<link rel="alternate" hreflang="x-default" href="{esc(site_url(content))}">',
        f'<meta name="theme-color" content="{THEME_COLOR}">',
        f'<link rel="icon" href="{TO_SITE_ROOT[lang]}favicon.ico" sizes="32x32">',
        f'<link rel="icon" href="{TO_SITE_ROOT[lang]}favicon.svg" type="image/svg+xml">',
        f'<link rel="apple-touch-icon" href="{TO_SITE_ROOT[lang]}apple-touch-icon.png">',
        *social_tags(content, lang),
        f'<script type="application/ld+json">{script_json(structured_data(content, lang))}</script>',
    ]


def render_block(tags: List[str], lang: str, indent: str) -> str:
    lines = [f"<!-- seo:start · generated by tools/build_seo.py from content/{lang}.yaml, do not edit -->",
             *tags, "<!-- seo:end -->"]
    return "".join(f"{indent}{line}\n" for line in lines)


# ── Page assembly ───────────────────────────────────────────────────────────

def set_html_lang(document: str, lang: str) -> str:
    match = re.search(r"<html\b[^>]*>", document)
    if match is None:
        raise ValueError("no <html> tag found")
    tag = re.sub(r'\s+lang="[^"]*"', "", match.group(0))
    return document[:match.start()] + tag[:5] + f' lang="{lang}"' + tag[5:] + document[match.end():]


def apply_head(document: str, block: str, lang: str, strip_original: bool) -> str:
    """Replace (or first insert) the SEO block right after <meta charset>, so title and description come first.

    strip_original: drop the bundle's own <title> and "requires JavaScript" <noscript>, which the block replaces.
    """
    document = BLOCK.sub("", document)
    head_end = document.find("</head>")
    if head_end < 0 or document.count("</head>") != 1:
        raise ValueError("expected exactly one </head>")
    head, rest = document[:head_end], document[head_end:]
    if strip_original:
        head = re.sub(r"[ \t]*<title>.*?</title>\n?", "", head, count=1, flags=re.S)
        head = re.sub(r"[ \t]*<noscript>.*?</noscript>\n?", "", head, count=1, flags=re.S)
    charset = re.search(r"<meta charset=\"[^\"]*\">\n", head)
    if charset is None:
        raise ValueError('expected <meta charset="utf-8"> in <head>')
    head = head[:charset.end()] + block + head[charset.end():]
    return set_html_lang(head + rest, lang)


def apply_static(document: str, content: Content, lang: str) -> str:
    """Replace (or first insert) the static page right after the bundle's loading message."""
    document = STATIC_BLOCK.sub("", document)
    loading = LOADING_DIV.search(document)
    if loading is None:
        raise ValueError('expected <div id="__bundler_loading"> in the outer page')
    block = (f"  <!-- static:start · generated by tools/build_seo.py from content/{lang}.yaml, do not edit -->\n"
             f"{static_page.render(content, lang)}\n  <!-- static:end -->\n")
    return document[:loading.end()] + block + document[loading.end():]


def build_page(bundle_html: str, content: Content, lang: str) -> str:
    outer = apply_head(bundle_html, render_block(head_tags(content, lang, True), lang, "  "), lang, strip_original=True)
    outer = apply_static(outer, content, lang)
    template = bundle.read_template(outer)
    template = apply_head(template, render_block(head_tags(content, lang, False), lang, ""), lang, strip_original=False)
    return bundle.write_template(outer, template)


# ── Sitemap and robots.txt ──────────────────────────────────────────────────

def previous_lastmods(sitemap_xml: Optional[str]) -> Dict[str, str]:
    if not sitemap_xml:
        return {}
    try:
        tree = ElementTree.fromstring(sitemap_xml)
    except ElementTree.ParseError:
        return {}
    return {(url.findtext("s:loc", "", SITEMAP_NS)): url.findtext("s:lastmod", "", SITEMAP_NS)
            for url in tree.findall("s:url", SITEMAP_NS)}


def render_sitemap(content: Content, lastmods: Dict[str, str]) -> str:
    alternates = "".join(f'    <xhtml:link rel="alternate" hreflang="{code}" href="{esc(page_url(content, code))}"/>\n'
                         for code in LANGUAGES)
    alternates += f'    <xhtml:link rel="alternate" hreflang="x-default" href="{esc(site_url(content))}"/>\n'
    urls = "".join(f"  <url>\n    <loc>{esc(page_url(content, lang))}</loc>\n"
                   f"    <lastmod>{lastmods[page_url(content, lang)]}</lastmod>\n{alternates}  </url>\n"
                   for lang in LANGUAGES)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            f"{urls}</urlset>\n")


def render_robots(content: Content) -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {site_url(content)}sitemap.xml\n"


# ── Build ───────────────────────────────────────────────────────────────────

@dataclass
class Output:
    path: Path
    text: str


def read_or_none(path: Path) -> Optional[str]:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def load_contents(root: Path) -> Tuple[Dict[str, Content], check_content.Report]:
    report = check_content.check_directory(root / "content")
    if not report.ok:
        return {}, report
    contents = {}
    for lang in LANGUAGES:
        data, _ = check_content.parse_yaml((root / "content" / f"{lang}.yaml").read_text(encoding="utf-8"), lang)
        contents[lang] = data
    return contents, report


def build_outputs(root: Path, contents: Dict[str, Content], today: dt.date) -> List[Output]:
    """Everything the build would write. The sitemap's lastmod moves only for pages that changed."""
    bundle_html = (root / PAGE_FILES["en"]).read_text(encoding="utf-8")
    pages = [Output(root / PAGE_FILES[lang], build_page(bundle_html, contents[lang], lang)) for lang in LANGUAGES]
    previous = previous_lastmods(read_or_none(root / "sitemap.xml"))
    lastmods = {}
    for lang, page in zip(LANGUAGES, pages):
        url = page_url(contents["en"], lang)
        unchanged = read_or_none(page.path) == page.text and previous.get(url)
        lastmods[url] = previous[url] if unchanged else today.isoformat()
    return pages + [Output(root / "sitemap.xml", render_sitemap(contents["en"], lastmods)),
                    Output(root / "robots.txt", render_robots(contents["en"]))]


def main(argv: List[str], root: Path = ROOT, today: Optional[dt.date] = None) -> int:
    options = argv[1:]
    if options not in ([], ["--check"]):
        print(__doc__[__doc__.index("Usage:"):__doc__.index("Writes")].rstrip(), file=sys.stderr)
        return 2
    contents, report = load_contents(root)
    for warning in report.warnings:
        print(f"! {warning}")
    if not report.ok:
        for error in report.errors:
            print(f"✗ {error}")
        print("\nNothing was written. Fix content/*.yaml first (details: python3 tools/check_content.py).")
        return 1
    outputs = build_outputs(root, contents, today or dt.date.today())
    stale = [output for output in outputs if read_or_none(output.path) != output.text]
    names = ", ".join(str(output.path.relative_to(root)) for output in stale)
    if options == ["--check"]:
        print(f"✗ out of date: {names}\nRun python3 tools/build_seo.py" if stale else "✓ SEO files are up to date")
        return 1 if stale else 0
    for output in stale:
        output.path.parent.mkdir(parents=True, exist_ok=True)
        output.path.write_text(output.text, encoding="utf-8")
    print(f"✓ wrote {names}" if stale else "✓ already up to date, nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
