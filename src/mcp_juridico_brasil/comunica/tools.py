"""Tools MCP do modulo Comunica/DJEN - descoberta e feed de carteira processual.

Este modulo resolve a lacuna estrutural do DataJud: como o DataJud nao indexa
as partes, ele so acompanha numeros ja conhecidos. O Comunica indexa parte e
OAB e por isso permite DESCOBRIR a carteira de um ente publico.

DISCLAIMER (OAB Rec. 001/2024): ferramenta de apoio ao advogado publico. Nao
constitui consultoria juridica e nao substitui o controle oficial de prazos
nem a conferencia no portal do tribunal.
"""

from __future__ import annotations

import collections
import datetime
from typing import Any

from mcp_juridico_brasil._core.errors import JuridicoValidationError
from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.comunica.client import (
    ComunicaClient,
    filtrar_por_destinatario,
    normalizar,
)
from mcp_juridico_brasil.shared.validators import validar_numero_cnj

logger = get_logger(__name__)

_client = ComunicaClient()

_DISCLAIMER = (
    "AVISO: dados do Diario de Justica Eletronico Nacional (DJEN/Comunica), "
    "publicos por forca da Resolucao CNJ 455/2022. Ferramenta de apoio ao "
    "advogado publico responsavel - nao constitui consultoria juridica e nao "
    "substitui o controle oficial de prazos. (OAB Recomendacao 001/2024)"
)

_LIMITACAO = (
    "LIMITACAO ESTRUTURAL: o Comunica e um feed de PUBLICACOES, nao um cadastro "
    "de processos. Um feito sem publicacao na janela consultada nao aparece, e a "
    "cobertura util comeca em 2024. Para a carteira historica completa e preciso "
    "o Dominio Judicial Eletronico (credencial ICP-Brasil) ou provider comercial."
)

_MAX_DIAS_JANELA = 400


def _valida_janela(dias: int) -> tuple[str, str]:
    if dias < 1 or dias > _MAX_DIAS_JANELA:
        raise JuridicoValidationError(
            field="dias",
            value=str(dias),
            reason=f"Informe entre 1 e {_MAX_DIAS_JANELA} dias.",
        )
    fim = datetime.date.today()
    return (fim - datetime.timedelta(days=dias)).isoformat(), fim.isoformat()


def _polo_legivel(polo: str | None) -> str:
    return {"A": "ativo", "P": "passivo"}.get((polo or "").upper(), "nao informado")


def _resumir(comunicacoes: list[dict[str, Any]], termos: list[str]) -> dict[str, Any]:
    """Agrupa comunicacoes por processo, montando a carteira."""
    obrig = [normalizar(t) for t in termos]
    processos: dict[str, dict[str, Any]] = {}

    for c in comunicacoes:
        numero = c.get("numero_processo") or ""
        dests = c.get("destinatarios") or []
        meu = next(
            (d for d in dests if all(t in normalizar(d.get("nome")) for t in obrig)),
            None,
        )
        p = processos.setdefault(
            numero,
            {
                "numero_processo": numero,
                "numero_formatado": c.get("numeroprocessocommascara"),
                "tribunal": c.get("siglaTribunal"),
                "orgao_julgador": c.get("nomeOrgao"),
                "classe": c.get("nomeClasse"),
                "polo_do_ente": _polo_legivel(meu.get("polo") if meu else None),
                "total_comunicacoes": 0,
                "ultima_publicacao": "",
                "ultimo_tipo": "",
                "outras_partes": [],
                "advogados": [],
            },
        )
        p["total_comunicacoes"] += 1
        data = c.get("data_disponibilizacao") or ""
        if data >= p["ultima_publicacao"]:
            p["ultima_publicacao"] = data
            p["ultimo_tipo"] = c.get("tipoComunicacao") or c.get("tipoDocumento") or ""
        for d in dests:
            nome = d.get("nome")
            if nome and not all(t in normalizar(nome) for t in obrig):
                if nome not in p["outras_partes"]:
                    p["outras_partes"].append(nome)
        for a in c.get("destinatarioadvogados") or []:
            adv = a.get("advogado") or {}
            rotulo = f"{adv.get('nome')} - OAB {adv.get('uf_oab')}/{adv.get('numero_oab')}"
            if adv.get("nome") and rotulo not in p["advogados"]:
                p["advogados"].append(rotulo)

    return processos


