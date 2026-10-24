from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import cairo

from manana.config import ROOT, load_settings
from manana.newspaper import SIZES, Typesetter, render_edition
from manana.pipeline import demo_edition, generate
from manana.summary_cache import SummaryCache


def dense_edition(count=7):
    edition = demo_edition(count)
    body = (
        "Las autoridades correspondientes informaron sobre los antecedentes disponibles y explicaron las "
        "consecuencias institucionales de los acontecimientos recientes. Las organizaciones involucradas "
        "solicitaron mayores precisiones respecto de las responsabilidades y señalaron que mantendrán "
        "informadas a las comunidades mientras continúan las investigaciones pertinentes."
    )
    headline = "Ministerio de Justicia suspende tramitación de rebajas de condena"
    for index, story in enumerate(edition["stories"]):
        story.update(
            headline=headline,
            summary=" ".join((body + " " + body).split()[:60 if index == 0 else 40]) + ".",
            section="Nacionales",
        )
    return edition


class LayoutTests(unittest.TestCase):
    def test_dense_seven_story_edition_fits_letter_and_a4_at_readable_sizes(self):
        original_draw = Typesetter.draw_story
        with tempfile.TemporaryDirectory() as directory:
            for count in (6, 7):
                for paper, (width, height) in SIZES.items():
                    with self.subTest(paper=paper, count=count):
                        edition = dense_edition(count)
                        before = [(story["headline"], story["summary"]) for story in edition["stories"]]
                        boxes = []

                        def draw(typesetter, story, x, top, column_width, style):
                            boxes.append((story, x, top, column_width, top + typesetter.story_size(story, column_width, style), style.body_size))
                            return original_draw(typesetter, story, x, top, column_width, style)

                        path = Path(directory) / f"{paper}-{count}.pdf"
                        with patch.object(Typesetter, "draw_story", new=draw):
                            render_edition(edition, path, paper)
                        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
                        self.assertTrue(path.with_suffix(".png").exists())
                        self.assertEqual([(story["headline"], story["summary"]) for story in edition["stories"]], before)
                        # Preflight and final PDF must draw each story exactly once.
                        self.assertEqual(len(boxes), count * 2)
                        for _, x, top, column_width, bottom, body_size in boxes:
                            self.assertGreaterEqual(body_size, 9.8)
                            self.assertGreaterEqual(x, 32)
                            self.assertLessEqual(x + column_width, width - 32 + 0.001)
                            self.assertGreaterEqual(top, 132)
                            self.assertLessEqual(bottom, height - 52 - 15 + 0.001)
                        for first in range(count):
                            _, x, top, column_width, bottom, _ = boxes[first]
                            for _, other_x, other_top, other_width, other_bottom, _ in boxes[first + 1:count]:
                                overlap_x = min(x + column_width, other_x + other_width) - max(x, other_x)
                                overlap_y = min(bottom, other_bottom) - max(top, other_top)
                                self.assertFalse(overlap_x > 0.001 and overlap_y > 0.001)
                        if shutil.which("pdfinfo"):
                            info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
                            self.assertRegex(info, r"Pages:\s+1\b")
                        if shutil.which("pdftotext"):
                            result = subprocess.run(["pdftotext", "-bbox", str(path), "-"], capture_output=True, text=True, check=True).stdout
                            root = ET.fromstring(result)
                            words = root.findall(".//{http://www.w3.org/1999/xhtml}word")
                            text = " ".join(word.text for word in words if word.text)
                            self.assertIn(f"{count} NOTICIAS", text)
                            self.assertEqual(text.count("Ministerio"), count)
                            self.assertEqual(text.count("Mañana"), 1)
                            for word in words:
                                self.assertGreaterEqual(float(word.attrib["xMin"]), 31)
                                self.assertLessEqual(float(word.attrib["xMax"]), width - 31)
                                self.assertLessEqual(float(word.attrib["yMax"]), height - 10)

    def test_font_widths_match_in_preflight_and_pdf_surfaces(self):
        recording = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, (0, 0, 612, 792))
        pdf = cairo.PDFSurface(io.BytesIO(), 612, 792)
        preview_typesetter = Typesetter(cairo.Context(recording))
        pdf_typesetter = Typesetter(cairo.Context(pdf))
        for size, family in ((20, "Liberation Serif"), (13.2, "Liberation Serif"), (9.8, "Liberation Serif"), (7.2, "DejaVu Sans")):
            for typesetter in (preview_typesetter, pdf_typesetter):
                typesetter.font(size, family)
            self.assertAlmostEqual(preview_typesetter.width("investigaciones institucionales"), pdf_typesetter.width("investigaciones institucionales"), places=6)
        pdf.finish()

    def test_pending_dense_summaries_render_without_model_rewrites_then_are_deleted(self):
        edition = dense_edition()
        articles = [story["article"] for story in edition["stories"]]
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(ROOT / "config.example.json")
            settings.output_dir = directory
            with SummaryCache(settings, lambda _: None) as cache:
                for index, story in enumerate(edition["stories"]):
                    key = cache.key(story["article"], story["section"], lead=index == 0, compact=True)
                    cache.save(key, {name: story[name] for name in ("headline", "summary", "section")})
                cache_file = cache.path
            client = Mock()
            client.select_model.return_value = settings.model
            client.select_articles.return_value = [(article, "Nacionales") for article in articles]
            client.summarize.side_effect = AssertionError("Cached summaries must not be generated again")
            messages = []
            with patch("manana.pipeline.create_model_client", return_value=client), \
                    patch("manana.pipeline.collect_news", return_value=(articles, [])):
                path = generate(settings, messages.append)
            self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
            client.summarize.assert_not_called()
            self.assertEqual(sum(message.startswith("Reutilizando resumen guardado:") for message in messages), 7)
            self.assertFalse(cache_file.exists())


if __name__ == "__main__":
    unittest.main()
