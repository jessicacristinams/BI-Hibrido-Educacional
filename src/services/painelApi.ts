/**
 * Cliente dos painéis: cada mudança de filtro vira um GET com o recorte pedido,
 * e o backend devolve só os números agregados (os dados por aluno ficam no servidor).
 */
import type { AlunosView, Categoria, DisciplinasView, Filtros } from "../types/painel";

const API_URL = import.meta.env.VITE_API_URL ?? "";

type Params = Record<string, string | string[] | null>;

function montarUrl(caminho: string, params: Params = {}): string {
  const qs = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (valor === null) continue;
    for (const v of Array.isArray(valor) ? valor : [valor]) qs.append(chave, v);
  }
  const s = qs.toString();
  return `${API_URL}${caminho}${s ? `?${s}` : ""}`;
}

async function getJson<T>(caminho: string, params?: Params, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(montarUrl(caminho, params), { signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new Error("Não foi possível conectar ao servidor. Verifique se o backend está rodando.");
  }
  if (!res.ok) {
    let detalhe = `Erro ${res.status} ao consultar o servidor.`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detalhe = body.detail;
    } catch {
      // corpo não-JSON (ex.: proxy do Vite com o backend desligado)
      if (res.status >= 500) detalhe = "Não foi possível conectar ao servidor. Verifique se o backend está rodando.";
    }
    throw new Error(detalhe);
  }
  return (await res.json()) as T;
}

export const buscarFiltros = (signal?: AbortSignal) => getJson<Filtros>("/api/painel/filtros", {}, signal);

export const buscarPainelAlunos = (
  f: { curso: string | null; periodos: string[]; indicadores: Categoria[] },
  signal?: AbortSignal
) => getJson<AlunosView>("/api/painel/alunos", { curso: f.curso, periodos: f.periodos, indicadores: f.indicadores }, signal);

export const buscarPainelDisciplinas = (
  f: { curso: string | null; periodos: string[]; disciplinas: string[] },
  signal?: AbortSignal
) =>
  getJson<DisciplinasView>(
    "/api/painel/disciplinas",
    { curso: f.curso, periodos: f.periodos, disciplinas: f.disciplinas },
    signal
  );

export const buscarOpcoesDisciplinas = (curso: string | null, signal?: AbortSignal) =>
  getJson<string[]>("/api/painel/disciplinas/opcoes", { curso }, signal);
