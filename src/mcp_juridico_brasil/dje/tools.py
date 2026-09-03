"""Tools MCP do módulo DJe - Domicílio Judicial Eletrônico (Fase 4).

DISCLAIMER OBRIGATÓRIO (OAB Rec. 001/2024 + Resolução CNJ 455/2022):
Estas ferramentas são destinadas exclusivamente a advogados e profissionais
do direito para acesso às comunicações processuais oficiais de seus clientes.
Não constituem consultoria jurídica. A análise e a decisão de confirmar
leitura de intimação são de responsabilidade exclusiva do advogado habilitado.

AVISO DE EFEITO JURÍDICO (confirmar_leitura_intimacao):
A confirmação de leitura de uma intimação via API DJe tem efeito jurídico
real e inicia a contagem oficial do prazo processual. Esta operação é
IRREVERSÍVEL e requer confirmação explícita em dois níveis:
  1. Parâmetro confirmar=True na chamada da tool.
  2. Variável de ambiente DJE_PERMITIR_CONFIRMACAO_LEITURA=true.
Sem ambas as condições satisfeitas, a tool opera em modo dry-run seguro.
"""

from __future__ import annotations

import os
import re

from mcp_juridico_brasil._core import JuridicoValidationError
from mcp_juridico_brasil._core.logging import get_logger
from mcp_juridico_brasil.dje.provider import DJeProvider
from mcp_juridico_brasil.shared.validators import validar_numero_cnj

logger = get_logger(__name__)

# Lazy initialization: DJeProvider e instanciado apenas na primeira chamada real,
# evitando leitura de os.environ no import do modulo (facilita testes com patch.dict).
_provider: DJeProvider | None = None

# Padrao conservador para id_comunicacao: alfanumerico com hifens/underscores,
# sem caracteres de path (/, .., etc.) que possam causar path traversal na URL.
_ID_COMUNICACAO_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _get_provider() -> DJeProvider:
    """Retorna (ou cria) o provider singleton do DJe."""
    global _provider
    if _provider is None:
        _provider = DJeProvider()
    return _provider


_DISCLAIMER = (
    "AVISO: Informações do Domicílio Judicial Eletrônico fornecidas para uso "
    "exclusivo do advogado responsável. Não constitui consultoria jurídica. "
    "Verifique sempre no portal do DJe antes de tomar decisões processuais. "
    "(Resolução CNJ 455/2022 | OAB Recomendação 001/2024)"
)

_AVISO_CONFIRMACAO = (
    "ATENÇÃO - EFEITO JURÍDICO IRREVERSÍVEL: A confirmação de leitura de "
    "intimação no Domicílio Judicial Eletrônico inicia oficialmente a contagem "
    "do prazo processual. Esta operação NÃO pode ser desfeita. "
    "Execute somente após revisão cuidadosa pelo advogado responsável."
)



def _diagnostico_configuracao() -> dict[str, object] | None:
    """Descreve o que falta para acessar o DJe, ou None se estiver tudo pronto.

    Credencial ausente é um ESTADO DE CONFIGURAÇÃO previsível, não uma falha de
    execução. Devolver isso como dado estruturado - em vez de levantar exceção -
    permite que o assistente diga ao procurador exatamente o que providenciar,
    em lugar de apenas reportar um erro.
    """
    from mcp_juridico_brasil.dje.certificado import CertificadoConfig

    faltando: list[str] = []
    if not os.environ.get("DJE_CLIENT_ID", "").strip():
        faltando.append("DJE_CLIENT_ID")
    if not os.environ.get("DJE_CLIENT_SECRET", "").strip():
        faltando.append("DJE_CLIENT_SECRET")
    if not os.environ.get("DJE_BEHALF_OF_CPF", "").strip():
        faltando.append("DJE_BEHALF_OF_CPF")
    if not CertificadoConfig.from_env().configurado():
        faltando.append("DJE_CERT_PATH")

    if not faltando:
        return None

    return {
        "configurado": False,
        "situacao": "NAO CONFIGURADO",
        "variaveis_faltando": faltando,
        "mensagem": (
            "O acesso ao Domicílio Judicial Eletrônico ainda não está configurado. "
            "Diferente do DJEN (diário público, sem autenticação), o DJe exige "
            "credenciamento do Município no portal do CNJ."
        ),
        "como_habilitar": [
            "1. Credenciar o Município no portal do Domicílio Judicial Eletrônico "
            "(domicilio-eletronico.pdpj.jus.br), com o e-CNPJ A1 e um representante legal.",
            "2. Obter client_id e client_secret no GeCli e preencher DJE_CLIENT_ID "
            "e DJE_CLIENT_SECRET.",
            "3. Definir DJE_BEHALF_OF_CPF com o CPF do procurador responsável — "
            "o CNJ exige esse cabeçalho para auditoria de quem dá ciência.",
            "4. Apontar DJE_CERT_PATH/DJE_CERT_SENHA para o .pfx do e-CNPJ A1.",
        ],
        "enquanto_isso": (
            "Use descobrir_carteira_processual e listar_publicacoes: o DJEN é público, "
            "não exige credencial e já cobre a triagem diária. O DJe acrescenta a "
            "intimação oficial dirigida ao Município e o efeito jurídico da ciência."
        ),
        "disclaimer": _DISCLAIMER,
    }


