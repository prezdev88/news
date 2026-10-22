from __future__ import annotations

import html
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from manana.config import AppError, DEFAULT_TOPICS, SOURCES, Settings, custom_source, load_settings, save_settings
from manana.gui import NewspaperApp
from manana.news import CHILE, collect_news, is_national_article, parse_feed, parse_listing
from manana.pipeline import generate
from manana.source_dialog import SourcesDialog

NOW = datetime(2026, 10, 22, 8, tzinfo=CHILE)
TITLES = (
    "Chile impulsa un nuevo plan de transporte para sus regiones",
    "Universidades chilenas abren becas para estudiantes de educación superior",
    "Emprendedores presentan una plataforma de inteligencia artificial para Chile",
)
BODY = "Las comunidades de Chile participaron en la presentación de una propuesta regional. " * 9
COOPERATIVA = next(source for source in SOURCES if source.name == "Cooperativa")


def article_html(title, body=BODY, published=NOW):
    data = {"@type": "NewsArticle", "headline": title, "articleBody": body, "datePublished": published.isoformat()}
    return '<script type="application/ld+json">' + json.dumps(data) + "</script>"


class PageResponse:
    def __init__(self, content):
        self.content = content.encode("utf-8")

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class PagesSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.pages:
            raise requests.ConnectionError("Unexpected fixture URL")
        return PageResponse(self.pages[url])


class SourceConfigurationTests(unittest.TestCase):
    def test_old_config_keeps_initial_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"article_count": 7}', encoding="utf-8")
            self.assertEqual(load_settings(path).sources, SOURCES)

    def test_custom_sources_and_disabled_choices_survive_save_and_reload(self):
        custom = custom_source("Mi medio", "https://medio.example/nacional/", "Tecnología")
        sources = (replace(COOPERATIVA, enabled=False), custom)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_settings(Settings(sources=sources), path)
            loaded = load_settings(path)
            self.assertEqual(loaded.sources, sources)
            self.assertEqual(loaded.active_sources, (custom,))
            self.assertIsInstance(json.loads(path.read_text())["sources"], list)
        self.assertTrue(COOPERATIVA.enabled)

    def test_new_source_validation_rejects_invalid_urls_and_duplicate_entries(self):
        for url in ("medio.example", "file:///tmp/feed.xml", "https://user:password@medio.example", "https://medio.example/a b", "https://[broken", "https://medio.example:bad"):
            with self.subTest(url=url), self.assertRaises(AppError):
                custom_source("Mi medio", url)
        with self.assertRaises(AppError):
            custom_source(" ", "https://medio.example")
        source = custom_source("Mi medio", "https://medio.example/section")
        for sources in ((source, source), (replace(source, enabled="false"),), ("bad",), (dict(asdict(source), unknown=True),)):
            with self.subTest(sources=sources), self.assertRaises(AppError):
                Settings(sources=sources).validate()

    def test_edit_preserves_preset_rules_until_its_url_changes(self):
        previous = replace(COOPERATIVA, enabled=False)
        renamed = custom_source("Nuevo nombre", previous.url, previous.section, previous)
        self.assertEqual(renamed.page_url, previous.page_url)
        self.assertEqual(renamed.article_prefix, previous.article_prefix)
        self.assertEqual(renamed.feed_url, previous.feed_url)
        changed = custom_source("Nuevo medio", "https://nuevo.example/feed", "", previous)
        self.assertFalse(changed.require_date_in_url)
        self.assertTrue(changed.require_chile)
        self.assertFalse(changed.enabled)

    def test_restoring_defaults_preserves_custom_sources(self):
        custom = custom_source("Mi medio", "https://medio.example/section")
        dialog = SimpleNamespace(sources=[replace(COOPERATIVA, enabled=False), custom], topics=list(DEFAULT_TOPICS), refresh=Mock())
        SourcesDialog.restore_defaults(dialog)
        self.assertIn(custom, dialog.sources)
        self.assertEqual(len(dialog.sources), len(SOURCES) + 1)
        self.assertTrue(all(source.enabled for source in dialog.sources))

    def test_manager_applies_choices_only_on_save_and_persists_them(self):
        app = NewspaperApp.__new__(NewspaperApp)
        app.root = Mock()
        app.busy = False
        app.settings = Settings()
        app.fields = {}
        app.sources_button = Mock()
        app.status = Mock()
        custom = custom_source("Mi medio", "https://medio.example/section")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch("manana.gui.SourcesDialog") as dialog, patch("manana.gui.save_settings", side_effect=lambda settings: save_settings(settings, path)):
                app.manage_sources()
                self.assertEqual(app.settings.sources, SOURCES)
                self.assertFalse(path.exists())
                on_save = dialog.call_args.args[2]
                on_save((custom,))
            self.assertEqual(app.settings.sources, (custom,))
            self.assertEqual(load_settings(path).active_sources, (custom,))
            app.sources_button.configure.assert_called_with(text="Fuentes (1)…")


