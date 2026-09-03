"""Monta o texto das mensagens. Funções puras: entra dado, sai string.

Este módulo NÃO conhece Telegram. É o que permitirá trocar de canal depois sem
mexer em regra.

O FILTRO DE LGPD MORA AQUI, e é o motivo de o módulo existir separado do
transporte. Publicação de diário é pública, mas agregar prazos de terceiros e
despejar num grupo de mensageria é tratamento de dado pessoal. A disciplina:

  1. Nenhum nome de pessoa natural em mensagem alguma — nem no grupo, nem no
     privado. O que identifica o caso é o número do processo.
  2. Sem inteiro teor. A mensagem leva um link; o texto se lê no painel, que
     tem login e auditoria.
  3. `verificar_privacidade()` é a rede de segurança: mesmo que um dia alguém
     acrescente um campo com nome, ele é redigido antes de sair daqui.

Regra de bolso: se a mensagem vazar num print de grupo, ela não pode expor mais
do que já está no número do processo.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape

import structlog

logger = structlog.get_logger(__name__)

REDIGIDO = "[nome suprimido]"

DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# Marcadores de pessoa jurídica. Nome que traz um deles não é pessoa natural e
# pode aparecer — mas, por decisão de projeto, nem esses entram nas mensagens.
_MARCAS_PJ = frozenset({
    "LTDA", "SA", "S/A", "EIRELI", "ME", "EPP", "MEI", "CIA", "COMPANHIA",
    "MUNICIPIO", "PREFEITURA", "ESTADO", "UNIAO", "FAZENDA", "INSS", "BANCO",
    "ASSOCIACAO", "SINDICATO", "COOPERATIVA", "FUNDACAO", "INSTITUTO", "IGREJA",
    "CONDOMINIO", "EMPRESA", "INDUSTRIA", "COMERCIO", "SERVICOS", "TRANSPORTES",
    "CONSTRUTORA", "DISTRIBUIDORA", "SUPERMERCADO", "AUTARQUIA", "CAMARA",
    "SECRETARIA", "DEPARTAMENTO", "CONSELHO", "ORDEM", "CAIXA", "TELEFONICA",
})

# Ligações que não identificam ninguém sozinhas.
_CONECTIVOS = frozenset({"DE", "DA", "DO", "DAS", "DOS", "E", "DI", "DEL", "LA", "VON"})


def _normalizar(texto: str | None) -> str:
    """Maiúsculas sem acento. Comparar nome com acento é comparar sorte."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def e_pessoa_natural(nome: str | None) -> bool:
    """Heurística deliberadamente PESSIMISTA: na dúvida, é pessoa natural.

    Errar para o lado de proteger custa um nome a menos numa mensagem. Errar
    para o outro lado custa dado pessoal num grupo de WhatsApp da equipe.
    """
    n = _normalizar(nome)
    if not n:
        return False
    fichas = set(re.split(r"[^A-Z0-9/]+", n)) - {""}
    return not (fichas & _MARCAS_PJ)


def _fichas_significativas(nome: str) -> list[str]:
    return [f for f in re.split(r"[^A-Z]+", _normalizar(nome))
            if len(f) >= 4 and f not in _CONECTIVOS]


def _fichas_permitidas(permitidos: list[str] | tuple[str, ...]) -> set[str]:
    """Fichas que NUNCA se redige — o nome do próprio destinatário, tipicamente.

    Sem isso o filtro se volta contra quem deveria proteger: basta o procurador
    Carlos Menezes receber um alerta de um processo movido por João Carlos para
    a mensagem virar "Prazo crítico — [nome suprimido] Menezes". Aconteceu em
    teste com dados reais, e é a razão deste parâmetro existir.
    """
    return {f for p in permitidos for f in _fichas_significativas(p)}


