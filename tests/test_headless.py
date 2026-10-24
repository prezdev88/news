from __future__ import annotations

import copy
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from manana.__main__ import main
from manana.config import AppError, ROOT, Settings, load_settings, save_settings
from manana.ollama import Ollama
from manana.newspaper import LayoutOverflowError
from manana.pipeline import generate
from test_app import BODY, FakeModelSession, FakeResponse, SUMMARY, fixture_articles


def native_response(content, reason="stop"):
    return FakeResponse({
        "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
        "done": True,
        "done_reason": reason,
    })


class FakeOllamaSession(FakeModelSession):
    def request(self, method, url, **kwargs):
        if method == "GET":
            self.calls.append((method, url, copy.deepcopy(kwargs)))
            return FakeResponse({"models": [{"name": "qwen3:4b"}]})
        response = super().request(method, url, **kwargs)
        message = response.payload["choices"][0]["message"]
        return FakeResponse({"message": message, "done": True, "done_reason": "stop"})


class HeadlessGenerationTests(unittest.TestCase):
    def test_alpha_config_runs_seven_news_to_letter_pdf_without_gui_viewer_or_printer(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            data = json.loads((ROOT / "config.example.json").read_text())
            # The same portable config must work outside the project directory.
            config_path.write_text(json.dumps(data))
            session = FakeOllamaSession()
            client = lambda settings, **kwargs: Ollama(settings, session=session, **kwargs)
            with patch("sys.argv", ["manana", "--config", str(config_path)]), \
                    patch("manana.pipeline.create_model_client", side_effect=client), \
                    patch("manana.pipeline.collect_news", return_value=(fixture_articles(), [])), \
                    patch("manana.__main__.open_pdf") as viewer, \
                    patch("manana.__main__.print_pdf") as printer, \
                    patch("manana.__main__.perf_counter", side_effect=[100.0, 3793.9]), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(), 0)
            self.assertIn("PDF listo:", output.getvalue())
            self.assertEqual(output.getvalue().splitlines()[-1], "Tiempo total de ejecución: 01:01:33 (hh:mm:ss)")
            viewer.assert_not_called()
            printer.assert_not_called()
            files = [path for path in (Path(directory) / "output").iterdir() if path.is_file()]
            self.assertEqual(len(files), 1)
            self.assertFalse((Path(directory) / "output/.cache/summaries.json").exists())
            pdf = files[0]
            self.assertEqual(pdf.suffix, ".pdf")
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
            self.assertEqual(len(session.calls), 9)  # one discovery, one selection, seven summaries
            payloads = [call[2]["json"] for call in session.calls[1:]]
            self.assertTrue(all(call[1] == "http://ollama:11434/api/chat" for call in session.calls[1:]))
            self.assertTrue(all(payload["think"] is False for payload in payloads))
            self.assertTrue(all(payload["options"]["num_ctx"] == 16384 for payload in payloads))
            self.assertIn("entre 45 y 60 palabras", payloads[1]["messages"][-1]["content"])
            self.assertIn("entre 25 y 35 palabras", payloads[2]["messages"][-1]["content"])
            self.assertEqual(payloads[0]["format"]["properties"]["selected"]["minItems"], 7)
            if shutil.which("pdfinfo"):
                info = subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout
                self.assertRegex(info, r"Pages:\s+1\b")
                self.assertIn("612 x 792 pts (letter)", info)
            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
                self.assertIn("7 NOTICIAS", text)

    def test_config_edits_are_reloaded_and_paths_follow_the_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            data = json.loads((ROOT / "config.example.json").read_text())
            data.update(model="qwen3:1.7b", article_count=3, lookback_hours=48, output_dir="ediciones")
            data["model_options"]["temperature"] = 0.1
            path.write_text(json.dumps(data))
            first = load_settings(path)
            self.assertEqual((first.model, first.article_count, first.lookback_hours), ("qwen3:1.7b", 3, 48))
            self.assertEqual(first.output_dir, str(Path(directory) / "ediciones"))
            save_settings(first, path)
            second = load_settings(path)
            self.assertEqual(second.sources, first.sources)
            self.assertEqual(second.topics, first.topics)
            self.assertEqual(second.model_options["temperature"], 0.1)
            self.assertFalse(second.print_after_generation)

    def test_compact_edition_does_not_repeat_all_requests_if_it_still_overflows(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                provider="ollama", base_url="http://ollama:11434", model="qwen3:4b",
                output_dir=directory, compact_summaries=True,
            )
            session = FakeOllamaSession()
            client = lambda current, **kwargs: Ollama(current, session=session, **kwargs)
            with patch("manana.pipeline.create_model_client", side_effect=client), \
                    patch("manana.pipeline.collect_news", return_value=(fixture_articles(), [])), \
                    patch("manana.pipeline.render_edition", side_effect=LayoutOverflowError("No caben las siete noticias")), \
                    self.assertRaisesRegex(LayoutOverflowError, "siete noticias"):
                generate(settings, lambda _: None)
            self.assertEqual(len([call for call in session.calls if call[0] == "POST"]), 8)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_43_word_second_story_is_shortened_and_the_seven_story_pdf_finishes(self):
        class LongSecondSummary(FakeOllamaSession):
            summaries = 0

            def request(self, method, url, **kwargs):
                prompt = kwargs.get("json", {}).get("messages", [{}])[-1].get("content", "")
                if prompt.startswith("Acorta únicamente"):
                    self.calls.append((method, url, copy.deepcopy(kwargs)))
                    return native_response({"summary": " ".join(BODY.split()[:30]) + "."})
                response = super().request(method, url, **kwargs)
                if prompt.startswith("Redacta una noticia"):
                    self.summaries += 1
                    if self.summaries == 2:
                        draft = json.loads(response.payload["message"]["content"])
                        draft["summary"] = " ".join(BODY.split()[:43]) + "."
                        return native_response(draft)
                return response

        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(ROOT / "config.example.json")
            settings.output_dir = directory
            session = LongSecondSummary()
            client = lambda current, **kwargs: Ollama(current, session=session, **kwargs)
            messages = []
            with patch("manana.pipeline.create_model_client", side_effect=client), \
                    patch("manana.pipeline.collect_news", return_value=(fixture_articles(), [])):
                pdf = generate(settings, messages.append)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
            self.assertEqual(list(Path(directory).glob("*.pdf")), [pdf])
            self.assertFalse((Path(directory) / settings.summary_cache_file).exists())
            self.assertEqual(session.summaries, 7)
            self.assertEqual(len([call for call in session.calls if call[0] == "POST"]), 9)
            self.assertTrue(any("43 palabras" in message for message in messages))
            self.assertIn("7 de 7 noticias", messages[-1])

    def test_check_config_needs_neither_display_nor_model_server(self):
        with patch("sys.argv", ["manana", "--config", str(ROOT / "config.example.json"), "--check-config"]), \
                patch("manana.__main__.generate") as generate, \
                patch("manana.__main__.create_model_client") as client, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 0)
        generate.assert_not_called()
        client.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["provider"], "ollama")

    def test_invalid_ollama_options_fail_before_generation(self):
        for change in (
            {"model_options": {"num_ctx": 0}},
            {"model_options": {"temperature": "high"}},
            {"model_options": {"num_predict": -1}},
            {"model_options": {"temperature": float("nan")}},
            {"base_url": "http://ollama:11434/v1"},
            {"think": 0},
            {"cache_summaries": "true"},
            {"summary_cache_file": ""},
            {"print_after_generation": "false"},
            {"download_timeout_seconds": 0},
            {"summary_lengths": {}},
        ):
            with self.subTest(change=change), self.assertRaises(AppError):
                values = dict(provider="ollama", base_url="http://ollama:11434", model="qwen3:4b")
                Settings(**(values | change)).validate()

    def test_legacy_config_never_silently_selects_lm_studio_in_headless_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            data = {"base_url": "http://localhost:1234/v1", "model": "google/gemma-4-e4b"}
            path.write_text(json.dumps(data))
            with patch("sys.argv", ["manana", "--config", str(path)]), \
                    patch("manana.__main__.generate") as generate, \
                    patch("sys.stderr", new_callable=io.StringIO) as error:
                self.assertEqual(main(), 1)
            generate.assert_not_called()
            self.assertIn("no indica provider", error.getvalue())
            self.assertIn("http://ollama:11434", error.getvalue())
            # The optional desktop interface can still open old preferences.
            self.assertEqual(load_settings(path).provider, "lmstudio")


