"""Fixtures globais da suite."""

import pytest

from mcp_juridico_brasil.shared.provider import reset_provider


@pytest.fixture(autouse=True)
def _provider_limpo():
    """Descarta o provider em cache antes e depois de cada teste.

    O provider virou singleton preguicoso (shared/provider.py); sem este reset
    a configuracao de ambiente de um teste vazaria para o seguinte.
    """
    reset_provider()
    yield
    reset_provider()
