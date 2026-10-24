from __future__ import annotations

import json

from .config import AppError
from .lmstudio import LMStudio
from .sorting import alphabetical_key


class Ollama(LMStudio):
    """Use Ollama's native controls with the shared editorial validations."""

    def models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise AppError("Ollama devolvió una lista de modelos inesperada.")
        return sorted((item["name"] for item in data["models"] if isinstance(item, dict) and isinstance(item.get("name"), str)), key=alphabetical_key)

    def select_model(self) -> str:
        models = self.models()
        model = self.settings.model
        if model not in models:
            if not self.settings.auto_pull_model:
                raise AppError(f"El modelo '{model}' no aparece en Ollama. Activa auto_pull_model en config.json para descargarlo.")
            self.progress(f"Descargando el modelo {model} en Ollama; la primera ejecución puede tardar…")
            result = self._request("POST", "/api/pull", json={"model": model, "stream": False})
            if not isinstance(result, dict) or result.get("status") != "success":
                raise AppError("Ollama no confirmó la descarga del modelo. Revisa docker compose logs ollama.")
        return model

    def _complete(self, prompt: str, schema: dict, token_limit: int) -> dict:
        if self.settings.structured_output:
            prompt += "\nESQUEMA JSON DE LA RESPUESTA:\n" + json.dumps(schema, ensure_ascii=False)
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": self.settings.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": self.settings.think,
            "keep_alive": self.settings.keep_alive,
            "options": {**self.settings.model_options, "num_predict": token_limit},
            "format": schema if self.settings.structured_output else "json",
        }
        response = self._request("POST", "/api/chat", json=payload)
        if not isinstance(response, dict) or not isinstance(response.get("message"), dict) or response.get("done") is not True:
            raise AppError("Ollama devolvió una respuesta incompleta o sin mensaje de texto.")
        return {"choices": [{
            "message": response["message"],
            "finish_reason": response.get("done_reason", "stop"),
        }]}


def create_model_client(settings, **kwargs):
    client_type = Ollama if settings.provider == "ollama" else LMStudio
    return client_type(settings, **kwargs)
