"""Certificado digital ICP-Brasil (e-CNPJ A1) para acesso autenticado ao DJe.

O Domicílio Judicial Eletrônico exige certificado ICP-Brasil no credenciamento e,
no handshake com o GeCli/PDPJ, autenticação mútua TLS (mTLS). Este módulo carrega
o arquivo PKCS#12 (.pfx/.p12) do Município e monta o ``ssl.SSLContext`` usado
pelo cliente HTTP.

TIPO DO CERTIFICADO - LEIA ANTES DE CONTRATAR
---------------------------------------------
Só o **A1** serve. A1 é um arquivo, instalável no servidor, e permite operação
automática. A3 é token físico ou cartão e exige alguém plugado na máquina - não
funciona para varredura desatendida.

SEGURANÇA (regras que este módulo cumpre)
-----------------------------------------
- A senha vem exclusivamente de variável de ambiente; nunca é logada, nunca entra
  em mensagem de exceção, e ``repr`` do dataclass a omite.
- Os PEM temporários necessários ao ``load_cert_chain`` nascem com permissão 0600
  via ``mkstemp`` (sem janela em 0644) e são apagados no ``finally``.
- A chave privada nunca é escrita em log nem retornada por função pública.
- ``check_hostname`` e ``CERT_REQUIRED`` ficam ligados: o servidor do CNJ é
  validado contra as CAs do sistema. Não desabilite isso.

O padrão de carga PKCS#12 e montagem do SSLContext segue a implementação já
validada em produção no acesso à SEFAZ com o mesmo certificado do Município.
"""

from __future__ import annotations

import datetime
import os
import ssl
import tempfile
import threading
from dataclasses import dataclass, field

from mcp_juridico_brasil._core.errors import JuridicoAPIError
from mcp_juridico_brasil._core.logging import get_logger

logger = get_logger(__name__)

# OID ICP-Brasil que carrega o CNPJ do titular dentro do otherName da SAN.
_OID_CNPJ_ICP_BRASIL = "2.16.76.1.3.3"

# Avisar com esta antecedência: certificado A1 vale 12 meses e vencer sem aviso
# significa perder o acesso às intimações do Município da noite para o dia.
DIAS_ALERTA_VENCIMENTO = 30


@dataclass
class CertificadoConfig:
    """Localização e senha do certificado. A senha nunca aparece em repr()."""

    caminho: str = ""
    # repr=False impede que a senha vaze em traceback ou log de dataclass.
    senha: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> CertificadoConfig:
        """Lê DJE_CERT_PATH e DJE_CERT_SENHA do ambiente.

        É o mesmo arquivo .pfx do e-CNPJ do Município usado nos demais sistemas
        da Prefeitura - não é preciso emitir um certificado só para o jurídico.
        """
        return cls(
            caminho=os.environ.get("DJE_CERT_PATH", "").strip(),
            senha=os.environ.get("DJE_CERT_SENHA", ""),
        )

    def configurado(self) -> bool:
        return bool(self.caminho)


@dataclass(frozen=True)
class InfoCertificado:
    """Dados públicos do certificado, para diagnóstico. Sem chave privada."""

    titular: str
    emissor: str
    cnpj: str | None
    valido_de: datetime.datetime
    valido_ate: datetime.datetime
    numero_serie: str

    @property
    def dias_para_vencer(self) -> int:
        agora = datetime.datetime.now(tz=datetime.timezone.utc)
        return (self.valido_ate - agora).days

    @property
    def vencido(self) -> bool:
        return self.dias_para_vencer < 0

    @property
    def proximo_do_vencimento(self) -> bool:
        return 0 <= self.dias_para_vencer <= DIAS_ALERTA_VENCIMENTO

    @property
    def situacao(self) -> str:
        if self.vencido:
            return "VENCIDO"
        if self.proximo_do_vencimento:
            return "VENCE EM BREVE"
        return "VALIDO"


def _ler_arquivo(caminho: str) -> bytes:
    try:
        with open(caminho, "rb") as f:
            return f.read()
    except OSError as exc:
        raise JuridicoAPIError(
            source="DJe/Certificado",
            reason=(
                f"Não foi possível abrir o certificado em '{caminho}': "
                f"{exc.strerror}. Verifique o caminho em DJE_CERT_PATH."
            ),
        ) from exc


