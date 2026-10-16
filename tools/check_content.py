#!/usr/bin/env python3
"""Validate content/en.yaml and content/es.yaml before uploading them.

Usage:
    python3 tools/check_content.py [content_dir]

Exit code 0 when both files are valid (warnings allowed), 1 otherwise.
YAML is parsed with YAML 1.2 core rules, the same way the page parses it
(js-yaml CORE_SCHEMA): `no`/`on` stay text, dates stay text, duplicate keys fail.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import yaml

LANGUAGES: Tuple[str, ...] = ("en", "es")
DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

Validator = Callable[[Any, str], List[str]]


# ── YAML loading ────────────────────────────────────────────────────────────

class CoreLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2 core booleans, no timestamps, no duplicate keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> Dict[Any, Any]:
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (str, int, float, bool)) and key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicated key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


_DROPPED_TAGS = {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
CoreLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regex) for tag, regex in resolvers if tag not in _DROPPED_TAGS]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
CoreLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def parse_yaml(text: str, name: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Parse YAML text; return (data, errors)."""
    try:
        data = yaml.load(text, Loader=CoreLoader)  # noqa: S506 — CoreLoader is a SafeLoader
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        problem = getattr(error, "problem", None) or str(error)
        return None, [f"{name}{where}: invalid YAML — {problem}"]
    if not isinstance(data, dict):
        return None, [f"{name}: expected a mapping at the top level"]
    return data, []


# ── Leaf validators ─────────────────────────────────────────────────────────

YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
ALLOWED_SCHEMES = {"http", "https", "mailto"}


def text(value: Any, path: str) -> List[str]:
    if isinstance(value, str) and value.strip():
        return []
    if isinstance(value, dict) and len(value) == 1:
        return [f'{path}: expected non-empty text — it contains ": ", wrap the whole text in "double quotes"']
    return [f"{path}: expected non-empty text, got {value!r}"]


def url(value: Any, path: str) -> List[str]:
    if not isinstance(value, str):
        return [f'{path}: expected a URL or "" (empty hides the link), got {value!r}']
    if value != value.strip() or " " in value:
        return [f"{path}: URL must not contain spaces (use %20), got {value!r}"]
    scheme = URL_SCHEME.match(value)
    if scheme and scheme.group(1).lower() not in ALLOWED_SCHEMES:
        return [f"{path}: URL scheme {scheme.group(1)!r} not allowed (use https://, http:// or mailto:)"]
    return []


def email(value: Any, path: str) -> List[str]:
    if isinstance(value, str) and EMAIL.match(value):
        return []
    return [f"{path}: expected an email address, got {value!r}"]


HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
# Catppuccin color names: the page maps them to the current theme (Mocha dark, Latte light).
CATPPUCCIN_NAMES: Tuple[str, ...] = (
    "rosewater", "flamingo", "pink", "mauve", "red", "maroon", "peach", "yellow", "green", "teal",
    "sky", "sapphire", "blue", "lavender", "text", "subtext1", "subtext0", "overlay2", "overlay1",
    "overlay0", "surface2", "surface1", "surface0", "base", "mantle", "crust",
)


def color(value: Any, path: str) -> List[str]:
    if isinstance(value, str) and (HEX_COLOR.fullmatch(value) or value in CATPPUCCIN_NAMES):
        return []
    return [f"{path}: expected '#rrggbb' (quoted) or a Catppuccin color name like yellow, got {value!r}"]


IMAGE_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


def image_slug(value: Any, path: str) -> List[str]:
    """A project image: the name of content/<slug>.jpg, without the extension."""
    if isinstance(value, str) and IMAGE_SLUG.fullmatch(value):
        return []
    return [f"{path}: expected the name of content/<name>.jpg (lowercase letters, digits, -), got {value!r}"]


def year_month(value: Any, path: str) -> List[str]:
    if isinstance(value, str) and YEAR_MONTH.match(value):
        return []
    return [f"{path}: expected YYYY-MM (e.g. 2024-05), got {value!r}"]


def optional_year_month(value: Any, path: str) -> List[str]:
    return [] if value is None else year_month(value, path)


def day(value: Any, path: str) -> List[str]:
    try:
        parsed = dt.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or len(value) != 10:
        return [f"{path}: expected YYYY-MM-DD (e.g. 2007-09-20), got {value!r}"]
    if parsed > dt.date.today():
        return [f"{path}: date {value} is in the future"]
    return []