async def descobrir_carteira_processual(
    nome_da_parte: str,
    termos_de_confirmacao: list[str] | None = None,
    dias: int = 60,
    tribunal: str | None = None,
    max_comunicacoes: int = 1000,
) -> dict[str, object]:
    """Descobre os processos de um ente pelo NOME DA PARTE, via DJEN/Comunica.

    Esta e a unica via publica e gratuita de levantar a carteira processual sem
    partir de uma lista de numeros CNJ - o DataJud nao indexa partes.

    Uso tipico para um departamento juridico municipal:
        descobrir_carteira_processual(
            nome_da_parte="PRADOPOLIS",
            termos_de_confirmacao=["MUNICIPIO", "PREFEITURA"],
            dias=60,
        )

    Args:
        nome_da_parte: Termo de busca do nome da parte (ex: 'PRADOPOLIS').
                       O filtro da API e difuso e casa tokens isolados.
        termos_de_confirmacao: Lista de termos alternativos usada para refinar
                       localmente o resultado - mantem so os destinatarios que
                       contenham nome_da_parte E ao menos um destes termos.
                       Descarta homonimos (ex: 'Residencial Pradopolis SPE').
        dias: Tamanho da janela retroativa de publicacoes (padrao 60, max 400).
        tribunal: Sigla para restringir a busca (ex: 'TJSP', 'TRT15').
        max_comunicacoes: Teto de comunicacoes lidas na varredura.

    Returns:
        Carteira agrupada por processo, com estatisticas por tribunal, classe
        e polo, alem dos avisos legais e das limitacoes da fonte.
    """
    inicio, fim = _valida_janela(dias)
    logger.info("comunica_descobrir_carteira", nome=nome_da_parte, dias=dias, tribunal=tribunal)

    brutas = await _client.buscar(
        nome_parte=nome_da_parte,
        sigla_tribunal=tribunal,
        data_inicio=inicio,
        data_fim=fim,
        max_itens=max_comunicacoes,
    )
    confirmadas = filtrar_por_destinatario(brutas, [nome_da_parte], termos_de_confirmacao)
    processos = _resumir(confirmadas, [nome_da_parte])

    lista = sorted(processos.values(), key=lambda p: p["ultima_publicacao"], reverse=True)

    return {
        "parametros": {
            "nome_da_parte": nome_da_parte,
            "termos_de_confirmacao": termos_de_confirmacao or [],
            "janela": {"inicio": inicio, "fim": fim, "dias": dias},
            "tribunal": tribunal,
        },
        "total_processos": len(lista),
        "total_comunicacoes_confirmadas": len(confirmadas),
        "total_comunicacoes_brutas": len(brutas),
        "descartadas_por_homonimia": len(brutas) - len(confirmadas),
        "por_tribunal": dict(collections.Counter(p["tribunal"] for p in lista)),
        "por_polo": dict(collections.Counter(p["polo_do_ente"] for p in lista)),
        "por_classe": dict(collections.Counter(p["classe"] for p in lista).most_common(15)),
        "processos": lista,
        "disclaimer": _DISCLAIMER,
        "limitacao": _LIMITACAO,
        "fonte": "DJEN / API Comunica (comunicaapi.pje.jus.br) - acesso publico",
    }