async def listar_intimacoes(
    numero_processo: str | None = None,
    apenas_pendentes: bool = True,
    limite: int = 50,
) -> dict[str, object]:
    """Lista comunicações processuais do Domicílio Judicial Eletrônico (DJe).

    Operação SOMENTE LEITURA - sem efeito jurídico.

    Retorna as intimações, citações e notificações recebidas no DJe para
    o CNPJ/CPF cadastrado via DJE_BEHALF_OF_CPF. Intimações em segredo
    de justiça têm o conteúdo suprimido; apenas metadados são exibidos.

    Credenciais necessárias (via variáveis de ambiente):
        DJE_CLIENT_ID           - client_id do OAuth2 (GeCli/DJe)
        DJE_CLIENT_SECRET       - client_secret do OAuth2 (GeCli/DJe)
        DJE_BEHALF_OF_CPF       - CPF do responsável (auditoria CNJ)

    Args:
        numero_processo: Número CNJ para filtrar comunicações de um processo
                         específico (ex: '0001234-56.2023.8.26.0100').
                         Se omitido, retorna todas as comunicações recentes.
        apenas_pendentes: Se True (padrão), retorna apenas comunicações
                          ainda não confirmadas como lidas.
        limite: Número máximo de comunicações a retornar (padrão: 50).

    Returns:
        Dicionário com lista de intimações, totais e avisos jurídicos.

    Sem credenciais configuradas, devolve um diagnóstico estruturado dizendo o
    que falta e como habilitar - não levanta exceção, porque credencial ausente
    é estado de configuração previsível, não falha de execução.

    Raises:
        JuridicoAPIError: Falha de comunicação com a API DJe ou credenciais
                          inválidas (diferente de ausentes).
    """
    if numero_processo is not None and not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason=(
                "Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO "
                "ou os 20 dígitos sem formatação."
            ),
        )

    pendencias = _diagnostico_configuracao()
    if pendencias is not None:
        logger.info("dje_listar_intimacoes_sem_credenciais")
        return pendencias

    logger.info(
        "dje_listar_intimacoes_solicitado",
        numero_processo=numero_processo,
        apenas_pendentes=apenas_pendentes,
    )

    resultado = await _get_provider().listar_intimacoes(
        numero_processo=numero_processo,
        apenas_pendentes=apenas_pendentes,
        limite=limite,
    )

    return {
        "intimacoes": [i.model_dump(mode="json") for i in resultado.intimacoes],
        "total": resultado.total,
        "pendentes": resultado.pendentes,
        "aviso_juridico": resultado.aviso_juridico,
        "disclaimer": _DISCLAIMER,
        "fonte": "Domicílio Judicial Eletrônico - API Comunica (Resolução CNJ 455/2022)",
        "nota_sigilosas": (
            "Intimações em segredo de justiça têm o campo 'conteudo' suprimido. "
            "Acesse-as diretamente pelo portal do DJe com certificado digital."
        ),
    }


async def confirmar_leitura_intimacao(
    numero_processo: str,
    id_intimacao: str,
    confirmar: bool = False,
) -> dict[str, object]:
    """Confirma a leitura de uma intimação no Domicílio Judicial Eletrônico.

    ╔══════════════════════════════════════════════════════════════════╗
    ║  AÇÃO DE ALTO RISCO - EFEITO JURÍDICO REAL E IRREVERSÍVEL       ║
    ║                                                                  ║
    ║  Confirmar a leitura de uma intimação via API DJe:               ║
    ║  - Registra ciência oficial com timestamp no sistema do CNJ.     ║
    ║  - INICIA a contagem do prazo processual correspondente.         ║
    ║  - NÃO pode ser desfeito via API.                                ║
    ╚══════════════════════════════════════════════════════════════════╝

    GATE DE SEGURANÇA (duplo):
    Esta tool opera em modo dry-run (sem efeito) por padrão. Para executar
    com efeito jurídico real, ambas as condições abaixo devem ser satisfeitas:

      1. confirmar=True deve ser passado explicitamente nesta chamada.
      2. DJE_PERMITIR_CONFIRMACAO_LEITURA=true deve estar definida no ambiente.

    Se qualquer uma das condições falhar, a tool retorna uma simulação sem
    qualquer chamada à API DJe - completamente seguro.

    Credenciais necessárias (via variáveis de ambiente):
        DJE_CLIENT_ID                       - client_id OAuth2
        DJE_CLIENT_SECRET                   - client_secret OAuth2
        DJE_BEHALF_OF_CPF                   - CPF do responsável (auditoria)
        DJE_PERMITIR_CONFIRMACAO_LEITURA    - deve ser 'true' para modo real

    Args:
        numero_processo: Número CNJ do processo (ex: '0001234-56.2023.8.26.0100').
        id_intimacao: ID único da intimação no DJe (obtido via listar_intimacoes).
        confirmar: DEVE ser True para indicar que o operador está ciente do
                   efeito jurídico e deseja prosseguir. False por padrão.
                   Mesmo com True, a operação só é executada se
                   DJE_PERMITIR_CONFIRMACAO_LEITURA=true estiver no ambiente.

    Returns:
        Dicionário com resultado da operação, modo de execução (real vs dry-run)
        e avisos de efeito jurídico.
    """
    if not validar_numero_cnj(numero_processo):
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason=(
                "Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO "
                "ou os 20 dígitos sem formatação."
            ),
        )

    if not _ID_COMUNICACAO_PATTERN.match(id_intimacao):
        raise JuridicoValidationError(
            field="id_intimacao",
            value=id_intimacao,
            reason=(
                "Formato inválido. O ID da intimação deve conter apenas letras, "
                "dígitos, hifens e underscores (max 64 caracteres)."
            ),
        )

    logger.info(
        "dje_confirmar_leitura_solicitado",
        id_intimacao=id_intimacao,
        numero_processo=numero_processo,
        confirmar=confirmar,
    )

    resultado = await _get_provider().confirmar_leitura(
        numero_processo=numero_processo,
        id_comunicacao=id_intimacao,
        confirmar=confirmar,
    )

    return {
        "resultado": resultado.model_dump(mode="json"),
        "aviso_juridico": _AVISO_CONFIRMACAO,
        "disclaimer": _DISCLAIMER,
        "executado": resultado.executado,
        "modo_dry_run": resultado.modo_dry_run,
        "instrucoes_para_modo_real": (
            "Para executar com efeito jurídico real: "
            "(1) passe confirmar=True; "
            "(2) defina DJE_PERMITIR_CONFIRMACAO_LEITURA=true no ambiente do servidor MCP. "
            "CONFIRME com o advogado responsável antes de habilitar."
        ),
    }




