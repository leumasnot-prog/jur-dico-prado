# Roadmap — MCP Jurídico Brasil (Pradópolis)

Documento de retomada. Estado real em 02/09/2026, para continuar em outra sessão.

## Grafo de arquitetura e dependências

```mermaid
graph TD
    subgraph S1["🟢 BLOCO 1: OPERACIONAL (Público e Gratuito — 100% Ativo)"]
        A[DJEN público<br/>API Comunica CNJ] --> B[descobrir_carteira_processual]
        A --> C[listar_publicacoes]
        D[DataJud CNJ<br/>API Pública Portaria 160] --> E[buscar_processo_por_numero]
        D --> F[listar_movimentacoes]
        D --> F2[resumir_andamento]
        G[Cálculo local de prazo<br/>Offline - CPC arts. 183/219/220/224] --> H[calcular_proximo_prazo]
    end

    subgraph S2["🟡 BLOCO 2: PENDENTE / FUTURO (Aguarda autorização e contratação da Prefeitura)"]
        I[Certificado A1 mTLS<br/>Pronto no código] --> J[verificar_certificado_dje]
        I --> K[listar_intimacoes]
        P[Provider Comercial / API Paga<br/>Judit / Escavador / TrackJud] --> P1[busca_por_documento_ou_parte]
        
        K -.-> BLOQ["⏸️ PENDENTE DE AUTORIZAÇÃO<br/>• Funcionalidade futura<br/>• API/serviço pago ou convênio formal<br/>• Depende de autorização e contratação da Prefeitura"]
        P -.-> BLOQ
        BLOQ -.libera com credenciais.-> N[DJE_CLIENT_ID / DJE_CLIENT_SECRET / DJE_BASE_URL<br/>configuráveis via .env sem mexer em código]
    end

    style S1 fill:#EAF5EC,stroke:#3E7C4F,stroke-width:2px
    style S2 fill:#FBF6EA,stroke:#8A5A00,stroke-width:2px
    style BLOQ fill:#F7ECD6,stroke:#8A5A00,stroke-width:2px
    style N fill:#FFFFFF,stroke:#8A5A00
```

## Estado dos blocos

### 🟢 O que está pronto, testado e em operação imediata
Estes blocos não dependem de contratação, mensalidade ou chaves pagas. Funcionam com as APIs públicas do Judiciário e cálculo local offline:

| Item | Ferramentas | Fonte / Regra | Status |
|---|---|---|---|
| **Descoberta de carteira** | `descobrir_carteira_processual` | DJEN / Comunica CNJ (público) | ✅ Operacional |
| **Feed de publicações** | `listar_publicacoes` | DJEN / Comunica CNJ (público) | ✅ Operacional |
| **Consulta processual** | `buscar_processo_por_numero` | DataJud CNJ (público) | ✅ Operacional |
| **Andamentos** | `listar_movimentacoes`, `resumir_andamento` | DataJud CNJ (público) | ✅ Operacional |
| **Cálculo de prazos** | `calcular_proximo_prazo` | Arts. 183, 219, 220, 224 CPC | ✅ Operacional |
| **Validação A1** | `verificar_certificado_dje` | Leitor local de `.pfx` mTLS | ✅ Operacional (14 testes) |
| **Console de testes** | `http://127.0.0.1:8777` | Servidor Starlette local | ✅ Operacional |
| **Painel visual** | `painel-pradopolis-local.html` | Interface do Jurídico Pradópolis | ✅ Operacional |

**Total de 357 testes passando (297 no MCP, 60 no backend), ruff e mypy limpos.**

### 🟢 Hermes — avisos no Telegram (Task 3, concluída em 03/09/2026)

| Item | Onde | Status |
|---|---|---|
| Resumo diário 08:00 no grupo | `backend/app/hermes/agendador.py` | ✅ Verificado |
| Alerta crítico no privado | idem | ✅ Verificado |
| Filtro de LGPD (nenhum nome de pessoa natural) | `hermes/formatador.py` | ✅ 5 testes |
| Não-repetição garantida pelo banco | índice parcial `uq_hermes_chave` | ✅ Provado em SQL |
| Opt-in por código, dois fatores | `hermes/webhook.py` + tela do painel | ✅ Ponta a ponta |
| Botão "Marcar como visto" | callback do webhook | ✅ Grava triagem e auditoria |

**Pendente:** nada foi exercitado contra a Bot API real — a verificação usou um Telegram
simulado local. Falta criar o bot no `@BotFather`, configurar `TELEGRAM_BOT_TOKEN` e
`PAINEL_BASE_URL` públicos e chamar `POST /hermes/webhook/registrar`. O webhook exige
HTTPS em URL pública; em `localhost` o Telegram não entrega. Ver `backend/DEPLOY.md`, §6.

---

### ⏸️ Funcionalidade futura / Deixada pendente (APIs Pagas e DJe Oficial)

> **Decisão de projeto:** Este módulo fica oficialmente **pausado/pendente**.
> Será configurado futuramente assim que a Prefeitura de Pradópolis autorizar e formalizar a contratação do serviço/API paga e o credenciamento institucional.

* **O que compreende:**
  1. `listar_intimacoes` (Domicílio Judicial Eletrônico com ciência formal via CNJ PDPJ).
  2. Providers comerciais pagos (Judit, Escavador ou TrackJud para recuperação de acervo passivo anterior a 2024).
* **Motivo da pausa:** Requer autorização administrativa e contratação onerosa pela Prefeitura. O código já está 100% arquitetado e desacoplado — quando a contratação ocorrer, bastará inserir as chaves e os endpoints no arquivo `.env`, sem necessidade de refatoração do sistema.

---

## Pendências de código (refinamentos)

1. **DL 779/69 no painel fiscal** (`painel-fiscal-pradopolis-main/backend/app/juridico/prazo.py`) — alinhar o cálculo do rito trabalhista no painel fiscal com a regra já ajustada no MCP.
2. ~~**Timeout no DJEN**~~ — **resolvido em 03/09/2026.** A varredura do backend passa
   `timeout=90.0` ao construir o `ComunicaClient` (`backend/app/services/acervo.py`). O
   padrão de 45s do MCP fica intocado: quem tem varredura de 2000 itens é o serviço, não
   a biblioteca. O retry com backoff já existia no agendador.
3. **Cosmético**: Atualizar contagem de tribunais no README para refletir exatamente os 92 dicionários suportados.

---

## Como retomar e testar

```bash
cd /Users/samuelpulcini/Downloads/mcp-juridico-brasil-main
uv run --extra dev pytest -q          # executa os 286 testes automatizados
uv run python scripts/console_local.py # abre o console em http://127.0.0.1:8777
```

