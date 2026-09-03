# Observações da execução — Task 1 (UX e Onboarding)

**Data:** 02/09/2026 · **Alvo:** `painel-pradopolis-local.html` (626 KB → 660 KB)
**Resultado:** os quatro ciclos fecharam. Todos os itens de verificação da task passaram.

---

## 1. Descoberta que mudou o escopo

**O painel não tinha o Decreto-Lei 779/69.** A task pedia um tooltip explicando a
etiqueta `15 × 4` — mas o painel só sabia calcular `× 2`. O tooltip seria uma explicação
para algo que a tela nunca mostrava.

Pior que isso: **o painel exibia prazos trabalhistas pela metade**. Contestação em
rito trabalhista aparecia como 30 dias úteis quando são 60 (art. 1º, II, do DL 779/69).
A regra já existia no MCP desde a rodada anterior; o painel standalone tinha sido
construído antes e ficou para trás.

Implementei a regra antes do Ciclo 1, porque um tooltip não pode explicar uma regra
que o sistema não aplica. **Impacto medido no acervo real de Pradópolis:**

| Regra aplicada | Publicações | O que mudou |
|---|---:|---|
| Quádruplo (DL 779/69, art. 1º, II) | 96 | eram 30 dias úteis, agora 60 |
| Dobro CLT (DL 779/69, art. 1º, III) | 66 | fundamento corrigido |
| Dobro CPC (art. 183) | 87 | inalterado |
| Simples | 76 | inalterado |

**96 publicações de 325 tinham prazo subcontado pela metade.** Isso não era refinamento
de interface — era erro de cálculo em quase um terço do acervo.

Também alinhei o prazo simples de Recurso Ordinário de 15 para **8 dias** (art. 895 da
CLT), que era outra divergência entre o painel e o MCP.

---

## 2. Desvios deliberados da especificação

### 2.1 O tooltip "prazo simples" virou três

A task especificava um texto único para a etiqueta `prazo simples`, redigido em torno
do Juizado Especial da Fazenda Pública. Ao testar, encontrei o problema: em
**embargos à execução fiscal** (rito comum, prazo próprio do art. 16 da LEF) o tooltip
abria falando de Juizado — o motivo errado.

Separei em três explicações escolhidas pelo motivo real:

- `jefp` — art. 7º da Lei 12.153/2009
- `proprio` — art. 183, §2º do CPC, citando o art. 16 da LEF
- `nao_fazenda` — parte não é Fazenda Pública

Um tooltip que explica a regra errada é pior que nenhum tooltip: ensina errado com
ar de autoridade.

### 2.2 Um sexto tooltip não previsto

A task listava cinco. Acrescentei `dobro_clt` (dobro para recorrer na Justiça do
Trabalho), porque ele é distinto do dobro do art. 183 e aparece em 66 publicações.
Sem ele, a etiqueta `8 × 2` num recurso trabalhista abriria a explicação do CPC.

---

## 3. Bug encontrado durante a verificação

O cabeçalho do painel de leitura tinha uma etiqueta fixa **"Prazo em dobro · art. 183"**,
exibida sempre que havia multiplicador. Depois do DL 779/69, ela passou a contradizer
o fundamento logo abaixo: o cabeçalho dizia CPC, o rodapé dizia Decreto-Lei.

Só apareceu no screenshot — nenhum teste programático pegaria, porque ambos os textos
existiam e estavam "corretos" isoladamente. Corrigido para refletir a regra real, e
verificado nos quatro casos:

| Regra | Cabeçalho | Etiqueta | Fundamento |
|---|---|---|---|
| quádruplo | Prazo quádruplo · DL 779/69 | 60 dias úteis | DL 779/69 |
| dobro CLT | Prazo em dobro · DL 779/69 | 10 dias úteis | DL 779/69 |
| dobro CPC | Prazo em dobro · art. 183 | 30 dias úteis | art. 183 |
| próprio | *(sem etiqueta)* | 30 dias úteis | art. 183, §2º |

**Lição:** coerência entre textos distintos que descrevem o mesmo fato não é capturada
por teste unitário. Precisa de olho na tela.

---

