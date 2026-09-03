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

## 7. Plano gratuito: o GitHub Actions no lugar do agendador interno

O plano free do Render **hiberna o serviço sem uso** — e sem uso é exatamente o estado
em que a varredura das 06h e os alertas do Hermes precisariam disparar sozinhos. O
`APScheduler` embutido não sobrevive à hibernação.

A saída não é pagar uma instância sempre ativa. É inverter quem chama: um workflow do
GitHub Actions (`.github/workflows/hermes-cron.yml`) faz um `POST` no serviço, e essa
chamada **acorda o container e dispara a tarefa na mesma requisição**. O atraso de
partida a frio (30-50s) não incomoda ninguém, porque não há pessoa esperando.

```
GitHub Actions ──POST /cron/varredura──▶ Render (acorda) ──▶ DJEN ──▶ Neon
               ──POST /cron/hermes ────▶ Render (acorda) ──▶ Telegram
```

**a) No Render**, as variáveis já vêm certas pelo `render.yaml`: `VARREDURA_ATIVA` e
`HERMES_ATIVO` ficam `false` (o agendador interno seria redundante), e `CRON_SECRET` é
gerado automaticamente. **Copie o valor gerado** — você vai precisar dele no passo (b).

**b) No GitHub**, em *Settings → Secrets and variables → Actions → New repository
secret*, crie dois segredos:

| Segredo | Valor |
|---|---|
| `PAINEL_BASE_URL` | a URL pública do Render, **sem barra no fim** (ex.: `https://painel-juridico-pradopolis.onrender.com`) |
| `CRON_SECRET` | exatamente o mesmo valor que o Render gerou |

Se os dois `CRON_SECRET` não baterem, o workflow recebe **403** e nada roda — é o
comportamento correto, e aparece no log da Action.

**c) Cadência do workflow**, e por que ela pode ser generosa:

| Rota | Quando | O que faz |
|---|---|---|
| `/cron/varredura` | 09:05 UTC (06:05 BRT), seg-sex | Varre o DJEN e grava o que é novo |
| `/cron/hermes` | a cada 30 min, todo dia | Resumo diário (uma vez só) e alertas críticos |

Chamar `/cron/hermes` de madrugada, no sábado ou dez vezes seguidas **não tem efeito**:
a regra de dia útil, a janela de silêncio e a não-repetição moram no serviço, não no
agendamento. Por isso o cron externo pode ser simples e burro — a inteligência está do
lado que tem o banco.

**d) Testar sem esperar o horário:** na aba *Actions* do repositório, escolha o workflow
e clique em *Run workflow*. O disparo manual chama `/cron/hermes`.

> **Se um dia migrar para plano pago**, é só inverter: `VARREDURA_ATIVA=true`,
> `HERMES_ATIVO=true` e apagar o workflow. O agendador interno volta a funcionar sem
> mudar uma linha de código.

## Alternativas ao Render

O mesmo `Dockerfile` serve para **Fly.io**, **Railway** ou qualquer host que rode
container — e as rotas `/cron/*` funcionam igual em qualquer um deles. Só o
`render.yaml` é específico.