def _carregar_pkcs12(config: CertificadoConfig) -> tuple[bytes, bytes, list[bytes]]:
    """Abre o .pfx e devolve (chave_pem, cert_pem, cadeia_pem).

    SEGURANÇA: a senha não aparece na mensagem de erro. A biblioteca subjacente
    pode ecoar o parâmetro em algumas falhas, por isso a exceção original é
    substituída por uma mensagem própria.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    dados = _ler_arquivo(config.caminho)

    try:
        chave, certificado, extras = pkcs12.load_key_and_certificates(
            dados, config.senha.encode("utf-8") or None
        )
    except Exception as exc:
        texto = str(exc).lower()
        if "mac" in texto or "password" in texto or "invalid" in texto:
            motivo = (
                "Senha incorreta ou arquivo corrompido. Confira DJE_CERT_SENHA. "
                "Lembre-se: precisa ser um certificado A1 (.pfx/.p12), não A3."
            )
        else:
            motivo = f"Falha ao ler o certificado PKCS#12 ({type(exc).__name__})."
        # `from None` corta o encadeamento para que a exceção original - que pode
        # conter o material sensível passado à biblioteca - não suba no traceback.
        raise JuridicoAPIError(source="DJe/Certificado", reason=motivo) from None

    if chave is None or certificado is None:
        raise JuridicoAPIError(
            source="DJe/Certificado",
            reason=(
                "O arquivo não contém chave privada e certificado juntos. "
                "Exporte o e-CNPJ como A1 com a chave privada incluída."
            ),
        )

    chave_pem = chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = certificado.public_bytes(serialization.Encoding.PEM)
    cadeia = [c.public_bytes(serialization.Encoding.PEM) for c in (extras or [])]
    return chave_pem, cert_pem, cadeia


def _escrever_pem_seguro(sufixo: str, conteudo: bytes) -> str:
    """Cria um PEM temporário já com permissão 0600 (mkstemp é atômico)."""
    fd, caminho = tempfile.mkstemp(suffix=sufixo)
    try:
        os.write(fd, conteudo)
    finally:
        os.close(fd)
    return caminho


def _montar_ssl_context(chave_pem: bytes, cert_pem: bytes, cadeia: list[bytes]) -> ssl.SSLContext:
    """Monta o SSLContext de cliente com o certificado do Município.

    Os PEM em disco existem apenas durante o ``load_cert_chain`` - o OpenSSL os
    lê para memória e os arquivos são removidos em seguida.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_default_certs()

    tmp_chave: str | None = None
    tmp_cert: str | None = None
    try:
        tmp_chave = _escrever_pem_seguro("_dje_key.pem", chave_pem)
        tmp_cert = _escrever_pem_seguro("_dje_cert.pem", cert_pem + b"".join(cadeia))
        ctx.load_cert_chain(certfile=tmp_cert, keyfile=tmp_chave)
    except ssl.SSLError as exc:
        raise JuridicoAPIError(
            source="DJe/Certificado",
            reason=f"O par chave/certificado foi recusado pelo OpenSSL: {exc.reason}.",
        ) from None
    finally:
        for caminho in (tmp_chave, tmp_cert):
            if caminho and os.path.exists(caminho):
                os.unlink(caminho)
    return ctx


def _extrair_cnpj(certificado: object) -> str | None:
    """Extrai o CNPJ do titular da SAN (otherName, OID ICP-Brasil 2.16.76.1.3.3).

    Best-effort: certificados fora do padrão ICP-Brasil simplesmente não têm o
    campo, e nesse caso devolvemos None em vez de falhar.
    """
    from cryptography import x509

    try:
        san = certificado.extensions.get_extension_for_class(  # type: ignore[attr-defined]
            x509.SubjectAlternativeName
        )
    except Exception:
        return None

    for nome in san.value:
        if not isinstance(nome, x509.OtherName):
            continue
        if nome.type_id.dotted_string != _OID_CNPJ_ICP_BRASIL:
            continue
        # O valor vem DER-encoded; os 14 dígitos do CNPJ são os primeiros do conteúdo.
        digitos = "".join(ch for ch in nome.value.decode("latin-1") if ch.isdigit())
        if len(digitos) >= 14:
            return digitos[:14]
    return None