async def listar_publicacoes(
    nome_da_parte: str | None = None,
    numero_oab: str | None = None,
    uf_oab: str | None = None,
    numero_processo: str | None = None,
    termos_de_confirmacao: list[str] | None = None,
    dias: int = 7,
    tribunal: str | None = None,
    incluir_inteiro_teor: bool = True,
    max_comunicacoes: int = 500,
) -> dict[str, object]:
    """Lista as publicacoes do DJEN com o inteiro teor, para leitura diaria.

    E o feed que substitui a leitura manual do diario oficial. Pode ser filtrado
    por parte (o ente), pela OAB de cada procurador ou por processo.

    Args:
        nome_da_parte: Nome da parte (ex: 'PRADOPOLIS').
        numero_oab: Numero da OAB do procurador (ex: '201321').
        uf_oab: UF da OAB (ex: 'SP'). Use junto com numero_oab.
        numero_processo: Numero CNJ para ver so as publicacoes de um processo.
        termos_de_confirmacao: Refino local do nome da parte (ver
                       descobrir_carteira_processual).
        dias: Janela retroativa em dias (padrao 7).
        tribunal: Sigla do tribunal para restringir.
        incluir_inteiro_teor: Se True, devolve o texto integral da publicacao -
                       e dele que sai o prazo e o ato a praticar.
        max_comunicacoes: Teto de itens retornados.

    Returns:
        Publicacoes ordenadas da mais recente para a mais antiga.
    """
    if numero_processo is not None and not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato invalido. Use o padrao CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    inicio, fim = _valida_janela(dias)
    brutas = await _client.buscar(
        nome_parte=nome_da_parte,
        numero_oab=numero_oab,
        uf_oab=uf_oab,
        numero_processo=numero_processo,
        sigla_tribunal=tribunal,
        data_inicio=inicio,
        data_fim=fim,
        max_itens=max_comunicacoes,
    )

    if nome_da_parte and termos_de_confirmacao:
        brutas = filtrar_por_destinatario(brutas, [nome_da_parte], termos_de_confirmacao)

    publicacoes = []
    for c in sorted(brutas, key=lambda x: x.get("data_disponibilizacao") or "", reverse=True):
        item: dict[str, Any] = {
            "id": c.get("id"),
            "data_disponibilizacao": c.get("data_disponibilizacao"),
            "tribunal": c.get("siglaTribunal"),
            "orgao_julgador": c.get("nomeOrgao"),
            "numero_processo": c.get("numero_processo"),
            "numero_formatado": c.get("numeroprocessocommascara"),
            "classe": c.get("nomeClasse"),
            "tipo_comunicacao": c.get("tipoComunicacao"),
            "tipo_documento": c.get("tipoDocumento"),
            "meio": c.get("meiocompleto") or c.get("meio"),
            "link_validacao": c.get("link"),
            "partes": [
                {"nome": d.get("nome"), "polo": _polo_legivel(d.get("polo"))}
                for d in (c.get("destinatarios") or [])
            ],
            "advogados": [
                {
                    "nome": (a.get("advogado") or {}).get("nome"),
                    "oab": f"{(a.get('advogado') or {}).get('uf_oab')}/"
                    f"{(a.get('advogado') or {}).get('numero_oab')}",
                }
                for a in (c.get("destinatarioadvogados") or [])
            ],
        }
        if incluir_inteiro_teor:
            item["texto"] = c.get("texto")
        publicacoes.append(item)

    return {
        "janela": {"inicio": inicio, "fim": fim, "dias": dias},
        "total": len(publicacoes),
        "publicacoes": publicacoes,
        "instrucao_triagem": (
            "Para cada publicacao: identifique o ato a praticar, o prazo em dias "
            "e se ha determinacao judicial expressa. Em seguida chame "
            "calcular_proximo_prazo com data_intimacao_iso igual a "
            "data_disponibilizacao, parte_fazenda_publica=True quando a parte for "
            "o ente publico, e o rito adequado. Nao emita juizo sobre o merito."
        ),
        "disclaimer": _DISCLAIMER,
        "limitacao": _LIMITACAO,
        "fonte": "DJEN / API Comunica (comunicaapi.pje.jus.br) - acesso publico",
    }


__all__ = ["descobrir_carteira_processual", "listar_publicacoes"]
