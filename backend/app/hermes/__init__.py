"""Hermes — o mensageiro do Departamento Jurídico.

Leva o recado a tempo. Não decide, não interpreta mérito, não confirma leitura
de intimação. Quatro módulos, deliberadamente separados:

    formatador.py  monta o texto      — não conhece Telegram
    telegram.py    envia              — não conhece regra de negócio
    agendador.py   decide quando/quem — junta os dois
    webhook.py     recebe os cliques

A fronteira entre formatador e transporte é o que permitirá trocar o canal (o
WhatsApp Business oficial, se um dia a Prefeitura contratar) sem reescrever
regra nenhuma.
"""
