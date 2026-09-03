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

## 6. Hermes — avisos no Telegram

Opcional. Sem `TELEGRAM_BOT_TOKEN` o serviço sobe igual, apenas não notifica; o
`/health` diz `"hermes_configurado": false`.

**a) Criar o bot.** No Telegram, fale com **@BotFather** → `/newbot`. Ele devolve um
token no formato `123456789:AAH...`. Esse token dá controle total do bot: trate como
senha, ponha só no `.env` do host, nunca no git.

**b) Descobrir o id do grupo.** Crie o grupo da Procuradoria, adicione o bot e mande
qualquer mensagem lá. Depois abra:

```
https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
```

O `chat.id` do grupo é **negativo** (ex.: `-1001234567890`). É esse valor que vai em
`TELEGRAM_CHAT_ID_GRUPO`.

**c) Variáveis no host:**

```
TELEGRAM_BOT_TOKEN=123456789:AAH...
TELEGRAM_CHAT_ID_GRUPO=-1001234567890
TELEGRAM_WEBHOOK_SECRET=<gere com: python -c "import secrets; print(secrets.token_urlsafe(32))">
PAINEL_BASE_URL=https://juridico-pradopolis.onrender.com
```

`PAINEL_BASE_URL` precisa ser a **URL pública** antes do primeiro envio — é dela que
saem os links das mensagens.

**d) Registrar o webhook.** Entre no painel como chefe e chame uma vez:

```
POST /hermes/webhook/registrar
```

O Telegram exige **HTTPS em URL pública**: em `localhost` ele não entrega, e os botões
das mensagens não funcionam.

**e) Cada pessoa faz o próprio opt-in.** Tela **Avisos no Telegram** → *Gerar meu
código* → envie `/vincular SEUCODIGO` ao bot. O código vale 15 minutos e serve uma vez.
Ninguém cadastra ninguém: é preciso a senha do painel e o Telegram da própria pessoa.

**Cadência:** resumo às 08:00 em dias úteis do calendário forense, no grupo; alerta
crítico no privado do responsável, no máximo um por publicação; silêncio das 20h às
07h — o que ocorre nessa janela entra no resumo da manhã.

## Alternativas ao Render

O mesmo `Dockerfile` serve para **Fly.io**, **Railway** ou qualquer host que rode
container. Só o `render.yaml` é específico.
