/**
 * Tipos das respostas da API dos painéis (backend/app/schemas/painel.py).
 * O navegador recebe só números agregados do recorte pedido; nenhum dado por aluno.
 *
 * LGPD: `null` num número = oculto, porque o grupo tem de 1 a `limiteSupressao - 1` pessoas.
 */

export type Categoria = "ATIVO" | "EVADIDO" | "RETIDO" | "FORMADO";

export const CATEGORIAS: readonly Categoria[] = ["ATIVO", "EVADIDO", "RETIDO", "FORMADO"];

export interface OpcoesFiltro {
  cursos: string[];
  /** Ordem cronológica. */
  periodos: string[];
}

/** GET /api/painel/filtros */
export interface Filtros {
  alunos: OpcoesFiltro;
  disciplinas: OpcoesFiltro;
  totais: { alunos: number; matriculas: number };
  /** "sintetico" = base de demonstração com alunos fictícios. */
  origemDados: "real" | "sintetico";
  limiteSupressao: number;
}

// ── Painel de Alunos (GET /api/painel/alunos) ───────────────────────────────
export interface KpiCategoria {
  categoria: Categoria;
  total: number | null;
  /** % sobre o total de alunos no recorte */
  taxa: number | null;
}

export interface SeriePonto {
  periodo: string;
  ativos: number | null;
  evadidos: number | null;
  retidos: number | null;
  formados: number | null;
}

export type SerieKey = Exclude<keyof SeriePonto, "periodo">;

export const SERIE_KEY: Record<Categoria, SerieKey> = {
  ATIVO: "ativos",
  EVADIDO: "evadidos",
  RETIDO: "retidos",
  FORMADO: "formados",
};

export interface SemestreValor {
  semestre: number;
  valor: number | null;
}

export interface TipoSaidaValor {
  tipo: string;
  valor: number | null;
}

export interface AlunosView {
  totalAlunos: number | null;
  /** true = recorte com menos de `limiteSupressao` alunos: nenhum número é exibido. */
  suprimido: boolean;
  limiteSupressao: number;
  /** Só as categorias visíveis (as marcadas no filtro Indicador, ou as 4). */
  kpis: KpiCategoria[];
  categoriasVisiveis: Categoria[];
  serieHistorica: SeriePonto[];
  /** [] quando EVADIDO não está entre as categorias visíveis. */
  evasaoPorSemestre: SemestreValor[];
  /** [] quando FORMADO não está entre as categorias visíveis. */
  formacaoPorSemestre: SemestreValor[];
  /** [] quando EVADIDO não está entre as categorias visíveis. */
  evasaoPorTipoSaida: TipoSaidaValor[];
}

// ── Painel de Disciplinas (GET /api/painel/disciplinas) ─────────────────────
export interface RankingItem {
  disciplina: string;
  valor: number;
}

export interface DisciplinasKpis {
  totalMatriculas: number | null;
  totalAprovados: number | null;
  totalReprovados: number | null;
  /** aprovados / (aprovados + reprovados) */
  taxaAprovacao: number | null;
  /** reprovados / (aprovados + reprovados) */
  taxaReprovacao: number | null;
}

export interface SeriePeriodo {
  periodo: string;
  aprovados: number | null;
  reprovados: number | null;
}

export interface LinhaTabela {
  curso: string;
  disciplina: string;
  /** true = menos de `limiteSupressao` matrículas: só curso e disciplina aparecem. */
  suprimido: boolean;
  matriculas: number | null;
  aprovados: number | null;
  reprovados: number | null;
  taxaAprovacao: number | null;
  mediaFinal: number | null;
  mediaFaltas: number | null;
}

export interface DisciplinasView {
  suprimido: boolean;
  limiteSupressao: number;
  kpis: DisciplinasKpis;
  rankingMaisAprovados: RankingItem[];
  rankingMaisReprovados: RankingItem[];
  rankingMelhorMedia: RankingItem[];
  rankingPiorMedia: RankingItem[];
  rankingMelhorFrequencia: RankingItem[];
  rankingMaisFaltas: RankingItem[];
  serieHistorica: SeriePeriodo[];
  tabela: LinhaTabela[];
}
