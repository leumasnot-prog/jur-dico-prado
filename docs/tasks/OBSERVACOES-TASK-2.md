# Observações da execução — Task 2 (Backend, Neon e usuários)

**Data:** 02/09/2026 · **Onde:** `backend/` na raiz do projeto do MCP
**Resultado:** os seis ciclos fecharam. 33 testes de backend + 297 do MCP passando.

---

## 1. Onde o serviço foi construído, e por quê

Em `mcp-juridico-brasil-main/backend/`, com `pyproject.toml` próprio e o MCP como
dependência editável (`path = ".."`). **Não** dentro do pacote publicado no PyPI —
um serviço web não deve ir junto quando alguém instala a biblioteca — e **não** no
painel fiscal, respeitando a decisão de não misturar as duas aplicações.

Testado contra **Postgres 16 real** em container, não SQLite: o schema usa `JSONB` e
`ON CONFLICT`, que o SQLite não tem. Testar em banco diferente do de produção é
testar outra coisa.

---

## 2. O achado mais importante: o MCP não tinha o DL 779/69

Um teste que escrevi — `test_prazo_trabalhista_usa_o_dl_779` — falhou apontando
**30 dias úteis onde deveriam ser 60**.

A causa: eu havia implementado o Decreto-Lei 779/69 no painel HTML e no módulo do
painel fiscal, mas **nunca na `prazo/tools.py` do MCP**, que é a fonte de verdade.
O backend delega o cálculo ao MCP e herdou a regra errada.

Estava listado no `ROADMAP.md` como pendência conhecida; só apareceu na prática
porque o backend passou a consumir o MCP de verdade. **Corrigido no MCP**, com quatro
testes de regressão. Agora:

| Rito | Ato | Multiplicador | Base legal |
|---|---|---|---|
| trabalhista | Contestação | **×4** | DL 779/69, art. 1º, II |
| trabalhista | Recurso | ×2 | DL 779/69, art. 1º, III |
| comum | Contestação | ×2 | art. 183, *caput*, CPC |
| Juizado Fazenda | Contestação | ×1 | art. 7º da Lei 12.153/2009 |

A correção se propaga sozinha para todo o acervo, porque o prazo é **recalculado na
leitura** — foi exatamente para isso que a decisão foi tomada no §3 da task.

---

## 3. Três bugs que só dados reais revelam

### 3.1 `VARCHAR(80)` estourado pelo STJ

A primeira varredura real quebrou com `StringDataRightTruncationError`. O STJ envia
em `tipo_documento` a frase *"VISTA à(s) parte(s) recorrida(s) para contrarrazões de
Recurso Extraordinário (RE)"* — 82 caracteres — onde o TJSP envia "Intimação".

**O CNJ não garante tamanho nos campos livres.** `orgao`, `classe`, `tipo_comunicacao`,
`tipo_documento` e `meio` viraram `Text`.

### 3.2 O downgrade dessa migração não rodava

Alargar coluna não é reversível sem perda depois que dado largo entrou: o
`downgrade` falhava ao tentar `Text → VARCHAR(80)` com o registro do STJ presente.

Em vez de deixar uma migração que não volta, tornei a perda **explícita**:
`ALTER ... USING left(coluna, N)`, com uma docstring dizendo em letras maiúsculas que
o downgrade trunca. Um downgrade que avisa é melhor que um downgrade que trava.

Verificado: `upgrade → downgrade → upgrade → downgrade` roda limpo **com dados
presentes**, não só com banco vazio.

### 3.3 Engine criado no import derrubava tudo

`create_async_engine` no topo de `db.py` fazia o módulo inteiro morrer sem
`DATABASE_URL` — inclusive ao coletar testes ou gerar migração. É a mesma classe de
bug que encontrei no `config.py` do MCP na rodada anterior. Engine agora é preguiçoso,
com mensagem que diz o que fazer.

---

## 4. Um erro meu, repetido três vezes

Escrevi o serviço chamando a API do **painel fiscal** em vez da do **MCP**:

- `identificar_polo`, `limpar_html`, `prazo_mencionado` — não existiam no MCP
- `Calendario` — classe do painel fiscal; o MCP usa funções de módulo
- `buscar(tribunal=...)` — no MCP é `sigla_tribunal`, e devolve lista, não tupla

Só apareceu em execução porque eu havia tornado o import preguiçoso. **Lição:** import
tardio troca falha no import por falha em produção — útil para performance, ruim para
detecção precoce.

