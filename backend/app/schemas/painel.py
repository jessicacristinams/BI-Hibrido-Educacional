"""Respostas dos painéis: só números agregados (nenhum identificador de aluno)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Categoria = Literal["ATIVO", "EVADIDO", "RETIDO", "FORMADO"]


class OpcoesFiltro(BaseModel):
    cursos: list[str]
    periodos: list[str]


class Totais(BaseModel):
    alunos: int
    matriculas: int


class FiltrosResponse(BaseModel):
    alunos: OpcoesFiltro
    disciplinas: OpcoesFiltro
    totais: Totais
    origemDados: Literal["real", "sintetico"]
    limiteSupressao: int


# LGPD: None = número oculto (grupo com 1 a limiteSupressao-1 pessoas).
class KpiCategoria(BaseModel):
    categoria: Categoria
    total: int | None
    taxa: float | None


class SeriePontoAlunos(BaseModel):
    periodo: str
    ativos: int | None
    evadidos: int | None
    retidos: int | None
    formados: int | None


class SemestreValor(BaseModel):
    semestre: int
    valor: int | None


class TipoSaidaValor(BaseModel):
    tipo: str
    valor: int | None


class PainelAlunos(BaseModel):
    totalAlunos: int | None
    suprimido: bool
    limiteSupressao: int
    kpis: list[KpiCategoria]
    categoriasVisiveis: list[Categoria]
    serieHistorica: list[SeriePontoAlunos]
    evasaoPorSemestre: list[SemestreValor]
    formacaoPorSemestre: list[SemestreValor]
    evasaoPorTipoSaida: list[TipoSaidaValor]


class KpisDisciplinas(BaseModel):
    totalMatriculas: int | None
    totalAprovados: int | None
    totalReprovados: int | None
    taxaAprovacao: float | None
    taxaReprovacao: float | None


class RankingItem(BaseModel):
    disciplina: str
    valor: float


class SeriePontoDisciplinas(BaseModel):
    periodo: str
    aprovados: int | None
    reprovados: int | None


class LinhaTabela(BaseModel):
    curso: str
    disciplina: str
    suprimido: bool
    matriculas: int | None
    aprovados: int | None
    reprovados: int | None
    taxaAprovacao: float | None
    mediaFinal: float | None
    mediaFaltas: float | None


class PainelDisciplinas(BaseModel):
    suprimido: bool
    limiteSupressao: int
    kpis: KpisDisciplinas
    rankingMaisAprovados: list[RankingItem]
    rankingMaisReprovados: list[RankingItem]
    rankingMelhorMedia: list[RankingItem]
    rankingPiorMedia: list[RankingItem]
    rankingMelhorFrequencia: list[RankingItem]
    rankingMaisFaltas: list[RankingItem]
    serieHistorica: list[SeriePontoDisciplinas]
    tabela: list[LinhaTabela]
