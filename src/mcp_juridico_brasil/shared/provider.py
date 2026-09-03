"""Acesso centralizado ao ProcessoProvider ativo.

CORRECAO (etapa 3): antes desta camada, cada modulo de tool instanciava
``DataJudProvider()`` diretamente no import, o que tornava ``selecionar_provider()``
codigo morto - trocar de provider exigia editar codigo. Agora todas as tools
chamam ``get_provider()``, que respeita a configuracao de ambiente e aplica
fallback automatico para o DataJud.

Variaveis de ambiente (ver comercial/registry.py):
    JURIDICO_PROVIDER            datajud | judit | escavador | trackjud
    JURIDICO_PROVIDER_COMERCIAL  alias historico, aceito para compatibilidade
    JURIDICO_PROVIDER_API_KEY    chave do provider comercial
"""

from __future__ import annotations

import threading

from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.datajud.provider import ProcessoProvider

logger = get_logger(__name__)

_provider: ProcessoProvider | None = None
_lock = threading.Lock()


def get_provider() -> ProcessoProvider:
    """Retorna o provider ativo (singleton preguicoso, thread-safe).

    A selecao acontece na primeira chamada real de uma tool - nunca no import
    do modulo -, o que mantem os testes livres de leitura de os.environ em
    tempo de coleta e permite ``patch.dict`` antes do primeiro uso.
    """
    global _provider
    if _provider is None:
        with _lock:
            if _provider is None:
                # Import local: evita ciclo comercial -> datajud -> shared.
                from mcp_juridico_brasil.comercial.registry import selecionar_provider

                _provider = selecionar_provider()
    return _provider


def reset_provider() -> None:
    """Descarta o provider em cache (uso em testes e apos troca de configuracao)."""
    global _provider
    with _lock:
        _provider = None


__all__ = ["get_provider", "reset_provider"]