class CustomSourceReadingTests(unittest.TestCase):
    def test_custom_source_flows_through_generation_and_is_recorded_in_audit(self):
        active = custom_source("Medio elegido", "https://medio.example/nacional")
        disabled = replace(COOPERATIVA, enabled=False)
        urls = [f"https://medio.example/noticia-{index}" for index in range(3)]
        pages = {url: article_html(title) for url, title in zip(urls, TITLES)}
        pages[active.url] = "<main>" + "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, TITLES)) + "</main>"
        session = PagesSession(pages)
        client = Mock()
        client.select_model.return_value = "local-test-model"
        client.select_articles.side_effect = lambda articles, count: [(article, "Sociedad") for article in articles[:count]]
        client.summarize.side_effect = lambda article, section, **kwargs: {"headline": article.title, "section": section, "summary": " ".join(BODY.split()[:45])}
        reader = lambda settings, progress: collect_news(settings, progress, session, NOW)
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(sources=(active, disabled), article_count=3, output_dir=directory)
            with patch("manana.pipeline.LMStudio", return_value=client), patch("manana.pipeline.collect_news", side_effect=reader):
                path = generate(settings, lambda _: None)
            self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
            audit = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(audit["sources"], [asdict(active)])
            self.assertEqual(audit["printed_count"], 3)
            self.assertTrue(all(story["article"]["source"] == active.name for story in audit["stories"]))
        self.assertNotIn(disabled.url, session.calls)

    def test_only_enabled_sources_are_downloaded_and_dateless_urls_work(self):
        active = custom_source("Medio elegido", "https://medio.example/nacional/")
        disabled = replace(custom_source("Medio apagado", "https://apagado.example/nacional/"), enabled=False)
        urls = [f"https://medio.example/noticia-{index}" for index in range(3)]
        pages = {url: article_html(title) for url, title in zip(urls, TITLES)}
        pages[active.url] = "<main>" + "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, TITLES)) + "</main>"
        session = PagesSession(pages)
        articles, _ = collect_news(Settings(sources=(active, disabled)), lambda _: None, session, NOW)
        self.assertEqual([article.url for article in articles], urls)
        self.assertTrue(all(article.source == "Medio elegido" for article in articles))
        self.assertNotIn(disabled.url, session.calls)
        self.assertEqual(len(session.calls), 4)

    def test_rss_and_atom_work_at_the_supplied_url_with_external_publisher_and_query_ids(self):
        source = custom_source("Mi RSS", "https://feeds.example/mi-medio")
        urls = [f"https://editor.example/?p={index}" for index in range(3)]
        for kind in ("rss", "atom"):
            with self.subTest(kind=kind):
                if kind == "rss":
                    items = "".join(f"<item><title>{title}</title><link>{html.escape(url + '&utm_source=feed')}</link></item>" for url, title in zip(urls, TITLES))
                    feed = '<rss version="2.0"><channel>' + items + "</channel></rss>"
                else:
                    items = "".join(f'<entry><title>{title}</title><link href="{html.escape(url)}"/></entry>' for url, title in zip(urls, TITLES))
                    feed = '<feed xmlns="http://www.w3.org/2005/Atom">' + items + "</feed>"
                pages = {url: article_html(title) for url, title in zip(urls, TITLES)}
                pages[source.url] = feed
                articles, _ = collect_news(Settings(sources=(source,)), lambda _: None, PagesSession(pages), NOW)
                self.assertEqual([article.url for article in articles], urls)

    def test_custom_sources_keep_chile_publication_date_and_text_filters(self):
        source = custom_source("Medio", "https://medio.example/nacional")
        urls = [f"https://medio.example/article-{index}" for index in range(6)]
        titles = (*TITLES, "Una empresa japonesa presenta software en su mercado local", "El municipio chileno anuncia una iniciativa antigua", "Una propuesta en Chile tiene texto insuficiente")
        pages = {url: article_html(title) for url, title in zip(urls[:3], TITLES)}
        pages[urls[3]] = article_html(titles[3], "Una empresa japonesa presentó novedades para el mercado de Tokio. " * 12)
        pages[urls[4]] = article_html(titles[4], published=NOW - timedelta(days=4))
        pages[urls[5]] = article_html(titles[5], body="Chile presenta una propuesta.")
        pages[source.url] = "<main>" + "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, titles)) + "</main>"
        articles, _ = collect_news(Settings(sources=(source,)), lambda _: None, PagesSession(pages), NOW)
        self.assertEqual([article.url for article in articles], urls[:3])

    def test_new_technology_source_keeps_its_section_and_requires_technology_content(self):
        source = custom_source("Tecnología local", "https://medio.example/tecnologia", "Tecnología")
        titles = ("Chile refuerza la ciberseguridad en sus servicios públicos", "Universidades chilenas amplían el acceso a internet en regiones", TITLES[2], TITLES[0])
        urls = [f"https://medio.example/tema-{index}" for index in range(4)]
        pages = {url: article_html(title) for url, title in zip(urls, titles)}
        pages[source.url] = "<main>" + "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, titles)) + "</main>"
        articles, _ = collect_news(Settings(sources=(source,)), lambda _: None, PagesSession(pages), NOW)
        self.assertEqual(len(articles), 3)
        self.assertTrue(all(article.section == "Tecnología" for article in articles))
        self.assertNotIn(urls[3], [article.url for article in articles])

    def test_external_links_are_accepted_only_from_explicitly_allowed_feeds(self):
        source = custom_source("Medio", "https://medio.example/section")
        url = "https://externo.example/article"
        self.assertFalse(is_national_article(url, source))
        self.assertTrue(is_national_article(url, source, from_feed=True))
        self.assertFalse(is_national_article(url, replace(source, allow_external_feed_articles=False), from_feed=True))
        self.assertFalse(is_national_article("javascript:alert(1)", source, from_feed=True))
        listing = f'<a href="{url}">{TITLES[0]}</a>'
        self.assertEqual(parse_listing(listing, source), [])
        feed = f'<rss version="2.0"><channel><item><title>{TITLES[0]}</title><link>{url}</link></item></channel></rss>'
        self.assertEqual(len(parse_feed(feed, source)), 1)

    def test_no_active_sources_fails_before_network_or_model_requests(self):
        settings = Settings(sources=tuple(replace(source, enabled=False) for source in SOURCES))
        session = PagesSession({})
        with self.assertRaisesRegex(AppError, "Activa al menos una fuente"):
            collect_news(settings, lambda _: None, session, NOW)
        self.assertFalse(session.calls)
        with patch("manana.pipeline.LMStudio") as model, self.assertRaisesRegex(AppError, "Activa al menos una fuente"):
            generate(settings, lambda _: None)
        model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
