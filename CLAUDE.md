# CLAUDE.md: johnny.com.mx

This is a static personal site, tracked in git (`origin`: https://github.com/TheOneAndOnlyJohnny/johnnycom.git, branch `main`). `.gitignore` excludes `deploy/`, the `tools/fonts/` cache, `.DS_Store` and Python caches. README.md covers the editing workflow and deployment, so this file only covers architecture and rules.

## Architecture

**`index.html` is a self-unpacking bundle.** Don't hand-edit the template inside it.
- The real page is a JSON-encoded HTML string in `<script type="__bundler/template">`. At load time, the bundler replaces the whole `documentElement` with that template and re-creates its scripts, keeping their attributes.
- To edit it, run `tools/bundle.py unpack`, edit the copy, run `pack`, then run `tools/build_seo.py`. `bundle.encode()` escapes `</` and `<!--`.
- The page logic is `<script type="text/x-dc">`: `class Component extends DCLogic`, evaluated by dc-runtime with `new Function`, so the CSP needs `'unsafe-eval'`.
  - `renderVals()` maps the YAML onto the bindings.
  - `componentDidUpdate` only receives `prevProps` (no `prevState`), so track previous state on the instance (e.g. `palWasOpen`).
- External libraries come from jsDelivr with pinned versions: `three@0.149.0`, `js-yaml@4.1.0` and `@fontsource/iosevka*@5.2.5`. Nothing heavy is embedded.

**Content comes from `content/<lang>.yaml`, loaded at runtime.**
- The page fetches it with `cache:'no-cache'` and parses it with `yaml.CORE_SCHEMA`. `tools/check_content.py` mirrors those rules (`CoreLoader`).
- Every user-visible string lives in the YAML, UI labels included, and both files share the same schema.
- Colors and section numbers are assigned in code.

**Language comes from the URL path, never from storage.**
- `Component.pagePath()` / `urlLang()` / `siteBase()` / `langPath()`: a path ending in `/es/` means Spanish, and the base is the path with `es/` removed. This keeps the site working under a subpath on development servers.
- The language toggle calls `history.pushState`, and `popstate` switches back.

**SEO (`tools/build_seo.py`)**
- The English `index.html` is both the input and the output. `es/index.html` is generated from it.
- The head block sits between `<!-- seo:start … -->` and `<!-- seo:end -->`, right after `<meta charset>`, in **both** the outer head and the template head.
  - The outer head is what crawlers read.
  - The template head is what replaces the document at unpack time.
  - `<title>` and the viewport are only written to the outer head.
- The block contains: description, canonical, hreflang (en, es, x-default), OG/Twitter tags, JSON-LD (`WebSite`, `ProfilePage`, `Person`), icons and theme-color.
- URLs:
  - Links to the site's own files are relative (`TO_SITE_ROOT`).
  - Canonical, hreflang, OG and sitemap URLs are absolute `https://johnny.com.mx/…`.
  - `sameAs` only lists real http(s) profile URLs.
- Static crawlable HTML (`tools/static_page.py`) sits between `<!-- static:start/end -->` in the outer body, under the loading overlay.
  - `STYLE` caps its height while JavaScript is on.
  - `NOSCRIPT_STYLE` hides the overlay and shows a readable dark page.
- Running it twice changes nothing. `--check` reports stale files. A page's sitemap `lastmod` only changes when that page changed.

**Images (`tools/make_images.py`)**
- Pillow draws the OG cards and icons straight from the YAML. It loads the same Iosevka woff2 files as the page; `FONTS` must stay in sync with the page's `@font-face` URLs, and a test checks this.
- The fonts are cached in `tools/fonts/`. Only changed files get written, and the output is byte-stable.
- Pillow is a dev-only dependency. Imports are guarded, so the other tools and tests run without it.
- Project images: each `projects.items[].image` slug turns `content/<slug>.jpg` into `img/projects/<slug>-640.webp`, `-1280.webp` and `-1280.jpg`. They're center-cropped to 16:9 with no metadata (WebP q80, JPEG q82 progressive).
  - `project_file_names()` is the list of those paths.
  - A missing source is an error, and nothing is written.
  - The originals in `content/` are never deployed.

**Colors and theme:** the page uses only Catppuccin variables (`var(--ctp-<name>)`).
- They're defined in the template's `<style>`: Latte on `:root` (the default, so the first paint is light) and Mocha on `:root[data-theme="dark"]`, each with its `color-scheme`.
- The theme lives in `state.theme`. It starts from the saved choice (`localStorage.theme`, read in try/catch), else `'light'`. The OS preference is deliberately never read.
- The visitor switches it in the ⌘K palette (`setTheme()` saves it).
- `syncTheme()` writes `<html data-theme>` and sets `<meta name="theme-color">` from `--ctp-base`.
- The Three.js terrain reads its colors (mauve, blue, pink, and `base` for the fog) from the same variables in `themeScene()`. It reruns when `state.theme` changes, updating the colors in place without rebuilding the scene.
- `build_seo.py` emits a single Latte `theme-color`, and the no-JS page (`NOSCRIPT_STYLE`) uses Latte too.
- Never hardcode a hex or `rgba()` in the template. Use the variables, or `color-mix()` with them for transparency; `test_bundle.py` enforces this.
- JS-built colors are `var()` strings too.
- Company colors from the YAML can be hex values (fixed) or Catppuccin names (they follow the theme).

**Hosting:** cPanel/LiteSpeed reads `.htaccess` (summarized in README.md).
- Any new external origin must be added to the CSP in `.htaccess`.
- `blog.johnny.com.mx`'s docroot is `public_html/blog`, so the root `.htaccess` applies to the blog too: the HTTPS redirect, the headers, the HTML CSP and the PHP block.
  - The `/blog` 301 is conditioned on the main host so it can't loop.
  - A blog engine that needs PHP or other origins needs its own `blog/.htaccess` overrides.
- The blog's files live outside this repo; nothing here builds, tests or deploys them.
- Any new file type needs a MIME type and caching rule.

**Experience:** `experience[]` holds companies, each with its `roles[]`.
- `expView()` builds one accordion item per company. `Component.companySpan()` takes the earliest `from` and the latest `to`, and stays open-ended while any role is current. The total duration covers that whole span.
- `state.open` is keyed by company index and starts as `{ 0: true }`, so only the newest company is expanded.
- Colors follow the company name.
- `static_page.py` mirrors this grouping without durations, which depend on the date and would make builds differ day to day.

**Sections:** about 01, experience 02, skills 03, projects 04, now 05 (full width), fun 06, contact 07.
- `navLinks`, the palette's `ids`, `static_page.SECTIONS` and the number spans in the template have to agree.
- There's no Writing section. `blog.url` (shared) is an external, unnumbered link labeled `ui.nav.blog` ("~/johnny/blog ↗") at the end of the nav, plus a ⌘K command (`window.open`, new tab). An empty URL hides both.

**Projects:** `projects.items[].image` is a slug for `content/<slug>.jpg`, and `alt` is required with it (`check_rules`).
- `"#"` is the "coming soon" URL (`static_page.PLACEHOLDER_URL`, `Component.realUrl()`): it's never output as a link. The card shows "code · soon" (`ui.projects.soon`), and a contact link set to `#` is hidden.
- Cards are 16:9. `Component.projectImage()` builds a `<picture>`: a WebP `srcset` (`sc-camel-src-set`, because the runtime only camel-cases attributes with that prefix) and a JPEG `<img>` fallback.
  - The `<img>` is lazy, async and has width/height.
  - Paths start from `siteBase()`, so they work under `/es/` and under a subpath.
  - Without an `image`, the card shows the striped `ui.projects.screenshot` placeholder.
- `PROJECT_IMAGE_WIDTHS` in the template must match `make_images.PROJECT_WIDTHS`; a test checks this.
- The grid uses `auto-fit`, so two cards fill the row.
- `static_page.py` adds a plain `<img>` (the 1280 JPEG, path relative per page via `TO_SITE_ROOT`, which now lives in `static_page`).

**Hero:** there's one hero, with no variants and no random pick.
- It shows centered text (role · location, a large alias, `hero.line`) over a Three.js wireframe terrain that ripples around the cursor (`initScene()`).
- The `motion` prop pauses the animation.
- The command palette opens from the header button or ⌘K / Ctrl K.

## Rules

- Never edit `es/index.html`, the seo/static blocks or `sitemap.xml`/`robots.txt` by hand. Regenerate them with `python3 tools/build_seo.py`.
- A new YAML field must be added to both languages and to the schema in `tools/check_content.py`. Add a test for it.
- Run the tests after any tool change: `cd tools && /usr/bin/python3 -m unittest discover -s .`
- Code style: Python 3 with type hints, standard library plus PyYAML (and Pillow only for `make_images.py`), and small functions.
- The deploy list lives in `FILES` in `tools/deploy.sh`, and `tools/test_deploy.py` expects the same list. A new file to upload goes in both; validators: see README.md.
- Every `make_images.project_file_names()` path for the YAML's images must be in that list; `test_every_project_image_is_deployed` checks this.
