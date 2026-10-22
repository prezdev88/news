from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from manana.config import AppError, DEFAULT_TOPICS, SOURCES, Settings, custom_source, load_settings, remove_topic, rename_topic, save_settings, source_topic, topic_name
from manana.gui import NewspaperApp
from manana.lmstudio import LMStudio
from manana.news import CHILE, Article, collect_news
from manana.newspaper import render_edition
from manana.pipeline import demo_edition

NOW = datetime(2026, 10, 22, 8, tzinfo=CHILE)
BODY = "Las comunidades de Chile participaron en la presentación de una propuesta regional. " * 9


class TopicConfigurationTests(unittest.TestCase):
    def test_custom_topic_is_normalized_registered_and_persisted(self):
        source = custom_source("Medio", "https://medio.example/cultura", "  Arte   local  ")
        settings = Settings(sources=(source,))
        settings.validate()
        self.assertEqual(settings.sources[0].section, "Arte local")
        self.assertIn("Arte local", settings.topics)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_settings(settings, path)
            loaded = load_settings(path)
        self.assertEqual(loaded.topics, settings.topics)
        self.assertEqual(loaded.sources, settings.sources)

    def test_names_and_duplicate_topics_are_validated(self):
        for name in ("", "   ", "x" * 41, None):
            with self.subTest(name=name), self.assertRaises(AppError):
                topic_name(name)
        self.assertEqual(topic_name("Ciencia\n y  salud"), "Ciencia y salud")
        for topics in ((), "Cultura", ("Cultura", "cultura"), ("Ciencia", " Ciencia ")):
            with self.subTest(topics=topics), self.assertRaises(AppError):
                Settings(topics=topics).validate()
        source = custom_source("Medio", "https://medio.example/cultura", "cultura")
        settings = Settings(topics=("Cultura",), sources=(source,))
        settings.validate()
        self.assertEqual(settings.topics, ("Cultura",))
        self.assertEqual(settings.sources[0].section, "Cultura")

    def test_renaming_updates_all_sources_without_changing_the_original(self):
        cooperativa = next(source for source in SOURCES if source.name == "Cooperativa")
        biobio_national = next(source for source in SOURCES if source.name == "BioBioChile" and not source.section)
        biobio_technology = next(source for source in SOURCES if source.name == "BioBioChile" and source.section == "Tecnología")
        original = Settings(sources=(cooperativa, replace(biobio_national, enabled=False), biobio_technology))
        updated = rename_topic(original, "Nacionales", "Actualidad")
        self.assertNotIn("Nacionales", updated.topics)
        by_url = {source.url: source for source in updated.sources}
        self.assertEqual(by_url[cooperativa.url].section, "Actualidad")
        self.assertEqual(by_url[biobio_national.url].section, "Actualidad")
        self.assertEqual(by_url[cooperativa.url].feed_url, cooperativa.feed_url)
        self.assertFalse(by_url[biobio_national.url].enabled)
        self.assertEqual(original.sources[0].section, "")
        updated = rename_topic(updated, "Tecnología", "Innovación")
        self.assertEqual(next(source for source in updated.sources if source.url == biobio_technology.url).section, "Innovación")
        self.assertNotIn("Tecnología", updated.topics)
        with self.assertRaises(AppError):
            rename_topic(original, "Tecnología", "Cultura")

    def test_deleting_reassigns_sources_and_preserves_at_least_one_topic(self):
        original = Settings()
        with self.assertRaisesRegex(AppError, "reasignar"):
            remove_topic(original, "Tecnología")
        updated = remove_topic(original, "Tecnología", "Ciencia")
        self.assertNotIn("Tecnología", updated.topics)
        technology_urls = {source.url for source in original.sources if source.section == "Tecnología"}
        national_urls = {source.url for source in original.sources if not source.section}
        self.assertTrue(all(source_topic(source) == "Ciencia" for source in updated.sources if source.url in technology_urls))
        updated = remove_topic(updated, "Nacionales", "Cultura")
        self.assertTrue(all(source.section == "Cultura" for source in updated.sources if source.url in national_urls))
        unused = remove_topic(original, "Deportes")
        self.assertNotIn("Deportes", unused.topics)
        with self.assertRaisesRegex(AppError, "al menos un tema"):
            remove_topic(Settings(topics=("Arte",), sources=()), "Arte")

    def test_manager_saves_the_edited_catalog_along_with_source_assignments(self):
        app = NewspaperApp.__new__(NewspaperApp)
        app.root = Mock()
        app.busy = False
        app.settings = Settings()
        app.fields = {}
        app.sources_button = Mock()
        app.status = Mock()
        source = custom_source("Medio", "https://medio.example/deportes", "Fútbol chileno")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch("manana.gui.SourcesDialog") as dialog, patch("manana.gui.save_settings", side_effect=lambda settings: save_settings(settings, path)):
                app.manage_sources()
                self.assertEqual(dialog.call_args.kwargs["topics"], DEFAULT_TOPICS)
                self.assertFalse(path.exists())
                dialog.call_args.args[2]((source,), ("Fútbol chileno",))
            loaded = load_settings(path)
        self.assertEqual(loaded.topics, ("Fútbol chileno",))
        self.assertEqual(loaded.sources[0].section, "Fútbol chileno")


