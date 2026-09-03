"""Modulo Comunica/DJEN - descoberta de carteira e feed de publicacoes.

Fonte publica e gratuita que, ao contrario do DataJud, indexa o nome das
partes e a OAB dos advogados. Sem autenticacao.
"""

from mcp_juridico_brasil.comunica.client import ComunicaClient, filtrar_por_destinatario
from mcp_juridico_brasil.comunica.tools import (
    descobrir_carteira_processual,
    listar_publicacoes,
)

__all__ = [
    "ComunicaClient",
    "descobrir_carteira_processual",
    "filtrar_por_destinatario",
    "listar_publicacoes",
]
