from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .config import AppError


# Bump when editorial prompts or summary validation change incompatibly.
CACHE_VERSION = 1


def fingerprint(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SummaryCache:
    """Keep validated work across failures until its PDF has been rendered."""

    def __init__(self, settings, progress=print):
        self.settings = settings
        self.progress = progress
        self.path = Path(settings.output_dir).expanduser() / Path(settings.summary_cache_file).expanduser()
        self.entries = {}
        self.lock = None

    def __enter__(self):
        if not self.settings.cache_summaries:
            return self
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(self.path.suffix + ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            self.lock = None
            if isinstance(exc, BlockingIOError):
                raise AppError("Ya hay una generación usando estos resúmenes temporales. Espera a que termine antes de reintentar.") from exc
            raise
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != CACHE_VERSION or not isinstance(data.get("entries"), dict):
                raise ValueError("formato incompatible")
            self.entries = data["entries"]
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeError):
            self.progress("Aviso: los resúmenes temporales no se pueden leer; se generarán nuevamente.")
        except OSError:
            self.lock.close()
            self.lock = None
            raise
        return self

    def __exit__(self, *exc):
        if self.lock is not None:
            self.lock.close()

    def key(self, article, section, *, lead, compact) -> str:
        # Do not serialize credentials or unrelated display/printing settings.
        fields = (
            "provider", "base_url", "model", "model_options", "think", "structured_output",
            "system_prompt", "max_output_tokens", "max_retry_output_tokens", "max_article_chars",
            "article_count", "summary_lengths",
        )
        return fingerprint({
            "version": CACHE_VERSION,
            "settings": {name: getattr(self.settings, name) for name in fields},
            "article": {
                "url": article.url, "source": article.source, "title": article.title,
                "published": article.published.isoformat() if article.published else None,
                "body": article.body,
            },
            "section": section, "lead": lead, "compact": compact,
        })

    def get(self, key):
        if not self.settings.cache_summaries or key not in self.entries:
            return None
        entry = self.entries[key]
        summary = entry.get("summary") if isinstance(entry, dict) else None
        if (
            not isinstance(summary, dict)
            or set(summary) != {"headline", "summary", "section"}
            or any(not isinstance(value, str) or not value.strip() for value in summary.values())
            or entry.get("checksum") != fingerprint(summary)
        ):
            self.progress("Aviso: un resumen temporal está dañado; se generará nuevamente.")
            return None
        return dict(summary)

    def save(self, key, summary):
        if not self.settings.cache_summaries:
            return
        self.entries[key] = {"summary": dict(summary), "checksum": fingerprint(summary)}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix=".summaries-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": CACHE_VERSION, "entries": self.entries}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError as exc:
            raise AppError(f"No se pudo guardar el avance en {self.path}. Los resúmenes guardados anteriormente se conservan: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def clear(self):
        if not self.settings.cache_summaries:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            self.progress(f"Aviso: el PDF se generó, pero no se pudieron eliminar los resúmenes temporales de {self.path}: {exc}")
            return
        self.entries.clear()
        self.progress("PDF generado; resúmenes temporales eliminados.")
