from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_HISTORICO_RECEBIDO = 20
MAX_TEXTO_HISTORICO = 4000


class HistoricoItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _cortar_texto(cls, v: object) -> object:
        return v[:MAX_TEXTO_HISTORICO] if isinstance(v, str) else v


class ChatRequest(BaseModel):
    pergunta: str = Field(min_length=1, max_length=1000)
    # Conversas longas não são recusadas: só as mensagens mais recentes servem de contexto.
    historico: list[HistoricoItem] = Field(default_factory=list)

    @field_validator("historico", mode="before")
    @classmethod
    def _ultimas_mensagens(cls, v: object) -> object:
        return v[-MAX_HISTORICO_RECEBIDO:] if isinstance(v, list) else v


class GraficoSpec(BaseModel):
    """Como desenhar `dados`: só nomes de colunas, nunca valores."""

    tipo: Literal["barra", "barra_horizontal", "linha"]
    x: str
    y: list[str] = Field(min_length=1, max_length=3)
    titulo: str = Field(default="", max_length=100)


class ChatResponse(BaseModel):
    resposta: str
    sql: str | None = None
    colunas: list[str] = Field(default_factory=list)
    dados: list[list[Any]] = Field(default_factory=list)
    total_linhas: int = 0
    truncado: bool = False
    grafico: GraficoSpec | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degradado"]
    banco: bool
    llm_configurado: bool
