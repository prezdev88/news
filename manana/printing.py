from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import AppError
from .sorting import alphabetical_key


@dataclass(frozen=True)
class PrinterList:
    names: tuple[str, ...]
    default: str = ""


@dataclass(frozen=True)
class PrintJob:
    printer: str
    paper: str
    job_id: str

    @property
    def message(self) -> str:
        reference = f" · {self.job_id}" if self.job_id else ""
        return f"Enviado a la cola de {self.printer} · {self.paper} · blanco y negro · 1 copia{reference}"


def _run(command: list[str], timeout: int = 10):
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        raise AppError("Faltan las herramientas de impresión de CUPS (lp, lpstat y lpoptions).") from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError("El sistema de impresión no respondió a tiempo. Revisa la impresora y CUPS antes de volver a intentarlo.") from exc
    except OSError as exc:
        raise AppError(f"No se pudo acceder al sistema de impresión: {exc}.") from exc


def list_printers() -> PrinterList:
    response = _run(["lpstat", "-e"])
    if response.returncode:
        detail = (response.stderr or response.stdout).strip()[:500]
        raise AppError("No se pudo consultar CUPS. Comprueba que el servicio de impresión esté disponible. " + detail)
    names = tuple(dict.fromkeys(line.strip() for line in response.stdout.splitlines() if line.strip()))
    if not names:
        raise AppError("No hay impresoras disponibles. Configura tu impresora en el sistema y vuelve a intentarlo.")
    response = _run(["lpstat", "-d"])
    match = re.search(r"^system default destination:\s*(\S+)", response.stdout, re.M)
    default = match.group(1) if match else ""
    if default and default not in names:
        names += (default,)
    if not default and len(names) == 1:
        default = names[0]
    return PrinterList(tuple(sorted(names, key=alphabetical_key)), default)


def monochrome_driver_options(options: str) -> list[str]:
    """Use an advertised PPD grayscale control in addition to standard IPP."""
    available = {}
    for line in options.splitlines():
        definition, separator, choices = line.partition(":")
        if separator:
            key = definition.partition("/")[0].strip()
            available[key] = {choice.lstrip("*") for choice in choices.split()}
    for key, choices in (
        ("CNGrayscale", ("True",)),
        ("ColorModel", ("Gray", "Grayscale", "Black", "KGray", "FastGray")),
        ("ColorMode", ("Monochrome", "Gray", "Grayscale", "Black")),
        ("OutputMode", ("Monochrome", "Gray", "Grayscale", "Black")),
    ):
        advertised = {value.casefold(): value for value in available.get(key, set())}
        for choice in choices:
            if choice.casefold() in advertised:
                return ["-o", f"{key}={advertised[choice.casefold()]}"]
    return []


def print_pdf(path: Path, printer: str = "", paper: str = "Carta") -> PrintJob:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise AppError("El PDF ya no existe. Genera o selecciona una edición antes de imprimir.")
    try:
        with path.open("rb") as document:
            if document.read(5) != b"%PDF-":
                raise AppError("El archivo seleccionado no es un PDF válido.")
    except OSError as exc:
        raise AppError(f"No se pudo leer el PDF: {exc}.") from exc
    if paper == "Letter":
        paper = "Carta"
    if paper not in {"Carta", "A4"}:
        raise AppError("El tamaño de impresión debe ser Carta (Letter) o A4.")
    if not printer:
        available = list_printers()
        printer = available.default
        if not printer:
            raise AppError("Hay varias impresoras y ninguna predeterminada. Selecciona una en la app o usa --printer NOMBRE.")
    if any(char.isspace() for char in printer):
        raise AppError("Usa el identificador de la impresora de CUPS, sin espacios.")
    extra_options = []
    try:
        response = _run(["lpoptions", "-p", printer, "-l"])
        if response.returncode == 0:
            extra_options = monochrome_driver_options(response.stdout)
    except AppError:
        # Driverless printers may not expose PPD options. The standard IPP
        # monochrome option is still submitted; never resubmit a print job.
        pass
    command = [
        "lp", "-d", printer, "-t", "La Mañana · Chile", "-n", "1", "-P", "1",
        "-o", "media=Letter" if paper == "Carta" else "media=A4",
        "-o", "print-color-mode=monochrome", "-o", "sides=one-sided",
        "-o", "number-up=1", "-o", "job-sheets=none",
        "-o", "orientation-requested=3", "-o", "fit-to-page",
        *extra_options, "--", str(path),
    ]
    response = _run(command, timeout=30)
    if response.returncode:
        detail = (response.stderr or response.stdout).strip()[:800]
        raise AppError("No se pudo enviar la hoja a la impresora. " + detail)
    match = re.search(r"request id is\s+(\S+)", response.stdout)
    return PrintJob(printer, paper, match.group(1) if match else "")