def verificar_privacidade(
    texto: str, nomes: list[str] | tuple[str, ...],
    permitidos: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Devolve os nomes de pessoa natural que vazaram para dentro de `texto`.

    Casa por ficha inteira (com fronteira de palavra), não por substring: sem
    isso, um nome de três letras acusaria vazamento em qualquer texto.
    """
    alvo = _normalizar(texto)
    seguras = _fichas_permitidas(permitidos)
    vazados = []
    for nome in nomes:
        if not e_pessoa_natural(nome):
            continue
        fichas = [f for f in _fichas_significativas(nome) if f not in seguras]
        if fichas and any(re.search(rf"\b{re.escape(f)}\b", alvo) for f in fichas):
            vazados.append(nome)
    return vazados


def redigir(
    texto: str, nomes: list[str] | tuple[str, ...],
    permitidos: list[str] | tuple[str, ...] = (),
) -> str:
    """Substitui por `[nome suprimido]` qualquer pessoa natural encontrada.

    Redige em vez de recusar o envio de propósito: um alerta de prazo que não
    chega é pior do que um alerta com um campo suprimido. O vazamento evitado
    vira log de erro — para virar correção, não silêncio.
    """
    vazados = verificar_privacidade(texto, nomes, permitidos)
    if not vazados:
        return texto
    logger.error("hermes_vazamento_bloqueado", quantidade=len(vazados))
    seguras = _fichas_permitidas(permitidos)
    saida = texto
    for nome in vazados:
        for ficha in sorted(_fichas_significativas(nome), key=len, reverse=True):
            if ficha in seguras:
                continue
            saida = re.sub(rf"(?i)\b{re.escape(ficha)}\b", REDIGIDO, saida)
    # Colapsa "[nome suprimido] DA [nome suprimido]" numa marca só: o conectivo
    # sobrevive à redação por ser curto demais para identificar alguém.
    conectivos = "|".join(sorted(_CONECTIVOS))
    padrao = rf"(?:{re.escape(REDIGIDO)}(?:[\s,]+(?:{conectivos})\b)?[\s,]*)+"
    return re.sub(padrao, REDIGIDO + " ", saida, flags=re.IGNORECASE).strip()


@dataclass(frozen=True)
class ItemPrazo:
    """O que o Hermes precisa saber de uma publicação para avisar sobre ela.

    `partes` não vai para a mensagem: existe só para alimentar o verificador de
    privacidade, que precisa saber quais nomes NÃO podem aparecer.
    """

    publicacao_id: str
    numero: str
    tribunal: str
    ato: str
    rito: str
    vencimento: datetime.date
    dias_restantes: int
    fundamento: str = ""
    partes: tuple[str, ...] = field(default=())
    responsavel_id: int | None = None
    motivo: str = "prazo"  # "prazo" ou a palavra-chave que disparou o alerta
    # O número SEM máscara, que é a chave do processo no banco. `numero` é o
    # formatado, para leitura humana — casar acompanhamento por ele daria
    # falso-negativo silencioso quando o CNJ não devolve a máscara.
    numero_processo: str = ""


def _br(d: datetime.date) -> str:
    return d.strftime("%d/%m")


def _br_completo(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _plural(n: int, um: str, muitos: str) -> str:
    return f"{n} {um if n == 1 else muitos}"


def _linha_item(i: ItemPrazo) -> str:
    return (f"   • <code>{escape(i.numero)}</code> · {escape(i.tribunal)} · "
            f"{escape(i.ato)} · vence {_br(i.vencimento)}")


def montar_resumo_diario(
    *,
    data: datetime.date,
    criticos: list[ItemPrazo],
    novas_por_tribunal: dict[str, int],
    sem_triagem: int,
    total_processos: int,
    base_url: str,
    urgentes: list[ItemPrazo] | None = None,
    dias_criticos: int = 3,
    limite_listado: int = 8,
) -> str:
    """O boletim das 08:00 no grupo da Procuradoria.

    Quando não há nada crítico, DIZ isso. Silêncio total faz a equipe duvidar se
    o sistema está no ar, e a dúvida vale menos que uma linha de texto.
    """
    dia = DIAS_SEMANA[data.weekday()]
    linhas = [f"☀️ <b>Procuradoria de Pradópolis</b> — {dia}, {_br(data)}", ""]

    if criticos:
        linhas.append(f"🔴 <b>{_plural(len(criticos), 'prazo vencendo', 'prazos vencendo')} "
                      f"em até {dias_criticos} dias úteis</b>")
        linhas += [_linha_item(i) for i in criticos[:limite_listado]]
        if len(criticos) > limite_listado:
            linhas.append(f"   <i>… e mais {len(criticos) - limite_listado} no painel</i>")
    else:
        linhas.append("🟢 <b>Nenhum prazo crítico.</b> O dia está sob controle.")
    linhas.append("")

    # Bloco separado de propósito: liminar e penhora são urgentes por NATUREZA,
    # não por prazo curto. Listá-las sob "vencendo em 3 dias" seria mentir sobre
    # a data — e uma linha errada num boletim de prazo corrói a confiança inteira.
    if urgentes:
        quantas = _plural(len(urgentes), "publicação sinalizada", "publicações sinalizadas")
        linhas.append(f"🟠 <b>{quantas}</b> (liminar, tutela, penhora ou bloqueio)")
        for i in urgentes[:limite_listado]:
            linhas.append(f"   • <code>{escape(i.numero)}</code> · {escape(i.tribunal)} · "
                          f"{escape(i.motivo)} · prazo {_br(i.vencimento)}")
        if len(urgentes) > limite_listado:
            linhas.append(f"   <i>… e mais {len(urgentes) - limite_listado} no painel</i>")
        linhas.append("")

    if sem_triagem:
        detalhe = " · ".join(f"{t} {q}" for t, q in
                             sorted(novas_por_tribunal.items(), key=lambda x: -x[1])[:6])
        linhas.append(f"🟡 <b>{_plural(sem_triagem, 'publicação nova', 'publicações novas')} "
                      f"sem triagem</b>")
        if detalhe:
            linhas.append(f"   {escape(detalhe)}")
    else:
        linhas.append("✅ <b>Triagem em dia.</b> Nenhuma publicação sem leitura.")
    linhas.append("")

    linhas.append(f"📋 Acervo: <b>{total_processos}</b> processos")
    linhas.append("")
    linhas.append(f'Abrir o painel → {escape(base_url.rstrip("/"))}/#publicacoes')
    linhas.append("")
    linhas.append("<i>Camada de alerta — não substitui o controle oficial de prazos. "
                  "Confira no portal do tribunal antes de peticionar.</i>")

    texto = "\n".join(linhas)
    nomes = [n for i in [*criticos, *(urgentes or [])] for n in i.partes]
    return redigir(texto, nomes)


def montar_alerta_critico(*, item: ItemPrazo, nome_procurador: str, base_url: str,
                          acompanhando: bool = False) -> str:
    """O aviso no privado do procurador responsável.

    Mesmo aqui não vai nome de terceiro nem inteiro teor: o que identifica o
    caso é o número, e o texto se lê no painel.
    """
    urgencia = ("<b>VENCE HOJE</b>" if item.dias_restantes == 0
                else "<b>VENCIDO</b>" if item.dias_restantes < 0
                else f"{_plural(item.dias_restantes, 'dia útil', 'dias úteis')}")
    titulo = "👁 <b>Processo que você acompanha</b>" if acompanhando else "⚠️ <b>Prazo crítico</b>"
    linhas = [
        f"{titulo} — {escape(nome_procurador)}",
        "",
        f"Processo <code>{escape(item.numero)}</code> · {escape(item.tribunal)}",
        f"Ato: {escape(item.ato)} ({escape(item.rito.replace('_', ' '))})",
        f"Vence: <b>{_br_completo(item.vencimento)}</b> — {urgencia}",
    ]
    if item.motivo != "prazo":
        linhas.append(f"Sinalizado por: <b>{escape(item.motivo)}</b> no texto da publicação")
    if item.fundamento:
        linhas += ["", f"<i>{escape(item.fundamento)}</i>"]
    if acompanhando:
        linhas += ["", "<i>Você pediu para ser avisado deste processo. Para parar, "
                       "desmarque no painel.</i>"]
    linhas += ["", "<i>Abra o painel para ler o inteiro teor.</i>"]

    # O nome de quem RECEBE não é dado de terceiro: ele fica de fora do filtro.
    return redigir("\n".join(linhas), item.partes, permitidos=[nome_procurador])


def botoes_alerta(publicacao_id: str, base_url: str) -> list[list[dict[str, str]]]:
    """Dois botões: um leva ao painel, o outro marca a triagem como em andamento.

    Não existe botão de "confirmar ciência da intimação": efeito jurídico
    irreversível não fica a um toque de distância num app de mensagem.
    """
    return [[
        {"text": "📂 Abrir no painel",
         "url": f'{base_url.rstrip("/")}/#publicacoes?id={publicacao_id}'},
        {"text": "👁 Marcar como visto", "callback_data": f"visto:{publicacao_id}"},
    ]]
