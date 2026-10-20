from __future__ import annotations

import re
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ALLOWED_EXTERNAL_HOSTS = {"github.com", "glaucosilvestri.it", "gloutchov.github.io"}


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[tuple[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        for attribute in ("href", "src", "srcset"):
            if values.get(attribute):
                self.references.append((attribute, values[attribute]))
        if tag == "img":
            self.images.append(values)
        if tag == "a":
            self.links.append(values)


class LandingPageTests(unittest.TestCase):
    def parse(self, name: str) -> tuple[str, SiteParser]:
        text = (SITE / name).read_text(encoding="utf-8")
        parser = SiteParser()
        parser.feed(text)
        return text, parser

    def test_required_site_files_exist(self) -> None:
        required = {
            "index.html", "404.html", "css/styles.css", "js/app.js", "js/i18n.js",
            "js/preferences.js", "js/theme-bootstrap.js", "assets/favicon.svg",
            "assets/dashboard-overview.png", "assets/dashboard-overview.webp",
            "assets/dashboard-efficiency.png", "assets/dashboard-efficiency.webp",
            "assets/guided-progress.png", "assets/guided-progress.webp",
        }
        missing = sorted(item for item in required if not (SITE / item).is_file())
        self.assertEqual([], missing)

    def test_local_references_exist_and_external_hosts_are_allowlisted(self) -> None:
        for name in ("index.html", "404.html"):
            _, parser = self.parse(name)
            for attribute, reference in parser.references:
                value = reference.split()[0] if attribute == "srcset" else reference
                if value.startswith("#"):
                    continue
                if value.startswith("/LocalAgentBenchmark/"):
                    local_value = value.removeprefix("/LocalAgentBenchmark/")
                    if local_value:
                        self.assertTrue((SITE / local_value).is_file(), f"missing {value} referenced by {name}")
                    continue
                parsed = urlparse(value)
                if parsed.scheme:
                    self.assertEqual("https", parsed.scheme)
                    self.assertIn(parsed.hostname, ALLOWED_EXTERNAL_HOSTS)
                    continue
                self.assertTrue((SITE / value).is_file(), f"missing {value} referenced by {name}")

    def test_navigation_anchors_have_targets(self) -> None:
        index, parser = self.parse("index.html")
        anchors = {link["href"][1:] for link in parser.links if link.get("href", "").startswith("#")}
        self.assertTrue(anchors.issubset(parser.ids), anchors - parser.ids)
        section_ids = ("news", "why", "method", "quick", "dashboard", "interpretation", "immersion", "start", "docs")
        self.assertTrue({"top", *section_ids}.issubset(parser.ids))
        for section_id, key in zip(
            section_ids,
            ("news_index", "why_index", "method_index", "quick_index", "dashboard_index", "limits_index", "immersion_index", "start_index", "docs_index"),
            strict=True,
        ):
            self.assertIn(f'href="#{section_id}" data-i18n="{key}"', index)

        styles = (SITE / "css" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".start-copy > p:not(.section-index)", styles)
        self.assertNotIn(".start-copy > p {", styles)

    def test_quick_path_is_honest_and_links_its_guide(self) -> None:
        index, parser = self.parse("index.html")
        self.assertIn('href="#quick"', index)
        self.assertIn("QUICK-START_Guided.md", index)
        self.assertIn('<strong>4</strong>', index)
        self.assertIn('<strong>2</strong>', index)
        links = {link.get("href", "") for link in parser.links}
        self.assertIn(
            "https://github.com/gloutchov/LocalAgentBenchmark/blob/main/QUICK-START_Guided.md",
            links,
        )

    def test_provider_news_follows_hero_actions_and_precedes_first_section(self) -> None:
        index, parser = self.parse("index.html")
        hero = index.split('<section class="hero"', 1)[1].split('</section>', 1)[0]
        news = index.split('<section class="section section-news"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('data-i18n="provider_update_title"', hero)
        self.assertLess(hero.index('data-i18n="hero_lede"'), hero.index('data-i18n="cta_repository"'))
        self.assertLess(hero.index('data-i18n="cta_repository"'), hero.index('data-i18n="cta_release"'))
        self.assertLess(hero.index('data-i18n="cta_release"'), hero.index('data-i18n="cta_quick"'))
        self.assertLess(index.index('id="news"'), index.index('id="why"'))
        for provider in ("Ollama", "LM Studio", "llama.cpp"):
            self.assertIn(f"<h3>{provider}</h3>", news)
        self.assertEqual(2, news.count('data-i18n="provider_new"'))
        self.assertIn('data-i18n="provider_update_title"', news)
        self.assertIn('data-i18n="provider_update_text"', news)
        guide = "https://github.com/gloutchov/LocalAgentBenchmark/blob/main/QUICK-START_LocalProviders.md"
        self.assertIn(guide, {link.get("href", "") for link in parser.links})
        self.assertEqual(2, index.count(f'href="{guide}"'))

    def test_full_immersion_start_and_language_scoped_documentation(self) -> None:
        index, parser = self.parse("index.html")
        self.assertIn('id="immersion"', index)
        self.assertIn('id="start"', index)
        for profile in ("smoke", "standard", "full", "showcase"):
            self.assertIn(f"--profile {profile}", index)
        self.assertIn("--cases CASE_ID", index)

        links = {link.get("href", "") for link in parser.links}
        docs = "https://github.com/gloutchov/LocalAgentBenchmark/blob/main/"
        for name in (
            "ISTRUZIONI.md",
            "INSTRUCTIONS.md",
            "QUICK-START_Guided.md",
            "QUICK-START_LocalProviders.md",
            "QUICK-START_Dashboard.md",
            "QUICK-START_Showcase.md",
            "QUICK-START_Case-Author.md",
            "QUICK-START_Windows.md",
            "QUICK-START_Linux.md",
        ):
            self.assertIn(docs + name, links)
        for internal in ("README.md", "SECURITY_MODEL.md", "MAP.md", "PLAN.md"):
            self.assertNotIn(docs + internal, links)
        self.assertIn('data-language-only="it" hidden', index)
        self.assertIn('data-language-only="en"', index)

    def test_images_have_dimensions_and_localised_alternatives(self) -> None:
        _, parser = self.parse("index.html")
        self.assertGreaterEqual(len(parser.images), 2)
        for image in parser.images:
            self.assertRegex(image.get("width", ""), r"^\d+$")
            self.assertRegex(image.get("height", ""), r"^\d+$")
            self.assertRegex(image.get("data-i18n-alt", ""), r"^[a-z0-9_]+$")
            header = (SITE / image["src"]).read_bytes()[:24]
            self.assertEqual(b"\x89PNG\r\n\x1a\n", header[:8])
            width, height = struct.unpack(">II", header[16:24])
            self.assertEqual((width, height), (int(image["width"]), int(image["height"])))

    def test_metadata_csp_accessibility_and_pages_prefix(self) -> None:
        index, _ = self.parse("index.html")
        self.assertIn('href="https://gloutchov.github.io/LocalAgentBenchmark/"', index)
        self.assertIn("connect-src 'none'", index)
        self.assertIn('class="skip-link"', index)
        self.assertIn('data-menu-toggle', index)
        self.assertEqual(2, index.count("data-language-option="))
        self.assertEqual(3, index.count("data-theme-option="))
        self.assertIn('data-theme-option="light"', index)
        self.assertIn('data-theme-option="dark"', index)
        self.assertIn('prefers-reduced-motion: reduce', (SITE / "css" / "styles.css").read_text())
        fallback = (SITE / "404.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(fallback.count('href="/LocalAgentBenchmark/"'), 2)
        self.assertIn('src="/LocalAgentBenchmark/js/app.js"', fallback)
        self.assertIn('href="/LocalAgentBenchmark/css/styles.css"', fallback)

    def test_no_remote_assets_tracking_or_source_video(self) -> None:
        all_text = "\n".join(path.read_text(encoding="utf-8") for path in SITE.rglob("*") if path.suffix in {".html", ".css", ".js"})
        self.assertIsNone(re.search(r"<(?:script|img)[^>]+src=['\"]https?://", all_text, re.I))
        self.assertIsNone(re.search(r"<link(?=[^>]+rel=['\"](?:stylesheet|icon)['\"])[^>]+href=['\"]https?://", all_text, re.I))
        self.assertIsNone(re.search(r"googletagmanager|google-analytics|plausible\.io|segment\.com", all_text, re.I))
        self.assertFalse((SITE / "assets" / "Dashboard.mov").exists())
        self.assertFalse((SITE / "assets" / "Guided.mov").exists())


if __name__ == "__main__":
    unittest.main()