def inspecionar(config: CertificadoConfig | None = None) -> InfoCertificado:
    """Lê os dados públicos do certificado, sem expor a chave privada.

    Serve ao diagnóstico: confirmar que o arquivo abre, de quem é, e quando vence.
    """
    from cryptography.hazmat.primitives.serialization import pkcs12

    cfg = config or CertificadoConfig.from_env()
    if not cfg.configurado():
        raise JuridicoAPIError(
            source="DJe/Certificado",
            reason="DJE_CERT_PATH não configurado. Informe o caminho do .pfx do e-CNPJ.",
        )

    dados = _ler_arquivo(cfg.caminho)
    try:
        _, certificado, _ = pkcs12.load_key_and_certificates(
            dados, cfg.senha.encode("utf-8") or None
        )
    except Exception:
        raise JuridicoAPIError(
            source="DJe/Certificado",
            reason="Senha incorreta ou arquivo corrompido. Confira DJE_CERT_SENHA.",
        ) from None

    if certificado is None:
        raise JuridicoAPIError(
            source="DJe/Certificado", reason="Nenhum certificado encontrado no arquivo."
        )

    def _texto(nome: object) -> str:
        try:
            return str(nome.rfc4514_string())  # type: ignore[attr-defined]
        except Exception:
            return str(nome)

    # not_valid_*_utc existe desde cryptography 42; os atributos sem sufixo estão
    # depreciados e devolvem datetime ingênuo.
    de = getattr(certificado, "not_valid_before_utc", None) or certificado.not_valid_before
    ate = getattr(certificado, "not_valid_after_utc", None) or certificado.not_valid_after
    if de.tzinfo is None:
        de = de.replace(tzinfo=datetime.timezone.utc)
    if ate.tzinfo is None:
        ate = ate.replace(tzinfo=datetime.timezone.utc)

    return InfoCertificado(
        titular=_texto(certificado.subject),
        emissor=_texto(certificado.issuer),
        cnpj=_extrair_cnpj(certificado),
        valido_de=de,
        valido_ate=ate,
        numero_serie=format(certificado.serial_number, "x"),
    )


class _ContextoCache:
    """Guarda o SSLContext por (caminho, mtime) — montar é caro, o arquivo é estável."""

    def __init__(self) -> None:
        self._ctx: ssl.SSLContext | None = None
        self._chave: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def obter(self, config: CertificadoConfig) -> ssl.SSLContext:
        try:
            mtime = os.path.getmtime(config.caminho)
        except OSError:
            mtime = 0.0
        chave = (config.caminho, mtime)
        with self._lock:
            if self._ctx is None or self._chave != chave:
                chave_pem, cert_pem, cadeia = _carregar_pkcs12(config)
                self._ctx = _montar_ssl_context(chave_pem, cert_pem, cadeia)
                self._chave = chave
                info = inspecionar(config)
                # Só metadados públicos vão para o log — nunca senha ou chave.
                logger.info(
                    "dje_certificado_carregado",
                    situacao=info.situacao,
                    dias_para_vencer=info.dias_para_vencer,
                    valido_ate=info.valido_ate.date().isoformat(),
                )
                if info.vencido:
                    logger.error("dje_certificado_vencido", valido_ate=str(info.valido_ate.date()))
                elif info.proximo_do_vencimento:
                    logger.warning(
                        "dje_certificado_perto_do_vencimento",
                        dias=info.dias_para_vencer,
                    )
            return self._ctx

    def limpar(self) -> None:
        with self._lock:
            self._ctx = None
            self._chave = None


_cache = _ContextoCache()


def obter_ssl_context(config: CertificadoConfig | None = None) -> ssl.SSLContext | None:
    """SSLContext com o certificado do Município, ou None se não configurado.

    Devolver None permite que o cliente HTTP siga sem mTLS nos ambientes em que
    ele não é exigido, em vez de quebrar a aplicação inteira.
    """
    cfg = config or CertificadoConfig.from_env()
    if not cfg.configurado():
        return None
    return _cache.obter(cfg)


def limpar_cache() -> None:
    """Descarta o SSLContext em cache (uso em testes e após troca do certificado)."""
    _cache.limpar()


__all__ = [
    "DIAS_ALERTA_VENCIMENTO",
    "CertificadoConfig",
    "InfoCertificado",
    "inspecionar",
    "limpar_cache",
    "obter_ssl_context",
]
