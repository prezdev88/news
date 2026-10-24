from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manana.__main__ import main
from manana.config import AppError, ROOT, Settings, load_settings, save_settings
from manana.ollama import Ollama
from manana.newspaper import LayoutOverflowError
from manana.pipeline import generate
from test_app import FakeModelSession, FakeResponse, SUMMARY, fixture_articles


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
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(), 0)
            viewer.assert_not_called()
            printer.assert_not_called()
            files = list((Path(directory) / "output").iterdir())
            self.assertEqual(len(files), 1)
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
            {"print_after_generation": "false"},
            {"download_timeout_seconds": 0},
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
        self.assertEqual(payload["format"]["properties"]["headline"]["maxLength"], 90)
        self.assertEqual(payload["format"]["properties"]["headline"]["minLength"], 12)
        self.assertIn('"maxLength": 90', payload["messages"][-1]["content"])
        self.assertIn("FIN DEL ARTÍCULO.", payload["messages"][-1]["content"])

        invalid = valid | {"headline": "Un titular que supera el margen. " * 4}
        session = FakeModelSession([native_response(invalid), native_response(invalid)])
        with self.assertRaisesRegex(AppError, "El titular tiene"):
            Ollama(self.settings(), session=session).summarize(article, "Regiones", True)
        correction = session.calls[1][2]["json"]["messages"][-1]["content"]
        self.assertLess(correction.index("FIN DEL ARTÍCULO."), correction.index("CORRECCIÓN NECESARIA"))


if __name__ == "__main__":
    unittest.main()
