#!/usr/bin/env python3
"""Unpack and re-pack the page template stored inside index.html.

index.html is a self-unpacking bundle: the real page (markup, styles and the
`text/x-dc` logic) is a JSON-encoded HTML string in
`<script type="__bundler/template">`. Edit the unpacked copy, then pack it back.

Usage:
    python3 tools/bundle.py unpack index.html template.html
    python3 tools/bundle.py pack   index.html template.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

TEMPLATE = re.compile(r'<script type="__bundler/template">(.*?)</script>', re.S)


def _find(bundle_html: str) -> re.Match[str]:
    match = TEMPLATE.search(bundle_html)
    if match is None:
        raise ValueError('no <script type="__bundler/template"> found; is this the bundled index.html?')
    return match


def encode(template: str) -> str:
    """JSON string that is safe inside <script>.

    `</` would end the script element early, and `<!--` would switch the HTML
    parser into a state where the real `</script>` no longer closes it.
    """
    return json.dumps(template).replace("</", "<\\/").replace("<!--", "<\\u0021--")


def read_template(bundle_html: str) -> str:
    return json.loads(_find(bundle_html).group(1))


def write_template(bundle_html: str, template: str) -> str:
    match = _find(bundle_html)
    return bundle_html[:match.start(1)] + encode(template) + bundle_html[match.end(1):]


def main(argv: List[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("unpack", "pack"):
        print(__doc__[__doc__.index("Usage:"):].rstrip(), file=sys.stderr)
        return 2
    action, bundle_path, template_path = argv[1], Path(argv[2]), Path(argv[3])
    bundle_html = bundle_path.read_text(encoding="utf-8")
    if action == "unpack":
        template_path.write_text(read_template(bundle_html), encoding="utf-8")
    else:
        bundle_path.write_text(write_template(bundle_html, template_path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
