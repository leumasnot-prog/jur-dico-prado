"""Testes do certificado digital A1 usado no acesso ao DJe.

Gera um PKCS#12 real (auto-assinado) em tempo de teste, com a extensão de CNPJ
do padrão ICP-Brasil, para exercitar o caminho completo: carga, montagem do
SSLContext e inspeção — sem depender do certificado verdadeiro do Município.
"""

from __future__ import annotations

import datetime
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil.dje import certificado as cert

CNPJ_FICTICIO = "12345678000190"
SENHA = "senha-de-teste"


def _gerar_pfx(
    tmp_path,
    senha: str = SENHA,
    dias_validade: int = 365,
    com_cnpj: bool = True,
    nome: str = "MUNICIPIO DE PRADOPOLIS:12345678000190",
) -> str:
    """Cria um .pfx auto-assinado e devolve o caminho."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil"),
            x509.NameAttribute(NameOID.COMMON_NAME, nome),
        ]
    )
    agora = datetime.datetime.now(tz=datetime.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        # O início precisa anteceder o fim mesmo quando geramos um cert já vencido.
        .not_valid_before(agora - datetime.timedelta(days=abs(dias_validade) + 2))
        .not_valid_after(agora + datetime.timedelta(days=dias_validade))
    )
    if com_cnpj:
        # otherName com o OID de CNPJ do ICP-Brasil, como num e-CNPJ real.
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.OtherName(
                        x509.ObjectIdentifier(cert._OID_CNPJ_ICP_BRASIL),
                        b"\x16\x0e" + CNPJ_FICTICIO.encode(),
                    )
                ]
            ),
            critical=False,
        )
    certificado = builder.sign(chave, hashes.SHA256())

    dados = pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode()),
    )
    caminho = tmp_path / "e-cnpj-teste.pfx"
    caminho.write_bytes(dados)
    return str(caminho)


@pytest.fixture(autouse=True)
def _cache_limpo():
    cert.limpar_cache()
    yield
    cert.limpar_cache()


# --- Configuração -----------------------------------------------------------


def test_sem_cert_path_nao_ha_mtls(monkeypatch):
    monkeypatch.delenv("DJE_CERT_PATH", raising=False)
    assert cert.CertificadoConfig.from_env().configurado() is False
    assert cert.obter_ssl_context() is None


def test_senha_nao_aparece_em_repr():
    """A senha não pode vazar em traceback nem em log de dataclass."""
    cfg = cert.CertificadoConfig(caminho="/tmp/x.pfx", senha="segredo-absoluto")
    assert "segredo-absoluto" not in repr(cfg)
    assert "/tmp/x.pfx" in repr(cfg)


# --- Carga e SSLContext -----------------------------------------------------


def test_monta_ssl_context_com_certificado_valido(tmp_path):
    cfg = cert.CertificadoConfig(caminho=_gerar_pfx(tmp_path), senha=SENHA)
    ctx = cert.obter_ssl_context(cfg)
    assert isinstance(ctx, ssl.SSLContext)
    # Verificação do servidor permanece ligada — não desabilitar.
    assert ctx.check_hostname is True
    assert ctx.verify_mode is ssl.CERT_REQUIRED


def test_context_e_cacheado(tmp_path):
    cfg = cert.CertificadoConfig(caminho=_gerar_pfx(tmp_path), senha=SENHA)
    assert cert.obter_ssl_context(cfg) is cert.obter_ssl_context(cfg)


def test_nao_deixa_pem_temporario_para_tras(tmp_path):
    """Os PEM existem só durante o load_cert_chain e são apagados no finally."""
    import glob
    import tempfile

    antes = set(glob.glob(f"{tempfile.gettempdir()}/*_dje_*.pem"))
    cert.obter_ssl_context(
        cert.CertificadoConfig(caminho=_gerar_pfx(tmp_path), senha=SENHA)
    )
    assert set(glob.glob(f"{tempfile.gettempdir()}/*_dje_*.pem")) == antes


# --- Erros ------------------------------------------------------------------


def test_senha_errada_da_erro_claro_sem_vazar_a_senha(tmp_path):
    cfg = cert.CertificadoConfig(caminho=_gerar_pfx(tmp_path), senha="senha-errada")
    with pytest.raises(JuridicoAPIError) as exc:
        cert.obter_ssl_context(cfg)
    texto = str(exc.value)
    assert "DJE_CERT_SENHA" in texto
    assert "senha-errada" not in texto
    assert "A1" in texto  # orienta sobre o tipo do certificado


def test_arquivo_inexistente_da_erro_com_o_caminho(tmp_path):
    cfg = cert.CertificadoConfig(caminho=str(tmp_path / "nao-existe.pfx"), senha=SENHA)
    with pytest.raises(JuridicoAPIError, match="DJE_CERT_PATH"):
        cert.obter_ssl_context(cfg)


def test_inspecionar_sem_configuracao_orienta(monkeypatch):
    monkeypatch.delenv("DJE_CERT_PATH", raising=False)
    with pytest.raises(JuridicoAPIError, match="DJE_CERT_PATH"):
        cert.inspecionar()


# --- Inspeção ---------------------------------------------------------------


def test_inspeciona_titular_cnpj_e_validade(tmp_path):
    info = cert.inspecionar(
        cert.CertificadoConfig(caminho=_gerar_pfx(tmp_path), senha=SENHA)
    )
    assert "PRADOPOLIS" in info.titular
    assert info.cnpj == CNPJ_FICTICIO
    assert info.situacao == "VALIDO"
    assert 300 < info.dias_para_vencer <= 365
    assert info.vencido is False


def test_certificado_vencido_e_sinalizado(tmp_path):
    caminho = _gerar_pfx(tmp_path, dias_validade=-10)
    info = cert.inspecionar(cert.CertificadoConfig(caminho=caminho, senha=SENHA))
    assert info.vencido is True
    assert info.situacao == "VENCIDO"
    assert info.dias_para_vencer < 0


def test_vencimento_proximo_dispara_alerta(tmp_path):
    """A1 vale 12 meses; vencer sem aviso derruba o acesso às intimações."""
    caminho = _gerar_pfx(tmp_path, dias_validade=10)
    info = cert.inspecionar(cert.CertificadoConfig(caminho=caminho, senha=SENHA))
    assert info.proximo_do_vencimento is True
    assert info.situacao == "VENCE EM BREVE"


def test_certificado_sem_cnpj_nao_quebra(tmp_path):
    """Certificado fora do padrão ICP-Brasil simplesmente não tem o campo."""
    caminho = _gerar_pfx(tmp_path, com_cnpj=False)
    info = cert.inspecionar(cert.CertificadoConfig(caminho=caminho, senha=SENHA))
    assert info.cnpj is None
    assert info.situacao == "VALIDO"


# --- Integração com o cliente DJe -------------------------------------------


def test_cliente_usa_mtls_quando_ha_certificado(tmp_path, monkeypatch):
    from mcp_juridico_brasil.dje.client import DJeOAuthClient

    monkeypatch.setenv("DJE_CERT_PATH", _gerar_pfx(tmp_path))
    monkeypatch.setenv("DJE_CERT_SENHA", SENHA)
    monkeypatch.setenv("DJE_CLIENT_ID", "id")
    monkeypatch.setenv("DJE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DJE_BEHALF_OF_CPF", "12345678901")

    client = DJeOAuthClient()
    assert client.tem_mtls() is True
    http = client._httpx_client()
    assert http is not None


def test_transporte_de_teste_desliga_mtls(tmp_path, monkeypatch):
    """Injetar mock não deve carregar o certificado real."""
    import httpx

    from mcp_juridico_brasil.dje.client import DJeOAuthClient

    monkeypatch.setenv("DJE_CERT_PATH", "/caminho/que/nao/existe.pfx")
    monkeypatch.setenv("DJE_CERT_SENHA", "x")
    client = DJeOAuthClient(_httpx_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    # Não levanta erro de certificado porque nem tenta carregá-lo.
    assert client._httpx_client() is not None


# --- Estado de configuração do DJe ------------------------------------------


async def test_listar_intimacoes_sem_credenciais_devolve_diagnostico(monkeypatch):
    """Credencial ausente é configuração pendente, não erro de execução.

    Antes desta mudança a tool levantava exceção e o operador via um traceback
    onde deveria ver o que precisa providenciar.
    """
    from mcp_juridico_brasil.dje.tools import listar_intimacoes

    for var in ("DJE_CLIENT_ID", "DJE_CLIENT_SECRET", "DJE_BEHALF_OF_CPF", "DJE_CERT_PATH"):
        monkeypatch.delenv(var, raising=False)

    r = await listar_intimacoes()
    assert r["configurado"] is False
    assert r["situacao"] == "NAO CONFIGURADO"
    assert set(r["variaveis_faltando"]) == {
        "DJE_CLIENT_ID",
        "DJE_CLIENT_SECRET",
        "DJE_BEHALF_OF_CPF",
        "DJE_CERT_PATH",
    }
    assert len(r["como_habilitar"]) == 4
    # Aponta a alternativa que já funciona hoje.
    assert "DJEN" in str(r["enquanto_isso"])


async def test_diagnostico_lista_so_o_que_falta(monkeypatch, tmp_path):
    from mcp_juridico_brasil.dje.tools import listar_intimacoes

    monkeypatch.setenv("DJE_CLIENT_ID", "id")
    monkeypatch.setenv("DJE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DJE_CERT_PATH", _gerar_pfx(tmp_path))
    monkeypatch.delenv("DJE_BEHALF_OF_CPF", raising=False)

    r = await listar_intimacoes()
    assert r["variaveis_faltando"] == ["DJE_BEHALF_OF_CPF"]


async def test_numero_cnj_invalido_ainda_e_rejeitado(monkeypatch):
    """A validação de entrada vem antes do diagnóstico de configuração."""
    from mcp_juridico_brasil._core.errors import JuridicoValidationError
    from mcp_juridico_brasil.dje.tools import listar_intimacoes

    for var in ("DJE_CLIENT_ID", "DJE_CLIENT_SECRET", "DJE_BEHALF_OF_CPF", "DJE_CERT_PATH"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(JuridicoValidationError):
        await listar_intimacoes(numero_processo="numero-invalido")
