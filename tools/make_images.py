#!/usr/bin/env python3
"""Render the share images and icons from content/*.yaml.

Usage:
    python3 tools/make_images.py

Writes (only files whose bytes changed):
    og-en.png, og-es.png   1200×630 link-preview cards: hero.prompt, name, hero.ridgeTitle, role, employer
    favicon.ico            48/32/16 px (the 16 px one is just "j")
    favicon.svg            vector icon (system monospace font)
    apple-touch-icon.png   180 px
    img/projects/<image>-640.webp, -1280.webp, -1280.jpg
                           each project `image` (content/<image>.jpg), center-cropped to 16:9

Needs Pillow (dev only: pip3 install --user pillow). The fonts are the same
Iosevka woff2 files the page loads; they are downloaded once into tools/fonts/.
Rerun this after changing the name, role, current employer, hero.prompt, hero.ridgeTitle
or a project image.
"""
from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import build_seo

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # checked in main() so the tests and the error message still work without it
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

ROOT = build_seo.ROOT
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_CDN = "https://cdn.jsdelivr.net/npm/@fontsource"
# Same packages and version as the page's @font-face rules.
FONTS: Dict[str, str] = {
    "mono-400": f"{FONT_CDN}/iosevka@5.2.5/files/iosevka-latin-400-normal.woff2",
    "mono-600": f"{FONT_CDN}/iosevka@5.2.5/files/iosevka-latin-600-normal.woff2",
    "aile-500": f"{FONT_CDN}/iosevka-aile@5.2.5/files/iosevka-aile-latin-500-normal.woff2",
    "etoile-700": f"{FONT_CDN}/iosevka-etoile@5.2.5/files/iosevka-etoile-latin-700-normal.woff2",
}

