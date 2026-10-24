from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from manana.config import AppError, ROOT, Settings, load_settings
from manana.ollama import Ollama
from manana.pipeline import generate
from manana.summary_cache import SummaryCache
from test_app import BODY, fixture_articles
from test_headless import FakeOllamaSession, native_response


class SummaryCacheTests(unittest.TestCase):
    def test_failed_seventh_story_resumes_six_then_success_clears_the_cache(self):
        articles = fixture_articles()

        class RejectSeventh(FakeOllamaSession):
            def request(self, method, url, **kwargs):
                prompt = kwargs.get("json", {}).get("messages", [{}])[-1].get("content", "")
                if prompt.startswith("Redacta una noticia") and articles[-1].title in prompt:
                    self.calls.append((method, url, copy.deepcopy(kwargs)))
                    return native_response({
                        "headline": "Comunidades participan en una consulta regional",
                        "summary": "La autoridad confirmó 987 casos " + " ".join(["antecedentes"] * 25) + ".",
                    })
                return super().request(method, url, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(ROOT / "config.example.json")
            settings.output_dir = directory
            cache_file = Path(directory) / settings.summary_cache_file
            failing_session = RejectSeventh()
            failing_factory = lambda current, **kwargs: Ollama(current, session=failing_session, **kwargs)
            with patch("manana.pipeline.collect_news", return_value=(articles, [])), \
                    patch("manana.pipeline.create_model_client", side_effect=failing_factory), \
                    self.assertRaisesRegex(AppError, "987"):
                generate(settings, lambda _: None)
            saved = json.loads(cache_file.read_text())
            self.assertEqual(len(saved["entries"]), 6)
            self.assertEqual(list(Path(directory).glob("*.pdf")), [])

            session = FakeOllamaSession()
            factory = lambda current, **kwargs: Ollama(current, session=session, **kwargs)
            messages = []
            with patch("manana.pipeline.collect_news", return_value=(articles, [])), \
                    patch("manana.pipeline.create_model_client", side_effect=factory):
                pdf = generate(settings, messages.append)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
            self.assertEqual(len([call for call in session.calls if call[0] == "POST"]), 2)
            self.assertEqual(sum(message.startswith("Reutilizando resumen guardado:") for message in messages), 6)
            self.assertFalse(cache_file.exists())
            self.assertIn("PDF generado; resúmenes temporales eliminados.", messages)

            # A successful edition must not cause the next PDF to reuse summaries.
            fresh_session = FakeOllamaSession()
            factory = lambda current, **kwargs: Ollama(current, session=fresh_session, **kwargs)
            with patch("manana.pipeline.collect_news", return_value=(articles, [])), \
                    patch("manana.pipeline.create_model_client", side_effect=factory):
                generate(settings, lambda _: None)
            self.assertEqual(len([call for call in fresh_session.calls if call[0] == "POST"]), 8)
            self.assertFalse(cache_file.exists())

    def test_reuse_requires_matching_article_model_parameters_and_editorial_profile(self):
        article = fixture_articles(1)[0]
        summary = {"headline": article.title, "summary": " ".join(BODY.split()[:30]) + ".", "section": "Regiones"}
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            with SummaryCache(settings, lambda _: None) as cache:
                key = cache.key(article, "Regiones", lead=False, compact=True)
                cache.save(key, summary)
            with SummaryCache(settings, lambda _: None) as cache:
                self.assertEqual(cache.get(key), summary)
                for changed in (replace(article, body=article.body + " Nueva información."), replace(article, title="Una noticia actualizada para la región"), replace(article, url=article.url + "/nuevo"), replace(article, published=article.published.replace(day=23))):
                    self.assertIsNone(cache.get(cache.key(changed, "Regiones", lead=False, compact=True)))
                for options in ({"lead": True, "compact": True}, {"lead": False, "compact": False}):
                    self.assertIsNone(cache.get(cache.key(article, "Regiones", **options)))
                self.assertIsNone(cache.get(cache.key(article, "Política", lead=False, compact=True)))
            for changes in ({"model": "otro-modelo"}, {"model_options": {"temperature": 0.2}}, {"system_prompt": "Otro criterio editorial"}, {"summary_lengths": settings.summary_lengths | {"compact": {"lead_words": [35, 45], "body_words": [20, 25], "headline_chars": 55}}}):
                with self.subTest(changes=changes), SummaryCache(replace(settings, **changes), lambda _: None) as cache:
                    self.assertIsNone(cache.get(cache.key(article, "Regiones", lead=False, compact=True)))

    def test_interrupt_preserves_progress_and_releases_the_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            summary = {"headline": "Un titular validado", "summary": "Un resumen validado.", "section": "Regiones"}
            with self.assertRaises(KeyboardInterrupt):
                with SummaryCache(settings, lambda _: None) as cache:
                    cache.save("saved", summary)
                    raise KeyboardInterrupt()
            with SummaryCache(settings, lambda _: None) as cache:
                self.assertEqual(cache.get("saved"), summary)

    def test_failed_atomic_save_keeps_previously_saved_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            summary = {"headline": "Un titular validado", "summary": "Un resumen validado.", "section": "Regiones"}
            with SummaryCache(settings, lambda _: None) as cache:
                cache.save("first", summary)
                with patch("manana.summary_cache.Path.replace", side_effect=OSError("disco lleno")), self.assertRaisesRegex(AppError, "guardados anteriormente"):
                    cache.save("second", summary)
            with SummaryCache(settings, lambda _: None) as cache:
                self.assertEqual(cache.get("first"), summary)
                self.assertIsNone(cache.get("second"))
                self.assertEqual(list(cache.path.parent.glob("*.tmp")), [])

    def test_damaged_entry_is_not_reused_and_other_entries_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            summary = {"headline": "Un titular validado", "summary": "Un resumen validado.", "section": "Regiones"}
            with SummaryCache(settings, lambda _: None) as cache:
                cache.save("good", summary)
                cache.save("damaged", summary)
                path = cache.path
            data = json.loads(path.read_text())
            data["entries"]["damaged"]["summary"]["summary"] = "Una cifra inventada: 987."
            path.write_text(json.dumps(data))
            with SummaryCache(settings, lambda _: None) as cache:
                self.assertEqual(cache.get("good"), summary)
                self.assertIsNone(cache.get("damaged"))

    def test_overlapping_generation_cannot_clear_another_process_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            with SummaryCache(settings, lambda _: None):
                with self.assertRaisesRegex(AppError, "Ya hay una generación"):
                    with SummaryCache(settings, lambda _: None):
                        self.fail("A second generation acquired the same cache")

    def test_unreadable_json_is_replaced_with_new_validated_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=True)
            path = Path(directory) / settings.summary_cache_file
            path.parent.mkdir(parents=True)
            path.write_text('{"version": 1, "entries":')
            summary = {"headline": "Un titular validado", "summary": "Un resumen validado.", "section": "Regiones"}
            messages = []
            with SummaryCache(settings, messages.append) as cache:
                self.assertIsNone(cache.get("saved"))
                cache.save("saved", summary)
            with SummaryCache(settings, lambda _: None) as cache:
                self.assertEqual(cache.get("saved"), summary)
            self.assertTrue(any("no se pueden leer" in message for message in messages))

    def test_layout_failure_keeps_all_validated_summaries_for_render_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(ROOT / "config.example.json")
            settings.output_dir = directory
            session = FakeOllamaSession()
            factory = lambda current, **kwargs: Ollama(current, session=session, **kwargs)
            with patch("manana.pipeline.collect_news", return_value=(fixture_articles(), [])), \
                    patch("manana.pipeline.create_model_client", side_effect=factory), \
                    patch("manana.pipeline.render_edition", side_effect=AppError("Fallo de maquetación")), \
                    self.assertRaisesRegex(AppError, "maquetación"):
                generate(settings, lambda _: None)
            path = Path(directory) / settings.summary_cache_file
            self.assertEqual(len(json.loads(path.read_text())["entries"]), 7)
            retry = FakeOllamaSession()
            factory = lambda current, **kwargs: Ollama(current, session=retry, **kwargs)
            with patch("manana.pipeline.collect_news", return_value=(fixture_articles(), [])), \
                    patch("manana.pipeline.create_model_client", side_effect=factory):
                generate(settings, lambda _: None)
            self.assertEqual(len([call for call in retry.calls if call[0] == "POST"]), 1)
            self.assertFalse(path.exists())

    def test_disabling_cache_does_not_create_or_remove_files(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory, cache_summaries=False)
            with SummaryCache(settings, lambda _: None) as cache:
                cache.save("entry", {})
                self.assertIsNone(cache.get("entry"))
                cache.clear()
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
