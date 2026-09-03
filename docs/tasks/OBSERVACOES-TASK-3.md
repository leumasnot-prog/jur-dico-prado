# Observações da execução — Task 3 (Hermes, avisos no Telegram)

**Data:** 03/09/2026 · **Onde:** `backend/app/hermes/`
**Resultado:** os cinco ciclos fecharam. 62 testes de backend (27 novos) + 297 do MCP.

---

## 1. O que foi construído

Quatro módulos, com a fronteira que a task pedia — e que é o que permitirá trocar de
canal depois sem reescrever regra nenhuma:

| Módulo | Responsabilidade | O que ele **não** sabe |
|---|---|---|
| `formatador.py` | monta o texto, filtra dado pessoal | o que é Telegram |
| `telegram.py` | fala com a Bot API, respeita rate limit | o que é prazo ou procurador |
| `agendador.py` | decide quando e para quem | como se escreve a mensagem |
| `webhook.py` | recebe `/vincular` e os cliques | como se envia |

Mais duas tabelas (`telegram_vinculos`, `hermes_envios`), a migração `8f21c4ad9e07`,
e uma tela nova no painel — **Avisos no Telegram** — para o opt-in.

---

## 2. A decisão que mais mudou o resultado: a garantia de não repetir é do banco

A task pede "máximo 1 alerta por publicação". A forma óbvia é um `SELECT` antes do
envio. A forma que resiste é um **índice parcial único**:

```sql
CREATE UNIQUE INDEX uq_hermes_chave ON hermes_envios (chave)
  WHERE (sucesso IS NOT FALSE);
```

`sucesso` tem três estados de propósito:

| Estado | Significado | Efeito na chave |
|---|---|---|
| `NULL` | reservado, envio em curso | **já bloqueia** duplicata |
| `TRUE` | entregue | bloqueia para sempre |
| `FALSE` | falhou | **libera** para nova tentativa |

O envio *reserva* a chave antes de chamar a API e só então manda. Isso fecha a janela
entre "decidi mandar" e "mandei" — se duas execuções coincidirem, a segunda encontra a
chave tomada e desiste. E uma falha de rede não apaga o alerta para sempre, que é o
defeito da abordagem ingênua de gravar só o sucesso.

Verificado direto no SQL, sem Python no caminho:

```
INSERT chave='alerta:X:2', sucesso=true   -> INSERT 0 1
INSERT chave='alerta:X:2', sucesso=null   -> ERROR: duplicate key ... uq_hermes_chave
INSERT chave='alerta:Y:2', sucesso=false  -> INSERT 0 1
INSERT chave='alerta:Y:2', sucesso=true   -> INSERT 0 1   (falha liberou a chave)
```

---

## 3. Dois bugs que só apareceram no texto real da mensagem

Os testes passavam. Subi um **Telegram falso** local (um servidor que aceita a Bot API
e grava o que recebeu), semeei o banco com um acervo verossímil e li as mensagens como
elas chegariam. Os dois defeitos abaixo estavam invisíveis até esse momento.

### 3.1 O filtro de privacidade se voltou contra quem devia proteger

A mensagem saiu assim:

```
⚠️ Prazo crítico — [nome suprimido] Menezes
```

O procurador **Carlos** Menezes recebeu um alerta de um processo movido por **João
Carlos** da Silva. O filtro viu a ficha "CARLOS" nas partes, encontrou "CARLOS" no
texto e redigiu — o primeiro nome do próprio destinatário.

O erro conceitual: **o nome de quem recebe não é dado de terceiro.** `redigir()` e
`verificar_privacidade()` ganharam o parâmetro `permitidos`, e o alerta privado passa
o nome do procurador nele. Regressão em `test_nome_do_destinatario_nao_e_redigido`.

Vale registrar que o filtro *funcionou* — errou para o lado de proteger demais, que é
o lado certo de errar. Mas uma mensagem que parece quebrada é uma mensagem que a
equipe para de ler.

### 3.2 O boletim mentia sobre a data

