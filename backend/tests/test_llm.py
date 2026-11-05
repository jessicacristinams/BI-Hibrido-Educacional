"""Cliente do modelo: com o Ollama, a API nativa envia o tamanho do contexto."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import LLMProviderError
from app.services.llm import OllamaClient, OpenAIClient, build_llm_client, eh_ollama


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("http://localhost:11434/v1", True),
        ("http://ollama:11434/v1", True),
        ("http://host.docker.internal:11434/v1", True),
        (None, False),
        ("https://api.openai.com/v1", False),
    ],
)
def test_detecta_ollama(url, esperado):
    assert eh_ollama(url) is esperado


def test_escolhe_o_cliente_pela_url():
    ollama = Settings(_env_file=None, openai_api_key="ollama", openai_base_url="http://localhost:11434/v1")
    assert isinstance(build_llm_client(ollama), OllamaClient)
    assert isinstance(build_llm_client(Settings(_env_file=None, openai_api_key="sk-x")), OpenAIClient)


def test_ollama_envia_num_ctx_e_formato_json():
    pedidos = []

    def responder(req: httpx.Request) -> httpx.Response:
        pedidos.append((req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"ok": true}'}})

    cliente = OllamaClient("http://localhost:11434/v1", "qwen2.5-coder:7b", 10, 8192, transport=httpx.MockTransport(responder))
    assert cliente.complete("sistema", [{"role": "user", "content": "oi"}], json_mode=True) == '{"ok": true}'
    caminho, corpo = pedidos[0]
    assert caminho == "/api/chat"  # API nativa, não /v1
    assert corpo["options"] == {"temperature": 0, "num_ctx": 8192}
    assert corpo["format"] == "json"
    assert corpo["messages"][0] == {"role": "system", "content": "sistema"}


def test_ollama_fora_do_ar_vira_erro_amigavel():
    def falhar(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusada")

    cliente = OllamaClient("http://localhost:11434", "m", 10, 8192, transport=httpx.MockTransport(falhar))
    with pytest.raises(LLMProviderError):
        cliente.complete("s", [{"role": "user", "content": "oi"}])
