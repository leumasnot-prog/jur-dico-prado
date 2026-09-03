"""Console local de testes das tools do MCP Jurídico Brasil.

Sobe um servidor HTTP em localhost que chama DIRETAMENTE as funções das tools do
MCP e mostra a resposta crua. Serve para exercitar o servidor sem precisar de um
cliente MCP configurado.

    uv run python scripts/console_local.py
    # abre em http://127.0.0.1:8777

Não faz parte do pacote publicado: é ferramenta de desenvolvimento. Todas as
operações expostas aqui são somente leitura — a confirmação de leitura de
intimação, que tem efeito jurídico irreversível, é deliberadamente omitida.
"""

from __future__ import annotations

import datetime
import json
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from mcp_juridico_brasil.comunica.tools import (
    descobrir_carteira_processual,
    listar_publicacoes,
)
from mcp_juridico_brasil.datajud.tribunais import listar_tribunais
from mcp_juridico_brasil.dje.tools import listar_intimacoes, verificar_certificado_dje
from mcp_juridico_brasil.movimentacoes.tools import listar_movimentacoes
from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo
from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero
from mcp_juridico_brasil.resumo.tools import resumir_andamento

HOJE = datetime.date.today().isoformat()


async def _tribunais() -> dict[str, Any]:
    t = listar_tribunais()
    return {"total": len(t), "tribunais": t}


# Cada entrada: (função, descrição, campos do formulário)
# Campo: (nome, rótulo, tipo, valor padrão)
TOOLS: dict[str, tuple[Callable[..., Awaitable[Any]], str, list[tuple[str, str, str, Any]]]] = {
    "verificar_certificado_dje": (
        verificar_certificado_dje,
        "Diagnóstico do certificado A1 do Município: abre o .pfx, confere o CNPJ e "
        "avisa quando vence. Local — não contata servidor nenhum.",
        [],
    ),
    "descobrir_carteira_processual": (
        descobrir_carteira_processual,
        "Descobre os processos do Município pelo NOME DA PARTE no diário nacional. "
        "É o que o DataJud não faz, porque não indexa partes.",
        [
            ("nome_da_parte", "Nome da parte", "text", "PRADOPOLIS"),
            ("termos_de_confirmacao", "Termos de confirmação (vírgula)", "text",
             "MUNICIPIO,PREFEITURA"),
            ("dias", "Janela (dias)", "number", 20),
            ("tribunal", "Tribunal (opcional)", "text", ""),
        ],
    ),
    "listar_publicacoes": (
        listar_publicacoes,
        "Feed do DJEN com inteiro teor. Filtra por parte, por OAB do procurador ou "
        "por processo.",
        [
            ("nome_da_parte", "Nome da parte", "text", "PRADOPOLIS"),
            ("termos_de_confirmacao", "Termos de confirmação (vírgula)", "text",
             "MUNICIPIO,PREFEITURA"),
            ("numero_oab", "OAB do procurador (opcional)", "text", ""),
            ("uf_oab", "UF da OAB", "text", "SP"),
            ("dias", "Janela (dias)", "number", 7),
        ],
    ),
    "calcular_proximo_prazo": (
        calcular_proximo_prazo,
        "Prazo em dias úteis com o prazo diferenciado do ente público. Troque o rito "
        "para ver o art. 183 do CPC ser afastado.",
        [
            ("numero_processo", "Número CNJ", "text", "4000698-43.2026.8.26.0222"),
            ("tribunal", "Tribunal", "text", "TJSP"),
            ("tipo_ato", "Tipo de ato", "text", "Contestacao"),
            ("uf", "UF", "text", "SP"),
            ("data_intimacao_iso", "Disponibilização (AAAA-MM-DD)", "text", HOJE),
            ("parte_fazenda_publica", "Fazenda Pública?", "bool", True),
            ("rito", "Rito", "select:comum,juizado_especial_fazenda,execucao_fiscal,trabalhista",
             "comum"),
            ("data_e_disponibilizacao_djen", "Data é do DJEN? (art. 224 §2º)", "bool", True),
        ],
    ),
    "buscar_processo_por_numero": (
        buscar_processo_por_numero,
        "Consulta o processo no DataJud CNJ.",
        [
            ("numero_processo", "Número CNJ", "text", "4000698-43.2026.8.26.0222"),
            ("tribunal", "Tribunal", "text", "TJSP"),
        ],
    ),
    "listar_movimentacoes": (
        listar_movimentacoes,
        "Histórico de andamentos do processo (DataJud).",
        [
            ("numero_processo", "Número CNJ", "text", "4000698-43.2026.8.26.0222"),
            ("tribunal", "Tribunal", "text", "TJSP"),
            ("limite", "Limite", "number", 10),
        ],
    ),
    "resumir_andamento": (
        resumir_andamento,
        "Dados do processo + instrução de resumo para o modelo.",
        [
            ("numero_processo", "Número CNJ", "text", "4000698-43.2026.8.26.0222"),
            ("tribunal", "Tribunal", "text", "TJSP"),
        ],
    ),
    "listar_intimacoes": (
        listar_intimacoes,
        "Intimações do Domicílio Judicial Eletrônico. EXIGE credenciais e certificado — "
        "sem elas devolve erro explicando o que falta.",
        [
            ("numero_processo", "Número CNJ (opcional)", "text", ""),
            ("apenas_pendentes", "Só pendentes?", "bool", True),
        ],
    ),
    "listar_tribunais": (_tribunais, "Os 91 tribunais suportados.", []),
}