```
🔴 3 prazos vencendo em até 3 dias úteis
   • 0011147-09.2023.5.15.0120 · TRT15 · Manifestacao · vence 08/10
```

Esse vencia em **24 dias úteis**. Ele estava na lista porque o texto menciona penhora
— urgente por natureza, não por prazo curto. Listar os dois sob o mesmo título é uma
linha errada num boletim de prazo, e uma linha errada corrói a confiança no boletim
inteiro.

Passaram a ser dois blocos, e um item entra em exatamente um deles:

```
🔴 2 prazos vencendo em até 3 dias úteis
   ...
🟠 1 publicação sinalizada (liminar, tutela, penhora ou bloqueio)
   • 0011147-09.2023.5.15.0120 · TRT15 · penhora · prazo 08/10
```

### 3.3 (Antes desses, um terceiro, pego por teste)

`test_palavra_urgente_alerta_mesmo_com_prazo_longo` falhou apontando zero itens. A
janela do `SELECT` ia só até `hoje + 10 dias`, então a penhora com vencimento em 40
nunca chegava ao filtro em Python. **O que a consulta não traz, o filtro nunca vê.** A
palavra de urgência passou a entrar no próprio SQL, com `ILIKE`.

### 3.4 Um dublê que mentia sobre a assinatura real

Fora do escopo do Hermes, mas colhido no caminho: o docstring do agendador dizia
"timeout de 90s com retry" e o cliente do MCP usava **45s** — o backend nunca passou
outro valor. Um comentário que mente sobre uma propriedade de robustez é pior que
comentário nenhum. Passei a construir o cliente com `timeout=90.0` no serviço, deixando
o padrão do MCP intocado: quem tem varredura de 2000 itens é o serviço, não a biblioteca.

Onze testes quebraram na hora. O dublê de DJEN aceitava apenas `_Cliente()`, sem
argumentos — **um dublê que não espelha a assinatura real deixa passar exatamente o erro
que ele deveria pegar.** É a mesma família de erro que me pegou três vezes na Task 2
(escrever contra uma API que eu supunha, em vez da que existe). Dublê alinhado, 60 testes
verdes.

### 3.5 O Hermes era refém da varredura

Ao ligar os dois no mesmo agendador, escrevi:

```python
if not settings.varredura_ativa:
    return None          # <- e o Hermes nunca era registrado
```

`VARREDURA_ATIVA=false` — o valor do meu próprio `.env` local — desligava **todos os
alertas em silêncio**. Duas chaves de configuração que a documentação apresenta como
independentes não podem ter uma sequestrando a outra, e o modo de falha é o pior
possível: nada quebra, o bot só emudece.

São chaves independentes agora. Uma segunda instância que não varre o DJEN (para não
duplicar a varredura) continua avisando, porque o Hermes só lê o banco. Verificado no
boot real:

```
varredura_desativada
agendador_iniciado  tarefas=['hermes_alertas', 'hermes_resumo']
```

---

## 4. Verificação, ciclo a ciclo

### Ciclo 1 — Bot e transporte
- Retry com backoff; `retry_after` do rate limit obedecido, com teto de 60s.
- **Token nunca em log nem em exceção.** A exceção do `httpx` traz a URL, e a URL traz
  o token — por isso todo erro que sai do módulo passa por `_mascarar()`.
  `test_token_nunca_aparece_no_erro` planta um token, força um `ConnectError` e falha
  se ele aparecer na mensagem.

### Ciclo 2 — Formatador e LGPD
- `test_nome_de_pessoa_natural_nunca_sai_na_mensagem_de_grupo` planta "JOAO CARLOS DA
  SILVA" num campo que **vai** para a mensagem e falha se o nome aparecer. É o teste
  central da task.
- Classificação PJ × PN verificada nos dois sentidos: redigir de menos vaza; redigir
  de mais come o nome do Município.
- Nem o alerta privado leva nome de terceiro ou inteiro teor — a mensagem leva número,
  tribunal, ato, prazo e o fundamento legal.

