"""Tool MCP: monitorar_processo.

Fase 2: verifica se houve atualizacao desde uma data de referencia.
Fase 3 (provider comercial): substituir polling por webhook push.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.monitoramento.store import obter_snapshot, salvar_snapshot
from mcp_juridico_brasil.shared.provider import get_provider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)

async def monitorar_processo(
    numero_processo: str,
    tribunal: str,
    desde_iso: str,
) -> dict[str, object]:
    """Verifica se um processo teve atualização após a data informada.

    Implementação Fase 2: polling via DataJud (sem tempo real).
    Fase 3 substituirá por notificação push via provider comercial.

    Args:
        numero_processo: Número no formato CNJ.
        tribunal: Sigla do tribunal (obrigatória para monitoramento).
        desde_iso: Data/hora de referência em formato ISO 8601
                   (ex: '2024-01-15T08:00:00').

    Returns:
        Dicionário indicando se houve atualização e a data da última.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    try:
        datetime.fromisoformat(desde_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JuridicoValidationError(
            field="desde_iso",
            value=desde_iso,
            reason="Data inválida. Use formato ISO 8601: YYYY-MM-DDTHH:MM:SS",
        ) from exc

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info(
        "monitorar_processo_solicitado",
        numero=numero_normalizado,
        tribunal=tribunal,
        desde=desde_iso,
    )

    processo = await get_provider().buscar_processo(numero_normalizado, tribunal)
    ultima = processo.data_ultima_atualizacao
    ultima_iso = ultima.isoformat() if ultima else None

    desde = datetime.fromisoformat(desde_iso.replace("Z", "+00:00"))
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    houve_atualizacao = ultima is not None and ultima > desde

    # Diff contra o snapshot anterior (antes de sobrescreve-lo).
    anterior = obter_snapshot(numero_normalizado)
    vistos: set[str] = set()
    if anterior:
        for m in (anterior.get("dados") or {}).get("movimentacoes") or []:
            vistos.add(f"{m.get('codigo')}|{m.get('data_hora')}")

    novas = [
        m.model_dump(mode="json")
        for m in processo.movimentacoes
        if m.data_hora > desde
        and (not vistos or f"{m.codigo}|{m.data_hora.isoformat()}" not in vistos)
    ]

    # CORRECAO (etapa 2): grava o snapshot para alimentar
    # listar_processos_monitorados e o resource processo://{n}/snapshot.
    salvar_snapshot(numero_normalizado, tribunal, processo.model_dump(mode="json"))

    return {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "desde": desde_iso,
        "houve_atualizacao": houve_atualizacao,
        "data_ultima_atualizacao_datajud": ultima_iso,
        "movimentacoes_novas": novas,
        "total_movimentacoes_novas": len(novas),
        "comparado_com_snapshot_anterior": anterior is not None,
        "aviso_defasagem": (
            "O DataJud pode ter atraso de T+1 a T+7 dias. "
            "Para monitoramento de prazos críticos, use um provider comercial "
            "com webhook (Fase 3) ou acesse diretamente o portal do tribunal."
        ),
    }


__all__ = ["monitorar_processo"]
