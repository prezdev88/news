from __future__ import annotations

import calendar
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

from .config import AppError, Settings, Source

CHILE = ZoneInfo("America/Santiago")
ARTICLE_DATE = re.compile(r"/(\d{4})[-/](\d{2})[-/](\d{2})(?:/|$)")
MONTHS = {name: index for index, name in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1
)}
TECHNOLOGY_TERMS = re.compile(
    r"\b(?:tecnolog\w*|inteligencia artificial|ia|ciberseguridad|ciberataques?|software|hardware|"
    r"robotica|robots?|informatica|computacion|telecomunicaciones|conectividad|internet|"
    r"digitalizacion|brecha digital|salud digital|educacion digital|aplicaciones? moviles?|apps?|"
    r"startups?|proteccion de datos|realidad virtual|realidad aumentada|innovacion tecnologica|5g|6g)\b"
)
CHILE_TERMS = re.compile(r"\b(?:chile|chilen[oa]s?|subtel|cenia|corfo|anci|teleton|universidad de concepcion|universidad de santiago)\b")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char))


@dataclass(frozen=True)
class Article:
    source: str
    title: str
    url: str
    published: datetime | None = None
    body: str = ""
    source_rank: int = 0
    section: str = ""


def is_technology_article(article: Article) -> bool:
    return article.section == "Tecnología" or bool(TECHNOLOGY_TERMS.search(normalize(article.title + " " + article.body[:2000])))


def has_chilean_context(article: Article) -> bool:
    return bool(CHILE_TERMS.search(normalize(article.title + " " + article.body)))


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(text)
        except (ValueError, TypeError, OverflowError):
            match = re.search(
                r"(\d{1,2})\s+(?:de\s+)?(" + "|".join(MONTHS) + r")\s+(?:de\s+)?(\d{4})(?:.*?(\d{1,2}):(\d{2}))?",
                text, re.I,
            )
            if not match:
                return None
            day, month, year, hour, minute = match.groups()
            try:
                result = datetime(int(year), MONTHS[month.lower()], int(day), int(hour or 0), int(minute or 0))
            except ValueError:
                return None
    return result if result.tzinfo else result.replace(tzinfo=CHILE)


def canonical_url(value: str) -> str:
    parsed = urlparse(value)
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "msclkid"}]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.params, urlencode(query), ""))


def is_national_article(url: str, source: Source, *, from_feed: bool = False) -> bool:
    try:
        parsed = urlparse(url)
        expected_host = urlparse(source.page_url).hostname
        host = parsed.hostname
    except ValueError:
        return False
    same_host = bool(host and expected_host and host.removeprefix("www.") == expected_host.removeprefix("www."))
    return (
        parsed.scheme in {"http", "https"}
        and bool(host)
        and not parsed.username and not parsed.password
        and (same_host or (from_feed and source.allow_external_feed_articles))
        and (parsed.path or "/").startswith(source.article_prefix)
        and (not source.require_date_in_url or ARTICLE_DATE.search(parsed.path) is not None)
        and canonical_url(url).rstrip("/") != canonical_url(source.page_url).rstrip("/")
    )


def _download(session: requests.Session, url: str, settings: Settings | None = None) -> bytes:
    timeout = (settings.connect_timeout_seconds, settings.download_timeout_seconds) if settings else (10, 25)
    max_bytes = settings.max_download_bytes if settings else 4_000_000
    with session.get(url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        chunks = []
        size = 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > max_bytes:
                raise AppError(f"El artículo supera el límite de descarga ({max_bytes} bytes).")
            chunks.append(chunk)
        # Keep the original bytes: RSS and HTML parsers understand XML/meta
        # charset declarations, including the Latin-1 still used by some feeds.
        return b"".join(chunks)


def parse_feed(content: str | bytes, source: Source) -> list[Article]:
    result = []
    for entry in feedparser.parse(content).entries:
        url = canonical_url(urljoin(source.page_url, entry.get("link", "")))
        if not is_national_article(url, source, from_feed=True):
            continue
        title = clean_text(BeautifulSoup(entry.get("title", ""), "html.parser").get_text(" "))
        published = parse_date(entry.get("published"))
        if not published and entry.get("published_parsed"):
            published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), timezone.utc)
        if len(title) >= 20:
            result.append(Article(source.name, title, url, published, source_rank=len(result), section=source.section))
    return result


def parse_listing(content: str | bytes, source: Source) -> list[Article]:
    soup = BeautifulSoup(content, "html.parser")
    for unwanted in soup.select("nav, header, footer, aside"):
        unwanted.decompose()
    result = []
    seen = set()
    for anchor in soup.select("a[href]"):
        url = canonical_url(urljoin(source.page_url, anchor["href"]))
        if url in seen or not is_national_article(url, source):
            continue
        title = clean_text(anchor.get_text(" "))
        if len(title) < 20:
            title = clean_text(anchor.get("title", ""))
        if len(title) >= 20:
            seen.add(url)
            result.append(Article(source.name, title, url, source_rank=len(result), section=source.section))
    return result


