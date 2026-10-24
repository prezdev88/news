from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .config import AppError, Settings
from .ollama import create_model_client
from .news import CHILE, Article, collect_news, is_technology_article
from .newspaper import LayoutOverflowError, render_edition
from .summary_cache import SummaryCache


def serialize(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Article):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def generate(settings: Settings, progress=print) -> Path:
    settings.validate()
    if not settings.active_sources:
        raise AppError("Activa al menos una fuente en «Fuentes de noticias».")
    with SummaryCache(settings, progress) as cache:
        return _generate(settings, progress, cache)


def _generate(settings, progress, cache):
    progress(f"Conectando con {settings.provider}…")
    client = create_model_client(settings, progress=progress)
    model = client.select_model()
    progress(f"Modelo: {model}")
    # Check the local model before downloading news, so a missing server fails fast.
    articles, warnings = collect_news(settings, progress)
    if len(articles) < settings.article_count:
        raise AppError(
            f"Pediste {settings.article_count} noticias, pero solo se encontraron {len(articles)} artículos utilizables. "
            "Amplía el período de noticias o elige una cantidad menor."
        )
    progress(f"Seleccionando las principales noticias entre {len(articles)} artículos…")
    selected = client.select_articles(articles, settings.article_count)

    def summarize(article, section, *, lead, compact):
        key = cache.key(article, section, lead=lead, compact=compact)
        saved = cache.get(key)
        if saved is not None:
            progress(f"Reutilizando resumen guardado: {article.title}")
            return saved
        summary = client.summarize(article, section, lead=lead, compact=compact)
        cache.save(key, summary)
        return summary

    stories = []
    for index, (article, section) in enumerate(selected):
        progress(f"Resumiendo {index + 1}/{len(selected)}: {article.title}")
        summary = summarize(article, section, lead=index == 0, compact=settings.compact_summaries)
        stories.append({**summary, "article": article})
    created = datetime.now(CHILE)
    edition = {
        "created": created, "model": model, "lookback_hours": settings.lookback_hours,
        "stories": stories, "warnings": warnings, "demo": False,
        "requested_count": settings.article_count,
    }
    output = Path(settings.output_dir).expanduser().resolve()
    filename = "la-manana-" + created.strftime("%Y-%m-%d-%H%M%S-%f") + ".pdf"
    progress("Maquetando el periódico…")
    pdf_path = output / filename
    try:
        render_edition(edition, pdf_path, settings.paper, preview=settings.save_preview)
    except LayoutOverflowError:
        if settings.compact_summaries:
            raise
        progress(f"Preparando resúmenes más breves para conservar las {settings.article_count} noticias en una página…")
        compact_stories = []
        for index, (article, section) in enumerate(selected):
            progress(f"Ajustando extensión {index + 1}/{len(selected)}: {article.title}")
            summary = summarize(article, section, lead=index == 0, compact=True)
            compact_stories.append({**summary, "article": article})
        edition["stories"] = compact_stories
        render_edition(edition, pdf_path, settings.paper, preview=settings.save_preview)
    cache.clear()
    edition["paper"] = settings.paper
    edition["sources"] = [asdict(source) for source in settings.active_sources]
    edition["topics"] = list(settings.topics)
    edition["candidate_count"] = len(articles)
    edition["printed_count"] = len(edition["stories"])
    edition["technology_count"] = sum(is_technology_article(story["article"]) or story["section"] == "Tecnología" for story in edition["stories"])
    if settings.save_metadata:
        pdf_path.with_suffix(".json").write_text(json.dumps(edition, ensure_ascii=False, indent=2, default=serialize) + "\n", encoding="utf-8")
    for warning in warnings:
        progress("Aviso: " + warning)
    progress(f"PDF listo: {pdf_path} · {len(edition['stories'])} de {settings.article_count} noticias")
    return pdf_path


def open_pdf(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise AppError(f"El PDF se guardó en {path}, pero no se pudo abrir el visor.") from exc


def demo_edition(count: int = 7) -> dict:
    created = datetime.now(CHILE)
    samples = [
        ("Una mañana informada empieza con una sola página", "Edición de muestra",
         "Esta edición de ejemplo permite revisar la tipografía y la distribución del periódico antes de conectar las noticias reales. La portada destaca el asunto principal y las columnas reúnen notas breves con su fuente. En una edición real, el programa leerá artículos de medios chilenos y pedirá a tu modelo local que los resuma. La extensión se ajustará al espacio disponible, conservando la cantidad elegida y una sola página."),
        ("Las noticias se leen antes de resumir", "El proceso",
         "El generador buscará artículos recientes en las secciones nacionales de los medios configurados. Leerá su contenido y comprobará que exista texto suficiente y una fecha válida. Los enlaces permitirán volver a la publicación original para ampliar la información."),
        ("La tecnología también tiene su lugar", "Tecnología",
         "La edición reservará una noticia para tecnología cuando haya información reciente relacionada con Chile. Podrá tratar sobre inteligencia artificial, ciberseguridad, conectividad o innovación. Esta nota contará dentro de la cantidad elegida y conservará su fuente, como las demás noticias."),
        ("Tu modelo local redactará los resúmenes", "La redacción",
         "La app enviará los textos al servidor de LM Studio que tengas configurado. El modelo recibirá instrucciones para conservar las cifras, las fechas y las atribuciones de cada fuente. Los resúmenes se escribirán en español y tendrán una extensión adecuada."),
        ("Cada artículo mantiene su procedencia", "Las fuentes",
         "Debajo de cada noticia aparecerán el medio y la fecha de publicación. El PDF incluirá enlaces a la fuente original. Junto al documento se guardarán los textos utilizados y los resúmenes, para que puedas revisar cómo se preparó la edición."),
        ("Una edición nueva cuando tú la necesites", "A tu ritmo",
         "El periódico se generará al ejecutar el programa o al pulsar el botón de la aplicación. Podrás elegir el modelo de LM Studio y el papel. Cada edición tendrá su propio archivo, con la fecha y la hora en el nombre."),
        ("El diseño conserva una lectura cómoda", "En papel",
         "La maqueta usa fondo blanco, tipografía de periódico y líneas finas. El generador comprobará el espacio antes de crear el archivo. Si la edición queda demasiado extensa, preparará resúmenes más breves para conservar todas las noticias en una sola página."),
    ]
    stories = []
    for title, section, summary in samples[:count]:
        article = Article("Ejemplo de diseño", title, "https://example.org/maqueta", created, summary)
        stories.append({"headline": title, "section": section, "summary": summary, "article": article})
    return {"created": created, "model": "maqueta", "lookback_hours": 24, "stories": stories, "warnings": [], "demo": True}