## 4. Verificação, item a item

### Ciclo 1 — Tooltips
- [x] Abrem por clique e por teclado (são `<button>`, Enter/Espaço nativos)
- [x] `Esc` fecha **e devolve o foco ao botão**; clique fora fecha; abrir um fecha o anterior
- [x] Clicar de novo no mesmo botão fecha (toggle)
- [x] Popover nunca sai da tela — testado em 1440, 1024 e 768px
- [x] Contraste: **10,25:1** (claro) e **10,16:1** (escuro) no corpo; 17,6 e 14,7 nos títulos. AA exige 4,5
- [x] `aria-expanded` alterna; popover tem `role="dialog"` e `aria-label`

### Ciclo 2 — Tour
- [x] Os 6 passos navegam sozinhos entre `#painel`, `#publicacoes` e `#prazos`
- [x] Recorte válido (largura e altura > 10px) em todos os 6
- [x] Setas ←/→ avançam e voltam; `Esc` sai a qualquer momento
- [x] Sair no meio não deixa overlay órfão nem trava o scroll do body
- [x] Rodar duas vezes seguidas funciona, sem máscara duplicada
- [x] Convite só na primeira visita, dispensável, sem modal bloqueante para quem já viu
- [x] `prefers-reduced-motion` troca o scroll suave por corte seco

### Ciclo 3 — Estados vazios
- [x] Busca sem resultado → "Nenhuma publicação com esses filtros" + botão que funciona
- [x] Prazo crítico vazio → **"Nenhum prazo crítico · O dia está sob controle"**, com
      classe própria e cor de boa notícia. É a única mensagem vazia que não é neutra
- [x] Leitor vazio e Carteira vazia explicam o próximo passo
- [x] Faixa educativa dispensável, e o "dispensar" persiste após re-render
- [x] `localStorage` bloqueado (simulado com `defineProperty` que lança) não quebra nada

### Ciclo 4 — Acessibilidade e polimento
- [x] Todos os botões de ajuda são focáveis, rotulados e operáveis por teclado
- [x] Prazo crítico tem **texto** ("2 dias", "vence hoje"), não só cor
- [x] Zero erro no console em todas as telas
- [x] Sem scroll horizontal em 1440, 1024 e 768px
- [x] Três estados de tema conferidos pelo token `--surface`:
      claro `#FFFFFF` · escuro `#141C1A` · sistema segue o SO

---

## 5. Decisões técnicas que valem registro

**Zero dependências, como a task exigia.** O tour tem ~130 linhas escritas à mão. O
painel continua abrindo com duplo clique, offline. Nenhum CDN.

**A seta do popover usa `var(--seta)`.** Na primeira versão eu injetava um `<style>`
por popover aberto — funcionava e era lixo. Trocado por variável CSS declarada uma vez.

**O tour não trava se um alvo sumir.** Se `querySelector` do passo devolver `null`,
ele pula para o próximo em vez de travar num recorte vazio. Um layout que mude no
futuro degrada, não quebra.

**Passos que precisam de publicação selecionada se viram sozinhos.** Os passos 3, 4 e 5
mostram o painel de leitura; se nada estiver selecionado, o tour seleciona a primeira
publicação antes de desenhar o recorte.

---

## 6. O que ficou de fora, e por quê

**Não migrei estas melhorias para o módulo jurídico do painel fiscal.** As três telas
React em `painel-fiscal-pradopolis-main` continuam sem tooltip, sem tour — e, mais
grave, **continuam sem o DL 779/69**. Aquele módulo segue com a decisão em aberto
(manter ou reverter), e não faria sentido investir nele antes disso.

Se a decisão for manter, o DL 779/69 lá é urgente pelo mesmo motivo que era aqui.

---

## 7. Estado para a Task 2

O painel está pronto e autoexplicativo, mas continua **sem persistência**: a triagem
mora no `localStorage` de uma máquina só. O critério de pronto da Task 1 foi atingido
— um estagiário consegue triar e explicar por que o prazo é de 60 dias. O que ele
ainda não consegue é que o colega veja o que ele fez.

É exatamente o que a Task 2 resolve.
