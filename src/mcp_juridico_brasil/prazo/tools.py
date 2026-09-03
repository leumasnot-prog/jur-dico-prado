"""Tool MCP: calcular_proximo_prazo.

Fase 2: cálculo de prazos processuais em dias úteis com calendário forense.

Regras implementadas:
- Art. 219 CPC: prazos contados em dias úteis
- Art. 224 CPC: termo inicial no primeiro dia útil após a intimação/publicação
- Art. 220 CPC: recesso forense (20/dez a 20/jan) suspende a contagem
- Feriados nacionais via workalendar + Sexta-feira Santa
- Feriados estaduais via workalendar subregions (parâmetro uf opcional)
- Feriados municipais informados pelo operador (parâmetro feriados_municipais)
- Art. 183 CPC: prazo em dobro para a Fazenda Pública (União, Estados, DF,
  Municípios e suas autarquias e fundações de direito público)
- Art. 183, §2º CPC: o dobro NÃO se aplica quando a lei fixa prazo próprio
- Art. 7º da Lei 12.153/2009: NÃO há prazo diferenciado no Juizado Especial
  da Fazenda Pública - o dobro é afastado nesse rito

IMPORTANTE: Este cálculo é uma estimativa técnica de apoio ao advogado.
Não substitui a verificação no portal do tribunal nem a análise do profissional
habilitado. Feriados municipais, pontos facultativos e suspensões extraordinárias
NÃO são automaticamente considerados.
"""

from __future__ import annotations

import datetime

from mcp_juridico_brasil._core import JuridicoValidationError, get_logger
from mcp_juridico_brasil.prazo.calendario import (
    UF_PARA_ISO,
    calcular_prazo,
    proximo_dia_util,
)
from mcp_juridico_brasil.shared.provider import get_provider
from mcp_juridico_brasil.shared.validators import normalizar_numero_cnj, validar_numero_cnj

logger = get_logger(__name__)
# Tabela de prazos CPC mais comuns em dias uteis (art. 219 CPC)
_PRAZOS_CPC: dict[str, int] = {
    "Contestacao": 15,
    "Recurso de Apelacao": 15,
    "Agravo Regimental": 15,
    "Agravo Interno": 15,
    "Embargos de Declaracao": 5,
    "Recurso Especial": 15,
    "Recurso Extraordinario": 15,
    "Contrarrazoes": 15,
    "Manifestacao": 15,
    "Impugnacao": 15,
    "Embargos de Divergencia": 15,
    "Agravo em Recurso Especial": 15,
    "Agravo em Recurso Extraordinario": 15,
    "Reclamacao": 15,
    "Resposta": 15,
    # Prazos proprios (art. 183, §2º CPC): a lei fixa prazo especifico e por
    # isso NAO se somam ao dobro da Fazenda Publica.
    "Embargos a Execucao Fiscal": 30,
    "Recurso Inominado": 10,
    "Contrarrazoes de Recurso Inominado": 10,
}

# Atos com prazo proprio em lei - imunes ao dobro do art. 183 (art. 183, §2º).
_PRAZOS_PROPRIOS: frozenset[str] = frozenset(
    {
        "Embargos a Execucao Fiscal",
        "Recurso Inominado",
        "Contrarrazoes de Recurso Inominado",
    }
)

# Atos de defesa na Justica do Trabalho: QUADRUPLO pelo DL 779/69, art. 1o, II.
# Os demais atos do rito trabalhista recebem dobro pelo art. 1o, III.
_ATOS_DEFESA_TRABALHISTA: frozenset[str] = frozenset({"Contestacao", "Manifestacao", "Resposta"})

# Ritos em que o prazo em dobro da Fazenda Publica e afastado por lei.
_RITOS_SEM_DOBRO: frozenset[str] = frozenset({"juizado_especial_fazenda"})
_RITOS_VALIDOS: frozenset[str] = frozenset(
    {"comum", "juizado_especial_fazenda", "execucao_fiscal", "trabalhista"}
)

_PRAZO_PADRAO_DIAS = 15


