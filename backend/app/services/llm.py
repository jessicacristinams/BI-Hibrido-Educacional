"""Cliente de LLM.

O restante do backend depende só do protocolo `LLMClient`, então trocar de
provedor (ou usar um falso nos testes) não mexe no fluxo do chat.
"""

from __future__ import annotations

import json
from typing import Protocol, TypedDict

from app.core.config import Settings
from app.core.errors import LLMNotConfiguredError, LLMProviderError


class LLMMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[LLMMessage], json_mode: bool = False) -> str: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str, timeout_s: float, base_url: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        self._model = model

    def complete(self, system: str, messages: list[LLMMessage], json_mode: bool = False) -> str:
        import openai

        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, *messages],
                temperature=0,
                **extra,
            )
        except openai.OpenAIError as exc:
            raise LLMProviderError("Falha ao consultar o modelo de linguagem. Tente novamente.") from exc
        return resp.choices[0].message.content or ""


class OllamaClient:
    """API nativa do Ollama (/api/chat).

    A API compatível com a OpenAI (/v1) ignora o tamanho do contexto e usa o padrão do Ollama (4096
    tokens), que corta o início do prompt do chat. A nativa aceita options.num_ctx.
    """

    def __init__(self, base_url: str, model: str, timeout_s: float, contexto: int, transport=None) -> None:
        import httpx

        raiz = base_url.rstrip("/")
        raiz = raiz[: -len("/v1")] if raiz.endswith("/v1") else raiz
        self._http = httpx.Client(base_url=raiz, timeout=timeout_s, transport=transport)
        self._model = model
        self._contexto = contexto

    def complete(self, system: str, messages: list[LLMMessage], json_mode: bool = False) -> str:
        import httpx

        corpo = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self._contexto},
        }
        if json_mode:
            corpo["format"] = "json"
        try:
            resp = self._http.post("/api/chat", json=corpo)
            resp.raise_for_status()
            return resp.json()["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Falha ao consultar o modelo de linguagem. Tente novamente.") from exc


def eh_ollama(base_url: str | None) -> bool:
    return bool(base_url) and (":11434" in base_url or "ollama" in base_url.lower())


def build_llm_client(settings: Settings) -> LLMClient:
    if not settings.openai_api_key:
        raise LLMNotConfiguredError("Assistente indisponível: OPENAI_API_KEY não configurada no backend.")
    if eh_ollama(settings.openai_base_url):
        return OllamaClient(settings.openai_base_url, settings.llm_model, settings.llm_timeout_s, settings.llm_contexto)
    return OpenAIClient(settings.openai_api_key, settings.llm_model, settings.llm_timeout_s, settings.openai_base_url)
