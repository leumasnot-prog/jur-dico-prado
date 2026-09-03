"""Ingestão do DJEN e montagem do acervo permanente.

O domínio processual vem do MCP (`mcp_juridico_brasil`): descoberta no DJEN,
inferência de ato e rito, e cálculo de prazo com as regras do ente público.
Este módulo só orquestra e persiste.

DECISÃO CENTRAL: o prazo é RECALCULADO na leitura, não lido do banco. A coluna
`vencimento` existe apenas para permitir índice e ordenação em SQL. Assim,
corrigir uma regra (como o DL 779/69) ou cadastrar um feriado municipal passa a
valer para todo o acervo, sem migração de dados.
"""

from __future__ import annotations

import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import hoje, settings
from app.models import Processo, Procurador, Publicacao, Triagem

logger = structlog.get_logger(__name__)


def _mcp():
    """Importa o MCP tarde: mantém o import deste módulo barato e testável."""
    from mcp_juridico_brasil.comunica.client import (
        ComunicaClient,
        filtrar_por_destinatario,
        identificar_polo,
        limpar_html,
        normalizar,
        prazo_mencionado,
    )
    return {
        "Cliente": ComunicaClient, "filtrar": filtrar_por_destinatario,
        "polo": identificar_polo, "limpar": limpar_html, "normalizar": normalizar,
        "prazo_texto": prazo_mencionado,
    }


def _inferir(documento: str, classe: str, tribunal: str) -> tuple[str, str]:
    """Ato provável e rito, pelas mesmas regras do módulo jurídico do MCP."""
    d, c, t = (documento or "").lower(), (classe or "").lower(), (tribunal or "").upper()
    rito = ("trabalhista" if t.startswith("TRT") or t == "TST"
            else "execucao_fiscal" if "execução fiscal" in c or "execucao fiscal" in c
            else "juizado_especial_fazenda" if "juizado" in c or "inominado" in c
            else "comum")
    if "execução fiscal" in c or "execucao fiscal" in c:
        ato = "Embargos a Execucao Fiscal"
    elif "inominado" in c:
        ato = "Recurso Inominado"
    elif "cumprimento de sentença" in c or "cumprimento de sentenca" in c:
        ato = "Impugnacao"
    elif "acórdão" in d or "acordao" in d:
        ato = "Embargos de Declaracao"
    elif "sentença" in d or "sentenca" in d:
        ato = "Recurso de Apelacao"
    elif "citação" in d or "citacao" in d or "notificação" in d or "notificacao" in d:
        ato = "Contestacao"
    else:
        ato = "Manifestacao"
    return ato, rito


async def calcular_vencimento(
    disponibilizacao: datetime.date, ato: str, rito: str
) -> datetime.date | None:
    """Delegado ao MCP, que é a fonte de verdade das regras de prazo."""
    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    try:
        r = await calcular_proximo_prazo(
            numero_processo="0000000-00.0000.0.00.0000",  # não usado quando a data é dada
            tribunal="TJSP", tipo_ato=ato, uf=settings.juridico_uf,
            data_intimacao_iso=disponibilizacao.isoformat(),
            parte_fazenda_publica=True, rito=rito, data_e_disponibilizacao_djen=True,
        )
        return datetime.date.fromisoformat(str(r["data_final_iso"]))
    except Exception as exc:  # regra nova ou ato desconhecido não pode derrubar a ingestão
        logger.warning("vencimento_nao_calculado", ato=ato, rito=rito, erro=type(exc).__name__)
        return None