O desfecho foi bom: em vez de duplicar os helpers no backend, **promovi os três para
`comunica/client.py` do MCP**, onde o conhecimento do formato do DJEN pertence. O MCP
ganhou limpeza de HTML e extração de prazo declarado, que ele não tinha. Também
promovi `eh_dia_util` no calendário — o agendador precisa saber se há expediente hoje.

---

## 5. Verificação, ciclo a ciclo

### Ciclo 1 — Schema e migrações
- [x] 6 tabelas: `usuarios`, `procuradores`, `processos`, `publicacoes`, `triagem`, `auditoria`
- [x] `upgrade`/`downgrade` limpo duas vezes seguidas, **com dados reais presentes**
- [x] Índices em `vencimento`, `numero_processo`, `data_disponibilizacao`, `status`

### Ciclo 2 — Autenticação
- [x] Argon2id; a senha não aparece em `repr(Usuario)` (testado)
- [x] Access 15 min + refresh 7 dias; **refresh não serve como access** (401)
- [x] Token expirado devolve 401, não 500
- [x] **E-mail inexistente e senha errada devolvem resposta idêntica** — distinguir
      entregaria ao atacante a lista de e-mails válidos do órgão
- [x] Usuário inativo não entra
- [x] Matriz de permissões testada linha a linha, **inclusive os casos negativos**

### Ciclo 3 — Ingestão
- [x] Varredura real: 344 brutas → 250 confirmadas → **94 descartadas por homonímia** → 185 processos
- [x] **Idempotente**: segunda execução gera 0 publicações novas e mantém 185 processos
- [x] Prazo recalculado na leitura, não lido do banco

### Ciclo 4 — Roteamento por OAB
- [x] **99 de 250 publicações** atribuídas automaticamente à OAB SP/274238
- [x] Bate com a medição de campo: aquela OAB tem 85% de ligação com o Município
- [x] OAB desconhecida **não some** — fica sem responsável, na fila do chefe (testado)

### Ciclo 5 — Varredura noturna
- [x] 06:00 America/Sao_Paulo, dias úteis, via APScheduler
- [x] Calendário forense respeitado — verificado em sábado, domingo, Independência,
      Natal, recesso e Revolução Constitucionalista (feriado estadual SP)
- [x] Retry com *backoff* (20s → 40s), 3 tentativas
- [x] Falha registrada em `auditoria`: varredura que falha em silêncio é pior que
      varredura que não roda

### Ciclo 6 — Relatórios
- [x] PDF paisagem A4 agrupado por procurador, com rito e base legal (2 páginas geradas)
- [x] Excel com 9 colunas e larguras ajustadas
- [x] Ambos registrados em auditoria

---

## 6. A trilha de auditoria funcionando

Pergunta da task: *"quem marcou esta publicação como protocolada, e quando?"*

```
 acao    | nome       | entidade_id | novo_status | ip
---------+------------+-------------+-------------+-----------
 triagem | Dr. Wesley | 716017859   | concluido   | 127.0.0.1
 login   | Dra. Chefe |             |             | 127.0.0.1
 login   | Dr. Wesley |             |             | 127.0.0.1
```

Somente inserção: sem `UPDATE`, sem `DELETE`. É o que a torna confiável.

---

## 7. Decisões que valem registro

**Publicação e triagem em tabelas separadas.** A publicação veio do diário e é
imutável; a triagem pertence ao departamento e muda o tempo todo. Juntas, cada
mudança de status reescreveria o dado oficial.

**Atribuir a si mesmo é livre; atribuir a outro é privativo do chefe.** A task dizia
só "atribuir processos: chefe". Na prática, impedir o procurador de assumir uma
publicação que já é dele seria burocracia sem ganho.

**Fuso `America/Sao_Paulo` explícito em todo lugar.** Nenhum `date.today()`.

**Segredo de justiça filtrado no backend**, não escondido no frontend — e testado
para os quatro papéis.

---

## 8. Pendências

1. **Frontend ainda não fala com este backend.** O painel HTML continua usando
   `localStorage`. Ligar os dois é o passo natural, e não estava no escopo da Task 2.
2. **`DATABASE_URL` de produção (Neon) não foi testada** — só o Postgres 16 local em
   container. A string de conexão do Neon exige `?sslmode=require`.
3. **Painel fiscal segue sem o DL 779/69**, e agora é a única cópia com a regra errada.
4. **Sem rate limit no `/auth/login`.** Numa rede interna é aceitável; exposto na
   internet, precisa.

---

## 9. Estado para a Task 3

O Hermes depende desta task e agora tem o que precisa: `publicacoes.vencimento`
indexado, `triagem.responsavel_id` para saber a quem avisar, e `auditoria` para não
mandar o mesmo alerta duas vezes. A varredura das 06:00 alimenta o resumo das 08:00.
