# Painel Processual — Departamento Jurídico de Pradópolis

Manual de uso e plano de evolução.

Escrito para ser lido por quem vai **usar** o sistema, não por quem vai programá-lo.
Nenhum conhecimento técnico é pressuposto.

---

## Sumário

**Parte I — Como funciona hoje**
1. [O que o sistema faz em uma frase](#1-o-que-o-sistema-faz-em-uma-frase)
2. [De onde vêm os dados](#2-de-onde-vêm-os-dados)
3. [Como o sistema descobre os processos do Município](#3-como-o-sistema-descobre-os-processos-do-município)
4. [As telas, uma a uma](#4-as-telas-uma-a-uma)
5. [Como o prazo é calculado](#5-como-o-prazo-é-calculado)
6. [Rotina diária sugerida](#6-rotina-diária-sugerida)
7. [O que o sistema não faz](#7-o-que-o-sistema-não-faz)

**Parte II — Plano de evolução**
8. [Por que precisamos de banco de dados](#8-por-que-precisamos-de-banco-de-dados)
9. [Certificado digital e o que ele destrava](#9-certificado-digital-e-o-que-ele-destrava)
10. [Login, papéis e trilha de auditoria](#10-login-papéis-e-trilha-de-auditoria)
11. [Roteiro em quatro fases](#11-roteiro-em-quatro-fases)
12. [Glossário](#12-glossário)

---

# Parte I — Como funciona hoje

## 1. O que o sistema faz em uma frase

**Ele varre o diário oficial eletrônico todos os dias, separa o que é do Município,
calcula o prazo de cada publicação já com o prazo em dobro da Fazenda Pública, e
entrega isso pronto para o procurador despachar.**

O que ele substitui, na prática:

| Hoje se faz assim | Com o painel |
|---|---|
| Alguém lê o diário procurando "Pradópolis" | A varredura é automática, nos 4 tribunais de uma vez |
| Anota o processo numa planilha | O processo entra na carteira sozinho |
| Conta o prazo no calendário de parede | O prazo já vem calculado, com os artigos citados |
| Descobre tarde que um prazo venceu | O painel abre mostrando o que vence em 3 dias |

Números da última varredura, para dar escala: **325 publicações** e
**229 processos** do Município em **45 dias**. Distribuídos assim:

- **TRT15** (Justiça do Trabalho, Campinas) — a maior fatia
- **TJSP** — Comarca de Guariba, foro 0222 (Pradópolis não tem vara própria)
- **TST** e **STJ** — recursos que subiram

E o Município está no **polo passivo em 62%** dos casos — ou seja, é réu em quase
dois terços do acervo. Isso é o perfil típico de um jurídico municipal.

---

## 2. De onde vêm os dados

O sistema bebe de **duas fontes públicas e gratuitas**, e é importante entender
o que cada uma dá — porque uma delas tem um limite que define todo o resto.

### Fonte 1 — DJEN / Comunica (a que descobre)

É o **Diário de Justiça Eletrônico Nacional**, criado pela Resolução CNJ 455/2022.
Tudo que é publicado nele é público por lei. Não exige senha nem cadastro.

**O que ela entrega:**
- O texto integral da publicação
- **O nome das partes** ← esta é a chave de tudo
- O nome e a OAB dos advogados intimados
- Tribunal, órgão julgador, classe, tipo de documento
- Link para conferir a publicação no sistema do próprio tribunal

### Fonte 2 — DataJud (a que acompanha)

É a base unificada do CNJ, cobrindo 91 tribunais.

**O que ela entrega:** movimentações do processo, classe, órgão julgador, datas.

**O que ela NÃO entrega — e isso é decisivo:** o DataJud **não indexa o nome das
partes**. Verifiquei os campos disponíveis um a um. Não existe campo de parte.

> **A consequência prática:** com o DataJud sozinho é impossível perguntar
> *"quais são os processos do Município de Pradópolis?"*. Ele só responde sobre
> números de processo que você já conhece. Foi exatamente por isso que ligamos
> o DJEN — é a única fonte pública que sabe quem é parte no quê.

### Fonte 3 — o cálculo, que é local

Os prazos **não** são consultados em lugar nenhum. São calculados na própria
máquina, aplicando o CPC. Isso significa que o cálculo funciona mesmo sem internet
e não depende de nenhum serviço de terceiro continuar existindo.

---

## 3. Como o sistema descobre os processos do Município

Vale entender esse fluxo, porque ele explica por que às vezes aparece coisa que
não é nossa — e por que o sistema descarta sozinho.

```
  ①  Pergunta ao DJEN: "publicações com a palavra PRADOPOLIS"
             │
             ▼
      442 publicações brutas
             │
  ②  Filtra: o destinatário precisa conter PRADOPOLIS
      E TAMBÉM (MUNICIPIO ou PREFEITURA)
             │
             ▼
      325 publicações confirmadas   (117 descartadas)
             │
  ③  Agrupa por número de processo
             ▼
      229 processos na carteira
             │
  ④  Para cada publicação: infere o ato, aplica o CPC,
      calcula o vencimento
             ▼
      Painel pronto
```

**Por que o passo ② existe.** A busca do DJEN é *difusa* — ela casa palavras soltas.
Procurando "PRADOPOLIS" vem também `RESIDENCIAL PRADÓPOLIS SPE LTDA.`, que é uma
empresa privada, nada a ver com o Município. O filtro exige que o nome tenha
"Pradópolis" **e** "Município" ou "Prefeitura". Foi assim que 117 publicações
alheias foram descartadas sem intervenção humana.

**Variações de grafia são tratadas.** O DJEN devolve o mesmo ente escrito de
várias formas — `MUNICIPIO DE PRADOPOLIS`, `PREFEITURA MUNICIPAL DE PRADÓPOLIS`,
`MUNICíPIO DE PRADóPOLIS`. O sistema normaliza acentos e maiúsculas antes de
comparar, então as três caem no mesmo lugar.

---

## 4. As telas, uma a uma

São seis telas. A navegação fica na coluna da esquerda.

### 4.1 Painel — *"o que exige atenção agora"*

É a tela de abertura. Responde a uma pergunta: **o que pode me causar problema hoje?**

**Os cinco indicadores do topo:**

| Indicador | O que significa | O que fazer |
|---|---|---|
| **Prazos em 3 dias** | vencimentos nos próximos 3 dias úteis | despachar hoje |
| **Sem triagem** | publicações que ninguém abriu ainda | ler e classificar |
| **Processos ativos** | feitos com publicação na janela | — |
| **Publicações** | total capturado no período | — |
| **Prazos encerrados** | já venceram | conferir se houve providência |

**Abaixo:** os vencimentos mais próximos (clique em qualquer linha para abrir a
publicação inteira), a distribuição por tribunal, a posição do Município
(autor × réu) e as matérias que mais consomem o departamento.

> **Uso sugerido:** é a tela que o procurador-chefe abre de manhã. Se os dois
> primeiros números estiverem baixos, o dia está sob controle.

---

### 4.2 Publicações — *o feed detalhado*

**É o coração do sistema.** Funciona como uma caixa de entrada de e-mail: a lista
fica à esquerda, o conteúdo à direita.

#### Coluna da esquerda — a fila de triagem

Cada linha traz o número do processo, o tribunal, quantos dias faltam para o
vencimento, a classe, o documento publicado e o ato a praticar.

- **Bolinha verde** = ainda não foi lida por ninguém
- **Etiqueta de prazo** muda de cor: vermelha até 3 dias, âmbar até 7, verde acima

**Filtros disponíveis:**
- Busca livre — funciona sobre número, parte, órgão **e o texto integral** da
  publicação. Procurar "medicamento" acha todas as ações de saúde.
- Por tribunal
- Por situação da triagem: sem triagem / em análise / providenciado
- **Prazo ≤ 3 dias** — o filtro do desespero

#### Coluna da direita — a leitura completa

Aqui está tudo que o advogado precisa para decidir sem abrir outro sistema:

**1. Contagem do prazo** — uma faixa com os quatro marcos:

```
 DISPONIBILIZAÇÃO → PUBLICAÇÃO → TERMO INICIAL → VENCIMENTO
   02/09/2026       03/09/2026     04/09/2026     19/10/2026
    (no DJEN)      1º dia útil     art. 224,      30 dias úteis
                   art. 224 §2º      caput
```

Logo abaixo: os **dias que não foram computados**, nomeados um a um
("07/09/2026 — Independência do Brasil"), e o **fundamento legal escrito por
extenso** — o sistema explica por que aplicou ou não o prazo em dobro.

**2. Avisos de conferência.** Quando o texto da publicação menciona um prazo
diferente do que o sistema calculou, aparece um alerta amarelo. Prazo fixado
pelo juiz prevalece sobre a regra geral — o sistema avisa em vez de esconder.
Há um aviso específico para o rito trabalhista (ver §5.5).

**3. Partes**, com o polo de cada uma, e o Município destacado em verde.

**4. Advogados intimados**, com número da OAB.

**5. Inteiro teor** — o texto integral da publicação, que é de onde sai o ato a
praticar e o prazo.

**6. Link de validação** — abre a publicação no sistema do próprio tribunal.
**Use sempre antes de peticionar.**

**7. Triagem** — quatro botões (sem triagem / em análise / providenciado / sem
providência), campo de procurador responsável e campo de anotação interna.
Fica salvo no navegador daquela máquina.

---

### 4.3 Prazos — *a agenda e a calculadora*

Duas coisas na mesma tela.

**À esquerda, a agenda de vencimentos** — todos os prazos ordenados por data, do
mais urgente ao mais distante, incluindo os vencidos nos últimos 14 dias (para
conferir se houve providência). A etiqueta `×2` marca onde o prazo em dobro foi
aplicado.

**À direita, a calculadora avulsa** — para conferir um prazo à mão, ou calcular
um caso que não veio pelo DJEN. Quatro campos:

| Campo | Observação |
|---|---|
| Disponibilização no DJEN | a data que consta da publicação |
| Ato a praticar | contestação, apelação, embargos… |
| **Rito** | **muda o resultado** — veja §5.4 |
| Parte | Município / Fazenda Pública ou particular |

**Abaixo dela, os feriados locais cadastrados.** Aniversário da cidade, padroeiro,
portarias de suspensão de expediente do foro. **Esta lista precisa ser mantida por
alguém do departamento** — o calendário nacional não conhece feriado de Pradópolis,
e prazo calculado em calendário desatualizado é prazo perdido.

---

### 4.4 Carteira — *o acervo inteiro*

Uma tabela com os 229 processos: número, classe, órgão julgador, polo do Município,
quantas publicações teve, a data da última e o próximo vencimento.

Filtros por texto livre (inclusive por nome da parte contrária), por tribunal e por
polo (réu / autor). Clique em qualquer linha para abrir o processo.

> **Uso sugerido:** relatório mensal para o gabinete, ou distribuição de carga
> entre procuradores.

---

### 4.5 Processo — *a ficha de um feito*

Abre ao clicar numa linha da Carteira. Traz o cabeçalho do processo, as partes
contrárias, os advogados que já apareceram nele, e a **linha do tempo de todas as
publicações** daquele processo — da mais recente para a mais antiga. Clique em
qualquer uma para voltar ao inteiro teor.

---

### 4.6 Minha agenda — *o calendário do que é seu*

As outras telas mostram **o acervo**. Esta mostra **você**: só os prazos sob sua
responsabilidade, mais os processos que você pediu para acompanhar.

Ela tem três partes, e a ordem não é acidental.

**1. A faixa vermelha do topo — o que exige decisão hoje**

Vem antes do calendário de propósito. Um calendário é uma tela que você precisa
*lembrar* de abrir e depois *interpretar*; a faixa já responde: *"estes 3 vencem já,
e 1 venceu"*. Cada linha traz dois botões:

- **Ver** — abre a publicação inteira no leitor.
- **Providenciei** — marca como concluído ali mesmo, sem navegar. O item some da faixa
  na hora, e o contador vermelho no menu diminui.

Quando não há nada apertado, a faixa fica verde: *"Nenhum prazo apertado. Você está em
dia."* É informação, não enfeite — o silêncio deixaria você em dúvida se o sistema
está funcionando.

**2. A grade do mês**

Cada dia mostra até dois prazos, coloridos por urgência: vermelho sólido para vencido,
vermelho vazado até 3 dias úteis, âmbar até 7, verde com mais folga, e riscado para o
que já foi providenciado. Use as setas ‹ › para ver os meses seguintes — é assim que
você enxerga a semana pesada chegando com antecedência.

Os dias **listrados** são dias sem expediente forense: fim de semana, feriado ou
recesso. Isso não é decoração: é a explicação visual de por que a contagem pula. Clique
num deles e o sistema diz por extenso que o prazo não corre ali.

**3. O dia aberto, à direita**

Clicando num dia, os prazos daquela data aparecem com o ato, a classe, quantos dias
úteis faltam e três botões — incluindo o mais importante desta tela:

> **🔕 Me avisa deste** — marque, e o Hermes passa a cobrar você no Telegram sobre esse
> processo específico, mesmo que ele não seja seu. Ao marcar, vira **🔔 Avisando**.

Esse botão existe porque o calendário sozinho não basta para quem tem dificuldade com
prazo: ele é passivo, e depende de você lembrar de abrir. Marcar um processo transforma
o acompanhamento em algo que **vai atrás de você**, não o contrário.

O número vermelho ao lado de "Minha agenda" no menu é o único contador do painel que
fala de você, e não do acervo: são os seus prazos apertados ou vencidos. Ele fica
visível de qualquer tela, e só zera quando você resolve.

---

### 4.7 Avisos no Telegram — *o sistema procurando você*

As telas anteriores esperam que alguém abra o painel. Esta faz o contrário: um bot
chamado **Hermes** leva o recado ao Telegram.

**O que chega, e quando:**

| Aviso | Quando | Onde |
|---|---|---|
| Resumo do dia | 08:00, dias úteis do calendário forense | grupo da Procuradoria |
| Alerta crítico | prazo ≤ 3 dias úteis, ou menção a liminar, tutela de urgência, penhora ou bloqueio | no seu privado |

O resumo traz os prazos que vencem, quantas publicações estão sem triagem e o tamanho
do acervo. **Quando não há nada crítico, ele diz isso** — se o bot ficasse mudo, você
não saberia se o dia está tranquilo ou se o sistema caiu.

O alerta crítico chega **uma vez por publicação**, nunca duas, e traz dois botões:
*Abrir no painel* e *Marcar como visto* — este último grava a triagem como **Em
análise** em seu nome, e a equipe inteira vê no painel.

Das **20h às 07h o bot cala**. O que acontecer nesse intervalo entra no resumo da manhã.

**Como passar a receber:** clique em *Gerar meu código*, abra o Telegram, procure o bot
do Departamento e envie `/vincular` seguido do código. Ele vale 15 minutos e serve uma
vez só. Para parar, o botão *Parar de receber avisos* — sem burocracia.

> **O que nunca vai pelo Telegram.** Nenhum nome de pessoa natural aparece nas
> mensagens — nem no grupo, nem no seu privado. O inteiro teor também não trafega: a
> mensagem leva o número do processo e um link, e o texto se lê no painel, onde há
> login e auditoria. A regra é simples: se a mensagem vazar num print de grupo, ela não
> pode expor mais do que já está no número do processo.

> **O Hermes não dá ciência de intimação.** Nenhum botão do bot produz efeito
> processual. Dar-se por intimado é ato irreversível e não fica a um toque de distância
> num aplicativo de mensagem.

---

### 4.8 Fontes e limites — *a página da honestidade*

Documenta de onde vem cada dado, o que o sistema **não** faz, e a base legal do
tratamento. **Leia antes de confiar em qualquer número** — e mostre esta tela a
quem perguntar de onde vieram as informações.

---

## 5. Como o prazo é calculado

Esta seção é a que os advogados vão querer conferir. Cada regra abaixo está
implementada e testada.

### 5.1 A data de publicação não é a data da disponibilização

O DJEN informa a data em que a publicação foi **disponibilizada**. Mas o
**art. 224, §2º do CPC** diz que a data de *publicação* é o **primeiro dia útil
seguinte** ao da disponibilização. E o prazo só começa a correr no primeiro dia
útil seguinte **à publicação** (art. 224, *caput*).

São dois saltos, não um:

```
disponibilizado 02/09 (qua) → publicado 03/09 (qui) → começa a correr 04/09 (sex)
```

Sem isso, todo prazo sairia **um dia útil adiantado**.

### 5.2 Contagem em dias úteis e recesso

- **Art. 219** — só dias úteis contam
- **Art. 220** — de 20/12 a 20/01 o prazo fica suspenso (recesso forense)
- Sábados, domingos, feriados nacionais e estaduais são pulados
- Feriados municipais entram pela lista da tela Prazos

O sistema mostra cada dia pulado e o motivo.

### 5.3 O prazo em dobro da Fazenda Pública

**Art. 183 do CPC** — o Município tem prazo em dobro para todas as suas
manifestações processuais. Era o erro mais grave da versão anterior do sistema,
que contava sempre prazo simples e **errava pela metade em quase todo cálculo**.

### 5.4 As três exceções ao dobro

Aqui é onde o sistema pode surpreender quem espera sempre o dobro:

| Situação | Prazo | Por quê |
|---|---|---|
| Rito comum, Município | **dobro** | art. 183, *caput* |
| **Juizado Especial da Fazenda Pública** | **simples** | art. 7º da Lei 12.153/2009 afasta o prazo diferenciado |
| **Embargos à execução fiscal** | 30 dias (próprio) | art. 16 da LEF — prazo próprio em lei afasta o dobro (art. 183, §2º) |
| Parte particular | simples | não é Fazenda Pública |

Por isso o campo **Rito** da calculadora importa tanto.

### 5.5 A ressalva do rito trabalhista

**Leia com atenção, porque é a maior fatia do acervo.**

Na Justiça do Trabalho o prazo em dobro do ente público **não vem do art. 183 do
CPC** — vem do **Decreto-Lei 779/69**, que concede prazo **em dobro para recorrer**
e **em quádruplo para contestar**.

O sistema **exibe um aviso** em toda publicação trabalhista, mas **ainda aplica a
regra do CPC nesse rito**. Enquanto isso não for corrigido:

> **Todo prazo trabalhista deve ser conferido manualmente.**

Está no topo do plano de melhorias (§11, Fase 1).

---

## 6. Rotina diária sugerida

Uma proposta de fluxo para o departamento:

**Manhã — 10 minutos, quem estiver de plantão**
0. O resumo do Hermes chega às 08:00 no grupo. Ele diz se há algo urgente **antes**
   de alguém abrir o sistema — mas não substitui os passos seguintes.
1. Abrir o **Painel**. Olhar os dois primeiros números.
2. Ir em **Publicações**, filtrar por **Sem triagem**.
3. Para cada uma: ler o inteiro teor, conferir o ato e o prazo, atribuir um
   responsável e marcar **Em análise**.
4. Qualquer coisa com prazo ≤ 3 dias vira assunto imediato.

**Ao longo do dia — cada procurador**
5. Filtrar Publicações pelo próprio nome no campo de responsável.
6. Antes de peticionar, abrir o **link de validação** e conferir no sistema do
   tribunal.
7. Protocolado o ato, marcar **Providenciado**. Feito isso, o Hermes para de
   alertar sobre ele.

**Uma vez, por pessoa**
7b. Tela **Avisos no Telegram** → *Gerar meu código* → `/vincular` no bot. Sem esse
    passo, os alertas do que é seu não chegam a você — vão para o grupo.

**Semanalmente — procurador-chefe**
8. **Carteira** para a visão do acervo; **Prazos** para conferir se algum
   vencimento passou sem providência.

**Sempre que houver portaria de suspensão de expediente**
9. Cadastrar a data nos feriados locais. Sem isso, os prazos daquele período
   saem errados.

---

## 7. O que o sistema não faz

Ser claro sobre isso evita confiança indevida.

- **Não substitui o controle oficial de prazos.** É camada de conferência.
- **Não é cadastro de processos, é feed de publicações.** Processo que não teve
  publicação na janela não aparece. A cobertura útil do DJEN começa em 2024 — em
  2023 há pouquíssimo, e antes disso praticamente nada. **A carteira histórica
  completa não sai daqui.**
- **Não lê os autos.** Nenhuma fonte pública devolve o teor das peças, só o texto
  da publicação.
- **Não enxerga processo em segredo de justiça** — é bloqueado na origem.
- **Não peticiona, não assina, não protocola.**
- **Não dispensa a conferência no portal do tribunal.**

Fundamento de conformidade: ferramenta de apoio ao advogado público, sem constituir
consultoria jurídica — OAB Recomendação 001/2024 e Resolução CNJ 615/2025. Dados
públicos por força da Resolução CNJ 455/2022, tratados nas hipóteses do art. 7º,
II e III da LGPD.

---

# Parte II — Plano de evolução

## 8. Por que precisamos de banco de dados

### O limite de hoje

O painel atual é **um arquivo só**. A triagem — responsável, situação, anotação —
fica gravada **no navegador da máquina onde foi feita**. Consequências:

- O que o Procurador A marcou, o Procurador B **não vê**
- Trocar de computador **perde tudo**
- Limpar o histórico do navegador **perde tudo**
- Não há histórico de quem fez o quê
- A carteira histórica não pode ser acumulada — cada varredura recomeça

### O que o banco resolve

Um banco de dados transforma o painel de *visualizador* em **sistema de gestão**:

| Recurso | O que muda na prática |
|---|---|
| **Acervo acumulado** | processos ficam guardados para sempre, não só os 45 dias da varredura |
| **Triagem compartilhada** | todos veem o mesmo estado, em tempo real |
| **Distribuição de carga** | cada procurador tem a sua fila |
| **Histórico de movimentação** | dá para ver a evolução do processo ao longo dos anos |
| **Trilha de auditoria** | quem leu o quê, quando |
| **Relatórios** | acervo por matéria, tempo médio, produtividade, passivo por assunto |
| **Anexos** | peças, pareceres, minutas presos ao processo |
| **Alertas** | e-mail quando um prazo entra em zona crítica |

### Como fica a arquitetura

Hoje:

```
   Painel (arquivo HTML)      Servidor MCP  ──→  DJEN + DataJud
   guarda no navegador
```

Depois:

```
   Painel  ──→  Serviço (API)  ──→  Banco de dados
                     │                 acervo, triagem, prazos,
                     │                 usuários, auditoria
                     ▼
                Servidor MCP  ──→  DJEN + DataJud + DJe
                     │
                Certificado A1 do Município
```

O serviço passa a ser o **único ponto que fala com os tribunais** e o único que
guarda o certificado. Isso é o que torna a auditoria confiável.

**Escolha técnica sugerida:** PostgreSQL. Gratuito, maduro, roda em servidor
modesto, e é o padrão em administração pública. O serviço em FastAPI (Python),
que é a mesma linguagem do MCP já construído — não precisa de mais uma
tecnologia na casa.

---

## 9. Certificado digital e o que ele destrava

### A correção que precisa ficar clara

**A carteira da OAB — física ou o aplicativo — não autentica nada em API de
tribunal.** Ela é documento de identidade profissional. Quem autentica perante o
Judiciário é **certificado digital ICP-Brasil**.

### Os dois certificados que interessam

**e-CNPJ do Município, tipo A1** — é o que o Domicílio Judicial Eletrônico exige.

> **Atenção ao tipo.** **A1 é arquivo** (`.pfx`), instalável no servidor, e permite
> operação automática. **A3 é token físico ou cartão** e exige alguém plugado na
> máquina — **não serve para automação**. Se o certificado do Município for A3,
> a varredura automática do DJe não funciona. Confirme isso antes de contratar.

**e-CPF do procurador** — o DJe exige o cabeçalho `On-behalf-Of` com o CPF do
responsável, justamente para registrar quem deu ciência.

### O que o certificado destrava

O **Domicílio Judicial Eletrônico**, que o Município é obrigado a manter desde
30/09/2024 e que é a fonte **oficial** das intimações — diferente do DJEN, que é
o diário público.

| | DJEN (hoje) | DJe (com certificado) |
|---|---|---|
| Credencial | nenhuma | certificado ICP-Brasil |
| Natureza | diário público | intimação dirigida ao Município |
| Cobertura | só o que foi publicado | **tudo que é endereçado ao ente** |
| Histórico | útil a partir de 2024 | completo |
| Efeito jurídico | nenhum | **confirmar leitura inicia o prazo** |

> **O ponto mais delicado do projeto inteiro.** Confirmar leitura de intimação
> pelo DJe **inicia oficialmente a contagem do prazo e é irreversível**. Hoje o
> MCP já protege isso com dois cadeados técnicos (um parâmetro explícito mais uma
> variável de ambiente). Quando houver login, o cadeado certo passa a ser humano:
> **um procurador solicita, o chefe aprova**. Nenhuma automação deve confirmar
> leitura sozinha.

---

## 10. Login, papéis e trilha de auditoria

### Quem entra no sistema

Recomendação: **SSO com o Gov.br** (Login Único, disponível para a administração
pública), exigindo conta **nível prata ou ouro** para procuradores. Elimina gestão
de senha e herda a prova de identidade do governo federal. Se a prefeitura já
tem Active Directory, integrar por LDAP resolve igualmente bem.

### Papéis sugeridos

| Papel | Pode |
|---|---|
| **Procurador-chefe** | tudo, inclusive aprovar confirmação de leitura |
| **Procurador** | ver e triar sua carteira, solicitar confirmação de leitura |
| **Assessor** | ver e triar, sem confirmar leitura |
| **Estagiário** | ver o que não é sigiloso, sem confirmar leitura |

Segredo de justiça fica restrito a quem tem atribuição.

### Onde a OAB realmente entra

Ela não autentica — mas é a **chave de roteamento**, e vale mais do que parece.
Cadastrando a OAB de cada procurador, o sistema entrega a publicação direto ao
responsável, sem triagem manual.

Testei com dados reais do Município, e o filtro **discrimina bem**:

| OAB | publicações | ligadas ao Município | leitura |
|---|---|---|---|
| SP/274238 | 161 | 137 (**85%**) | procurador do ente |
| SP/325606 | 127 | 60 (47%) | atua para os dois lados |
| SP/201321 | 351 | 46 (13%) | advogado da parte contrária |

O próprio percentual serve de conferência: se uma OAB cadastrada como do
departamento vier com 13%, foi cadastrada errado.

> **Ressalva honesta:** não existe API pública limpa para verificar se uma OAB está
> ativa — o cadastro nacional da OAB tem captcha e é hostil a automação. Dá para
> fazer o cruzamento acima mais conferência manual no cadastramento. Isso é
> **conferência**, não autenticação, e não deve ser chamado de outra coisa.

### Trilha de auditoria

Registrar, sem possibilidade de edição: quem entrou, quando, o que leu, o que
triou, e **sobretudo quem confirmou leitura de intimação** — com CPF, endereço de
origem, data, hora e uma marca de integridade do registro.

---

## 11. Roteiro em quatro fases

Ordenado por **retorno sobre esforço**, não por dificuldade técnica.

### Fase 1 — Corrigir o que está errado *(sem infraestrutura nova)*

- [ ] **Prazo trabalhista pelo Decreto-Lei 779/69** — dobro para recorrer,
      quádruplo para contestar. É a maior fatia do acervo e hoje está pela regra
      errada. **Prioridade máxima.**
- [ ] Cadastro dos feriados municipais e das portarias de suspensão do foro
- [ ] Cadastro das OAB dos procuradores e roteamento automático das publicações

> Nada aqui depende de banco, certificado ou servidor. É o melhor retorno imediato.

### Fase 2 — Banco de dados

- [ ] PostgreSQL e serviço em FastAPI
- [ ] Acervo acumulado (não só a janela da varredura)
- [ ] Triagem compartilhada entre procuradores
- [ ] Varredura automática diária
- [ ] Relatórios de acervo e produtividade

### Fase 3 — Login e auditoria

- [ ] SSO Gov.br ou Active Directory
- [ ] Papéis e restrição de segredo de justiça
- [ ] Trilha de auditoria imutável
- [ ] Alertas por e-mail em zona crítica de prazo

### Fase 4 — Certificado e Domicílio Judicial Eletrônico

- [ ] Contratar/confirmar **e-CNPJ A1** (não A3)
- [ ] Credenciar o Município no portal do DJe
- [ ] Integrar e validar a API Comunica autenticada
- [ ] Aprovação por dois procuradores para confirmar leitura
- [ ] Migrar a fonte primária de intimações do DJEN para o DJe

**Por que o certificado vem por último:** é o item que mais depende de terceiros
(contratação, credenciamento, prazos administrativos) e o de maior risco jurídico.
Faz sentido chegar nele com o resto já rodando e auditável.

---

## 12. Glossário

| Termo | Em português claro |
|---|---|
| **API** | forma de um programa pedir dados a outro, sem pessoa no meio |
| **MCP** | o programa que criamos, que conversa com os tribunais e responde ao assistente de IA |
| **DJEN** | Diário de Justiça Eletrônico Nacional — o diário público |
| **DJe / Domicílio Judicial Eletrônico** | a caixa postal oficial do Município no CNJ |
| **DataJud** | base de dados do CNJ com as movimentações dos 91 tribunais |
| **ICP-Brasil** | o sistema oficial de certificados digitais do país |
| **e-CNPJ A1** | certificado do Município em arquivo — permite automação |
| **e-CNPJ A3** | certificado em token físico — **não** permite automação |
| **SSO / Gov.br** | entrar no sistema com a conta única do governo |
| **Disponibilização** | o dia em que a publicação entrou no diário |
| **Publicação** | o primeiro dia útil seguinte — é dela que corre o prazo |
| **Termo inicial** | o primeiro dia efetivamente contado do prazo |
| **Polo ativo / passivo** | quem processa / quem é processado |
| **Triagem** | ler a publicação, entender o ato e decidir o encaminhamento |

---

*Documento gerado com base na aplicação em funcionamento e verificado contra as
APIs reais do CNJ. Os números citados vêm de varredura efetiva do acervo do
Município.*