CRUST, MANTLE, BASE, SURFACE0 = "#11111b", "#181825", "#1e1e2e", "#313244"
TEXT, SUBTEXT, OVERLAY = "#cdd6f4", "#bac2de", "#6c7086"
MAUVE, BLUE, GREEN, RED, YELLOW = "#cba6f7", "#89b4fa", "#a6e3a1", "#f38ba8", "#f9e2af"
WIDTH, HEIGHT = 1200, 630
PROJECT_DIR = "img/projects"
PROJECT_WIDTHS: Tuple[int, ...] = (640, 1280)  # the page's srcset; the JPEG fallback uses the largest
PROJECT_RATIO = (16, 9)
WEBP_QUALITY, JPEG_QUALITY = 80, 82
Run = Tuple[str, str]  # (text, color)
Fetch = Callable[[str], bytes]

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="18" fill="#1e1e2e"/><text x="50" y="52" dominant-baseline="middle" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="44" font-weight="700" fill="#cba6f7">~/j</text></svg>
"""


# ── Fonts ───────────────────────────────────────────────────────────────────

def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def font_file(name: str, font_dir: Path = FONT_DIR, fetch: Fetch = download) -> Path:
    """The cached woff2 for `name`, downloading it the first time."""
    path = font_dir / FONTS[name].rsplit("/", 1)[1]
    if path.is_file():
        return path
    font_dir.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(fetch(FONTS[name]))
    partial.replace(path)
    return path


class Fonts:
    def __init__(self, font_dir: Path = FONT_DIR, fetch: Fetch = download) -> None:
        self.font_dir, self.fetch = font_dir, fetch

    def __call__(self, name: str, size: int) -> "ImageFont.FreeTypeFont":
        return ImageFont.truetype(str(font_file(name, self.font_dir, self.fetch)), size)


# ── Drawing ─────────────────────────────────────────────────────────────────

def draw_runs(draw: "ImageDraw.ImageDraw", xy: Tuple[float, float], runs: List[Run], face: "ImageFont.FreeTypeFont") -> float:
    """Draw differently colored pieces of text on one line; return the x where the line ends."""
    x, y = xy
    for text, color in runs:
        draw.text((x, y), text, font=face, fill=color)
        x += draw.textlength(text, font=face)
    return x


def draw_window(draw: "ImageDraw.ImageDraw", title: str, fonts: Fonts) -> None:
    draw.rounded_rectangle((40, 40, WIDTH - 40, HEIGHT - 40), radius=20, fill=BASE, outline=SURFACE0, width=2)
    draw.rounded_rectangle((41, 41, WIDTH - 41, 96), radius=19, fill=MANTLE, corners=(True, True, False, False))
    draw.line((41, 96, WIDTH - 41, 96), fill=SURFACE0, width=2)
    for index, color in enumerate((RED, YELLOW, GREEN)):
        draw.ellipse((72 + index * 28, 61, 86 + index * 28, 75), fill=color)
    draw.text((WIDTH / 2, 68), title, font=fonts("mono-400", 22), fill=OVERLAY, anchor="mm")


def og_image(content: build_seo.Content, fonts: Fonts) -> "Image.Image":
    identity, hero = content["identity"], content["hero"]
    image = Image.new("RGB", (WIDTH, HEIGHT), CRUST)
    draw = ImageDraw.Draw(image)
    draw_window(draw, f"~/{identity['handle']}", fonts)

    prompt = [(hero["prompt"]["user"], GREEN), (":", TEXT), ("~", BLUE), ("$ ", TEXT), (hero["prompt"]["command"], TEXT)]
    cursor_x = draw_runs(draw, (96, 136), prompt, fonts("mono-400", 30)) + 8
    draw.rectangle((cursor_x, 140, cursor_x + 15, 172), fill=MAUVE)
    name = fonts("etoile-700", 96)
    draw_runs(draw, (92, 196), [(identity["firstName"] + " ", TEXT), (f"“{identity['alias']}”", MAUVE)], name)
    draw.text((92, 300), identity["lastName"], font=name, fill=TEXT)
    draw.text((96, 432), hero["ridgeTitle"], font=fonts("aile-500", 36), fill=SUBTEXT)

    footer, employer = fonts("mono-400", 26), build_seo.current_employer(content)
    role = [(identity["role"], BLUE)] + ([("  ·  ", OVERLAY), (employer, TEXT)] if employer else [])
    draw_runs(draw, (96, 520), role, footer)
    draw.text((WIDTH - 96, 520), identity["domain"], font=footer, fill=OVERLAY, anchor="ra")
    return image


def icon(size: int, rounded: bool, fonts: Fonts) -> "Image.Image":
    """~/j like the header logo, drawn large and scaled down; at 16 px only the j stays legible."""
    scale, label = 512, "~/j" if size > 16 else "j"
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, scale - 1, scale - 1), radius=92 if rounded else 0, fill=BASE)
    draw.text((scale / 2, scale / 2 + 8), label, font=fonts("mono-600", 230 if size > 16 else 420), fill=MAUVE, anchor="mm")
    return image.resize((size, size), Image.LANCZOS)


# ── Project images ──────────────────────────────────────────────────────────

class MissingSource(Exception):
    pass


def project_slugs(contents: Dict[str, build_seo.Content]) -> List[str]:
    """Every project `image`, in page order (shared across languages, so the union is the same list)."""
    slugs: List[str] = []
    for content in contents.values():
        for item in content["projects"]["items"]:
            if item.get("image") and item["image"] not in slugs:
                slugs.append(item["image"])
    return slugs


def project_file_names(slug: str) -> List[str]:
    """Published paths for one project image; the deploy list and the page reference these."""
    return [f"{PROJECT_DIR}/{slug}-{width}.webp" for width in PROJECT_WIDTHS] + [f"{PROJECT_DIR}/{slug}-{PROJECT_WIDTHS[-1]}.jpg"]


def crop_to_ratio(image: "Image.Image") -> "Image.Image":
    """Center-crop to PROJECT_RATIO so every card is the same shape."""
    ratio_w, ratio_h = PROJECT_RATIO
    width, height = image.size
    crop_w, crop_h = min(width, height * ratio_w // ratio_h), min(height, width * ratio_h // ratio_w)
    left, top = (width - crop_w) // 2, (height - crop_h) // 2
    return image.crop((left, top, left + crop_w, top + crop_h))


def encode(image: "Image.Image", kind: str) -> bytes:
    buffer = io.BytesIO()
    if kind == "webp":
        image.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
    else:
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buffer.getvalue()  # no EXIF or other metadata is carried over


def project_images(slug: str, content_dir: Path) -> Dict[str, bytes]:
    source = content_dir / f"{slug}.jpg"
    if not source.is_file():
        raise MissingSource(f"content/{slug}.jpg not found (projects.items[].image: {slug})")
    with Image.open(source) as original:
        cropped = crop_to_ratio(original.convert("RGB"))
    files: Dict[str, bytes] = {}
    for width in PROJECT_WIDTHS:
        resized = cropped.resize((width, width * PROJECT_RATIO[1] // PROJECT_RATIO[0]), Image.LANCZOS)
        files[f"{PROJECT_DIR}/{slug}-{width}.webp"] = encode(resized, "webp")
        if width == PROJECT_WIDTHS[-1]:
            files[f"{PROJECT_DIR}/{slug}-{width}.jpg"] = encode(resized, "jpeg")
    return files


# ── Output ──────────────────────────────────────────────────────────────────

def png(image: "Image.Image") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def ico(images: List["Image.Image"]) -> bytes:
    buffer = io.BytesIO()
    sizes = [image.size for image in images]
    images[0].save(buffer, format="ICO", sizes=sizes, append_images=images[1:])
    return buffer.getvalue()


def render_all(contents: Dict[str, build_seo.Content], fonts: Fonts, content_dir: Path) -> Dict[str, bytes]:
    files = {f"og-{lang}.png": png(og_image(content, fonts)) for lang, content in contents.items()}
    files["apple-touch-icon.png"] = png(icon(180, rounded=False, fonts=fonts).convert("RGB"))
    files["favicon.ico"] = ico([icon(size, rounded=True, fonts=fonts) for size in (48, 32, 16)])
    files["favicon.svg"] = FAVICON_SVG.encode("utf-8")
    for slug in project_slugs(contents):
        files.update(project_images(slug, content_dir))
    return files


def main(argv: List[str], root: Path = ROOT, fonts: Optional[Fonts] = None) -> int:
    if argv[1:]:
        print(__doc__[__doc__.index("Usage:"):__doc__.index("Writes")].rstrip(), file=sys.stderr)
        return 2
    if Image is None:
        print("✗ needs Pillow: pip3 install --user pillow", file=sys.stderr)
        return 2
    contents, report = build_seo.load_contents(root)
    if not report.ok:
        print("\n".join(f"✗ {error}" for error in report.errors) + "\n\nNothing was written. Fix content/*.yaml first.")
        return 1
    try:
        files = render_all(contents, fonts or Fonts(), root / "content")
    except MissingSource as error:
        print(f"✗ {error}\n\nNothing was written.", file=sys.stderr)
        return 1
    changed = [name for name, data in files.items() if not (root / name).is_file() or (root / name).read_bytes() != data]
    for name in changed:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(files[name])
    print(f"✓ wrote {', '.join(changed)}" if changed else "✓ already up to date, nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