def year(value: Any, path: str) -> List[str]:
    as_text = str(value) if isinstance(value, (int, str)) and not isinstance(value, bool) else ""
    if re.fullmatch(r"\d{4}", as_text):
        return []
    return [f"{path}: expected a 4-digit year, got {value!r}"]


def count(value: Any, path: str) -> List[str]:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return []
    return [f"{path}: expected a whole number ≥ 0, got {value!r}"]


def lang_code(value: Any, path: str) -> List[str]:
    if value in LANGUAGES:
        return []
    return [f"{path}: expected one of {', '.join(LANGUAGES)}, got {value!r}"]


def text_list(min_items: int = 1, exact: Optional[int] = None) -> Validator:
    def check(value: Any, path: str) -> List[str]:
        if not isinstance(value, list):
            return [f"{path}: expected a list, got {value!r}"]
        if exact is not None and len(value) != exact:
            return [f"{path}: expected exactly {exact} items, got {len(value)}"]
        if len(value) < min_items:
            return [f"{path}: expected at least {min_items} item(s)"]
        return [error for index, item in enumerate(value) for error in text(item, f"{path}[{index}]")]
    return check


def label_map(value: Any, path: str) -> List[str]:
    """`label: text` pairs, rendered in file order."""
    if not isinstance(value, dict) or not value:
        return [f"{path}: expected at least one `label: text` line"]
    errors: List[str] = []
    for key, item in value.items():
        if not isinstance(key, str) or key.isdigit():
            errors.append(f"{path}: label {key!r} must be text, not only digits (quote it or reword it)")
            continue
        errors += text(item, f"{path}.{key}")
    return errors


# ── Schema ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ListOf:
    item: "Spec"
    min_items: int = 1


@dataclass(frozen=True)
class OptionalKey:
    """A key that may be left out; when present it must match `spec`."""
    spec: "Spec"


Spec = Union[Validator, ListOf, OptionalKey, Dict[str, "Spec"]]

SCHEMA: Dict[str, Spec] = {
    "meta": {"title": text, "lang": lang_code, "description": text},
    "identity": {
        "firstName": text, "lastName": text, "alias": text, "handle": text,
        "domain": text, "email": email, "role": text, "locationShort": text,
    },
    "hero": {
        "prompt": {"user": text, "command": text},
        "line": text, "ridgeTitle": text, "cursorHint": text,
    },
    "about": {"summary": text, "facts": label_map},
    "experience": ListOf({
        "company": text,
        "color": OptionalKey(color),
        "roles": ListOf({"role": text, "from": year_month, "to": optional_year_month, "bullets": text_list()}),
    }),
    "skills": ListOf({"title": text, "items": text_list()}),
    "projects": {
        "subtitle": text,
        "items": ListOf({
            "title": text, "year": year, "description": text,
            "tags": text_list(min_items=0), "code": url, "live": url,
            "image": OptionalKey(image_slug), "alt": OptionalKey(text),
        }, min_items=0),
    },
    "blog": {"url": url},
    "now": {"updated": text, "items": label_map},
    "fun": {
        "subtitle": text,
        "albums": {"since": day, "input": text, "output": text, "line": text, "meta": text},
        "coffee": {
            "since": day, "perWorkday": count, "input": text, "output": text,
            "line": text, "meta": text, "workdays": text,
        },
    },
    "contact": {"title": text, "links": ListOf({"label": text, "url": url}, min_items=0)},
    "footer": {"copyright": text, "credits": text},
    "ui": {
        "nav": {key: text for key in
                ("about", "experience", "skills", "projects", "blog", "now", "fun", "contact")},
        "dates": {"present": text, "now": text, "year": text, "month": text,
                  "months": text_list(exact=12)},
        "projects": {"screenshot": text, "code": text, "live": text, "soon": text},
        "email": {"copy": text, "copied": text, "toast": text},
        "palette": {key: text for key in
                    ("placeholder", "empty", "navigate", "run", "goto", "action",
                     "backToTop", "switchLanguage", "copyEmail", "lightTheme", "darkTheme")},
    },
}

# Maps whose keys are translated labels: compared across languages by count only.
LABEL_MAP_PATHS = {"about.facts", "now.items"}