def _article_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from _article_objects(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if any(kind in {"NewsArticle", "Article", "ReportageNewsArticle"} for kind in types):
            yield value
        if "@graph" in value:
            yield from _article_objects(value["@graph"])


def extract_article(content: str | bytes, article: Article) -> Article:
    soup = BeautifulSoup(content, "html.parser")
    published = article.published
    body = ""
    title = article.title
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = list(_article_objects(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            continue
        for data in objects:
            published = parse_date(data.get("datePublished")) or published
            if isinstance(data.get("headline"), str):
                title = clean_text(data["headline"])
            candidate = data.get("articleBody", "")
            if isinstance(candidate, str):
                candidate = clean_text(BeautifulSoup(candidate, "html.parser").get_text(" "))
                if len(candidate) > len(body):
                    body = candidate
    for attribute, name in (("property", "article:published_time"), ("name", "datePublished"), ("itemprop", "datePublished")):
        tag = soup.find("meta", attrs={attribute: name})
        if tag:
            published = parse_date(tag.get("content")) or published
    if not published:
        time_tag = soup.find("time", datetime=True)
        if time_tag:
            published = parse_date(time_tag.get("datetime"))
    for unwanted in soup.select("script, style, nav, header, footer, aside, form, .related, .relacionados, .share, .social, .newsletter, .comments, .comentarios"):
        unwanted.decompose()
    if not body:
        selectors = (
            '[itemprop="articleBody"]', ".article-body", ".article__body", ".article-text",
            ".entry-content", ".post-content", ".cuerpo-articulo", "#cuerpo", ".cuerpo", "article",
        )
        for selector in selectors:
            candidates = []
            for element in soup.select(selector):
                paragraphs = [clean_text(p.get_text(" ")) for p in element.find_all("p")]
                candidates.append("\n\n".join(dict.fromkeys(p for p in paragraphs if len(p) >= 35)))
            candidate = max(candidates, key=len, default="")
            if len(candidate.split()) >= 80:
                body = candidate
                break
    if not published:
        # Some publishers expose a human-readable publication date rather than metadata.
        text = soup.get_text(" ", strip=True)
        for match in re.finditer(r"\d{1,2}\s+(?:de\s+)?(?:" + "|".join(MONTHS) + r")\s+(?:de\s+)?\d{4}(?:\s+a las\s+\d{1,2}:\d{2})?", text, re.I):
            published = parse_date(match.group())
            if published:
                break
    if not published:
        match = ARTICLE_DATE.search(urlparse(article.url).path)
        if match:
            try:
                published = datetime(*(int(part) for part in match.groups()), tzinfo=CHILE)
            except ValueError:
                pass
    return replace(article, title=title, published=published, body=body)


def is_recent(article: Article, now: datetime, hours: int) -> bool:
    return article.published is not None and now - timedelta(hours=hours) <= article.published <= now + timedelta(minutes=15)


def collect_news(settings: Settings, progress=print, session=None, now=None) -> tuple[list[Article], list[str]]:
    settings.validate()
    if not settings.active_sources:
        raise AppError("Activa al menos una fuente en «Fuentes de noticias».")
    now = now or datetime.now(CHILE)
    session = session or requests.Session()
    session.headers.update({"User-Agent": settings.user_agent, "Accept-Language": settings.accept_language})
    articles = []
    warnings = []
    seen_urls = set()
    for source in settings.active_sources:
        label = f"{source.name} · {source.section}" if source.section else source.name
        progress(f"Leyendo {label}…")
        candidates = []
        if source.feed_url:
            try:
                candidates = parse_feed(_download(session, source.feed_url, settings), source)
            except (requests.RequestException, AppError, LookupError) as exc:
                warnings.append(f"{source.name}: RSS no disponible ({type(exc).__name__}); se intenta la portada nacional.")
        if not candidates:
            try:
                content = _download(session, source.page_url, settings)
                candidates = parse_feed(content, source) or parse_listing(content, source)
            except (requests.RequestException, AppError, LookupError) as exc:
                warnings.append(f"{source.name}: no se pudo leer la portada ({type(exc).__name__}).")
                continue
        accepted = 0
        failures = 0
        for candidate in candidates[:settings.candidates_per_source * 2]:
            if candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)
            if candidate.published and not is_recent(candidate, now, settings.lookback_hours):
                continue
            try:
                article = extract_article(_download(session, candidate.url, settings), candidate)
            except (requests.RequestException, AppError, LookupError):
                failures += 1
                continue
            if len(article.body.split()) < 80 or not is_recent(article, now, settings.lookback_hours):
                failures += 1
                continue
            if source.require_chile and not has_chilean_context(article):
                continue
            if source.section == "Tecnología" and not TECHNOLOGY_TERMS.search(normalize(article.title + " " + article.body[:2000])):
                continue
            normalized_title = normalize(article.title)
            if any(SequenceMatcher(None, normalized_title, normalize(existing.title)).ratio() > 0.88 for existing in articles):
                continue
            articles.append(article)
            accepted += 1
            progress(f"  {source.name}: {accepted} noticias disponibles")
            if accepted >= (min(settings.technology_candidates_per_source, settings.candidates_per_source) if source.section == "Tecnología" else settings.candidates_per_source):
                break
        if failures:
            warnings.append(f"{source.name}: {failures} notas descartadas por acceso, fecha o texto insuficiente.")
        if not candidates:
            warnings.append(f"{label}: no se encontraron artículos en la página.")
        elif not accepted and not failures:
            warnings.append(f"{label}: ninguna nota cumplió los filtros de fecha, contenido y relación con Chile.")
    if not any(is_technology_article(article) for article in articles):
        warning = (
            f"No se encontraron noticias de tecnología relacionadas con Chile en las fuentes consultadas "
            f"para las últimas {settings.lookback_hours} horas. Amplía el período para incluir esa sección."
        )
        warnings.append(warning)
        progress("Aviso: " + warning)
    if len(articles) < 3:
        details = "\n".join(warnings)
        raise AppError(
            f"Se encontraron {len(articles)} noticias utilizables; se necesitan al menos 3. "
            "Comprueba internet o amplía el período a 48 horas.\n" + details
        )
    return articles, warnings
