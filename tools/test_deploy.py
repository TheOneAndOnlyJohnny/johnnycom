"""Tests for deploy.sh.  Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

import build_seo
import make_images

PROJECT = Path(__file__).resolve().parent.parent
EXPECTED = sorted([
    ".htaccess", "index.html", "es/index.html", "sitemap.xml", "robots.txt",
    "content/en.yaml", "content/es.yaml",
    "og-en.png", "og-es.png", "favicon.ico", "favicon.svg", "apple-touch-icon.png",
    *[f"img/projects/{slug}-{size}" for slug in ("finsanity", "juanderful") for size in ("640.webp", "1280.webp", "1280.jpg")],
])


class DeployTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        ignore = shutil.ignore_patterns("fonts", "__pycache__", "deploy")
        shutil.copytree(PROJECT, self.root, dirs_exist_ok=True, ignore=ignore)

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def deploy(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.root / "tools" / "deploy.sh")], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "PYTHON": sys.executable})

    def deployed(self) -> List[str]:
        out = self.root / "deploy"
        return sorted(str(path.relative_to(out)) for path in out.rglob("*") if path.is_file())

    def test_folder_has_exactly_the_upload_list(self) -> None:
        (self.root / "notes.md").write_text("private")
        (self.root / ".DS_Store").write_text("junk")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.deployed(), EXPECTED)
        self.assertEqual((self.root / "deploy/index.html").read_bytes(), (self.root / "index.html").read_bytes())
        self.assertIn("deploy/ is ready (18 files)", result.stdout)
        self.assertFalse((self.root / "deploy/content/finsanity.jpg").exists(), "originals stay out")

    def test_rerun_removes_stale_files(self) -> None:
        self.deploy()
        (self.root / "deploy/old.pdf").write_text("stale")
        self.deploy()
        self.assertEqual(self.deployed(), EXPECTED)

    def test_invalid_content_leaves_no_folder(self) -> None:
        self.deploy()
        es_file = self.root / "content/es.yaml"
        es_file.write_text(es_file.read_text(encoding="utf-8").replace("description:", "descripcion:", 1), encoding="utf-8")
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "deploy").exists())

    def test_every_project_image_is_deployed(self) -> None:
        contents, report = build_seo.load_contents(PROJECT)
        self.assertTrue(report.ok, report.errors)
        listed = set(EXPECTED)
        for slug in make_images.project_slugs(contents):
            for name in make_images.project_file_names(slug):
                self.assertIn(name, listed, f"add {name} to FILES in deploy.sh and EXPECTED here")

    def test_blog_redirect_only_on_the_main_host(self) -> None:
        # blog.johnny.com.mx's files live in blog/ under this .htaccess, so an unconditioned rule would loop there.
        htaccess = (PROJECT / ".htaccess").read_text(encoding="utf-8")
        self.assertIn("\tRewriteCond %{HTTP_HOST} ^(www\\.)?johnny\\.com\\.mx$ [NC]\n"
                      "\tRewriteRule ^blog(?:/(.*))?$ https://blog.johnny.com.mx/$1 [R=301,L]\n", htaccess)
        self.assertLess(htaccess.index("RewriteRule ^blog"), htaccess.index("# Force HTTPS"), "one hop from http:// too")

    def test_missing_file_fails(self) -> None:
        (self.root / "favicon.svg").unlink()
        result = self.deploy()
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing favicon.svg", result.stderr)
        self.assertFalse((self.root / "deploy").exists())


if __name__ == "__main__":
    unittest.main()