# Values that are not translated and should match in both files.
SHARED_FIELDS: Tuple[str, ...] = (
    "identity.firstName", "identity.lastName", "identity.alias", "identity.handle",
    "identity.domain", "identity.email",
    "experience[].company", "experience[].color", "experience[].roles[].from", "experience[].roles[].to",
    "projects.items[].year", "projects.items[].tags", "projects.items[].code", "projects.items[].live",
    "projects.items[].image",
    "blog.url", "contact.links[].url",
    "fun.albums.since", "fun.coffee.since", "fun.coffee.perWorkday",
)


def join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def validate(value: Any, spec: Spec, path: str = "") -> List[str]:
    if isinstance(spec, OptionalKey):
        return validate(value, spec.spec, path)
    if isinstance(spec, ListOf):
        if not isinstance(value, list):
            return [f"{path}: expected a list, got {value!r}"]
        if len(value) < spec.min_items:
            return [f"{path}: expected at least {spec.min_items} item(s)"]
        return [error for index, item in enumerate(value)
                for error in validate(item, spec.item, f"{path}[{index}]")]
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return [f"{path or 'file'}: expected `key: value` lines, got {value!r}"]
        errors = [f"{join(path, key)}: missing" for key, child in spec.items()
                  if key not in value and not isinstance(child, OptionalKey)]
        errors += [f"{join(path, str(key))}: unknown key (typo?)" for key in value if key not in spec]
        return errors + [error for key, child in spec.items() if key in value
                         for error in validate(value[key], child, join(path, key))]
    return spec(value, path)


def check_rules(content: Dict[str, Any], lang: str) -> List[str]:
    """Cross-field rules the schema cannot express."""
    errors: List[str] = []
    meta = content.get("meta")
    if isinstance(meta, dict) and meta.get("lang") not in (None, lang):
        errors.append(f"meta.lang: is {meta['lang']!r} but the file is {lang}.yaml")
    for path, role in roles(content):
        start, end = role.get("from"), role.get("to")
        if isinstance(start, str) and isinstance(end, str) and end < start:
            errors.append(f"{path}: `to` ({end}) is before `from` ({start})")
    return errors + image_alt_errors(content)


def image_alt_errors(content: Dict[str, Any]) -> List[str]:
    """A project image needs alt text (for screen readers and search), and alt text needs an image."""
    projects = content.get("projects")
    items = projects.get("items") if isinstance(projects, dict) else None
    errors: List[str] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict) or ("image" in item) == ("alt" in item):
            continue
        missing = "alt" if "image" in item else "image"
        errors.append(f"projects.items[{index}]: `{missing}` is required when `{'image' if missing == 'alt' else 'alt'}` is set")
    return errors


