"""Pauta semanal em PDF e Excel — para a reunião de equipe e o despacho."""

from __future__ import annotations

import datetime
import io
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import hoje
from app.models import Publicacao, Triagem, Usuario

RITO_LEGIVEL = {
    "comum": "Comum (art. 183 CPC)",
    "trabalhista": "Trabalhista (DL 779/69)",
    "juizado_especial_fazenda": "Juizado Esp. Fazenda",
    "execucao_fiscal": "Execução fiscal",
}


async def coletar(sessao: AsyncSession, dias: int = 7) -> dict[str, list[dict]]:
    """Vencimentos dos próximos N dias, agrupados por procurador responsável."""
    fim = hoje() + datetime.timedelta(days=dias)
    linhas = await sessao.execute(
        select(Publicacao, Triagem, Usuario)
        .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
        .outerjoin(Usuario, Usuario.id == Triagem.responsavel_id)
        .where(Publicacao.vencimento.is_not(None),
               Publicacao.vencimento.between(hoje(), fim))
        .order_by(Publicacao.vencimento)
    )
    por_procurador: dict[str, list[dict]] = defaultdict(list)
    for pub, tri, usuario in linhas:
        chave = usuario.nome if usuario else "Sem responsável atribuído"
        por_procurador[chave].append({
            "vencimento": pub.vencimento, "processo": pub.numero_processo,
            "tribunal": pub.tribunal, "ato": pub.ato_inferido or "—",
            "rito": RITO_LEGIVEL.get(pub.rito_inferido or "", pub.rito_inferido or "—"),
            "classe": pub.classe or "—",
            "status": (tri.status if tri else "novo"),
            "dias": (pub.vencimento - hoje()).days,
        })
    return dict(por_procurador)


def para_excel(dados: dict[str, list[dict]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Pauta semanal"
    ws.append(["Responsável", "Vencimento", "Dias", "Processo", "Tribunal",
               "Ato", "Rito / base legal", "Classe", "Situação"])
    for celula in ws[1]:
        celula.font = celula.font.copy(bold=True)
    for procurador, itens in dados.items():
        for i in itens:
            ws.append([procurador, i["vencimento"], i["dias"], i["processo"], i["tribunal"],
                       i["ato"], i["rito"], i["classe"], i["status"]])
    for col, largura in zip("ABCDEFGHI", (26, 12, 7, 26, 10, 22, 26, 30, 14), strict=False):
        ws.column_dimensions[col].width = largura
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def para_pdf(dados: dict[str, list[dict]], dias: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=14*mm, bottomMargin=14*mm)
    estilos = getSampleStyleSheet()
    blocos = [
        Paragraph("<b>Pauta semanal — Departamento Jurídico de Pradópolis</b>",
                  estilos["Title"]),
        Paragraph(f"Vencimentos dos próximos {dias} dias · gerado em "
                  f"{hoje().strftime('%d/%m/%Y')}", estilos["Normal"]),
        Spacer(1, 7*mm),
    ]
    if not dados:
        blocos.append(Paragraph("Nenhum vencimento no período.", estilos["Normal"]))

    for procurador, itens in dados.items():
        blocos.append(Paragraph(f"<b>{procurador}</b> — {len(itens)} prazo(s)",
                                estilos["Heading3"]))
        tabela = [["Vence", "Dias", "Processo", "Trib.", "Ato", "Rito / base legal", "Situação"]]
        for i in itens:
            tabela.append([i["vencimento"].strftime("%d/%m/%Y"), str(i["dias"]), i["processo"],
                           i["tribunal"], i["ato"], i["rito"], i["status"]])
        t = Table(tabela, repeatRows=1, colWidths=[22*mm, 12*mm, 48*mm, 18*mm,
                                                   44*mm, 52*mm, 26*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF0EE")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F4C4A")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D3DAD6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9F8")]),
        ]))
        blocos.extend([t, Spacer(1, 6*mm)])

    blocos.append(Paragraph(
        "<font size=7 color='#66716D'>Apoio ao procurador responsável. Não constitui "
        "controle oficial de prazos — confira sempre no portal do tribunal.</font>",
        estilos["Normal"]))
    doc.build(blocos)
    return buffer.getvalue()
