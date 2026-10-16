# johnny.com.mx

Personal site of Juan “Johnny” Guzmán: a static page served from cPanel/LiteSpeed. There's no CMS, no PHP and no build server.
English is at `/` and Spanish at `/es/`.
Source: https://github.com/TheOneAndOnlyJohnny/johnnycom (`deploy/` and `tools/fonts/` are build output and aren't tracked).

## Editing content

All text, dates and URLs live in `content/en.yaml` and `content/es.yaml`. The page loads them at runtime.

1. Edit **both** files. They must keep the same keys, the same number of list items and the same order. Names, dates and URLs are duplicated in both on purpose, so change them in both.
2. Rebuild the SEO files. This also validates the content first:
   ```sh
   python3 tools/build_seo.py
   ```
3. Run `./tools/deploy.sh` and upload the contents of `deploy/` (see [Deploy](#deploy)).

Tips (also in the YAML header):
- Quote a value if it starts with `[ { > | * & ! % @` or a backtick, or if it contains `": "` or `" #"`.
- Months are `YYYY-MM` and days are `YYYY-MM-DD`.
- `experience` is a list of companies, each with its `roles` (`role`, `from`, `to`, `bullets`). Keep both levels newest first; the checker warns otherwise.
  - Leave `to` empty for the current role.
  - The page works out each company's dates and total time from its roles.
  - Optional `color` per company: a quoted hex (`'#004977'`, the same in both themes) or a Catppuccin name (`yellow`), which follows the theme. Leave it out to use the automatic palette.
- An empty URL (`""`) hides that link. `"#"` means "coming soon": it's never rendered as a link.
- Projects can have an `image` (the name of `content/<name>.jpg`, the same in both files) plus a translated `alt`; one requires the other. After adding or changing one, run `python3 tools/make_images.py`. Without an image, the card shows a striped placeholder.
- `blog.url` is the external blog (`https://blog.johnny.com.mx/`). It shows as "~/johnny/blog ↗" (`ui.nav.blog`) at the end of the nav and in ⌘K, opening in a new tab. There's no Writing section.
- `meta.description` is required. Over 160 characters only triggers a warning.

Validate without building: `python3 tools/check_content.py` (exit 1 on errors).

## Tools

The tools need Python 3 with PyYAML (`pip3 install --user pyyaml`).

| Command | What it does |
|---|---|
| `python3 tools/check_content.py [dir]` | Schema check plus EN/ES parity. Uses YAML 1.2 core rules like the page does, so `no` stays text and duplicate keys fail. |
| `python3 tools/build_seo.py` | Validates the content, then writes `index.html`, `es/index.html`, `sitemap.xml` and `robots.txt`. Running it again changes nothing, and a page's `lastmod` only moves when that page changed. |
| `python3 tools/build_seo.py --check` | Exit 1 if any generated file is out of date. Writes nothing. |
| `python3 tools/make_images.py` | Renders the share images and icons from the YAML, and the project images from `content/<image>.jpg` (needs Pillow). |
| `python3 tools/bundle.py unpack index.html t.html` | Extracts the page template so you can edit its markup, styles or logic. |
| `python3 tools/bundle.py pack index.html t.html` | Puts the edited template back. Run `build_seo.py` afterwards. |

Tests: `cd tools && python3 -m unittest discover -s .` (the image-rendering tests skip without Pillow and `tools/fonts/`)

### Changing the page itself (layout, styles, logic)

```sh
python3 tools/bundle.py unpack index.html /tmp/t.html
# edit /tmp/t.html
python3 tools/bundle.py pack index.html /tmp/t.html
python3 tools/build_seo.py        # regenerates es/index.html from the English bundle
```
Only edit the English `index.html`. `es/index.html` is generated, and any edit to it is overwritten.

### Share images, icons and project images

`og-en.png`, `og-es.png` (1200×630), `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` and `img/projects/*` (WebP 640/1280 + JPEG 1280, cropped to 16:9 from `content/<image>.jpg`) come from:

```sh
pip3 install --user pillow        # one time, development only
python3 tools/make_images.py      # writes only the images that changed
```

The cards show `hero.prompt`, the name, `hero.ridgeTitle`, the role and the current employer, so rerun it after changing any of those. `hero.prompt` and `hero.ridgeTitle` are used only by these images.
The first run downloads the page's Iosevka fonts (woff2) into `tools/fonts/`.

## Themes

The page has a light theme (Catppuccin Latte) and a dark one (Mocha).
- **Default:** light for every first-time visitor; the OS setting is ignored.
- **Switching:** ⌘K / Ctrl K ▸ "Switch to light/dark theme" switches it, and the choice is remembered in that browser.
- **Labels:** `ui.palette.lightTheme` and `ui.palette.darkTheme` in the YAML.
- **Not themed:** the loading screen and the no-JavaScript page are always light; the share images stay dark.

## Local development

Any static server works, including under a subpath (e.g. `https://standalone.localhost/johnny/`). The page works out its base from the URL.
- **Development servers usually ignore `.htaccess`**, so they skip the CSP, the cache headers and the YAML MIME type. Test those on production.
- **Safari caches aggressively without cache headers.** Use Develop ▸ Disable Caches.

## Deploy

```sh
./tools/deploy.sh
```

This rebuilds the site (the content check and `build_seo.py`) and recreates `deploy/` with only the files to upload:

```
.htaccess  index.html  es/index.html  content/en.yaml  content/es.yaml  sitemap.xml
robots.txt  og-en.png  og-es.png  favicon.ico  favicon.svg  apple-touch-icon.png
img/projects/{finsanity,juanderful}-{640.webp,1280.webp,1280.jpg}
```

Upload the **contents** of `deploy/` to the web root. `.htaccess` is a hidden file, so enable "Show Hidden Files" in cPanel's File Manager to check it arrived.
- **Errors:** if the content is invalid or a file is missing, the script stops and `deploy/` is removed.
- **Server-side cleanup:** uploading never deletes anything on the server, so remove retired files there by hand.
- **Never upload** `tools/`, `*.md` or the source images in `content/*.jpg`. `.htaccess` blocks `.md` and `.py` anyway.
- **New project image:** add its three `img/projects/` files to `FILES` in `tools/deploy.sh` and to `tools/test_deploy.py`. A test fails until you do.

After an SEO-relevant change:
1. Check the browser Console on the live site for CSP errors.
2. Run Google's [Rich Results Test](https://search.google.com/test/rich-results) (ProfilePage), [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) and the [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/).
3. Submit or resubmit `https://johnny.com.mx/sitemap.xml` in Search Console.

## Blog

`blog.johnny.com.mx` is served from `public_html/blog` on the server. `johnny.com.mx/blog/*` 301s there.
- **Placeholder:** for now `blog/index.html` is a static "coming soon" page: Latte, EN + ES, `noindex`, no scripts, and a link back.
- **Deploy:** it's **not** in `deploy/`. Upload `blog/index.html` once into `public_html/blog/`, and replace it when the real blog arrives. Remove the `noindex` then.
- **Root `.htaccess`:** it also applies to the blog, including HTTPS, the headers, the CSP and the PHP block, so a PHP blog needs its own `blog/.htaccess`.

## `.htaccess` summary

It does the following:
- 301s `johnny.com.mx/blog/*` to `blog.johnny.com.mx/*`, keeping the path and query. It only does this on the main host, because the subdomain's files are in `blog/`, under this same `.htaccess`.
- Redirects to HTTPS and allows only GET/HEAD.
- Blocks dotfiles, backups and notes, and never executes scripts.
- Sends security headers, plus a CSP on `*.html`.
- `no-cache` on HTML and YAML. YAML is served as `text/yaml` with `X-Robots-Tag: noindex`.
- Images (png, ico, svg, jpg, webp) are cached for a week with `CORP: cross-origin` so link previews can load them. WebP has its own MIME type. SVGs get a script-blocking CSP.
- Gzip covers text, XML, YAML and icons.