class TopicSelectionTests(unittest.TestCase):
    def articles(self):
        return [
            Article("Deportes", "Un torneo regional reúne a equipos de Chile", "https://medio.example/deportes", NOW, BODY, section="Fútbol chileno"),
            Article("Cultura", "Una exposición recorre el patrimonio de Chile", "https://medio.example/cultura", NOW, BODY, section="Arte local"),
            Article("Ciencia", "Chile presenta una propuesta de inteligencia artificial", "https://medio.example/ciencia", NOW, BODY, section="Innovación"),
        ]

    def test_model_schema_hints_and_output_respect_user_defined_topics(self):
        topics = ("Fútbol chileno", "Arte local", "Innovación")
        client = LMStudio(Settings(topics=topics, sources=()), session=Mock())
        response = {"selected": [{"id": index, "section": "Arte local"} for index in range(3)]}
        with patch.object(client, "generate_json", return_value=response) as request:
            selected = client.select_articles(self.articles(), 3)
        self.assertEqual([section for _, section in selected], list(topics))
        prompt, schema = request.call_args.args
        self.assertEqual(schema["properties"]["selected"]["items"]["properties"]["section"]["enum"], ["Arte local", "Fútbol chileno", "Innovación"])
        self.assertIn('"section_hint": "Fútbol chileno"', prompt)
        self.assertIn('"section_hint": "Innovación"', prompt)
        self.assertNotIn("Tecnología", [section for _, section in selected])

    def test_technology_reservation_keeps_its_custom_topic_and_exact_count(self):
        topics = ("Fútbol chileno", "Arte local", "Innovación")
        client = LMStudio(Settings(topics=topics, sources=()), session=Mock())
        articles = self.articles()
        extra = Article("Cultura", "Bibliotecas chilenas realizan una consulta a sus lectores", "https://medio.example/libros", NOW, BODY, section="Arte local")
        articles.insert(2, extra)
        response = {"selected": [{"id": index, "section": "Arte local"} for index in range(3)]}
        with patch.object(client, "generate_json", return_value=response):
            selected = client.select_articles(articles, 3)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({article.url for article, _ in selected}), 3)
        self.assertEqual(selected[-1], (articles[-1], "Innovación"))

    def test_removed_categories_are_rejected_in_the_model_response(self):
        client = LMStudio(Settings(topics=("Arte local",), sources=()), session=Mock())
        articles = [replace(article, section="") for article in self.articles()]
        response = {"selected": [{"id": index, "section": "Política"} for index in range(3)]}
        with patch.object(client, "generate_json", return_value=response) as request, self.assertRaises(AppError):
            client.select_articles(articles, 3)
        self.assertEqual(request.call_count, 2)

    def test_named_source_topics_keep_the_full_candidate_limit(self):
        source = custom_source("Deportes", "https://medio.example/deportes", "Fútbol chileno")
        titles = (
            "Colo Colo confirma su plantel para el torneo chileno",
            "El básquetbol regional prepara una competencia escolar",
            "Atletas nacionales entrenan para una nueva temporada",
            "Federación chilena publica el calendario de ciclismo",
            "La selección femenina de fútbol inicia sus prácticas",
        )
        urls = [f"https://medio.example/nota-{index}" for index in range(5)]
        pages = {source.url: "<main>" + "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, titles)) + "</main>"}
        for url, title in zip(urls, titles):
            data = {"@type": "NewsArticle", "headline": title, "articleBody": BODY, "datePublished": NOW.isoformat()}
            pages[url] = '<script type="application/ld+json">' + json.dumps(data) + "</script>"
        with patch("manana.news._download", side_effect=lambda session, url: pages[url].encode("utf-8")):
            articles, _ = collect_news(Settings(sources=(source,)), lambda _: None, Mock(), NOW)
        self.assertEqual(len(articles), 5)
        self.assertTrue(all(article.section == "Fútbol chileno" for article in articles))

    def test_custom_and_long_topic_labels_render_on_one_page(self):
        edition = demo_edition(7)
        for index, story in enumerate(edition["stories"]):
            story["section"] = "Fútbol chileno" if index == 0 else "W" * 40
            story["summary"] = " ".join(story["summary"].split()[:40]) + "."
        with tempfile.TemporaryDirectory() as directory:
            for paper in ("Carta", "A4"):
                path = Path(directory) / f"{paper}.pdf"
                render_edition(edition, path, paper)
                self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
                if shutil.which("pdfinfo"):
                    metadata = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
                    self.assertRegex(metadata, r"Pages:\s+1\b")
                if shutil.which("pdftotext"):
                    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
                    self.assertIn("FÚTBOL CHILENO", text)
                    self.assertIn("7 NOTICIAS", text)


if __name__ == "__main__":
    unittest.main()
