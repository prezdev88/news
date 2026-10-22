from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manana.__main__ import main
from manana.config import AppError, Settings
from manana.printing import PrintJob, list_printers, monochrome_driver_options, print_pdf


def response(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class PrintingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "la mañana; prueba.pdf"
        self.path.write_bytes(b"%PDF-1.7\nfixture\n")

    def test_letter_is_the_default_and_the_english_alias_is_accepted(self):
        self.assertEqual(Settings().paper, "Carta")
        settings = Settings(paper="Letter")
        settings.validate()
        self.assertEqual(settings.paper, "Carta")

    def test_one_copy_letter_monochrome_no_banner_and_canon_grayscale(self):
        options = "CNGrayscale/Grayscale Printing: *False True\nPageSize/Page Size: *A4 Letter\n"
        with patch("manana.printing.subprocess.run", side_effect=[response(options), response("request id is Canon_G2100-42 (1 file(s))\n")]) as run:
            job = print_pdf(self.path, printer="Canon_G2100")
        command = run.call_args_list[-1].args[0]
        self.assertEqual(command[:3], ["lp", "-d", "Canon_G2100"])
        for option in ("media=Letter", "print-color-mode=monochrome", "CNGrayscale=True", "sides=one-sided", "number-up=1", "job-sheets=none", "fit-to-page"):
            self.assertIn(option, command)
        self.assertEqual(command[command.index("-n") + 1], "1")
        self.assertEqual(command[command.index("-P") + 1], "1")
        self.assertEqual(command[-2:], ["--", str(self.path)])
        self.assertEqual(job.job_id, "Canon_G2100-42")
        self.assertEqual(job.paper, "Carta")
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_a4_is_available_when_explicitly_chosen(self):
        with patch("manana.printing.subprocess.run", side_effect=[response(), response("request id is Printer-1")]) as run:
            print_pdf(self.path, printer="Printer", paper="A4")
        self.assertIn("media=A4", run.call_args.args[0])

    def test_default_printer_is_used_without_guessing_among_multiple_devices(self):
        results = [response("Other\nCanon_G2100\n"), response("system default destination: Canon_G2100\n"), response(), response("request id is Canon_G2100-2")]
        with patch("manana.printing.subprocess.run", side_effect=results):
            job = print_pdf(self.path)
        self.assertEqual(job.printer, "Canon_G2100")
        with patch("manana.printing.subprocess.run", side_effect=[response("First\nSecond\n"), response("no system default destination", returncode=1)]) as run:
            with self.assertRaisesRegex(AppError, "Selecciona una"):
                print_pdf(self.path)
        self.assertTrue(all(call.args[0][0] != "lp" for call in run.call_args_list))

    def test_only_available_printer_can_be_used_without_a_system_default(self):
        with patch("manana.printing.subprocess.run", side_effect=[response("Canon_G2100\n"), response("no system default destination", returncode=1)]):
            printers = list_printers()
        self.assertEqual(printers.names, ("Canon_G2100",))
        self.assertEqual(printers.default, "Canon_G2100")

    def test_driverless_printer_still_receives_standard_monochrome_option(self):
        with patch("manana.printing.subprocess.run", side_effect=[response(stderr="No PPD", returncode=1), response("request id is Office-3")]) as run:
            print_pdf(self.path, printer="Office")
        self.assertIn("print-color-mode=monochrome", run.call_args.args[0])

    def test_driver_option_is_only_selected_when_advertised(self):
        self.assertEqual(monochrome_driver_options("ColorModel/Color Mode: *RGB Gray CMYK"), ["-o", "ColorModel=Gray"])
        self.assertEqual(monochrome_driver_options("CNGrayscale/Grayscale Printing: *false true"), ["-o", "CNGrayscale=true"])
        self.assertEqual(monochrome_driver_options("ColorModel/Color Mode: *RGB CMYK"), [])

    def test_failed_print_submission_is_not_retried(self):
        with patch("manana.printing.subprocess.run", side_effect=[response(), response(stderr="Printer unavailable", returncode=1)]) as run:
            with self.assertRaisesRegex(AppError, "No se pudo enviar"):
                print_pdf(self.path, printer="Office")
        self.assertEqual(sum(call.args[0][0] == "lp" for call in run.call_args_list), 1)

    def test_missing_or_invalid_pdf_never_submits_a_job(self):
        with patch("manana.printing.subprocess.run") as run:
            with self.assertRaisesRegex(AppError, "ya no existe"):
                print_pdf(self.path.with_name("missing.pdf"), printer="Office")
            self.path.write_text("not a PDF")
            with self.assertRaisesRegex(AppError, "PDF válido"):
                print_pdf(self.path, printer="Office")
        run.assert_not_called()

    def test_missing_cups_and_empty_printer_list_have_clear_errors(self):
        with patch("manana.printing.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(AppError, "CUPS"):
                list_printers()
        with patch("manana.printing.subprocess.run", return_value=response()):
            with self.assertRaisesRegex(AppError, "No hay impresoras"):
                list_printers()

    def test_cli_prints_a_saved_pdf_without_contacting_lm_studio(self):
        with patch("sys.argv", ["manana", "--print-file", str(self.path)]), patch("manana.__main__.load_settings", return_value=Settings(printer="Office")), patch("manana.__main__.print_pdf", return_value=PrintJob("Office", "Carta", "Office-1")) as printer, patch("manana.__main__.generate") as generate, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(), 0)
        printer.assert_called_once_with(self.path, printer="Office", paper="Carta")
        generate.assert_not_called()

    def test_normal_generation_does_not_print_implicitly(self):
        with patch("sys.argv", ["manana", "--no-open"]), patch("manana.__main__.load_settings", return_value=Settings()), patch("manana.__main__.generate", return_value=self.path), patch("manana.__main__.print_pdf") as printer:
            self.assertEqual(main(), 0)
        printer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
