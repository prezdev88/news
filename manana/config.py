from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


class AppError(Exception):
    """An actionable error that can be shown directly to the user."""


@dataclass(frozen=True)
class Source:
    name: str
    page_url: str
    article_prefix: str
    feed_url: str = ""
    section: str = ""
    require_chile: bool = False


SOURCES = (
    Source(
        "Cooperativa",
        "https://www.cooperativa.cl/noticias/pais",
        "/noticias/pais/",
        "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_1___1.xml",
    ),
    Source(
        "BioBioChile",
        "https://www.biobiochile.cl/lista/categorias/nacional",
        "/noticias/nacional/",
    ),
    Source(
        "El Mostrador",
        "https://www.elmostrador.cl/noticias/pais/",
        "/noticias/pais/",
    ),
    Source(
        "BioBioChile",
        "https://www.biobiochile.cl/lista/categorias/pc-e-internet",
        "/noticias/ciencia-y-tecnologia/pc-e-internet/",
        section="Tecnología",
        require_chile=True,
    ),
    Source(
        "El Mostrador",
        "https://www.elmostrador.cl/agenda-pais/agenda-innovacion/",
        "/agenda-pais/",
        section="Tecnología",
        require_chile=True,
    ),
)


@dataclass
class Settings:
    base_url: str = "http://localhost:1234/v1"
    model: str = ""
    paper: str = "Carta"
    printer: str = ""
    article_count: int = 7
    lookback_hours: int = 24
    candidates_per_source: int = 8
    timeout_seconds: int = 240
    max_output_tokens: int = 4096
    max_article_chars: int = 8000
    output_dir: str = str(ROOT / "output")

    @property
    def api_key(self) -> str:
        return os.environ.get("LMSTUDIO_API_KEY", "")

    def validate(self) -> None:
        self.base_url = self.base_url.strip().rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AppError("La dirección de LM Studio debe comenzar con http:// o https://.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AppError("Usa una URL sin credenciales, consultas ni fragmentos.")
        if parsed.path in {"", "/"}:
            self.base_url += "/v1"
        elif parsed.path != "/v1":
            raise AppError("La URL de LM Studio debe terminar en /v1, sin /chat/completions.")
        if self.paper == "Letter":
            self.paper = "Carta"
        if self.paper not in {"A4", "Carta"}:
            raise AppError("El tamaño de papel debe ser A4 o Carta.")
        if not isinstance(self.printer, str) or any(char.isspace() for char in self.printer):
            raise AppError("El nombre de impresora debe ser el identificador de CUPS, sin espacios.")
        if not 3 <= self.article_count <= 7:
            raise AppError("El periódico admite entre 3 y 7 noticias por página.")
        if not 1 <= self.lookback_hours <= 72:
            raise AppError("El período de noticias debe estar entre 1 y 72 horas.")
        if not 3 <= self.candidates_per_source <= 16:
            raise AppError("La cantidad de candidatos por medio debe estar entre 3 y 16.")
        if not 15 <= self.timeout_seconds <= 1800:
            raise AppError("El tiempo de espera debe estar entre 15 y 1800 segundos.")
        if type(self.max_output_tokens) is not int or not 1024 <= self.max_output_tokens <= 8192:
            raise AppError("El límite de salida debe ser un entero entre 1024 y 8192 tokens.")
        if not 2000 <= self.max_article_chars <= 16000:
            raise AppError("El límite de texto por artículo debe estar entre 2000 y 16000 caracteres.")
        if not self.output_dir.strip():
            raise AppError("Selecciona una carpeta para guardar el PDF.")


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = Settings(**data)
        settings.validate()
        return settings
    except (OSError, ValueError, TypeError) as exc:
        raise AppError(f"No se pudo leer {path.name}: {exc}") from exc


def save_settings(settings: Settings, path: Path = CONFIG_PATH) -> None:
    settings.validate()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
