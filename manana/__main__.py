from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import AppError, CONFIG_PATH, load_settings
from .ollama import create_model_client
from .newspaper import render_edition
from .pipeline import demo_edition, generate, open_pdf
from .printing import list_printers, print_pdf


def main():
    parser = argparse.ArgumentParser(description="Genera un periódico de Chile de una página usando config.json, sin GUI por defecto.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="Abrir la aplicación de escritorio")
    mode.add_argument("--demo", action="store_true", help="Generar una maqueta sin internet ni modelo")
    mode.add_argument("--models", action="store_true", help="Listar los modelos disponibles en el servidor configurado")
    mode.add_argument("--check-config", action="store_true", help="Validar y mostrar la configuración sin descargar noticias ni consultar el modelo")
    mode.add_argument("--printers", action="store_true", help="Listar las impresoras disponibles")
    mode.add_argument("--print-file", type=Path, help="Imprimir un PDF guardado sin volver a generar noticias")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="Archivo JSON de configuración; predeterminado config.json del proyecto")
    parser.add_argument("--model", help="Identificador del modelo local")
    parser.add_argument("--base-url", help="Servidor del modelo; predeterminado el valor de config.json")
    parser.add_argument("--paper", choices=("A4", "Carta", "Letter"), help="Tamaño de papel; predeterminado Carta (Letter)")
    parser.add_argument("--printer", help="Identificador de la impresora de CUPS")
    parser.add_argument("--print", dest="print_after_generation", action="store_true", default=None, help="Imprimir una copia en negro después de generar el PDF")
    parser.add_argument("--count", type=int, choices=range(3, 8), help="Cantidad de noticias: 3–7")
    parser.add_argument("--hours", type=int, help="Buscar noticias de las últimas 1–72 horas")
    parser.add_argument("--max-output-tokens", type=int, help="Presupuesto inicial de salida: 1024–8192 tokens, hasta max_retry_output_tokens")
    parser.add_argument("--output-dir", help="Carpeta de destino")
    viewer = parser.add_mutually_exclusive_group()
    viewer.add_argument("--open", dest="open_pdf_after_generation", action="store_true", default=None, help="Abrir el PDF en el visor del equipo")
    viewer.add_argument("--no-open", dest="open_pdf_after_generation", action="store_false", help="Guardar el PDF sin abrir el visor")
    args = parser.parse_args()
    try:
        if not args.config.is_file():
            raise AppError(f"Falta el archivo de configuración {args.config}. Copia config.example.json a config.json.")
        settings = load_settings(args.config, require_provider=not args.gui)
        for argument, field in (("model", "model"), ("base_url", "base_url"), ("paper", "paper"), ("printer", "printer"), ("count", "article_count"), ("hours", "lookback_hours"), ("max_output_tokens", "max_output_tokens"), ("output_dir", "output_dir"), ("print_after_generation", "print_after_generation"), ("open_pdf_after_generation", "open_pdf_after_generation")):
            value = getattr(args, argument)
            if value is not None:
                setattr(settings, field, value)
        settings.validate()
        if args.check_config:
            print(json.dumps(asdict(settings), ensure_ascii=False, indent=2))
            return 0
        if args.printers:
            available = list_printers()
            for name in available.names:
                print(name + (" (predeterminada)" if name == available.default else ""))
            return 0
        if args.print_file:
            print(print_pdf(args.print_file, printer=settings.printer, paper=settings.paper).message)
            return 0
        if args.gui:
            from .gui import launch
            launch(settings)
            return 0
        if args.models:
            for model in create_model_client(settings).models():
                print(model)
            return 0
        if args.demo:
            edition = demo_edition(settings.article_count)
            path = Path(settings.output_dir) / "ejemplo.pdf"
            render_edition(edition, path, settings.paper, preview=settings.save_preview)
            print(f"Maqueta de ejemplo: {path}")
        else:
            path = generate(settings, lambda text: print(text, flush=True))
        if settings.print_after_generation:
            print(print_pdf(path, printer=settings.printer, paper=settings.paper).message)
        if settings.open_pdf_after_generation:
            open_pdf(path)
        return 0
    except (AppError, OSError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nGeneración cancelada.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
