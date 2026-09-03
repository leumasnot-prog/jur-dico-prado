<!-- mcp-name: io.github.DeHor-Labs/mcp-juridico-brasil -->

# Painel Jurídico de Pradópolis

Sistema de acompanhamento processual do **Departamento Jurídico da Prefeitura
Municipal de Pradópolis/SP**. Descobre os processos do Município no diário oficial
eletrônico, calcula os prazos com o prazo diferenciado do ente público e organiza a
triagem da equipe.

Duas peças:

| Peça | O que é |
|---|---|
| **`src/mcp_juridico_brasil/`** | Servidor MCP — conecta assistentes de IA ao DataJud e ao DJEN. Publicado no PyPI. |
| **`backend/`** | Serviço FastAPI + PostgreSQL que usa o MCP e serve o painel web. |

---

## O problema que resolve

O DataJud do CNJ é gratuito e cobre 91 tribunais, mas **não indexa o nome das
partes** — verificamos campo a campo. Com ele sozinho é impossível perguntar
*"quais são os processos do Município?"*.

O **DJEN** (Diário de Justiça Eletrônico Nacional, Resolução CNJ 455/2022) indexa
parte e OAB, é público e não exige credencial. É ele que descobre a carteira.

Números de uma varredura real de 30 dias em Pradópolis:

```
344 comunicações brutas → 250 confirmadas → 94 descartadas por homonímia
185 processos · TRT15 e TJSP concentram o acervo · 62% no polo passivo
99 publicações roteadas automaticamente pela OAB do procurador
```

---

## Prazos: a parte que não pode errar

O cálculo é local — não depende de rede — e aplica as regras que mudam conforme o rito:

| Rito | Ato | Prazo | Base legal |
|---|---|---|---|
| Comum | qualquer | **dobro** | art. 183, *caput*, CPC |
| **Trabalhista** | contestar | **quádruplo** | art. 1º, II, DL 779/69 |
| **Trabalhista** | recorrer | **dobro** | art. 1º, III, DL 779/69 |
| Juizado Esp. Fazenda | qualquer | simples | art. 7º da Lei 12.153/2009 |
| Prazo próprio em lei | ex. embargos à exec. fiscal | simples | art. 183, §2º, CPC |

> **O rito trabalhista é o mais fácil de errar.** O prazo diferenciado ali **não vem
> do CPC**, e sim do Decreto-Lei 779/69. Como o TRT15 concentra boa parte do acervo
> de Pradópolis, aplicar o art. 183 subconta a contestação pela metade.

E a contagem respeita os dois saltos do art. 224: a data que o diário informa é a de
**disponibilização**; a publicação é o primeiro dia útil seguinte (§2º), e o prazo só
começa a correr no dia útil seguinte a ela (*caput*).

---

## Como rodar

### Serviço completo (painel + API)

```bash
cd backend
cp .env.example .env          # preencha DATABASE_URL e JWT_SECRET
uv sync
alembic upgrade head
python -m app.criar_chefe "Seu Nome" voce@pradopolis.sp.gov.br
uvicorn app.main:app --reload
```

Painel em `http://127.0.0.1:8000` · API em `/docs`.

### Só o MCP, num assistente de IA

```bash
uvx mcp-juridico-brasil
```

Ferramentas: `descobrir_carteira_processual`, `listar_publicacoes`,
`calcular_proximo_prazo`, `buscar_processo_por_numero`, `listar_movimentacoes`,
`resumir_andamento`, `verificar_certificado_dje`, `listar_tribunais`.

### Console de testes do MCP

```bash
uv run python scripts/console_local.py     # http://127.0.0.1:8777
```

---

## Publicação

Ver [`backend/DEPLOY.md`](backend/DEPLOY.md) — Neon (banco) + Render (serviço), com
as duas pegadinhas da string de conexão do Neon documentadas.

---

## Papéis

| Ação | Chefe | Procurador | Assessor | Estagiário |
|---|:--:|:--:|:--:|:--:|
| Ver o acervo | ✅ | ✅ | ✅ | ✅ |
| Triar publicação | ✅ | ✅ | ✅ | ✅ |
| Atribuir a outra pessoa | ✅ | — | — | — |
| Ver segredo de justiça | ✅ | ✅ | — | — |
| Disparar varredura | ✅ | ✅ | — | — |
| Gerenciar usuários | ✅ | — | — | — |

Permissão é verificada **no backend**. Toda ação vai para uma trilha de auditoria
somente-inserção.

---

## Limites, ditos com todas as letras

- **Não substitui o controle oficial de prazos.** É camada de conferência.
- **O DJEN é feed de publicações, não cadastro de processos.** Feito sem publicação na
  janela não aparece; a cobertura útil começa em 2024.
- **Não lê os autos** — nenhuma fonte pública devolve o teor das peças.
- **Não enxerga processo em segredo de justiça** — bloqueado na origem.
- **Não peticiona, não assina, não protocola.**
- O módulo do **Domicílio Judicial Eletrônico** está pronto no código mas **não
  validado contra a API real** — depende de credenciamento do Município no CNJ.

Ferramenta de apoio ao advogado público. Não constitui consultoria jurídica —
OAB Recomendação 001/2024 e Resolução CNJ 615/2025.

---

## Documentação

- [`docs/tasks/`](docs/tasks/) — tasks de evolução e observações de cada execução
- [`ROADMAP.md`](ROADMAP.md) — estado atual e pendências
- [`MANUAL-PRADOPOLIS.md`](MANUAL-PRADOPOLIS.md) — manual de uso para os advogados

## Licença

MIT.