class OllamaTests(unittest.TestCase):
    def settings(self, **kwargs):
        return Settings(provider="ollama", base_url="http://ollama:11434", model="qwen3:4b", **kwargs)

    def test_missing_model_downloads_the_configured_name_once(self):
        session = FakeModelSession([
            FakeResponse({"models": []}), FakeResponse({"status": "success"}),
            FakeResponse({"models": [{"name": "qwen3:4b"}]}),
        ])
        client = Ollama(self.settings(auto_pull_model=True), session=session)
        self.assertEqual(client.select_model(), "qwen3:4b")
        self.assertEqual(client.select_model(), "qwen3:4b")
        downloads = [call for call in session.calls if call[0] == "POST"]
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0][1], "http://ollama:11434/api/pull")
        self.assertEqual(downloads[0][2]["json"], {"model": "qwen3:4b", "stream": False})

    def test_missing_model_is_not_replaced_or_downloaded_when_disabled(self):
        session = FakeModelSession([FakeResponse({"models": [{"name": "another:latest"}]})])
        with self.assertRaisesRegex(AppError, "auto_pull_model"):
            Ollama(self.settings(auto_pull_model=False), session=session).select_model()
        self.assertEqual(len(session.calls), 1)

    def test_native_controls_and_truncation_retry_use_configured_budgets(self):
        session = FakeModelSession([
            FakeResponse({"done": True, "done_reason": "length", "message": {"content": '{"ok":'}}),
            native_response({"ok": True}),
        ])
        options = {"temperature": 0.1, "num_ctx": 8192, "num_thread": 2, "num_gpu": 0, "seed": 123}
        settings = self.settings(model_options=options, max_output_tokens=1024, max_retry_output_tokens=2048, keep_alive="2m", system_prompt="Editor de pruebas")
        client = Ollama(settings, session=session)
        self.assertEqual(client.generate_json("test", {"type": "object"}), {"ok": True})
        first, second = [call[2]["json"] for call in session.calls]
        self.assertEqual(first["options"], options | {"num_predict": 1024})
        self.assertEqual(second["options"], options | {"num_predict": 2048})
        self.assertFalse(first["think"])
        self.assertFalse(first["stream"])
        self.assertEqual(first["keep_alive"], "2m")
        self.assertEqual(first["messages"][0]["content"], "Editor de pruebas")
        self.assertNotIn("reasoning_effort", first)

    def test_unfinished_native_response_is_rejected(self):
        session = FakeModelSession([FakeResponse({"done": False, "message": {"content": "{}"}})])
        with self.assertRaisesRegex(AppError, "incompleta"):
            Ollama(self.settings(), session=session).generate_json("test", {})

    def test_summary_headline_bound_reaches_ollama_and_remains_locally_validated(self):
        article = fixture_articles(1)[0]
        valid = {"headline": "Comunidades participan en una consulta regional", "summary": SUMMARY}
        session = FakeModelSession([native_response(valid)])
        client = Ollama(self.settings(), session=session)
        result = client.summarize(article, "Regiones", True)
        self.assertEqual(result["headline"], valid["headline"])
        payload = session.calls[0][2]["json"]
        self.assertEqual(payload["format"]["properties"]["headline"]["maxLength"], 75)
        self.assertEqual(payload["format"]["properties"]["headline"]["minLength"], 12)
        self.assertIn('"maxLength": 75', payload["messages"][-1]["content"])
        self.assertIn("FIN DEL ARTÍCULO.", payload["messages"][-1]["content"])

        invalid = valid | {"headline": "Un titular que supera el margen. " * 4}
        session = FakeModelSession([native_response(invalid), native_response(invalid)])
        with self.assertRaisesRegex(AppError, "El titular tiene"):
            Ollama(self.settings(), session=session).summarize(article, "Regiones", True)
        correction = session.calls[1][2]["json"]["messages"][-1]["content"]
        self.assertLess(correction.index("FIN DEL ARTÍCULO."), correction.index("CORRECCIÓN NECESARIA"))

    def test_compact_word_limit_is_in_the_first_native_request(self):
        article = fixture_articles(1)[0]
        draft = {"headline": "Comunidades participan en una consulta regional", "summary": " ".join(SUMMARY.split()[:30]) + "."}
        session = FakeModelSession([native_response(draft)])
        Ollama(self.settings(), session=session).summarize(article, "Regiones", False, compact=True)
        schema = session.calls[0][2]["json"]["format"]
        pattern = schema["properties"]["summary"]["pattern"]
        for count in (25, 30, 35):
            with self.subTest(count=count):
                self.assertIsNotNone(re.fullmatch(pattern, " ".join(["información"] * count) + "."))
        for count in (20, 24, 36, 40, 43):
            with self.subTest(count=count):
                self.assertIsNone(re.fullmatch(pattern, " ".join(["información"] * count) + "."))
        self.assertEqual(schema["properties"]["headline"]["maxLength"], 65)
        prompt = session.calls[0][2]["json"]["messages"][-1]["content"]
        self.assertIn("entre 25 y 35 palabras", prompt)
        self.assertIn('"pattern"', prompt)

    def test_word_boundaries_keep_accents_and_quotes_without_hidden_extra_words(self):
        article = fixture_articles(1)[0]
        draft = {"headline": "Comunidades participan en una consulta regional", "summary": SUMMARY}
        session = FakeModelSession([native_response(draft)])
        Ollama(self.settings(), session=session).summarize(article, "Regiones", False, compact=True)
        pattern = session.calls[0][2]["json"]["format"]["properties"]["summary"]["pattern"]
        words = ["Según", "Núñez,", "«la", "propuesta»"] + ["información"] * 21
        self.assertIsNotNone(re.fullmatch(pattern, " ".join(words) + "."))
        for separator in ("\n", "\t", "\u00a0", "\u2003", "\u202f", "\u3000"):
            with self.subTest(separator=repr(separator)):
                self.assertIsNone(re.fullmatch(pattern, separator.join(words) + "."))
        self.assertIsNone(re.fullmatch(pattern, " ".join(words)))

    def test_43_word_summary_is_rewritten_alone_and_keeps_the_valid_headline(self):
        original = fixture_articles(1)[0]
        article = replace(original, body=original.body + " ANTECEDENTE_EXCLUSIVO_DEL_ARTICULO.")
        headline = "Justicia revisa la tramitación de rebajas de condena"
        long_summary = " ".join(["antecedentes"] * 43) + "."
        short_summary = " ".join(["antecedentes"] * 30) + "."
        session = FakeModelSession([
            native_response({"headline": headline, "summary": long_summary}),
            native_response({"summary": short_summary}),
        ])
        result = Ollama(self.settings(), session=session).summarize(article, "Política", False, compact=True)
        self.assertEqual(result["headline"], headline)
        self.assertEqual(result["summary"], short_summary)
        self.assertEqual(len(session.calls), 2)
        payload = session.calls[1][2]["json"]
        self.assertEqual(set(payload["format"]["properties"]), {"summary"})
        correction = payload["messages"][-1]["content"]
        self.assertIn("43 palabras", correction)
        self.assertIn(long_summary, correction)
        self.assertNotIn("ANTECEDENTE_EXCLUSIVO_DEL_ARTICULO", correction)

    def test_shortening_keeps_the_original_numeric_claim_guard(self):
        article = fixture_articles(1)[0]
        long_summary = " ".join(["antecedentes"] * 43) + "."
        invalid = "La autoridad confirmó 987 casos " + " ".join(["antecedentes"] * 25) + "."
        session = FakeModelSession([
            native_response({"headline": "Comunidades participan en una consulta regional", "summary": long_summary}),
            native_response({"summary": invalid}),
        ])
        with self.assertRaisesRegex(AppError, "987"):
            Ollama(self.settings(), session=session).summarize(article, "Regiones", False, compact=True)

    def test_rejected_numeric_claim_is_corrected_without_digits_in_the_schema(self):
        article = fixture_articles(1)[0]
        headline = "Comunidades participan en una consulta regional"
        valid_summary = " ".join(BODY.split()[:30]) + "."
        invalid_summary = "La autoridad confirmó 987 casos " + " ".join(["antecedentes"] * 25) + "."
        session = FakeModelSession([
            native_response({"headline": headline, "summary": invalid_summary}),
            native_response({"headline": headline, "summary": valid_summary}),
        ])
        result = Ollama(self.settings(), session=session).summarize(article, "Regiones", False, compact=True)
        self.assertEqual(result["summary"], valid_summary)
        initial_prompt = session.calls[0][2]["json"]["messages"][-1]["content"]
        self.assertIn("CIFRAS EN DÍGITOS PRESENTES EN LA FUENTE", initial_prompt)
        correction = session.calls[1][2]["json"]
        self.assertIn("sin cantidades", correction["messages"][-1]["content"])
        self.assertIn("No sustituyas", correction["messages"][-1]["content"])
        properties = correction["format"]["properties"]
        self.assertIsNotNone(re.fullmatch(properties["summary"]["pattern"], valid_summary))
        self.assertIsNone(re.fullmatch(properties["summary"]["pattern"], invalid_summary))
        self.assertIsNone(re.fullmatch(properties["headline"]["pattern"], headline + " 987"))

    def test_numeric_correction_is_validated_when_server_ignores_the_no_digits_schema(self):
        article = replace(fixture_articles(1)[0], body=BODY + " La consulta contó con 13 comunidades.")
        headline = "Comunidades participan en una consulta regional"
        session = FakeModelSession([
            native_response({"headline": headline, "summary": "La autoridad confirmó 987 casos " + " ".join(["antecedentes"] * 25) + "."}),
            native_response({"headline": headline, "summary": "La autoridad confirmó 13 casos " + " ".join(["antecedentes"] * 25) + "."}),
        ])
        with self.assertRaisesRegex(AppError, "sin cantidades"):
            Ollama(self.settings(), session=session).summarize(article, "Regiones", False, compact=True)

    def test_custom_lengths_control_the_prompt_and_the_schema(self):
        lengths = self.settings().summary_lengths
        lengths["compact"] = {"lead_words": [40, 50], "body_words": [20, 28], "headline_chars": 55}
        draft = {"headline": "Comunidades participan en una consulta regional", "summary": " ".join(["antecedentes"] * 24) + "."}
        session = FakeModelSession([native_response(draft)])
        Ollama(self.settings(summary_lengths=lengths), session=session).summarize(fixture_articles(1)[0], "Regiones", False, compact=True)
        payload = session.calls[0][2]["json"]
        self.assertIn("entre 20 y 28 palabras", payload["messages"][-1]["content"])
        self.assertEqual(payload["format"]["properties"]["headline"]["maxLength"], 55)
        pattern = payload["format"]["properties"]["summary"]["pattern"]
        self.assertIsNotNone(re.fullmatch(pattern, " ".join(["texto"] * 28) + "."))
        self.assertIsNone(re.fullmatch(pattern, " ".join(["texto"] * 29) + "."))


if __name__ == "__main__":
    unittest.main()