async def verificar_certificado_dje() -> dict[str, object]:
    """Verifica o certificado digital do Município usado no acesso ao DJe.

    Operação LOCAL e somente leitura: não contata nenhum servidor, não expõe a
    chave privada e não registra a senha. Use para responder três perguntas:

      1. O arquivo abre com a senha configurada?
      2. É mesmo o certificado do Município (confere o CNPJ)?
      3. Quando vence?

    A terceira importa mais do que parece: o certificado A1 vale 12 meses, e
    vencer sem aviso significa perder o acesso às intimações oficiais do
    Município da noite para o dia. Rode esta verificação periodicamente.

    Variáveis de ambiente:
        DJE_CERT_PATH   - caminho do .pfx/.p12 do e-CNPJ A1 do Município
        DJE_CERT_SENHA  - senha do certificado (nunca é registrada em log)

    Returns:
        Situação do certificado (VALIDO / VENCE EM BREVE / VENCIDO), titular,
        emissor, CNPJ, validade e dias restantes.
    """
    from mcp_juridico_brasil.dje.certificado import CertificadoConfig, inspecionar

    cfg = CertificadoConfig.from_env()
    if not cfg.configurado():
        return {
            "configurado": False,
            "situacao": "NAO CONFIGURADO",
            "mensagem": (
                "DJE_CERT_PATH não está definido. Sem certificado, as tools do DJe "
                "operam apenas com client_id/secret e o GeCli provavelmente recusará "
                "o handshake em produção."
            ),
            "orientacao": (
                "Aponte DJE_CERT_PATH para o arquivo .pfx do e-CNPJ A1 do Município - "
                "o mesmo certificado já usado nos demais sistemas da Prefeitura - e "
                "defina DJE_CERT_SENHA. Certificado A3 (token físico) NÃO funciona "
                "para operação automática."
            ),
        }

    info = inspecionar(cfg)
    logger.info(
        "dje_certificado_verificado",
        situacao=info.situacao,
        dias_para_vencer=info.dias_para_vencer,
    )

    retorno: dict[str, object] = {
        "configurado": True,
        "situacao": info.situacao,
        "titular": info.titular,
        "emissor": info.emissor,
        "cnpj": info.cnpj,
        "numero_serie": info.numero_serie,
        "valido_de": info.valido_de.date().isoformat(),
        "valido_ate": info.valido_ate.date().isoformat(),
        "dias_para_vencer": info.dias_para_vencer,
        "aviso_tipo": (
            "Apenas certificado A1 (arquivo) permite operação automática. "
            "A3 (token ou cartão) exige presença física e não serve para varredura."
        ),
    }
    if info.vencido:
        retorno["acao_necessaria"] = (
            "CERTIFICADO VENCIDO - o acesso ao DJe está interrompido. "
            "Renove o e-CNPJ e atualize o arquivo apontado por DJE_CERT_PATH."
        )
    elif info.proximo_do_vencimento:
        retorno["acao_necessaria"] = (
            f"O certificado vence em {info.dias_para_vencer} dias. "
            "Providencie a renovação antes disso para não perder o acesso às intimações."
        )
    return retorno


__all__ = [
    "confirmar_leitura_intimacao",
    "listar_intimacoes",
    "verificar_certificado_dje",
]