async def calcular_proximo_prazo(
    numero_processo: str,
    tribunal: str,
    tipo_ato: str | None = None,
    uf: str | None = None,
    data_intimacao_iso: str | None = None,
    parte_fazenda_publica: bool = False,
    rito: str = "comum",
    feriados_municipais: dict[str, str] | None = None,
    data_e_disponibilizacao_djen: bool = False,
) -> dict[str, object]:
    """Calcula o próximo prazo processual em dias úteis com calendário forense.

    Implementa art. 219 (dias úteis), art. 224 (termo inicial no dia seguinte)
    e art. 220 CPC (suspensão no recesso forense 20/dez a 20/jan).

    Args:
        numero_processo: Número no formato CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO).
        tribunal: Sigla do tribunal (ex: 'TJSP', 'TRF1').
        tipo_ato: Tipo do ato processual para selecionar prazo CPC
                  (ex: 'Contestacao', 'Embargos de Declaracao').
                  Se omitido, usa prazo padrão de 15 dias úteis.
        uf: Sigla da UF para incluir feriados estaduais no cálculo
            (ex: 'SP', 'RJ', 'MG'). Se omitida, usa apenas feriados nacionais.
        data_intimacao_iso: Data de intimação/publicação em ISO 8601
                            (ex: '2025-01-15'). Se omitida, usa a data da
                            última movimentação disponível no DataJud.
        parte_fazenda_publica: True quando a parte representada é a Fazenda
                            Pública (União, Estado, DF, Município, autarquia ou
                            fundação de direito público). Aplica o prazo em
                            dobro do art. 183 do CPC. Use True para qualquer
                            processo do Município.
        rito: 'comum' (padrão), 'juizado_especial_fazenda', 'execucao_fiscal'
                            ou 'trabalhista'. No Juizado Especial da Fazenda
                            Pública o dobro é afastado (art. 7º da Lei
                            12.153/2009).
        feriados_municipais: Mapa {'AAAA-MM-DD': 'descrição'} com feriados
                            locais e suspensões de expediente do foro.
        data_e_disponibilizacao_djen: True quando a data informada é a de
                            DISPONIBILIZAÇÃO no Diário eletrônico (é o que o
                            DJEN devolve). Nesse caso a publicação ocorre no
                            primeiro dia útil seguinte (art. 224, §2º, do CPC)
                            e só a partir dela corre o termo inicial.

    Returns:
        Dicionário com termo_inicial, data_final, dias_uteis, feriados
        que afetaram o cálculo e campo 'aviso' com limitações.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason="Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO.",
        )

    if uf is not None and uf.upper() not in UF_PARA_ISO:
        raise JuridicoValidationError(
            field="uf",
            value=uf,
            reason=(
                f"UF '{uf}' não reconhecida. Use sigla de 2 letras (ex: 'SP', 'RJ', 'MG'). "
                f"UFs suportadas: {', '.join(sorted(UF_PARA_ISO.keys()))}"
            ),
        )

    if rito not in _RITOS_VALIDOS:
        raise JuridicoValidationError(
            field="rito",
            value=rito,
            reason=f"Rito inválido. Use um de: {', '.join(sorted(_RITOS_VALIDOS))}.",
        )

    municipais: dict[datetime.date, str] = {}
    for data_str, descricao in (feriados_municipais or {}).items():
        try:
            municipais[datetime.date.fromisoformat(data_str[:10])] = descricao
        except ValueError as exc:
            raise JuridicoValidationError(
                field="feriados_municipais",
                value=data_str,
                reason="Chave inválida. Use datas ISO 8601 no formato YYYY-MM-DD.",
            ) from exc

    # Validar e parsear data_intimacao_iso se fornecida
    data_intimacao_input: datetime.date | None = None
    if data_intimacao_iso is not None:
        try:
            data_intimacao_input = datetime.date.fromisoformat(
                data_intimacao_iso[:10]  # aceita datetime completo, usa só a data
            )
        except ValueError as exc:
            raise JuridicoValidationError(
                field="data_intimacao_iso",
                value=data_intimacao_iso,
                reason="Data inválida. Use formato ISO 8601: YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS",
            ) from exc

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info(
        "calcular_prazo_solicitado",
        numero=numero_normalizado,
        tipo_ato=tipo_ato,
        uf=uf,
        data_intimacao=data_intimacao_iso,
    )

    # Buscar ultima movimentacao se data nao fornecida explicitamente
    data_referencia: datetime.date | None = data_intimacao_input
    fonte_data = "fornecida pelo usuario"
    ultima_mov_dict: dict[str, object] | None = None

    if data_referencia is None:
        processo = await get_provider().buscar_processo(numero_normalizado, tribunal)
        ultima_mov = processo.movimentacoes[0] if processo.movimentacoes else None

        if not ultima_mov:
            return {
                "numero_processo": numero_normalizado,
                "tribunal": tribunal,
                "prazo_estimado": None,
                "motivo": "Nenhuma movimentação disponível no DataJud para calcular prazo.",
                "aviso": (
                    "AVISO: Não foi possível calcular o prazo pois o processo não "
                    "possui movimentações registradas no DataJud. Verifique o portal "
                    "do tribunal ou forneça data_intimacao_iso manualmente."
                ),
            }

        data_referencia = ultima_mov.data_hora.date()
        fonte_data = "ultima movimentacao DataJud"
        ultima_mov_dict = ultima_mov.model_dump(mode="json")

    dias_simples = _PRAZOS_CPC.get(tipo_ato or "", _PRAZO_PADRAO_DIAS)
    if tipo_ato and tipo_ato not in _PRAZOS_CPC:
        logger.warning(
            "tipo_ato_nao_reconhecido",
            tipo_ato=tipo_ato,
            prazo_aplicado=_PRAZO_PADRAO_DIAS,
        )
    tipo_ato_desc = tipo_ato or f"padrao ({_PRAZO_PADRAO_DIAS} dias uteis)"

    # CORRECAO (etapa 1) - art. 183 do CPC: a Fazenda Publica tem prazo em dobro
    # para todas as suas manifestacoes processuais. Antes desta correcao a tool
    # devolvia sempre o prazo simples, errando pela metade em quase todo calculo
    # de um departamento juridico municipal.
    multiplicador = 1
    if not parte_fazenda_publica:
        fundamento = "Prazo simples - parte nao e Fazenda Publica."
    elif rito == "trabalhista":
        # O prazo diferenciado do ente publico na Justica do Trabalho NAO decorre
        # do art. 183 do CPC, e sim do Decreto-Lei 779/69. Aplicar o CPC aqui
        # subconta a contestacao pela metade.
        if tipo_ato in _ATOS_DEFESA_TRABALHISTA:
            multiplicador = 4
            fundamento = (
                "Prazo em QUADRUPLO (art. 1o, II, do Decreto-Lei 779/69): na Justica do "
                "Trabalho o ente publico tem prazo quadruplicado para contestar. O art. 183 "
                "do CPC nao se aplica a este rito."
            )
        else:
            multiplicador = 2
            fundamento = (
                "Prazo em DOBRO (art. 1o, III, do Decreto-Lei 779/69): na Justica do Trabalho "
                "o ente publico tem prazo em dobro para recorrer. O art. 183 do CPC nao se "
                "aplica a este rito."
            )
    elif rito in _RITOS_SEM_DOBRO:
        fundamento = (
            "Prazo SIMPLES: no Juizado Especial da Fazenda Publica nao ha prazo "
            "diferenciado para a Fazenda (art. 7º da Lei 12.153/2009), o que "
            "afasta o dobro do art. 183 do CPC."
        )
    elif tipo_ato in _PRAZOS_PROPRIOS:
        fundamento = (
            f"Prazo SIMPLES: '{tipo_ato}' tem prazo proprio fixado em lei, "
            "hipotese em que o dobro nao incide (art. 183, §2º, do CPC)."
        )
    else:
        multiplicador = 2
        fundamento = (
            "Prazo EM DOBRO (art. 183, caput, do CPC): a Fazenda Publica - aqui o "
            "Municipio - goza de prazo em dobro para todas as suas manifestacoes "
            f"processuais. Prazo simples de {dias_simples} dias uteis dobrado para "
            f"{dias_simples * 2}."
        )

    dias = dias_simples * multiplicador
    # Mantido para nao quebrar quem ja consome este campo.
    dobro_aplicado = multiplicador > 1

    # Art. 224, §2º do CPC: considera-se data de publicacao o primeiro dia util
    # seguinte ao da disponibilizacao no Diario de Justica eletronico. O feed do
    # DJEN devolve a DISPONIBILIZACAO, entao sem este passo o prazo sairia um
    # dia util adiantado.
    data_disponibilizacao: datetime.date | None = None
    if data_e_disponibilizacao_djen:
        data_disponibilizacao = data_referencia
        data_referencia = proximo_dia_util(data_referencia, uf, municipais or None)

    resultado = calcular_prazo(
        data_intimacao=data_referencia,
        dias_uteis=dias,
        uf=uf,
        feriados_municipais=municipais or None,
    )

    feriados_lista = [
        {"data": d.isoformat(), "descricao": nome} for d, nome in resultado.feriados_no_periodo
    ]

    status_prazo = "VENCIDO" if resultado.data_final < datetime.date.today() else "EM ABERTO"

    retorno: dict[str, object] = {
        "numero_processo": numero_normalizado,
        "tribunal": tribunal,
        "tipo_ato": tipo_ato_desc,
        "dias_uteis_prazo": dias,
        "dias_uteis_prazo_simples": dias_simples,
        "parte_fazenda_publica": parte_fazenda_publica,
        "rito": rito,
        "prazo_em_dobro_aplicado": dobro_aplicado,
        "multiplicador": multiplicador,
        "fundamento_prazo": fundamento,
        "uf_considerada": uf or "nao informada (apenas feriados nacionais)",
        "fonte_data_intimacao": fonte_data,
        "data_intimacao_iso": data_referencia.isoformat(),
        "data_disponibilizacao_iso": (
            data_disponibilizacao.isoformat() if data_disponibilizacao else None
        ),
        "regra_publicacao": (
            "Data de publicacao = 1º dia util seguinte a disponibilizacao "
            "(art. 224, §2º, do CPC)."
            if data_disponibilizacao
            else "Data tratada como data de intimacao/publicacao."
        ),
        "termo_inicial_iso": resultado.termo_inicial.isoformat(),
        "termo_inicial_legivel": resultado.termo_inicial.strftime("%d/%m/%Y"),
        "data_final_iso": resultado.data_final.isoformat(),
        "data_final_legivel": resultado.data_final.strftime("%d/%m/%Y"),
        "status_prazo": status_prazo,
        "feriados_e_recessos_no_periodo": feriados_lista,
        "total_feriados_e_recessos": len(feriados_lista),
        "dias_recesso_forense": resultado.dias_recesso,
        "aviso": resultado.aviso,
        "base_legal": (
            "Art. 219, 220 e 224 do CPC/2015"
            + (
                "; art. 1o do Decreto-Lei 779/69 (prazo diferenciado do ente publico "
                "na Justica do Trabalho)"
                if rito == "trabalhista" and dobro_aplicado
                else "; art. 183 do CPC/2015 (prazo em dobro da Fazenda Publica)"
                if dobro_aplicado
                else ""
            )
        ),
        "limitacao": (
            "Feriados nacionais e estaduais sao cobertos automaticamente; "
            "feriados municipais e suspensoes de expediente devem ser informados "
            "em feriados_municipais. Pontos facultativos (Carnaval, Corpus Christi) "
            "e suspensoes extraordinarias NAO sao aplicados automaticamente. "
            "O prazo em dobro depende de parte_fazenda_publica=True e do rito "
            "informado - confira sempre o rito antes de confiar no resultado."
        ),
    }

    if ultima_mov_dict is not None:
        retorno["ultima_movimentacao"] = ultima_mov_dict

    return retorno


__all__ = ["calcular_proximo_prazo"]