def roles(content: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Every well-formed experience[i].roles[j] with its path."""
    found: List[Tuple[str, Dict[str, Any]]] = []
    experience = content.get("experience")
    for index, company in enumerate(experience if isinstance(experience, list) else []):
        company_roles = company.get("roles") if isinstance(company, dict) else None
        for role_index, role in enumerate(company_roles if isinstance(company_roles, list) else []):
            if isinstance(role, dict):
                found.append((f"experience[{index}].roles[{role_index}]", role))
    return found


def order_warnings(content: Dict[str, Any]) -> List[str]:
    """Experience should be newest first: roles inside a company, and companies by their latest start."""
    warnings: List[str] = []
    latest_starts: List[Tuple[int, str]] = []
    experience = content.get("experience")
    for index, company in enumerate(experience if isinstance(experience, list) else []):
        starts = [role.get("from") for path, role in roles(content) if path.startswith(f"experience[{index}].")]
        starts = [start for start in starts if isinstance(start, str)]
        if starts != sorted(starts, reverse=True):
            warnings.append(f"experience[{index}].roles: not newest first")
        if starts:
            latest_starts.append((index, max(starts)))
    for (_, newer), (index, older) in zip(latest_starts, latest_starts[1:]):
        if older > newer:
            warnings.append(f"experience[{index}]: starts after the company above it; list companies newest first")
    return warnings


def check_language(content: Dict[str, Any], lang: str) -> List[str]:
    return validate(content, SCHEMA) + check_rules(content, lang)


DESCRIPTION_MAX = 160  # longer descriptions get cut off in search results


def language_warnings(content: Dict[str, Any]) -> List[str]:
    """Valid but worth fixing."""
    meta = content.get("meta")
    description = meta.get("description") if isinstance(meta, dict) else None
    warnings = order_warnings(content)
    if isinstance(description, str) and len(description) > DESCRIPTION_MAX:
        warnings.insert(0, f"meta.description: {len(description)} characters; search results cut it off after ~{DESCRIPTION_MAX}")
    return warnings


# ── Cross-language comparison ───────────────────────────────────────────────

def kind(value: Any) -> str:
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return "empty" if value is None else "text/number"


def compare_structure(first: Any, second: Any, path: str = "") -> List[str]:
    if kind(first) != kind(second) and not (path.endswith(".to") and None in (first, second)):
        return [f"{path}: {kind(first)} in en.yaml but {kind(second)} in es.yaml"]
    if isinstance(first, list):
        errors = [] if len(first) == len(second) else [
            f"{path}: {len(first)} items in en.yaml but {len(second)} in es.yaml"]
        return errors + [error for index, (a, b) in enumerate(zip(first, second))
                         for error in compare_structure(a, b, f"{path}[{index}]")]
    if isinstance(first, dict):
        if path in LABEL_MAP_PATHS:
            return [] if len(first) == len(second) else [
                f"{path}: {len(first)} entries in en.yaml but {len(second)} in es.yaml"]
        errors = [f"{join(path, str(key))}: only in en.yaml" for key in first if key not in second]
        errors += [f"{join(path, str(key))}: only in es.yaml" for key in second if key not in first]
        return errors + [error for key in first if key in second
                         for error in compare_structure(first[key], second[key], join(path, str(key)))]
    return []


def values_at(content: Any, dotted: str) -> List[Tuple[str, Any]]:
    """Resolve 'a.b[].c' into [(concrete_path, value), ...]."""
    found: List[Tuple[str, Any]] = [("", content)]
    for part in dotted.split("."):
        is_list = part.endswith("[]")
        key = part[:-2] if is_list else part
        step: List[Tuple[str, Any]] = []
        for path, node in found:
            if not isinstance(node, dict) or key not in node:
                continue
            child, child_path = node[key], join(path, key)
            if is_list and isinstance(child, list):
                step += [(f"{child_path}[{index}]", item) for index, item in enumerate(child)]
            elif not is_list:
                step.append((child_path, child))
        found = step
    return found


def compare_shared(first: Dict[str, Any], second: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    for dotted in SHARED_FIELDS:
        second_values = dict(values_at(second, dotted))
        for path, value in values_at(first, dotted):
            if path in second_values and second_values[path] != value:
                warnings.append(f"{path}: en.yaml has {value!r} but es.yaml has {second_values[path]!r}")
    return warnings


# ── Report ──────────────────────────────────────────────────────────────────

@dataclass
class Report:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_directory(content_dir: Path) -> Report:
    report = Report()
    parsed: Dict[str, Dict[str, Any]] = {}
    for lang in LANGUAGES:
        file_path = content_dir / f"{lang}.yaml"
        if not file_path.is_file():
            report.errors.append(f"{lang}.yaml: file not found in {content_dir}")
            continue
        data, errors = parse_yaml(file_path.read_text(encoding="utf-8"), f"{lang}.yaml")
        report.errors += errors
        if data is None:
            continue
        parsed[lang] = data
        report.errors += [f"{lang}.yaml › {error}" for error in check_language(data, lang)]
        report.warnings += [f"{lang}.yaml › {warning}" for warning in language_warnings(data)]
    if len(parsed) == len(LANGUAGES):
        first, second = (parsed[lang] for lang in LANGUAGES)
        report.errors += [f"en/es mismatch › {error}" for error in compare_structure(first, second)]
        report.warnings += [f"en/es differ › {warning}" for warning in compare_shared(first, second)]
    return report


def main(argv: List[str]) -> int:
    content_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONTENT_DIR
    report = check_directory(content_dir)
    for error in report.errors:
        print(f"✗ {error}")
    for warning in report.warnings:
        print(f"! {warning}")
    if report.ok:
        suffix = f" ({len(report.warnings)} warning(s))" if report.warnings else ""
        print(f"✓ en.yaml and es.yaml are valid{suffix}")
        return 0
    print(f"\n{len(report.errors)} error(s). Fix them before uploading.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