### Ciclo 3 — Resumo diário
- Sai às 08:00 em dia útil, no grupo.
- **Não sai** no sábado nem em 07/09 (feriado nacional) — testado com data fixa nos
  dois casos, usando o calendário forense do MCP.
- Sem nada crítico, ainda avisa: "Nenhum prazo crítico. O dia está sob controle."
  Silêncio total faz a equipe duvidar se o sistema está no ar.
- Não repete no mesmo dia.

### Ciclo 4 — Alerta crítico
- Vai ao privado do responsável; **três disparos seguidos produzem uma mensagem.**
- Falha de envio grava `sucesso=false` e permite nova tentativa — verificado.
- Triagem `concluído` não gera alerta.
- Silêncio 20h–07h respeitado (a janela cruza a meia-noite: o teste é união, não
  interseção).
- **Publicação sem responsável vai ao grupo.** O pior destino de um prazo crítico é
  destino nenhum, e o texto de grupo já é seguro por construção.

### Ciclo 5 — Botões e callback
- Opt-in completo exercitado contra o serviço rodando: login → `POST /hermes/vinculo/codigo`
  → `/vincular <código>` no webhook → estado `vinculado`.
- **Clique de quem não está vinculado é recusado** com mensagem clara, e a triagem não
  muda. Verificado no banco: antes `novo`, depois `novo`.
- Clique do procurador vinculado gravou `andamento`, `atualizado_por_id = 2` e a
  auditoria com `{"origem": "telegram"}`. Os botões somem da mensagem depois do clique.
- Webhook sem o cabeçalho de segredo, ou com segredo errado: **403**.

---

## 5. O opt-in, e por que ele é de dois fatores

Ninguém é cadastrado sem autorizar. O código nasce no painel — a pessoa precisa da
senha dela para pedir — e é resgatado de dentro do Telegram dela. São dois canais
independentes; nenhum administrador consegue inscrever alguém sozinho.

O código vale **15 minutos** e serve uma vez. Gerar outro invalida o anterior.
Desvincular apaga a linha inteira: o opt-out é tão simples quanto o opt-in.

---

## 6. Decisões que valem registro

1. **Nome de pessoa natural não sai em mensagem alguma** — nem no privado. A task
   permitia "mais contexto" no privado; o mockup dela própria não usava nome nenhum.
   Adotar a regra absoluta a torna testável, e o número do processo já identifica o caso.
2. **Sem inteiro teor no Telegram**, sempre. A mensagem leva um link; o texto se lê no
   painel, onde há login e auditoria.
3. **Sem botão de confirmar ciência de intimação.** Está escrito na tela, não só no
   código: efeito jurídico irreversível não fica a um toque de distância num app de
   mensagem.
4. **Alerta de publicação sem dono vai ao grupo** em vez de sumir.
5. **O serviço sobe sem o token.** Sem `TELEGRAM_BOT_TOKEN` o Hermes fica mudo e o
   resto funciona igual — `hermes_configurado` aparece no `/health`.

---

## 7. Pendências

1. **Nada foi testado contra a Bot API real.** Toda a verificação usou um Telegram
   falso local. Falta criar o bot no `@BotFather`, pôr o token no `.env` de produção e
   rodar `POST /hermes/webhook/registrar`. O webhook exige **HTTPS com URL pública** —
   em `localhost` o Telegram não entrega.
2. **`PAINEL_BASE_URL` precisa ser a URL pública** antes do primeiro envio, senão os
   links das mensagens apontam para `127.0.0.1`.
3. **O critério de pronto da task ainda não foi atingido**, por definição: ele pede
   cinco dias úteis seguidos de resumo às 08:00 sem intervenção. Só o tempo fecha esse.
4. **O painel não recarrega `sessao.usuario`** após o login — vi a barra superior
   mostrar um usuário antigo do `localStorage` enquanto a tela mostrava o correto.
   É anterior a esta task e não é do Hermes, mas confunde.
5. **Sem limite de tentativas no `/auth/login`** (herdado da Task 2).