async def varrer_e_persistir(
    sessao: AsyncSession, *, dias: int | None = None, tribunal: str | None = None
) -> dict[str, Any]:
    """Lê o DJEN, refina a homonímia e grava o que for novo.

    Idempotente: rodar duas vezes não duplica nada e não perde nada.
    """
    m = _mcp()
    dias = dias or settings.varredura_janela_dias
    fim = hoje()
    inicio = fim - datetime.timedelta(days=dias)

    # Assinatura do MCP: sigla_tribunal (nao "tribunal"), e devolve LISTA.
    brutas = await m["Cliente"]().buscar(
        nome_parte=settings.juridico_nome_parte, sigla_tribunal=tribunal,
        data_inicio=inicio.isoformat(), data_fim=fim.isoformat(), max_itens=2000,
    )
    # filtrar_por_destinatario recebe LISTA de termos obrigatorios.
    confirmadas = m["filtrar"](
        brutas, [settings.juridico_nome_parte], settings.termos_confirmacao
    )

    principal = m["normalizar"](settings.juridico_nome_parte)
    confirmacao = [m["normalizar"](t) for t in settings.termos_confirmacao]

    def e_o_ente(nome: str | None) -> bool:
        n = m["normalizar"](nome)
        return principal in n and (not confirmacao or any(t in n for t in confirmacao))

    processos: dict[str, dict] = {}
    linhas_pub: list[dict] = []

    for c in confirmadas:
        numero = str(c.get("numero_processo") or "")
        if not numero:
            continue
        destinatarios = c.get("destinatarios") or []
        partes = [{"nome": d.get("nome", ""), "polo": m["polo"](d.get("polo")),
                   "e_o_ente": e_o_ente(d.get("nome"))}
                  for d in destinatarios if d.get("nome")]
        advogados = [{"nome": (a.get("advogado") or {}).get("nome", ""),
                      "oab": f"{(a.get('advogado') or {}).get('uf_oab')}/"
                             f"{(a.get('advogado') or {}).get('numero_oab')}"}
                     for a in (c.get("destinatarioadvogados") or [])
                     if (a.get("advogado") or {}).get("nome")]

        classe, tribunal_pub = c.get("nomeClasse") or "", c.get("siglaTribunal") or ""
        documento = c.get("tipoDocumento") or c.get("tipoComunicacao") or ""
        ato, rito = _inferir(documento, classe, tribunal_pub)
        data_disp = datetime.date.fromisoformat(str(c.get("data_disponibilizacao"))[:10])
        texto = m["limpar"](c.get("texto"))

        p = processos.setdefault(numero, {
            "numero_processo": numero,
            "numero_formatado": c.get("numeroprocessocommascara"),
            "tribunal": tribunal_pub, "orgao": c.get("nomeOrgao"), "classe": classe or None,
            "polo_do_ente": "nao_informado", "partes_contrarias": [], "advogados": [],
        })
        meu = next((x for x in partes if x["e_o_ente"]), None)
        if meu and p["polo_do_ente"] == "nao_informado":
            p["polo_do_ente"] = meu["polo"]
        for x in partes:
            if not x["e_o_ente"] and x["nome"] not in p["partes_contrarias"]:
                p["partes_contrarias"].append(x["nome"])
        for a in advogados:
            rotulo = f"{a['nome']} — OAB {a['oab']}"
            if rotulo not in p["advogados"]:
                p["advogados"].append(rotulo)

        linhas_pub.append({
            "id": str(c.get("id")), "numero_processo": numero,
            "data_disponibilizacao": data_disp, "tribunal": tribunal_pub,
            "orgao": c.get("nomeOrgao"), "classe": classe or None,
            "tipo_comunicacao": c.get("tipoComunicacao"), "tipo_documento": c.get("tipoDocumento"),
            "meio": c.get("meiocompleto") or c.get("meio"), "link_validacao": c.get("link"),
            "partes": partes, "advogados": advogados, "texto": texto or None,
            "prazo_no_texto": m["prazo_texto"](texto),
            "ato_inferido": ato, "rito_inferido": rito,
            "vencimento": await calcular_vencimento(data_disp, ato, rito),
        })

    # Processo evolui -> UPDATE. Publicação é imutável -> DO NOTHING.
    for p in processos.values():
        stmt = insert(Processo).values(**p)
        await sessao.execute(stmt.on_conflict_do_update(
            index_elements=["numero_processo"],
            set_={k: stmt.excluded[k] for k in
                  ("numero_formatado", "orgao", "classe", "polo_do_ente",
                   "partes_contrarias", "advogados")},
        ))

    novas = 0
    for linha in linhas_pub:
        r = await sessao.execute(
            insert(Publicacao).values(**linha).on_conflict_do_nothing(index_elements=["id"])
        )
        if r.rowcount:
            novas += 1

    await sessao.flush()
    atribuidas = await rotear_por_oab(sessao)
    await sessao.commit()

    resultado = {
        "janela_inicio": inicio.isoformat(), "janela_fim": fim.isoformat(),
        "comunicacoes_brutas": len(brutas), "comunicacoes_confirmadas": len(confirmadas),
        "descartadas_por_homonimia": len(brutas) - len(confirmadas),
        "processos": len(processos), "publicacoes_novas": novas,
        "atribuidas_por_oab": atribuidas,
    }
    logger.info("varredura_concluida", **resultado)
    return resultado


async def rotear_por_oab(sessao: AsyncSession) -> int:
    """Atribui publicações sem responsável ao procurador cuja OAB foi intimada.

    Publicação com OAB desconhecida NÃO some: fica sem responsável, e a fila do
    chefe é justamente a das não atribuídas.
    """
    mapa: dict[str, int] = {}
    achado = await sessao.execute(select(Procurador).where(Procurador.ativo.is_(True)))
    for p in achado.scalars():
        mapa[f"{p.oab_uf.upper()}/{p.oab_numero}"] = p.usuario_id
    if not mapa:
        return 0

    sem_dono = await sessao.execute(
        select(Publicacao).outerjoin(Triagem).where(Triagem.publicacao_id.is_(None))
    )
    atribuidas = 0
    for pub in sem_dono.scalars():
        for a in (pub.advogados or []):
            uid = mapa.get(str(a.get("oab", "")).upper())
            if uid:
                sessao.add(Triagem(publicacao_id=pub.id, responsavel_id=uid))
                atribuidas += 1
                break
    await sessao.flush()
    return atribuidas
