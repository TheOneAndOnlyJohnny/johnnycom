"""Plain, semantic HTML of the whole page, rendered from one content/<lang>.yaml.

build_seo.py puts it in the outer index.html so crawlers and link previews that
don't run JavaScript still read the real content. It sits under the loading
overlay, the bundle replaces it when the page unpacks, and visitors with
JavaScript off see it (see NOSCRIPT_STYLE).
"""
from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Tuple

Content = Dict[str, Any]
SECTIONS = ("about", "experience", "skills", "projects", "now", "fun", "contact")
OTHER_LANGUAGE = {"en": ("es", "es/"), "es": ("en", "../")}  # relative: works under a subpath too
TO_SITE_ROOT: Dict[str, str] = {"en": "", "es": "../"}  # from each page to the site's own files
PROJECT_IMAGE = "img/projects/{slug}-1280.jpg"  # made by make_images.py; universal fallback format

# With JavaScript on, the page sits under the bundle's overlay for a moment; keep it from adding a scrollbar.
STYLE = "#static-page{max-height:100vh;overflow:hidden}"

# Only applies with JavaScript off: hide the bundle's overlay and make the static page readable (Catppuccin Latte).
NOSCRIPT_STYLE = (
    "#__bundler_thumbnail,#__bundler_loading{display:none}#static-page{max-height:none;overflow:visible}"
    "body{display:block;background:#eff1f5;color:#4c4f69;font:16px/1.6 ui-sans-serif,system-ui,sans-serif}"
    "#static-page{max-width:46rem;margin:0 auto;padding:2rem 1rem}"
    "#static-page a{color:#1e66f5}#static-page h2{color:#8839ef;margin-top:2.5rem}"
    "#static-page dt{font-weight:600}#static-page dd{margin:0 0 .5rem}#static-page img{max-width:100%;height:auto}"
)


PLACEHOLDER_URL = "#"  # "coming soon": shown on the page as a label, never as a link


def has_url(url: str) -> bool:
    return bool(url) and url != PLACEHOLDER_URL


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def link(url: str, text: str, external: bool = False) -> str:
    rel = ' rel="noopener noreferrer"' if external else ""
    return f'<a href="{esc(url)}"{rel}>{esc(text)}</a>'


def definitions(pairs: Dict[str, Any]) -> str:
    return "<dl>" + "".join(f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in pairs.items()) + "</dl>"


def bullet_list(items: List[str]) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def section(section_id: str, heading: str, body: List[str]) -> str:
    return f'<section id="{section_id}">\n<h2>{esc(heading)}</h2>\n' + "\n".join(body) + "\n</section>"


def month(value: Optional[str], dates: Dict[str, Any]) -> str:
    if not value:
        return esc(dates["present"])
    year, number = value.split("-")
    return f'<time datetime="{value}">{esc(dates["months"][int(number) - 1])} {year}</time>'


# ── Sections ────────────────────────────────────────────────────────────────

def header(content: Content, lang: str) -> str:
    identity, ui = content["identity"], content["ui"]
    other_lang, other_path = OTHER_LANGUAGE[lang]
    nav = [f'<a href="#{section_id}">{esc(ui["nav"][section_id])}</a>' for section_id in SECTIONS]
    if content["blog"]["url"]:
        nav.append(link(content["blog"]["url"], ui["nav"]["blog"], external=True))
    nav.append(f'<a href="{other_path}" hreflang="{other_lang}" lang="{other_lang}">{esc(ui["palette"]["switchLanguage"])}</a>')
    return ("<header>\n"
            f'<h1>{esc(identity["firstName"])} “{esc(identity["alias"])}” {esc(identity["lastName"])}</h1>\n'
            f'<p>{esc(identity["role"])} · {esc(identity["locationShort"])}</p>\n'
            f'<p>{esc(content["hero"]["line"])}</p>\n'
            f'<nav>{" · ".join(nav)}</nav>\n'
            "</header>")


def company_span(roles: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """First start and last end across a company's roles; no end while any role is current."""
    ends = [role.get("to") for role in roles]
    return min(role["from"] for role in roles), None if not all(ends) else max(ends)


def experience(content: Content) -> List[str]:
    """One article per company with its roles inside. No durations: they'd change with the build date."""
    dates, articles = content["ui"]["dates"], []
    for company in content["experience"]:
        start, end = company_span(company["roles"])
        roles = [f'<h4>{esc(role["role"])}</h4>\n<p>{month(role["from"], dates)} — {month(role.get("to"), dates)}</p>\n'
                 f'{bullet_list([esc(bullet) for bullet in role["bullets"]])}' for role in company["roles"]]
        articles.append(f'<article>\n<h3>{esc(company["company"])}</h3>\n<p>{month(start, dates)} — {month(end, dates)}</p>\n'
                        + "\n".join(roles) + "\n</article>")
    return articles


def skills(content: Content) -> List[str]:
    return [f'<h3>{esc(group["title"])}</h3>\n{bullet_list([esc(item) for item in group["items"]])}'
            for group in content["skills"]]


def project_image(project: Dict[str, Any], lang: str) -> str:
    if not project.get("image"):
        return ""
    src = TO_SITE_ROOT[lang] + PROJECT_IMAGE.format(slug=project["image"])
    return f'<img src="{esc(src)}" alt="{esc(project["alt"])}" width="1280" height="720" loading="lazy" decoding="async">\n'


def projects(content: Content, lang: str) -> List[str]:
    labels, body = content["ui"]["projects"], [f'<p>{esc(content["projects"]["subtitle"])}</p>']
    for project in content["projects"]["items"]:
        links = [link(project[kind], labels[kind], external=True) for kind in ("code", "live") if has_url(project.get(kind, ""))]
        body.append(f'<article>\n<h3>{esc(project["title"])} ({esc(project["year"])})</h3>\n' + project_image(project, lang)
                    + f'<p>{esc(project["description"])}</p>\n<p>{esc(" · ".join(project.get("tags") or []))}</p>\n'
                    + (f'<p>{" · ".join(links)}</p>\n' if links else "") + "</article>")
    return body


def fun(content: Content) -> List[str]:
    stats = content["fun"]
    return [f'<p>{esc(stats["subtitle"])}</p>',
            bullet_list([esc(stats["albums"]["line"]), esc(stats["coffee"]["line"])])]


def contact(content: Content) -> List[str]:
    email = content["identity"]["email"]
    links = [link(item["url"], item["label"], external=True) for item in content["contact"]["links"] if has_url(item["url"])]
    return [f'<p>{esc(content["contact"]["title"])}</p>',
            bullet_list([link(f"mailto:{email}", email), *links])]


def render(content: Content, lang: str) -> str:
    nav, now = content["ui"]["nav"], content["now"]
    body = [
        header(content, lang),
        "<main>",
        section("about", nav["about"], [f'<p>{esc(content["about"]["summary"])}</p>', definitions(content["about"]["facts"])]),
        section("experience", nav["experience"], experience(content)),
        section("skills", nav["skills"], skills(content)),
        section("projects", nav["projects"], projects(content, lang)),
        section("now", nav["now"], [f'<p>{esc(now["updated"])}</p>', definitions(now["items"])]),
        section("fun", nav["fun"], fun(content)),
        section("contact", nav["contact"], contact(content)),
        "</main>",
        f'<footer>\n<p>{esc(content["footer"]["copyright"])}</p>\n<p>{esc(content["footer"]["credits"])}</p>\n</footer>',
    ]
    return '<div id="static-page">\n' + "\n".join(body) + "\n</div>"
