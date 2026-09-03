# Publicação — Neon + Render

Passo a passo para colocar o painel no ar. Leva cerca de 20 minutos.

## 1. Banco no Neon

1. Crie a conta em [neon.tech](https://neon.tech) — o plano gratuito comporta o
   volume de Pradópolis com folga (185 processos, ~250 publicações/mês).
2. Crie um projeto na região **AWS us-east-1** ou **sa-east-1** (São Paulo).
3. Copie a *connection string* e faça **duas adaptações obrigatórias**:

```
# O Neon entrega assim:
postgresql://usuario:senha@ep-xxx.neon.tech/neondb?sslmode=require

# O serviço precisa assim (driver asyncpg):
postgresql+asyncpg://usuario:senha@ep-xxx.neon.tech/neondb?ssl=require
```

> **Duas pegadinhas:** o driver tem de ser `+asyncpg`, e o `asyncpg` usa `ssl=require`,
> não `sslmode=require`. Com o parâmetro errado a conexão falha com mensagem pouco clara.

## 2. Serviço no Render

1. Conecte o repositório do GitHub.
2. O `render.yaml` já descreve o serviço — basta confirmar.
3. Preencha `DATABASE_URL` com a string do passo 1. O `JWT_SECRET` é gerado sozinho.

O container roda `alembic upgrade head` antes de subir. Se a migração falhar, o
container não sobe — é o comportamento correto: servir com schema desatualizado é
pior que não servir.

## 3. Primeiro usuário

Não há cadastro aberto — o primeiro chefe é criado por linha de comando:

```bash
python -m app.criar_chefe "Nome do Procurador-Chefe" chefe@pradopolis.sp.gov.br
```

O comando pede a senha sem ecoar na tela e não a registra em log nem no histórico.
Depois disso, os demais usuários são cadastrados pelo próprio painel.

## 4. Primeira varredura

Entre no painel e use **Varrer o diário**. A partir daí a varredura roda sozinha às
06:00 nos dias úteis, respeitando feriados e recesso forense.

## 5. Feriados locais

Configure `JURIDICO_FERIADOS_LOCAIS` com os feriados municipais e as portarias de
suspensão de expediente do foro:

```
JURIDICO_FERIADOS_LOCAIS=2026-05-20=Aniversário de Pradópolis,2026-08-06=Padroeiro
```

Vale para todo o acervo assim que salvo — os prazos são recalculados na leitura.

## Alternativas ao Render

O mesmo `Dockerfile` serve para **Fly.io**, **Railway** ou qualquer host que rode
container. Só o `render.yaml` é específico.
