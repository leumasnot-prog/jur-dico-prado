"""Cliente da API publica Comunica / DJEN (CNJ).

Endpoint: https://comunicaapi.pje.jus.br/api/v1/comunicacao

Ao contrario do DataJud - que NAO indexa as partes -, o Comunica expoe
o nome das partes e a OAB dos advogados de cada comunicacao. E por isso a
unica fonte publica e gratuita capaz de DESCOBRIR a carteira processual de
um ente, em vez de apenas acompanhar numeros ja conhecidos.

Fundamento: Diario de Justica Eletronico Nacional (Resolucao CNJ 455/2022).
As publicacoes sao publicas por forca de lei; a API nao exige autenticacao.

LIMITACOES ESTRUTURAIS (documentadas nas tools):
- E um feed de PUBLICACOES, nao um cadastro de processos: so enxerga feitos
  que tiveram publicacao no periodo consultado. Cobertura util a partir de 2024.
- O filtro nomeParte e difuso (casa tokens isolados), exigindo refino local -
  feito em filtrar_por_destinatario().
- Sem limite de taxa publicado: as chamadas sao serializadas e espacadas.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any

import httpx

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil._core.logging import get_logger

logger = get_logger(__name__)

# URL fixa - nenhum dado externo e interpolado na base (prevencao de SSRF).
_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

_TIMEOUT = 45.0
_ITENS_POR_PAGINA = 100
_MAX_PAGINAS = 60
_PAUSA_ENTRE_PAGINAS = 0.4


def normalizar(texto: str | None) -> str:
    """Remove acentos, colapsa espacos e devolve em caixa alta."""
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", base).upper().strip()


def limpar_html(texto: str | None) -> str:
    """Converte o texto da publicacao em texto corrido.

    O DJEN devolve o inteiro teor com <br> e, ocasionalmente, outras tags. Sem
    esta limpeza o texto chega ao leitor com marcacao no meio.
    """
    if not texto:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", texto)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", t).strip()


# Duas formas usuais de o juizo declarar prazo no corpo da publicacao.
_PRAZO_RE = (
    re.compile(
        r"prazo\s+(?:legal\s+)?(?:de\s+)?(\d{1,3})\s*\(?[a-zcaeiou\s]*\)?\s*dias?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:no|em)\s+(\d{1,3})\s*\(?[a-zcaeiou\s]*\)?\s*dias?\s+"
        r"(?:uteis\s+)?(?:para|a\s+contar)",
        re.IGNORECASE,
    ),
)


def prazo_mencionado(texto: str | None) -> int | None:
    """Extrai um prazo em dias declarado no texto da publicacao, se houver.

    Serve para CONFRONTAR com o prazo da tabela: quando o juizo fixa prazo
    diverso, prevalece o do despacho. A interface alerta em vez de esconder.
    """
    if not texto:
        return None
    for rx in _PRAZO_RE:
        m = rx.search(texto)
        if m:
            return int(m.group(1))
    return None


def identificar_polo(polo: str | None) -> str:
    """Converte o codigo de polo do DJEN em rotulo legivel."""
    return {"A": "ativo", "P": "passivo"}.get((polo or "").upper(), "nao_informado")


class ComunicaClient:
    """Acesso somente-leitura ao feed publico de comunicacoes processuais."""

    def __init__(self, base_url: str = _BASE_URL, timeout: float = _TIMEOUT) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def _pagina(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                resposta = await http.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="Comunica/DJEN", reason="Timeout ao consultar o feed de comunicacoes."
            ) from exc
        except httpx.RequestError as exc:
            raise JuridicoAPIError(
                source="Comunica/DJEN", reason=f"Erro de rede: {exc}"
            ) from exc

        if resposta.status_code != 200:
            raise JuridicoAPIError(
                source="Comunica/DJEN",
                status_code=resposta.status_code,
                reason="Resposta inesperada do feed de comunicacoes.",
            )
        dados: dict[str, Any] = resposta.json()
        return dados

    async def buscar(
        self,
        nome_parte: str | None = None,
        numero_oab: str | None = None,
        uf_oab: str | None = None,
        numero_processo: str | None = None,
        sigla_tribunal: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        max_itens: int = 1000,
    ) -> list[dict[str, Any]]:
        """Pagina o feed e devolve as comunicacoes brutas (sem refino de nome).

        Ao menos um entre nome_parte, numero_oab e numero_processo deve ser
        informado - uma varredura sem filtro traria o diario nacional inteiro.
        """
        if not any([nome_parte, numero_oab, numero_processo]):
            raise JuridicoAPIError(
                source="Comunica/DJEN",
                reason=(
                    "Informe ao menos um filtro: nome_parte, numero_oab ou "
                    "numero_processo. Consulta sem filtro nao e permitida."
                ),
            )

        base: dict[str, Any] = {"itensPorPagina": _ITENS_POR_PAGINA}
        if nome_parte:
            base["nomeParte"] = nome_parte
        if numero_oab:
            base["numeroOab"] = numero_oab
        if uf_oab:
            base["ufOab"] = uf_oab.upper()
        if numero_processo:
            base["numeroProcesso"] = numero_processo
        if sigla_tribunal:
            base["siglaTribunal"] = sigla_tribunal.upper()
        if data_inicio:
            base["dataDisponibilizacaoInicio"] = data_inicio
        if data_fim:
            base["dataDisponibilizacaoFim"] = data_fim

        coletadas: list[dict[str, Any]] = []
        for pagina in range(1, _MAX_PAGINAS + 1):
            dados = await self._pagina({**base, "pagina": pagina})
            itens = dados.get("items") or []
            coletadas.extend(itens)
            if pagina == 1:
                logger.info(
                    "comunica_busca_iniciada",
                    total_bruto=dados.get("count"),
                    filtro_nome=nome_parte,
                    filtro_oab=numero_oab,
                )
            if len(itens) < _ITENS_POR_PAGINA or len(coletadas) >= max_itens:
                break
            await asyncio.sleep(_PAUSA_ENTRE_PAGINAS)

        return coletadas[:max_itens]


def filtrar_por_destinatario(
    comunicacoes: list[dict[str, Any]],
    termos_obrigatorios: list[str],
    termos_alternativos: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Refina localmente o resultado difuso do filtro nomeParte.

    Mantem apenas as comunicacoes em que ALGUM destinatario contenha todos os
    termos_obrigatorios e ao menos um dos termos_alternativos (quando dados).

    Exemplo para o Municipio: obrigatorios=['PRADOPOLIS'],
    alternativos=['MUNICIPIO', 'PREFEITURA'] - o que descarta homonimos como
    'Residencial Pradopolis SPE Ltda'.
    """
    obrig = [normalizar(t) for t in termos_obrigatorios]
    alt = [normalizar(t) for t in (termos_alternativos or [])]

    def casa(nome: str | None) -> bool:
        n = normalizar(nome)
        if not all(t in n for t in obrig):
            return False
        return not alt or any(t in n for t in alt)

    return [
        c for c in comunicacoes if any(casa(d.get("nome")) for d in (c.get("destinatarios") or []))
    ]


__all__ = [
    "ComunicaClient",
    "filtrar_por_destinatario",
    "identificar_polo",
    "limpar_html",
    "normalizar",
    "prazo_mencionado",
]