_LISTA = {"termos_de_confirmacao"}


def _converter(campos: list[tuple[str, str, str, Any]], corpo: dict[str, Any]) -> dict[str, Any]:
    """Converte o payload do formulário nos tipos que a tool espera."""
    kwargs: dict[str, Any] = {}
    for nome, _rot, tipo, _pad in campos:
        if nome not in corpo:
            continue
        valor = corpo[nome]
        if isinstance(valor, str) and not valor.strip() and tipo != "bool":
            continue  # campo vazio = usar o padrão da tool
        if nome in _LISTA:
            kwargs[nome] = [t.strip() for t in str(valor).split(",") if t.strip()]
        elif tipo == "number":
            kwargs[nome] = int(valor)
        elif tipo == "bool":
            kwargs[nome] = bool(valor)
        else:
            kwargs[nome] = valor
    return kwargs


async def executar(request: Request) -> JSONResponse:
    nome = request.path_params["tool"]
    entrada = TOOLS.get(nome)
    if entrada is None:
        return JSONResponse({"erro": f"tool desconhecida: {nome}"}, status_code=404)

    funcao, _desc, campos = entrada
    try:
        corpo = await request.json() if await request.body() else {}
    except json.JSONDecodeError:
        corpo = {}

    inicio = datetime.datetime.now()
    try:
        resultado = await funcao(**_converter(campos, corpo))
        ms = int((datetime.datetime.now() - inicio).total_seconds() * 1000)
        return JSONResponse({"ok": True, "ms": ms, "resultado": resultado})
    except Exception as exc:
        ms = int((datetime.datetime.now() - inicio).total_seconds() * 1000)
        return JSONResponse(
            {
                "ok": False,
                "ms": ms,
                "erro": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc().splitlines()[-6:],
            },
            status_code=200,
        )


async def pagina(_request: Request) -> HTMLResponse:
    html = (Path(__file__).parent / "console_local.html").read_text(encoding="utf-8")
    cards = []
    for nome, (_f, desc, campos) in TOOLS.items():
        cards.append({"nome": nome, "descricao": desc, "campos": campos})
    return HTMLResponse(html.replace("__TOOLS__", json.dumps(cards, ensure_ascii=False)))


app = Starlette(
    routes=[
        Route("/", pagina),
        Route("/t/{tool}", executar, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    print("\n  Console do MCP Jurídico  ->  http://127.0.0.1:8777\n")
    uvicorn.run(app, host="127.0.0.1", port=8777, log_level="warning")
