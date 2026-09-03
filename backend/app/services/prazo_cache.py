"""Cálculo completo de prazo, memoizado.

O prazo é recalculado NA LEITURA (decisão do §3 da Task 2): assim uma correção
de regra ou um feriado municipal novo valem para todo o acervo, sem migração.

O custo disso é recalcular a cada listagem. Como a combinação
(data, ato, rito, uf) se repete muito no acervo — 250 publicações caem em poucas
dezenas de combinações — um cache resolve sem abrir mão da decisão.
"""

from __future__ import annotations

import datetime
from typing import Any

_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}


async def prazo_completo(
    disponibilizacao: datetime.date, ato: str | None, rito: str | None, uf: str = "SP"
) -> dict[str, Any] | None:
    """Devolve a memória de cálculo inteira, ou None se não houver ato inferido."""
    if not ato:
        return None
    chave = (disponibilizacao.isoformat(), ato, rito or "comum", uf)
    if chave in _cache:
        return _cache[chave]

    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    try:
        r = await calcular_proximo_prazo(
            numero_processo="0000000-00.0000.0.00.0000",
            tribunal="TJSP", tipo_ato=ato, uf=uf,
            data_intimacao_iso=disponibilizacao.isoformat(),
            parte_fazenda_publica=True, rito=rito or "comum",
            data_e_disponibilizacao_djen=True,
        )
    except Exception:
        return None

    resumo = {
        "ato": r["tipo_ato"],
        "rito": r["rito"],
        "dias": r["dias_uteis_prazo"],
        "simples": r["dias_uteis_prazo_simples"],
        "mult": r.get("multiplicador", 1),
        "disponibilizacao": r.get("data_disponibilizacao_iso"),
        "publicacao": r["data_intimacao_iso"],
        "termo": r["termo_inicial_iso"],
        "fim": r["data_final_iso"],
        "fundamento": r["fundamento_prazo"],
        "base_legal": r["base_legal"],
        "obstaculos": [[o["data"], o["descricao"]]
                       for o in r.get("feriados_e_recessos_no_periodo", [])],
    }
    # A regra guia a escolha do tooltip pedagógico na interface.
    fund = str(resumo["fundamento"])
    resumo["regra"] = (
        "quadruplo" if resumo["mult"] == 4
        else "dobro_clt" if resumo["mult"] == 2 and "779/69" in fund
        else "dobro_cpc" if resumo["mult"] == 2
        else "jefp" if "12.153" in fund
        else "proprio" if "183, §2" in fund or "183, §2º" in fund or "proprio" in fund.lower()
        else "nao_fazenda"
    )
    _cache[chave] = resumo
    return resumo


def limpar() -> None:
    """Descarta o cache — usar após mudança de regra ou de feriado local."""
    _cache.clear()
