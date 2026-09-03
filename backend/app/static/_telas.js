const EXPLICACOES = {
  publicacao: {
    t: "Por que a publicação é no dia seguinte",
    c: "O diário informa a data de <b>disponibilização</b>. O CPC considera publicado no primeiro dia útil seguinte (art. 224, §2º) — e o prazo só começa a correr no dia útil seguinte à publicação (art. 224, <em>caput</em>). São dois saltos, não um."
  },
  dobro_cpc: {
    t: "Prazo em dobro da Fazenda Pública",
    c: "O Município tem prazo em dobro para todas as suas manifestações processuais (art. 183, <em>caput</em>, do CPC). O prazo simples de 15 dias úteis passa a 30."
  },
  quadruplo: {
    t: "Prazo quádruplo na Justiça do Trabalho",
    c: "Na Justiça do Trabalho o prazo diferenciado <b>não vem do CPC</b>, e sim do Decreto-Lei 779/69: quádruplo para contestar (art. 1º, II) e dobro para recorrer (art. 1º, III)."
  },
  dobro_clt: {
    t: "Prazo em dobro para recorrer",
    c: "Na Justiça do Trabalho o ente público recorre em dobro por força do Decreto-Lei 779/69, art. 1º, III — <b>não</b> pelo art. 183 do CPC, que não se aplica a este rito."
  },
  jefp: {
    t: "Por que aqui não há dobro",
    c: "No Juizado Especial da Fazenda Pública não existe prazo diferenciado para a Fazenda (art. 7º da Lei 12.153/2009), o que afasta o dobro do art. 183 do CPC."
  },
  proprio: {
    t: "Prazo próprio fixado em lei",
    c: "Quando a lei fixa prazo específico para o ato, o dobro do art. 183 <b>não incide</b> (art. 183, §2º, do CPC). É o caso dos embargos à execução fiscal, com 30 dias pelo art. 16 da Lei 6.830/80."
  },
  nao_fazenda: {
    t: "Prazo simples",
    c: "O prazo diferenciado do art. 183 do CPC vale para a Fazenda Pública. Fora dessa hipótese, aplica-se o prazo simples."
  },
  polo: {
    t: "Posição do Município",
    c: "<b>Passivo</b> = o Município é réu, foi processado. <b>Ativo</b> = o Município é autor, processou. Em Pradópolis, 62% do acervo é passivo — o perfil típico de um jurídico municipal."
  }
};

/** Botão de ajuda ancorado a um dado. `k` é a chave em EXPLICACOES. */
// Se a regra vier desconhecida do backend, o botão simplesmente não aparece —
// melhor sem explicação do que a tela inteira quebrar.
const ajuda = k => !EXPLICACOES[k] ? "" : `<button type="button" class="explica" data-explica="${k}"
  aria-expanded="false" aria-label="Explicação: ${esc(EXPLICACOES[k].t)}">?</button>`;

let popAberto = null;
function fecharPop(){
  if(!popAberto) return;
  popAberto.botao?.setAttribute("aria-expanded","false");
  popAberto.el.remove();
  popAberto = null;
}
function abrirPop(botao){
  const chave = botao.dataset.explica, dados = EXPLICACOES[chave];
  if(!dados) return;
  const jaEra = popAberto?.botao === botao;
  fecharPop();
  if(jaEra) return;                       // clicar de novo fecha

  const el = document.createElement("div");
  el.className = "pop";
  el.setAttribute("role","dialog");
  el.setAttribute("aria-label", dados.t);
  el.innerHTML = `<h4>${esc(dados.t)}</h4><div>${dados.c}</div>`;
  document.body.appendChild(el);

  // Posiciona abaixo do botão; sobe se não couber. Corrige transbordo lateral.
  const b = botao.getBoundingClientRect(), r = el.getBoundingClientRect();
  const margem = 10;
  let topo = b.bottom + 9, lado = "baixo";
  if(topo + r.height > innerHeight - margem){ topo = b.top - r.height - 9; lado = "cima"; }
  let esq = b.left + b.width/2 - r.width/2;
  esq = Math.max(margem, Math.min(esq, innerWidth - r.width - margem));
  el.style.top = `${Math.max(margem, topo)}px`;
  el.style.left = `${esq}px`;
  el.dataset.lado = lado;
  // seta apontando para o botão, presa aos limites do balão
  // A seta acompanha o botão, mas fica presa aos limites do balão para não
  // "vazar" quando o popover é empurrado pela borda da tela.
  const seta = Math.max(12, Math.min(b.left + b.width/2 - esq - 4.5, r.width - 21));
  el.style.setProperty("--seta", `${seta}px`);

  botao.setAttribute("aria-expanded","true");
  popAberto = { el, botao };
}

document.addEventListener("click", e => {
  const botao = e.target.closest?.(".explica");
  if(botao){ e.stopPropagation(); abrirPop(botao); return; }
  if(!e.target.closest?.(".pop")) fecharPop();
});
document.addEventListener("keydown", e => {
  if(e.key === "Escape" && popAberto){ const b = popAberto.botao; fecharPop(); b?.focus(); }
});
addEventListener("scroll", fecharPop, true);
addEventListener("resize", fecharPop);

/* ═══════════════════════════════════════════════════════════════
   Telas
   ═══════════════════════════════════════════════════════════════ */
// Acesso TARDIO: o shell só existe depois do login, então capturar o elemento
// no carregamento do script guarda um null para sempre.
const view = new Proxy({}, {
  get: (_, prop) => {
    const n = el("view");
    const v = n?.[prop];
    return typeof v === "function" ? v.bind(n) : v;
  },
  set: (_, prop, valor) => { const n = el("view"); if (n) n[prop] = valor; return true; },
});

function barras(obj, total){
  const ent = Object.entries(obj).sort((a,b)=>b[1]-a[1]).slice(0,8);
  return `<div class="bars">${ent.map(([k,v])=>`
    <div class="bar-row">
      <div>
        <div class="bar-lbl"><span>${esc(titulo(k))}</span><span>${v}</span></div>
        <div class="track"><div class="fill" style="width:${(v/total*100).toFixed(1)}%"></div></div>
      </div>
      <div class="bar-pct">${Math.round(v/total*100)}%</div>
    </div>`).join("")}</div>`;
}
const conta = (arr, f) => arr.reduce((a,x)=>{ const k=f(x); a[k]=(a[k]||0)+1; return a; },{});

/* ── Painel ─────────────────────────────────────────────────── */
function telaPainel(){
  const abertos = PUBS.filter(p => p.prazo.restantes >= 0);
  const crit = abertos.filter(p => p.prazo.restantes <= 3);
  const sem = PUBS.filter(p => p.status_triagem === "novo");
  const vencidos = PUBS.filter(p => p.prazo.restantes < 0 && p.status_triagem !== "concluido");
  const prox = [...abertos].sort((a,b)=>a.prazo.fim.localeCompare(b.prazo.fim)).slice(0,9);

  view.innerHTML = `
  <div class="kpis">
    <div class="kpi crit"><div class="k">Prazos em 3 dias</div><div class="v">${crit.length}</div>
      <div class="d">exigem despacho imediato</div></div>
    <div class="kpi warn"><div class="k">Sem triagem</div><div class="v">${sem.length}</div>
      <div class="d">publicações ainda não lidas</div></div>
    <div class="kpi acc"><div class="k">Processos ativos</div><div class="v">${PROCESSOS.length}</div>
      <div class="d">com publicação na janela</div></div>
    <div class="kpi ok"><div class="k">Publicações</div><div class="v">${PUBS.length}</div>
      <div class="d">últimos 45 dias</div></div>
    <div class="kpi"><div class="k">Prazos encerrados</div><div class="v">${vencidos.length}</div>
      <div class="d">verificar se houve providência</div></div>
  </div>

  <div class="grid2" style="margin-bottom:14px">
    <div class="card">
      <div class="card-h"><h3>Vencimentos mais próximos</h3>
        <span class="hint">art. 183 do CPC aplicado</span></div>
      <div class="agenda">
        ${prox.map(p=>`
        <div class="ag-row" data-goto="${esc(p.id)}">
          <div><div class="ag-date">${fmtD(p.prazo.fim)}</div>
            <div class="ag-when">${sevTxt(p.prazo.restantes)}</div></div>
          <div><div class="cell-num">${esc(p.numero)}</div>
            <div class="cell-sub">${esc(p.ato)} · ${esc(titulo(p.classe))}</div></div>
          <span class="pill ${sev(p.prazo.restantes)}">${p.prazo.dias}du${p.prazo.dobro?" ×2":""}</span>
        </div>`).join("")}
      </div>
    </div>
    <div class="stack">
      <div class="card">
        <div class="card-h"><h3>Distribuição por tribunal</h3></div>
        ${barras(conta(PROCESSOS,p=>p.tribunal), PROCESSOS.length)}
      </div>
      <div class="card">
        <div class="card-h"><h3>Posição do Município</h3></div>
        ${barras(conta(PROCESSOS,p=>p.polo==="passivo"?"Polo passivo (réu)":p.polo==="ativo"?"Polo ativo (autor)":"Não informado"), PROCESSOS.length)}
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>Matérias que mais consomem o departamento</h3>
      <span class="hint">por processo, não por publicação</span></div>
    ${barras(conta(PROCESSOS,p=>p.classe), PROCESSOS.length)}
  </div>`;
  view.querySelectorAll("[data-goto]").forEach(r =>
    r.onclick = () => { sel = r.dataset.goto; location.hash = "#publicacoes"; });
}

/* ── Publicações (feed bipartido) ───────────────────────────── */
let sel = null, filtro = { q:"", trib:"", status:"", prazo:"" };

const FAIXA_VISTA = "pradopolis.faixa.v1";

function faixaEducativa(){
  if(leu(FAIXA_VISTA)) return "";
  return `<div class="faixa" id="faixa">
    <span>⚖️</span>
    <span>Os prazos aqui já consideram o prazo diferenciado do ente público
      (arts. 183 e 224 do CPC; Decreto-Lei 779/69 no rito trabalhista).
      <b>Confira sempre no portal do tribunal antes de peticionar</b> — este painel é
      apoio, não controle oficial de prazo.</span>
    <button class="fechar" aria-label="Dispensar aviso">×</button>
  </div>`;
}

function telaPublicacoes(){
  view.innerHTML = faixaEducativa() + `
  <div class="feed">
    <div class="feed-list">
      <div class="feed-tools">
        <input class="feed-search" id="q" placeholder="Buscar por número, parte, órgão ou teor…" value="${esc(filtro.q)}">
        <div class="chips" id="chips-t"></div>
        <div class="chips" id="chips-s"></div>
      </div>
      <div class="feed-scroll" id="flist"></div>
    </div>
    <div class="reader" id="reader"></div>
  </div>`;

  const tribs = [...new Set(PUBS.map(p=>p.tribunal))].sort();
  el("chips-t").innerHTML = [["","Todos"],...tribs.map(t=>[t,t])]
    .map(([v,l])=>`<button class="chip" data-f="trib" data-v="${v}" aria-pressed="${filtro.trib===v}">${l}</button>`).join("");
  el("chips-s").innerHTML = [["","Tudo"],["novo","Sem triagem"],["andamento","Em análise"],
    ["concluido","Providenciado"],["__crit","Prazo ≤ 3 dias"]]
    .map(([v,l])=>{ const on = v==="__crit" ? filtro.prazo==="crit" : filtro.status===v && filtro.prazo!=="crit";
      return `<button class="chip" data-f="${v==="__crit"?"prazo":"status"}" data-v="${v==="__crit"?"crit":v}" aria-pressed="${on}">${l}</button>`; }).join("");

  view.querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const f = c.dataset.f, v = c.dataset.v;
    if(f==="prazo"){ filtro.prazo = filtro.prazo==="crit" ? "" : "crit"; filtro.status=""; }
    else { filtro[f] = filtro[f]===v ? "" : v; if(f==="status") filtro.prazo=""; }
    telaPublicacoes();
  });
  el("q").oninput = e => { filtro.q = e.target.value; pintaLista(); };
  el("faixa")?.querySelector(".fechar")?.addEventListener("click", () => {
    grava(FAIXA_VISTA, "1");
    el("faixa").remove();
  });
  pintaLista(); pintaLeitor();
}

function filtrados(){
  const q = semAcento(filtro.q).toLowerCase();
  return PUBS.filter(p => {
    if(filtro.trib && p.tribunal !== filtro.trib) return false;
    if(filtro.status && p.status_triagem !== filtro.status) return false;
    if(filtro.prazo === "crit" && !(p.prazo.restantes >= 0 && p.prazo.restantes <= 3)) return false;
    if(!q) return true;
    return semAcento(`${p.numero} ${p.orgao} ${p.classe} ${p.texto} ${p.partes.map(x=>x.nome).join(" ")}`)
      .toLowerCase().includes(q);
  });
}

function pintaLista(){
  const lst = filtrados();
  const box = el("flist");
  if(!lst.length){
    // "Nenhum prazo crítico" é boa notícia e precisa soar como tal — não pode
    // usar o mesmo tom de "sua busca não achou nada".
    box.innerHTML = filtro.prazo === "crit"
      ? `<div class="empty bom"><strong>Nenhum prazo crítico</strong>
           Nada vence nos próximos 3 dias úteis. O dia está sob controle.
           <button class="btn sm" data-limpar="1">Ver todas as publicações</button></div>`
      : `<div class="empty"><strong>Nenhuma publicação com esses filtros</strong>
           Tente outro termo de busca ou remova os filtros ativos.
           <button class="btn sm" data-limpar="1">Limpar filtros</button></div>`;
    box.querySelector("[data-limpar]").onclick = () => {
      filtro = { q:"", trib:"", status:"", prazo:"" };
      telaPublicacoes();
    };
    return;
  }
  box.innerHTML = lst.map(p => {
    const s = p, r = p.prazo.restantes;
    return `<div class="fitem ${sel===String(p.id)?"sel":""}" data-id="${p.id}">
      <div class="fitem-top">
        ${s.status==="novo"?'<span class="unread"></span>':""}
        <span class="fitem-num">${esc(p.numero)}</span>
        <span class="tag">${esc(p.tribunal)}</span>
        <span class="pill ${sev(r)}" style="margin-left:auto">${sevTxt(r)}</span>
      </div>
      <div class="fitem-cls">${esc(titulo(p.classe))} · ${esc(p.documento||p.tipo)}</div>
      <div class="fitem-bot">
        <span class="mono">${fmtD(p.data)}</span>·<span>${esc(p.ato)}</span>
        ${s.responsavel_nome?`·<span>${esc(s.responsavel_nome)}</span>`:""}
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll(".fitem").forEach(n => n.onclick = () => { sel = n.dataset.id; telaPublicacoes(); });
}

function pintaLeitor(){
  const box = el("reader");
  const p = PUBS.find(x => String(x.id) === String(sel));
  if(!p){ box.innerHTML = `<div class="empty"><strong>Selecione uma publicação</strong>
    Clique num item da lista à esquerda para ler o inteiro teor, conferir a contagem
    do prazo e fazer a triagem.</div>`; return; }
  const s = p, z = p.prazo;
  const divergente = p.declarado && p.declarado.dias !== z.simples;

  box.innerHTML = `
  <div class="reader-h">
    <h2 class="mono">${esc(p.numero)}</h2>
    <div class="sub" style="color:var(--muted);font-size:12.5px">
      ${esc(titulo(p.classe))} · ${esc(p.orgao)} · ${esc(p.tribunal)}</div>
    <div style="display:flex;gap:6px;margin-top:9px;flex-wrap:wrap">
      <span class="pill ${sev(z.restantes)}">Prazo ${sevTxt(z.restantes)}</span>
      <span class="pill acc">Município no polo ${esc(p.poloEnte)}</span>
      <span class="pill neutral">${esc(p.documento||p.tipo)}</span>
      ${z.mult>1 ? `<span class="pill ${z.regra==="quadruplo"?"warn":"info"}">${
        z.regra==="quadruplo" ? "Prazo quádruplo · DL 779/69"
        : z.regra==="dobro_clt" ? "Prazo em dobro · DL 779/69"
        : "Prazo em dobro · art. 183"}</span>` : ""}
    </div>
  </div>

  <div class="reader-body">
    <div class="sect">
      <div class="sect-t">Contagem do prazo</div>
      <div class="prazo-box">
        <div class="prazo-head">
          <strong style="font-family:var(--slab);font-size:14px">${esc(z.ato)}</strong>
          <span class="pill neutral">${z.dias} dias úteis</span>
          ${z.mult>1
            ? `<span class="pill ${z.regra==="quadruplo"?"warn":"info"}">${z.simples} × ${z.mult}</span>${ajuda(z.regra)}`
            : `<span class="pill neutral">prazo simples</span>${ajuda(z.regra)}`}
          <span style="margin-left:auto;font-size:11.5px;color:var(--muted)">rito ${esc(z.rito)}</span>
        </div>
        <div class="prazo-grid">
          <div class="pstep"><div class="pl">Disponibilização</div>
            <div class="pv">${fmtD(z.disponibilizacao)}</div><div class="pn">no DJEN</div></div>
          <div class="pstep"><div class="pl">Publicação${ajuda("publicacao")}</div>
            <div class="pv">${fmtD(z.publicacao)}</div><div class="pn">1º dia útil seguinte<br>art. 224, §2º</div></div>
          <div class="pstep"><div class="pl">Termo inicial</div>
            <div class="pv">${fmtD(z.termo)}</div><div class="pn">art. 224, caput</div></div>
          <div class="pstep"><div class="pl">Vencimento</div>
            <div class="pv" style="color:var(--${sev(z.restantes)==="crit"?"crit":sev(z.restantes)==="warn"?"warn":"ok"})">${fmtD(z.fim)}</div>
            <div class="pn">${sevTxt(z.restantes)}</div></div>
        </div>
        ${z.obstaculos.length?`<div class="legal"><b>Dias não computados:</b> ${
          z.obstaculos.map(o=>`${fmtD(o[0])} — ${esc(o[1])}`).join(" · ")}</div>`:""}
        <div class="legal">${esc(z.fundamento)}</div>
      </div>
      ${divergente?`<div class="note"><b>Conferir:</b> o texto da publicação menciona
        “${esc(p.declarado.trecho)}”, mas a contagem acima usa ${z.simples} dias úteis para
        ${esc(z.ato)}. Quando o juízo fixa prazo diverso, prevalece o prazo do despacho.</div>`:""}
      ${z.rito==="trabalhista"?`<div class="note"><b>Rito trabalhista:</b> a contagem em dias úteis
        segue o art. 775 da CLT e o prazo em dobro do ente público vem do Decreto-Lei 779/69,
        não do art. 183 do CPC. Confira o prazo no PJe-JT antes de agendar.</div>`:""}
    </div>

    <div class="sect">
      <div class="sect-t">Partes</div>
      <div class="parties">
        ${p.partes.map(x=>`<div class="party ${ehEnte(x.nome)?"ente":""}">
          <span class="polo">${POLO[(x.polo||"").toUpperCase()]||"—"}</span>
          <span>${esc(x.nome)}</span></div>`).join("")}
      </div>
    </div>

    ${p.advogados.length?`<div class="sect">
      <div class="sect-t">Advogados intimados</div>
      <div class="parties">${p.advogados.map(a=>`<div class="party">
        <span class="polo">OAB</span><span>${esc(a.nome)}</span>
        <span class="mono" style="color:var(--muted);font-size:11.5px">${esc(a.oab)}</span></div>`).join("")}</div>
    </div>`:""}

    <div class="sect">
      <div class="sect-t">Inteiro teor</div>
      <div class="teor">${esc(p.texto || "Sem texto disponível nesta comunicação.")}</div>
      <dl class="kv" style="margin-top:4px">
        <dt>Meio</dt><dd>${esc(p.meio||"—")}</dd>
        <dt>Tipo</dt><dd>${esc(p.tipo||"—")} · ${esc(p.documento||"—")}</dd>
        <dt>Órgão</dt><dd>${esc(p.orgao||"—")}</dd>
        ${p.link?`<dt>Validação</dt><dd><a href="${esc(p.link)}" target="_blank" rel="noopener"
          style="color:var(--accent);word-break:break-all">Conferir no sistema do tribunal ↗</a></dd>`:""}
      </dl>
    </div>

    <div class="sect">
      <div class="sect-t">Triagem</div>
      <div class="triage">
        ${[["novo","Sem triagem"],["andamento","Em análise"],["concluido","Providenciado"],
           ["sem_providencia","Sem providência"]].map(([v,l])=>
          `<button class="btn sm" data-set="${v}" aria-pressed="${s.status_triagem===v}">${l}</button>`).join("")}
      </div>
      <div style="display:grid;gap:10px;margin-top:4px">
        <div class="fld"><label for="nota">Anotação interna</label>
          <input id="nota" value="${esc(s.anotacao)}" placeholder="providência adotada"></div>
      </div>
    </div>
  </div>`;

  box.querySelectorAll("[data-set]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    if (await salvarTriagem(p, { status_triagem: b.dataset.set })) telaPublicacoes();
    else b.disabled = false;
  });
  const nota = el("nota");
  if (nota) nota.onchange = async () => {
    if (await salvarTriagem(p, { anotacao: nota.value })) pintaLista();
  };
}

/* ── Prazos ─────────────────────────────────────────────────── */
function telaPrazos(){
  const abertos = PUBS.filter(p => p.prazo.restantes >= -14)
    .sort((a,b)=>a.prazo.fim.localeCompare(b.prazo.fim));
  view.innerHTML = `
  <div class="split">
    <div class="card">
      <div class="card-h"><h3>Agenda de vencimentos</h3>
        <span class="hint">${abertos.length} prazos · art. 183 do CPC aplicado ao Município</span></div>
      <div class="agenda">${abertos.map(p=>{
        const s = p;
        return `<div class="ag-row" data-goto="${p.id}">
          <div><div class="ag-date">${fmtD(p.prazo.fim)}</div>
            <div class="ag-when">${sevTxt(p.prazo.restantes)}</div></div>
          <div><div class="cell-num">${esc(p.numero)} <span class="tag">${esc(p.tribunal)}</span></div>
            <div class="cell-sub">${esc(p.ato)} · ${esc(titulo(p.classe))}${s.responsavel_nome?` · ${esc(s.responsavel_nome)}`:""}</div></div>
          <div style="display:flex;gap:5px;align-items:center">
            ${p.prazo.dobro?'<span class="pill info">×2</span>':""}
            <span class="pill ${sev(p.prazo.restantes)}">${p.prazo.dias}du</span>
          </div>
        </div>`;}).join("")}</div>
    </div>

    <div class="stack">
      <div class="card">
        <div class="card-h"><h3>Calculadora de prazo</h3></div>
        <div class="calc">
          <div class="fld"><label for="c-data">Disponibilização no DJEN</label>
            <input type="date" id="c-data" value="${iso(new Date())}"></div>
          <div class="fld"><label for="c-ato">Ato a praticar</label>
            <select id="c-ato">${Object.keys(PRAZOS).map(k=>
              `<option${k==="Contestação"?" selected":""}>${k}</option>`).join("")}</select></div>
          <div class="fld"><label for="c-rito">Rito</label>
            <select id="c-rito">
              <option value="comum">Comum (art. 183 aplica)</option>
              <option value="jefp">Juizado Especial da Fazenda Pública</option>
              <option value="trabalhista">Trabalhista</option>
            </select></div>
          <div class="fld"><label for="c-faz">Parte</label>
            <select id="c-faz">
              <option value="1">Município / Fazenda Pública</option>
              <option value="0">Particular</option>
            </select></div>
          <div class="calc-out" id="c-out"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-h"><h3>Feriados locais</h3>
          <span class="hint">o que o calendário nacional não cobre</span></div>
        <div style="padding:13px 16px;font-size:12.5px;line-height:1.6;color:var(--ink-2)">
          Feriados municipais e portarias de suspensão de expediente do foro são
          configurados no servidor, em <code>JURIDICO_FERIADOS_LOCAIS</code>, e valem
          para todo o acervo assim que salvos — os prazos são recalculados na leitura.
          <div class="note" style="margin-top:9px">Mantenha essa lista atualizada.
            Prazo calculado sobre calendário desatualizado é prazo perdido.</div>
        </div>
      </div>
      </div>
    </div>
  </div>`;

  const rodar = async () => {
    // Quem calcula é o backend, que delega ao MCP — a tela não duplica a regra.
    let z;
    try {
      z = await api("/acervo/calcular-prazo", { method: "POST", body: JSON.stringify({
        disponibilizacao: el("c-data").value, ato: el("c-ato").value,
        rito: el("c-rito").value, fazenda_publica: el("c-faz").value === "1",
      })});
    } catch (erro) {
      el("c-out").innerHTML = `<div style="color:var(--crit);font-size:12.5px">${esc(erro.message)}</div>`;
      return;
    }
    el("c-out").innerHTML = `
      <div style="font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600">Vencimento</div>
      <div class="big">${fmtD(z.fim)}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:2px">
        ${z.dias} dias úteis${z.mult>1?` (${z.simples} × ${z.mult})`:""} · publicação em ${fmtD(z.publicacao)} · termo em ${fmtD(z.termo)}</div>
      <div style="font-size:11.5px;color:var(--muted);margin-top:9px;line-height:1.5;
        border-top:1px solid var(--line);padding-top:9px">${esc(z.fundamento)}</div>
      ${z.obstaculos.length?`<div style="font-size:11.5px;color:var(--muted);margin-top:7px">
        <b style="color:var(--ink-2)">Não computados:</b> ${z.obstaculos.map(o=>fmtD(o[0])).join(" · ")}</div>`:""}`;
  };
  ["c-data","c-ato","c-rito","c-faz"].forEach(i => el(i).onchange = rodar);
  rodar();
  view.querySelectorAll("[data-goto]").forEach(r =>
    r.onclick = () => { sel = r.dataset.goto; location.hash = "#publicacoes"; });
}

/* ── Carteira ───────────────────────────────────────────────── */
let cf = { q:"", trib:"", polo:"" };
const AJUDA_POLO = `<button type="button" class="explica" data-explica="polo"
  aria-expanded="false" aria-label="Explicação: posição do Município">?</button>`;

function telaCarteira(){
  const q = semAcento(cf.q).toLowerCase();
  const lst = PROCESSOS.filter(p =>
    (!cf.trib || p.tribunal===cf.trib) && (!cf.polo || p.polo===cf.polo) &&
    (!q || semAcento(`${p.numero} ${p.classe} ${p.orgao} ${p.contra.join(" ")}`).toLowerCase().includes(q)));
  const tribs = [...new Set(PROCESSOS.map(p=>p.tribunal))].sort();

  view.innerHTML = `
  <div class="card">
    <div class="card-h">
      <h3>Carteira processual</h3>
      <span class="hint">${lst.length} de ${PROCESSOS.length} processos</span>
    </div>
    <div style="padding:11px 14px;border-bottom:1px solid var(--line);display:flex;gap:9px;flex-wrap:wrap">
      <input class="feed-search" style="max-width:320px" id="cq"
        placeholder="Buscar número, classe, órgão ou parte contrária…" value="${esc(cf.q)}">
      <div class="chips">${[["","Todos"],...tribs.map(t=>[t,t])].map(([v,l])=>
        `<button class="chip" data-f="trib" data-v="${v}" aria-pressed="${cf.trib===v}">${l}</button>`).join("")}</div>
      <div class="chips">${[["","Ambos os polos"],["passivo","Réu"],["ativo","Autor"]].map(([v,l])=>
        `<button class="chip" data-f="polo" data-v="${v}" aria-pressed="${cf.polo===v}">${l}</button>`).join("")}</div>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Processo</th><th>Classe</th><th>Órgão</th>
          <th>Polo${AJUDA_POLO}</th>
          <th>Publicações</th><th>Última</th><th>Próximo prazo</th>
        </tr></thead>
        <tbody>${lst.map(p=>`
          <tr data-num="${esc(p.numero)}">
            <td><div class="cell-num">${esc(p.numero)}</div>
              <div class="cell-sub">${esc(p.tribunal)}</div></td>
            <td>${esc(titulo(p.classe))}</td>
            <td style="max-width:230px">${esc(p.orgao)}</td>
            <td><span class="pill ${p.polo==="passivo"?"warn":"acc"}">${esc(p.polo)}</span></td>
            <td class="num">${p.pubs.length}</td>
            <td class="cell-num">${fmtD(p.ultima)}</td>
            <td>${p.proximo?`<span class="pill ${sev(p.proximo.restantes)}">${fmtD(p.proximo.fim)}</span>`
              :'<span class="pill neutral">sem prazo aberto</span>'}</td>
          </tr>`).join("")}</tbody>
      </table>
    </div>
  </div>`;
  el("cq").oninput = e => { cf.q = e.target.value; telaCarteira(); el("cq").focus(); };
  view.querySelectorAll(".chip").forEach(c => c.onclick = () => {
    cf[c.dataset.f] = cf[c.dataset.f]===c.dataset.v ? "" : c.dataset.v; telaCarteira(); });
  view.querySelectorAll("tbody tr").forEach(r =>
    r.onclick = () => { proc = r.dataset.num; location.hash = "#processo"; });
}

/* ── Processo ───────────────────────────────────────────────── */
let proc = null;
function telaProcesso(){
  const p = PROCESSOS.find(x => x.numero === proc) || PROCESSOS[0];
  if(!p){ view.innerHTML = `<div class="empty"><strong>Carteira vazia</strong>
    Uma <em>varredura</em> é a leitura automática do diário oficial em busca do nome do
    Município — é ela que descobre os processos e alimenta esta tela.</div>`; return; }
  proc = p.numero;
  view.innerHTML = `
  <div class="stack">
    <div class="card">
      <div class="card-h" style="align-items:flex-start;flex-direction:column;gap:7px">
        <h3 class="mono" style="font-size:16px">${esc(p.numero)}</h3>
        <div style="font-size:12.5px;color:var(--muted)">${esc(titulo(p.classe))} · ${esc(p.orgao)} · ${esc(p.tribunal)}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span class="pill ${p.polo==="passivo"?"warn":"acc"}">Município no polo ${esc(p.polo)}</span>
          <span class="pill neutral">${p.pubs.length} publicações</span>
          ${p.proximo?`<span class="pill ${sev(p.proximo.restantes)}">Próximo prazo ${fmtD(p.proximo.fim)} · ${sevTxt(p.proximo.restantes)}</span>`:""}
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0">
        <div style="padding:14px 16px;border-right:1px solid var(--line)">
          <div class="sect-t" style="margin-bottom:8px">Partes contrárias</div>
          <div class="parties">${p.contra.length?p.contra.map(c=>
            `<div class="party"><span>${esc(c)}</span></div>`).join(""):'<span style="color:var(--muted);font-size:12.5px">—</span>'}</div>
        </div>
        <div style="padding:14px 16px">
          <div class="sect-t" style="margin-bottom:8px">Advogados intimados</div>
          <div class="parties">${p.advogados.length?p.advogados.map(a=>
            `<div class="party"><span style="font-size:12.5px">${esc(a)}</span></div>`).join(""):'<span style="color:var(--muted);font-size:12.5px">—</span>'}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>Linha do tempo das publicações</h3>
        <span class="hint">clique para abrir o inteiro teor</span></div>
      <div class="agenda">${p.pubs.map(x=>`
        <div class="ag-row" data-goto="${x.id}">
          <div><div class="ag-date">${fmtD(x.data)}</div>
            <div class="ag-when">${esc(x.tribunal)}</div></div>
          <div><div style="font-size:13px;font-weight:500">${esc(x.documento||x.tipo)}</div>
            <div class="cell-sub">${esc((x.texto||"").slice(0,120))}…</div></div>
          <span class="pill ${sev(x.prazo.restantes)}">${fmtD(x.prazo.fim)}</span>
        </div>`).join("")}</div>
    </div>
  </div>`;
  view.querySelectorAll("[data-goto]").forEach(r =>
    r.onclick = () => { sel = r.dataset.goto; location.hash = "#publicacoes"; });
}

/* ── Fontes e limites ───────────────────────────────────────── */
function telaFontes(){
  view.innerHTML = `
  <div class="grid2">
    <div class="card">
      <div class="card-h"><h3>De onde vem cada dado</h3></div>
      <div style="padding:15px 17px;display:flex;flex-direction:column;gap:14px;font-size:13px;line-height:1.6">
        <div>
          <span class="pill acc">DJEN · Comunica</span>
          <p style="margin:7px 0 0">Feed público de publicações do Diário de Justiça Eletrônico Nacional
          (Resolução CNJ 455/2022). Sem autenticação. É a <b>única fonte pública que indexa o nome
          das partes</b> — por isso é ela que descobre a carteira, e não o DataJud.
          Alimenta: publicações, partes, advogados, inteiro teor, link de validação.</p>
        </div>
        <div>
          <span class="pill acc">DataJud CNJ</span>
          <p style="margin:7px 0 0">Base unificada do CNJ, 91 tribunais, gratuita.
          Alimenta: movimentações, classe, órgão julgador, datas.
          <b>Não indexa partes</b> e tem defasagem de T+1 a T+7 dias.</p>
        </div>
        <div>
          <span class="pill neutral">Cálculo local</span>
          <p style="margin:7px 0 0">Prazos calculados no próprio servidor MCP, sem chamada externa:
          art. 219 (dias úteis), 224 §2º (publicação no 1º dia útil seguinte à disponibilização),
          220 (recesso de 20/12 a 20/01) e 183 (dobro da Fazenda Pública).</p>
        </div>
      </div>
    </div>

    <div class="stack">
      <div class="card">
        <div class="card-h"><h3>O que este painel não faz</h3></div>
        <div style="padding:15px 17px;display:flex;flex-direction:column;gap:11px;font-size:12.5px;line-height:1.6">
          <div><b>Não substitui o controle oficial de prazos.</b> O DJEN é feed de publicações,
            não cadastro de processos: um feito sem publicação na janela não aparece, e a cobertura
            útil começa em 2024.</div>
          <div><b>Não lê os autos.</b> Nenhuma das fontes públicas devolve o teor das peças —
            só o texto da publicação.</div>
          <div><b>Não enxerga processos em segredo de justiça.</b> São bloqueados na origem.</div>
          <div><b>Não dispensa a conferência no portal do tribunal</b> antes de qualquer
            ato processual.</div>
        </div>
      </div>
      <div class="card">
        <div class="card-h"><h3>Conformidade</h3></div>
        <div style="padding:15px 17px;font-size:12.5px;line-height:1.6;color:var(--ink-2)">
          Ferramenta de apoio ao advogado público. Não constitui consultoria jurídica; a análise e a
          decisão processual são do procurador habilitado — OAB Recomendação 001/2024 e Resolução
          CNJ 615/2025. Dados públicos por força da Resolução CNJ 455/2022, tratados na
          hipótese do art. 7º, II e III da LGPD.
          <div class="note" style="margin-top:11px">Nesta demonstração os nomes de pessoas naturais
            foram substituídos por pseudônimos. Os números de processo, órgãos e classes são reais.</div>
        </div>
      </div>
    </div>
  </div>`;
}


/* ═══════════════════════════════════════════════════════════════
   Minha agenda — calendário pessoal

   PRINCÍPIO: calendário é interface PASSIVA. Só ajuda quem lembra de
   abrir, e quem tem dificuldade com prazo é exatamente quem não lembra.
   Por isso a tela tem três camadas, nesta ordem de peso visual:

     1. A faixa "agora"  — decisão, não consulta. Vem antes de tudo.
     2. A grade do mês   — planejamento, e o feriado explicando a contagem.
     3. "Me avisa deste" — o empurrão, que não depende de abrir a tela.

   O estado vazio da faixa é uma RECOMPENSA ("você está em dia"), não um
   "nada encontrado": para quem teme a tela de prazos, o alívio importa.
   ═══════════════════════════════════════════════════════════════ */

const MESES = ["janeiro","fevereiro","março","abril","maio","junho",
               "julho","agosto","setembro","outubro","novembro","dezembro"];
const DIAS_CURTOS = ["dom","seg","ter","qua","qui","sex","sáb"];
const DIAS_LONGOS = ["domingo","segunda","terça","quarta","quinta","sexta","sábado"];
const SEV_TXT = { vencido:"Vencido", critico:"Crítico", atencao:"Atenção",
                  tranquilo:"No prazo", feito:"Providenciado" };

let AG = { mes:null, dados:null, pendencias:[], dia:null };

const mesAtual = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
};

function mesVizinho(m, passo){
  const [a, mm] = m.split("-").map(Number);
  const d = new Date(Date.UTC(a, mm - 1 + passo, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,"0")}`;
}

/** Abre a publicação no leitor, pelo mesmo caminho das outras telas. */
const irParaPub = id => { sel = id; location.hash = "#publicacoes"; };

const emDiasUteis = n => n < 0
  ? `venceu há ${-n} ${-n === 1 ? "dia útil" : "dias úteis"}`
  : n === 0 ? "vence hoje"
  : `faltam ${n} ${n === 1 ? "dia útil" : "dias úteis"}`;

function telaAgenda(){
  view.innerHTML = `
    <div id="ag-agora"></div>
    <div class="split">
      <div class="card">
        <div class="cal-topo">
          <button class="btn sm" id="ag-ant" aria-label="Mês anterior">‹</button>
          <div class="cal-mes" id="ag-mes">—</div>
          <button class="btn sm" id="ag-prox" aria-label="Próximo mês">›</button>
        </div>
        <div id="ag-grade"><div class="empty"><strong>Carregando…</strong></div></div>
        <div class="legenda">
          <span><i style="background:var(--crit)"></i>Vencido</span>
          <span><i style="background:var(--crit-soft);box-shadow:inset 0 0 0 1px var(--crit)"></i>Até 3 dias úteis</span>
          <span><i style="background:var(--warn-soft)"></i>Até 7</span>
          <span><i style="background:var(--ok-soft)"></i>Mais folga</span>
          <span><i style="background:repeating-linear-gradient(135deg,var(--surface) 0 3px,var(--surface-2) 3px 6px)"></i>Sem expediente — o prazo não corre</span>
        </div>
      </div>
      <div class="card">
        <div class="card-h"><h3 id="ag-dia-t">Selecione um dia</h3></div>
        <div id="ag-dia"><div class="empty"><strong>Clique num dia do calendário</strong>
          <span>Os prazos daquele dia aparecem aqui, com o que fazer em cada um.</span></div></div>
      </div>
    </div>`;

  el("ag-ant").onclick  = () => carregarAgenda(mesVizinho(AG.mes, -1));
  el("ag-prox").onclick = () => carregarAgenda(mesVizinho(AG.mes, +1));
  carregarAgenda(AG.mes || mesAtual());
}

async function carregarAgenda(mes){
  AG.mes = mes;
  el("ag-mes").textContent = `${MESES[Number(mes.split("-")[1]) - 1]} ${mes.split("-")[0]}`;
  try{
    const [dados, pend] = await Promise.all([agenda.mes(mes), agenda.pendencias()]);
    AG.dados = dados; AG.pendencias = pend;
  }catch(erro){
    el("ag-grade").innerHTML = `<div class="empty"><strong>Não foi possível carregar</strong>
      <span>${esc(erro.message)}</span></div>`;
    return;
  }
  pintarAgora();
  pintarGrade();
  if(AG.dia) pintarDia(AG.dia);
}

/* ── Camada 1: a faixa que responde "o que eu faço agora" ────────── */

function pintarAgora(){
  const itens = AG.pendencias, caixa = el("ag-agora");
  if(!itens.length){
    caixa.innerHTML = `<div class="agora calmo"><div class="agora-h">
      <span class="num">✓</span>
      <span>Nenhum prazo apertado. Você está em dia.</span></div></div>`;
    return;
  }
  const vencidos = itens.filter(i => i.severidade === "vencido").length;
  caixa.innerHTML = `<div class="agora">
    <div class="agora-h"><span class="num">${itens.length}</span>
      <span>${itens.length === 1 ? "prazo exige" : "prazos exigem"} decisão hoje${
        vencidos ? ` — <b>${vencidos} já ${vencidos === 1 ? "venceu" : "venceram"}</b>` : ""}</span></div>
    <div class="agora-lista">${itens.map(i => `
      <div class="agora-item">
        <div class="quando">${emDiasUteis(i.dias_uteis)}</div>
        <div class="oq">
          <div class="cell-num">${esc(i.numero)} <span class="tag">${esc(i.tribunal)}</span></div>
          <div class="cell-sub">${esc(i.ato || "—")} · vence ${fmtD(i.vencimento)}</div>
        </div>
        <div class="acoes">
          <button class="btn sm" data-abrir="${esc(i.id)}">Ver</button>
          <button class="btn sm" data-feito="${esc(i.id)}">Providenciei</button>
        </div>
      </div>`).join("")}</div></div>`;
  ligarAcoes(caixa);
}

/* ── Camada 2: a grade do mês ────────────────────────────────────── */

function pintarGrade(){
  const { dias, nao_uteis, hoje: hojeIso, mes } = AG.dados;
  const naoUteis = new Set(nao_uteis);
  const [ano, mm] = mes.split("-").map(Number);
  const vazios = new Date(Date.UTC(ano, mm - 1, 1)).getUTCDay();
  const ultimoDia = new Date(Date.UTC(ano, mm, 0)).getUTCDate();

  let html = DIAS_CURTOS.map(d => `<div class="cal-h">${d}</div>`).join("");
  for(let i = 0; i < vazios; i++) html += `<div class="cal-d fora"></div>`;

  for(let d = 1; d <= ultimoDia; d++){
    const iso = `${ano}-${String(mm).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const itens = dias[iso] || [];
    const cls = ["cal-d"];
    if(naoUteis.has(iso)) cls.push("nao-util");
    if(iso === hojeIso)   cls.push("hoje");
    if(iso === AG.dia)    cls.push("sel");
    const mostra = itens.slice(0, 2), resto = itens.length - mostra.length;
    html += `<button class="${cls.join(" ")}" data-dia="${iso}"
        aria-label="dia ${d}, ${itens.length} ${itens.length === 1 ? "prazo" : "prazos"}${
          naoUteis.has(iso) ? ", sem expediente forense" : ""}">
      <span class="n">${d}</span>
      <span class="cal-pts">${mostra.map(i =>
        `<span class="cal-pt ${i.severidade}">${esc(i.ato || i.tribunal)}</span>`).join("")}${
        resto > 0 ? `<span class="cal-mais">+${resto}</span>` : ""}</span>
    </button>`;
  }
  el("ag-grade").innerHTML = `<div class="cal">${html}</div>`;
  el("ag-grade").querySelectorAll("[data-dia]").forEach(b =>
    b.onclick = () => pintarDia(b.dataset.dia));
}

/* ── Camada 3: o dia aberto, com "me avisa deste" ────────────────── */

function pintarDia(iso){
  AG.dia = iso;
  pintarGrade();
  const itens = AG.dados.dias[iso] || [];
  const semExpediente = AG.dados.nao_uteis.includes(iso);
  el("ag-dia-t").textContent = `${DIAS_LONGOS[parseD(iso).getUTCDay()]}, ${fmtD(iso)}`;

  if(!itens.length){
    el("ag-dia").innerHTML = `<div class="empty">
      <strong>Nenhum prazo seu neste dia</strong>
      <span>${semExpediente
        ? "E não há expediente forense nesta data — o prazo não corre."
        : "Dia livre na sua agenda."}</span></div>`;
    return;
  }

  const pilula = s => s === "vencido" || s === "critico" ? "crit"
                    : s === "atencao" ? "warn" : s === "feito" ? "neutral" : "ok";

  el("ag-dia").innerHTML = `<div class="dia-det">
    ${semExpediente ? `<div class="note"><b>Sem expediente forense nesta data.</b>
      O cálculo empurra para o próximo dia útil qualquer prazo que cairia aqui.</div>` : ""}
    ${itens.map(i => `
      <div class="dia-item ${i.severidade}">
        <div>
          <div class="cell-num">${esc(i.numero)} <span class="tag">${esc(i.tribunal)}</span>
            <span class="pill ${pilula(i.severidade)}">${SEV_TXT[i.severidade]}</span></div>
          <div class="cell-sub">${esc(i.ato || "—")} · ${esc(titulo(i.classe || ""))}</div>
        </div>
        <div class="cell-sub">${emDiasUteis(i.dias_uteis).replace(/^./, c => c.toUpperCase())}${
          i.meu ? "" : " · <i>processo que você acompanha</i>"}</div>
        <div class="acoes">
          <button class="btn sm" data-abrir="${esc(i.id)}">Abrir</button>
          ${i.severidade !== "feito"
            ? `<button class="btn sm" data-feito="${esc(i.id)}">Providenciei</button>` : ""}
          <button class="btn sm" data-seguir="${esc(i.numero_processo)}"
            aria-pressed="${i.acompanhado}">
            ${i.acompanhado ? "🔔 Avisando" : "🔕 Me avisa deste"}</button>
        </div>
      </div>`).join("")}
  </div>`;
  ligarAcoes(el("ag-dia"));
}

/** Ações compartilhadas pela faixa "agora" e pelo painel do dia. */
function ligarAcoes(caixa){
  caixa.querySelectorAll("[data-abrir]").forEach(b =>
    b.onclick = () => irParaPub(b.dataset.abrir));

  caixa.querySelectorAll("[data-feito]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "Salvando…";
    // A publicação pode não estar em PUBS (a agenda alcança meses fora da
    // janela de 45 dias do feed). O id basta para a API.
    const alvo = PUBS.find(p => p.id === b.dataset.feito) || { id: b.dataset.feito };
    if(await salvarTriagem(alvo, { status_triagem: "concluido" })) carregarAgenda(AG.mes);
    else { b.disabled = false; b.textContent = "Providenciei"; }
  });

  caixa.querySelectorAll("[data-seguir]").forEach(b => b.onclick = async () => {
    const ligado = b.getAttribute("aria-pressed") === "true";
    b.disabled = true;
    try{
      await (ligado ? agenda.largar(b.dataset.seguir) : agenda.seguir(b.dataset.seguir));
      carregarAgenda(AG.mes);
    }catch(erro){ alert(erro.message); b.disabled = false; }
  });
}


/* ═══════════════════════════════════════════════════════════════
   Minha conta — senha, e (para a chefia) a equipe

   A senha provisória é MOSTRADA UMA VEZ, na tela de quem criou, e não
   é enviada por canal nenhum: o painel não tem e-mail, e mandar senha
   por Telegram ou WhatsApp é justamente o que não se deve fazer. Quem
   cria dita a senha à pessoa, que troca no primeiro acesso.
   ═══════════════════════════════════════════════════════════════ */

const PAPEL_TXT = {
  chefe: "Procurador-chefe — atribui, gerencia usuários e vê segredo de justiça",
  procurador: "Procurador — vê segredo de justiça e dispara varredura",
  assessor: "Assessor / auxiliar administrativa — distribui os feitos entre os procuradores",
  estagiario: "Estagiário — lê e tria, sem acesso a segredo de justiça"
};

function telaConta(){
  const chefia = USUARIO?.papel === "chefe";
  view.innerHTML = `
  <div class="${chefia ? "split" : ""}">
    <div class="stack">
      <div class="card">
        <div class="card-h"><h3>Meus dados</h3></div>
        <div style="padding:15px 17px;font-size:13px;line-height:1.7">
          <div><b>${esc(USUARIO?.nome || "—")}</b></div>
          <div class="cell-sub">${esc(USUARIO?.email || "")}</div>
          <p style="margin:10px 0 0"><span class="pill acc">${esc(USUARIO?.papel || "")}</span></p>
          <p style="margin:9px 0 0;color:var(--muted)">${esc(PAPEL_TXT[USUARIO?.papel] || "")}</p>
          ${(USUARIO?.oabs || []).length ? `
            <p style="margin:13px 0 0">Inscrições na OAB:
              ${USUARIO.oabs.map(o => `<span class="tag mono">${esc(o)}</span>`).join(" ")}</p>
            <div class="note" style="margin-top:9px">É por estas inscrições que as
              publicações caem sozinhas na sua fila. Se faltar alguma, peça à chefia.</div>`
            : `<div class="note" style="margin-top:13px">Você não tem OAB cadastrada —
               suas publicações precisam ser distribuídas manualmente.</div>`}
        </div>
      </div>

      <div class="card">
        <div class="card-h"><h3>Trocar minha senha</h3></div>
        <div class="calc">
          <div class="fld"><label for="s-atual">Senha atual</label>
            <input type="password" id="s-atual" autocomplete="current-password"></div>
          <div class="fld"><label for="s-nova">Senha nova</label>
            <input type="password" id="s-nova" autocomplete="new-password"
                   placeholder="mínimo 10 caracteres"></div>
          <div class="fld"><label for="s-conf">Repita a senha nova</label>
            <input type="password" id="s-conf" autocomplete="new-password"></div>
          <div class="acoes"><button class="btn" id="s-salvar">Trocar senha</button></div>
          <div id="s-aviso"></div>
        </div>
      </div>
    </div>

    ${chefia ? `<div class="card">
      <div class="card-h"><h3>Equipe</h3>
        <button class="btn sm" id="u-novo">Cadastrar pessoa</button></div>
      <div id="u-lista"><div class="empty"><strong>Carregando…</strong></div></div>
    </div>` : ""}
  </div>`;

  el("s-salvar").onclick = trocarMinhaSenha;
  if(chefia){ el("u-novo").onclick = formularioNovoUsuario; listarEquipe(); }
}

async function trocarMinhaSenha(){
  const aviso = el("s-aviso");
  const atual = el("s-atual").value, nova = el("s-nova").value, conf = el("s-conf").value;
  const erro = t => aviso.innerHTML = `<div class="login-erro" role="alert">${esc(t)}</div>`;

  if(nova.length < 10) return erro("A senha nova precisa de ao menos 10 caracteres.");
  if(nova !== conf)    return erro("As duas senhas novas não conferem.");

  const b = el("s-salvar");
  b.disabled = true; b.textContent = "Trocando…";
  try{
    await minhaConta.trocar(atual, nova);
    aviso.innerHTML = `<div class="note"><b>Senha trocada.</b> Ela já vale para o
      próximo acesso — e para o Telegram, nada muda.</div>`;
    ["s-atual","s-nova","s-conf"].forEach(i => el(i).value = "");
  }catch(e){ erro(e.message); }
  finally{ b.disabled = false; b.textContent = "Trocar senha"; }
}

/* ── Chefia: a equipe ────────────────────────────────────────────── */

async function listarEquipe(){
  let pessoas;
  try{ pessoas = await minhaConta.usuarios(); }
  catch(e){
    el("u-lista").innerHTML = `<div class="empty"><strong>Não foi possível carregar</strong>
      <span>${esc(e.message)}</span></div>`;
    return;
  }
  el("u-lista").innerHTML = `<div class="agenda">${pessoas.map(u => `
    <div class="ag-row" style="grid-template-columns:1fr auto">
      <div>
        <div class="cell-num">${esc(u.nome)}
          <span class="pill ${u.ativo ? "acc" : "neutral"}">${esc(u.papel)}</span></div>
        <div class="cell-sub">${esc(u.email)}${
          u.oabs.length ? ` · OAB ${u.oabs.map(esc).join(", ")}` : " · sem OAB"}</div>
      </div>
      <button class="btn sm" data-redef="${u.id}" data-nome="${esc(u.nome)}">Redefinir senha</button>
    </div>`).join("")}</div>`;

  el("u-lista").querySelectorAll("[data-redef]").forEach(b => b.onclick = async () => {
    const nova = senhaProvisoria();
    if(!confirm(`Redefinir a senha de ${b.dataset.nome}?\n\n`
      + `A senha provisória será:\n\n    ${nova}\n\n`
      + `Anote AGORA — ela não é mostrada de novo, e não é enviada por e-mail `
      + `nem por mensagem. Dite à pessoa, que deve trocá-la no primeiro acesso.`)) return;
    b.disabled = true;
    try{
      await minhaConta.redefinir(b.dataset.redef, nova);
      alert(`Senha de ${b.dataset.nome} redefinida.\n\n    ${nova}\n\n`
        + `Esta é a última vez que ela aparece. A troca ficou registrada na auditoria.`);
    }catch(e){ alert(e.message); }
    finally{ b.disabled = false; }
  });
}

function formularioNovoUsuario(){
  const alvo = el("u-lista");
  alvo.innerHTML = `<div class="calc">
    <div class="fld"><label for="n-nome">Nome completo</label>
      <input type="text" id="n-nome" placeholder="NOME COMO APARECE NO DIÁRIO"></div>
    <div class="fld"><label for="n-email">E-mail funcional</label>
      <input type="email" id="n-email" placeholder="nome@pradopolis.sp.gov.br"></div>
    <div class="fld"><label for="n-papel">Papel</label>
      <select id="n-papel">
        <option value="procurador">Procurador</option>
        <option value="assessor">Assessor / auxiliar administrativa</option>
        <option value="estagiario">Estagiário</option>
        <option value="chefe">Procurador-chefe</option>
      </select></div>
    <div class="fld"><label for="n-oabs">Inscrições na OAB</label>
      <input type="text" id="n-oabs" placeholder="SP/274238, MG/130719">
      <div class="hint">Separe por vírgula. É por elas que as publicações são
        roteadas — sem OAB, tudo cai na fila da chefia.</div></div>
    <div class="acoes">
      <button class="btn" id="n-salvar">Cadastrar</button>
      <button class="btn sm" id="n-cancelar">Cancelar</button>
    </div>
    <div id="n-aviso"></div>
  </div>`;

  el("n-cancelar").onclick = listarEquipe;
  el("n-salvar").onclick = async () => {
    const aviso = el("n-aviso");
    const nome = el("n-nome").value.trim(), email = el("n-email").value.trim();
    if(nome.length < 2 || !email)
      return aviso.innerHTML = `<div class="login-erro">Preencha nome e e-mail.</div>`;

    const senha = senhaProvisoria();
    const b = el("n-salvar");
    b.disabled = true; b.textContent = "Cadastrando…";
    try{
      await minhaConta.criar({ nome, email, senha, papel: el("n-papel").value,
        oabs: el("n-oabs").value.split(",").map(x => x.trim()).filter(Boolean) });
      alert(`${nome} cadastrado.\n\nSenha provisória:\n\n    ${senha}\n\n`
        + `Anote AGORA — não é mostrada de novo nem enviada por canal nenhum. `
        + `Dite à pessoa, que deve trocá-la no primeiro acesso em "Minha conta".`);
      listarEquipe();
    }catch(e){
      aviso.innerHTML = `<div class="login-erro">${esc(e.message)}</div>`;
      b.disabled = false; b.textContent = "Cadastrar";
    }
  };
}


/* ═══════════════════════════════════════════════════════════════
   Avisos no Telegram (Hermes) — Task 3
   O opt-in é por código de vida curta: a pessoa se identifica no
   painel com a senha dela e depois fala com o bot do Telegram dela.
   São dois fatores independentes — ninguém cadastra ninguém.
   ═══════════════════════════════════════════════════════════════ */

function telaAvisos(){
  view.innerHTML = `
  <div class="grid2">
    <div class="card">
      <div class="card-h"><h3>Meu Telegram</h3></div>
      <div id="hermes-corpo" style="padding:15px 17px;font-size:13px;line-height:1.6">
        <div class="empty"><strong>Consultando…</strong></div>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h3>O que o Hermes faz — e o que não faz</h3></div>
      <div style="padding:15px 17px;display:flex;flex-direction:column;gap:13px;font-size:13px;line-height:1.6">
        <div>
          <span class="pill acc">Resumo diário</span>
          <p style="margin:7px 0 0">Às <b>08:00</b>, em dias úteis do calendário forense, no grupo da
          Procuradoria: os prazos vencendo em até 3 dias úteis, quantas publicações estão sem triagem
          e o tamanho do acervo. Não sai em fim de semana, feriado nem recesso.</p>
        </div>
        <div>
          <span class="pill acc">Alerta crítico</span>
          <p style="margin:7px 0 0">No seu privado, quando um prazo seu cai para <b>3 dias úteis ou
          menos</b> — ou quando a publicação menciona liminar, tutela de urgência, penhora ou bloqueio,
          que não esperam o prazo encurtar. <b>Um alerta por publicação</b>, nunca dois.</p>
        </div>
        <div>
          <span class="pill">Silêncio 20h–07h</span>
          <p style="margin:7px 0 0">O que acontece de madrugada entra no resumo da manhã.</p>
        </div>
        <div class="note">
          <b>Nenhum nome de pessoa natural sai numa mensagem</b>, nem no grupo nem no privado, e o
          inteiro teor nunca vai pelo Telegram — a mensagem leva o número do processo e um link, e o
          texto se lê aqui, onde há login e auditoria. Se a mensagem vazar num print, ela não expõe
          mais do que já está no número do processo.
        </div>
        <div class="note">
          O Hermes <b>não confirma ciência de intimação</b>. Efeito jurídico irreversível não fica a um
          toque de distância num aplicativo de mensagem.
        </div>
      </div>
    </div>
  </div>`;
  pintarHermes();
}

async function pintarHermes(){
  const box = el("hermes-corpo");
  let s;
  try { s = await hermes.ver(); }
  catch(erro){
    box.innerHTML = `<div class="empty"><strong>Não foi possível consultar</strong>
      <span>${esc(erro.message)}</span></div>`;
    return;
  }

  if(!s.hermes_disponivel){
    box.innerHTML = `<div class="empty"><strong>Hermes não está configurado</strong>
      <span>O servidor está sem <code>TELEGRAM_BOT_TOKEN</code>. Fale com quem administra o painel.</span></div>`;
    return;
  }

  if(s.situacao === "vinculado"){
    box.innerHTML = `
      <p><span class="pill ok">Vinculado</span></p>
      <p style="margin:11px 0 0">Conta do Telegram: <b>${esc(s.nome_telegram || "—")}</b><br>
      Autorizado em ${s.desde ? esc(String(s.desde).slice(0,10).split("-").reverse().join("/")) : "—"}.</p>
      <p style="margin:13px 0 0">Você recebe no privado os alertas das publicações sob sua
      responsabilidade.</p>
      <div class="acoes" style="margin-top:15px">
        <button class="btn sm" id="h-sair">Parar de receber avisos</button>
      </div>`;
    el("h-sair").onclick = async () => {
      if(!confirm("Desvincular seu Telegram? Você deixa de receber os alertas de prazo.")) return;
      try { await hermes.desvincular(); pintarHermes(); }
      catch(erro){ alert(erro.message); }
    };
    return;
  }

  const temCodigo = s.situacao === "aguardando_codigo" && s.codigo;
  box.innerHTML = `
    <p><span class="pill">${temCodigo ? "Aguardando confirmação" : "Sem vínculo"}</span></p>
    <p style="margin:11px 0 0">Para receber os avisos, três passos:</p>
    <ol style="margin:9px 0 0;padding-left:19px;display:flex;flex-direction:column;gap:6px">
      <li>Abra o Telegram e procure o bot do Departamento Jurídico.</li>
      <li>Peça seu código aqui — ele vale <b>15 minutos</b> e serve uma vez só.</li>
      <li>Envie ao bot: <code class="mono">/vincular SEUCODIGO</code></li>
    </ol>
    ${temCodigo ? `
      <div class="calc-out" style="margin-top:15px;text-align:center">
        <div class="bar-lbl">Seu código</div>
        <div class="big mono" style="letter-spacing:.14em">${esc(s.codigo)}</div>
        <div class="hint">Envie <code class="mono">/vincular ${esc(s.codigo)}</code> ao bot</div>
      </div>` : ""}
    <div class="acoes" style="margin-top:15px">
      <button class="btn sm" id="h-codigo">${temCodigo ? "Gerar outro código" : "Gerar meu código"}</button>
      <button class="btn sm" id="h-recarregar">Já enviei — conferir</button>
    </div>`;

  el("h-codigo").onclick = async (ev) => {
    ev.target.disabled = true;
    try { await hermes.pedirCodigo(); }
    catch(erro){ alert(erro.message); }
    pintarHermes();
  };
  el("h-recarregar").onclick = () => pintarHermes();
}


/* ═══════════════════════════════════════════════════════════════
   Tour guiado — Ciclo 2
   Escrito à mão de propósito: o painel é um arquivo único que abre
   offline com duplo clique, e não pode depender de CDN.
   ═══════════════════════════════════════════════════════════════ */
const TOUR = [
  { tela:"painel", alvo:".kpis",
    t:"Comece o dia aqui",
    c:"Estes dois primeiros números respondem se o dia está sob controle: <b>prazos vencendo em 3 dias</b> e <b>publicações que ninguém leu ainda</b>." },
  { tela:"publicacoes", alvo:".feed-list",
    t:"Sua fila de triagem",
    c:"A bolinha verde marca o que ainda não foi lido. A etiqueta colorida à direita é o prazo — <b>vermelha até 3 dias</b>." },
  { tela:"publicacoes", alvo:".prazo-box", precisaSelecao:true,
    t:"A memória de cálculo",
    c:"Quatro marcos, do diário até o vencimento, com o artigo que justifica cada salto. O <b>?</b> ao lado de cada um explica a regra." },
  { tela:"publicacoes", alvo:".teor", precisaSelecao:true,
    t:"O texto integral",
    c:"O inteiro teor da publicação, de onde sai o ato e o prazo. <b>Sempre</b> confira no link do tribunal antes de peticionar." },
  { tela:"publicacoes", alvo:".triage", precisaSelecao:true,
    t:"Triagem",
    c:"Classifique e atribua um responsável. É isso que faz o resto da equipe saber o que já foi tratado." },
  { tela:"prazos", alvo:".agenda",
    t:"Agenda e acervo",
    c:"A agenda de vencimentos e, na <b>Carteira</b>, o acervo completo — é daqui que sai o relatório semanal." }
];

const TOUR_VISTO = "pradopolis.tour.v1";
let tourPasso = -1, tourNos = null;

const leu = k => { try { return localStorage.getItem(k); } catch(e){ return null; } };
const grava = (k,v) => { try { localStorage.setItem(k,v); } catch(e){} };

function tourFechar(){
  tourNos?.mask?.remove(); tourNos?.hole?.remove(); tourNos?.balao?.remove();
  tourNos = null; tourPasso = -1;
  document.removeEventListener("keydown", tourTeclado);
  document.body.style.removeProperty("overflow");
}

function tourTeclado(e){
  if(e.key === "Escape"){ e.preventDefault(); tourFechar(); }
  else if(e.key === "ArrowRight"){ e.preventDefault(); tourIr(tourPasso+1); }
  else if(e.key === "ArrowLeft"){ e.preventDefault(); tourIr(tourPasso-1); }
}

async function tourIr(i){
  if(i < 0) return;
  if(i >= TOUR.length){ grava(TOUR_VISTO,"1"); tourFechar(); return; }
  const passo = TOUR[i];
  tourPasso = i;

  // Leva à tela do passo e, quando o passo mostra o painel de leitura,
  // garante que há uma publicação selecionada.
  if(location.hash.slice(1) !== passo.tela){ location.hash = "#"+passo.tela; await espera(360); }
  if(passo.precisaSelecao && !sel){
    const primeira = PUBS.find(p => p.prazo);
    if(primeira){ sel = String(primeira.id); telaPublicacoes(); await espera(320); }
  }

  const alvo = document.querySelector(passo.alvo);
  if(!alvo){ return tourIr(i+1); }          // alvo ausente: não trava o tour
  alvo.scrollIntoView({ block:"center", behavior: reduzido() ? "auto" : "smooth" });
  await espera(reduzido() ? 40 : 320);
  tourDesenhar(alvo, passo, i);
}

const espera = ms => new Promise(r => setTimeout(r, ms));
const reduzido = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function tourDesenhar(alvo, passo, i){
  if(!tourNos){
    const mask = document.createElement("div"); mask.className = "tour-mask";
    mask.addEventListener("click", tourFechar);
    const hole = document.createElement("div"); hole.className = "tour-hole";
    const balao = document.createElement("div"); balao.className = "tour-balao";
    balao.setAttribute("role","dialog"); balao.setAttribute("aria-modal","true");
    balao.setAttribute("aria-live","polite");
    document.body.append(mask, hole, balao);
    tourNos = { mask, hole, balao };
    document.addEventListener("keydown", tourTeclado);
  }
  const { hole, balao } = tourNos;
  const b = alvo.getBoundingClientRect(), pad = 6;
  Object.assign(hole.style, {
    top:`${b.top-pad}px`, left:`${b.left-pad}px`,
    width:`${b.width+pad*2}px`, height:`${b.height+pad*2}px`
  });

  balao.innerHTML = `
    <h3>${esc(passo.t)}</h3>
    <p>${passo.c}</p>
    <div class="tour-rodape">
      <span class="tour-passos">${i+1} de ${TOUR.length}</span>
      <button class="btn sm" data-tour="sair">Sair</button>
      ${i>0?`<button class="btn sm" data-tour="voltar">Voltar</button>`:""}
      <button class="btn sm pri" data-tour="proximo">${i===TOUR.length-1?"Concluir":"Próximo"}</button>
    </div>`;

  // Posiciona o balão do lado com mais espaço, sem sair da tela.
  const lg = 360, margem = 14;
  let topo = b.bottom + 14;
  if(topo + 190 > innerHeight) topo = Math.max(margem, b.top - 190);
  let esq = Math.min(Math.max(margem, b.left), innerWidth - lg - margem);
  Object.assign(balao.style, { top:`${topo}px`, left:`${esq}px` });

  balao.querySelector('[data-tour="proximo"]').onclick = () => tourIr(i+1);
  balao.querySelector('[data-tour="sair"]').onclick = tourFechar;
  balao.querySelector('[data-tour="voltar"]')?.addEventListener("click", () => tourIr(i-1));
  balao.querySelector('[data-tour="proximo"]').focus();
}

function tourConvite(){
  const cx = document.createElement("div");
  cx.className = "tour-inicio";
  cx.innerHTML = `<div class="cx" role="dialog" aria-modal="true" aria-label="Tour do painel">
    <h3>Primeira vez por aqui?</h3>
    <p>Um tour de 1 minuto mostra como o painel é usado no dia a dia do departamento.</p>
    <div class="acoes">
      <button class="btn" data-c="nao">Agora não</button>
      <button class="btn pri" data-c="sim">Fazer o tour</button>
    </div></div>`;
  document.body.appendChild(cx);
  const fim = () => { grava(TOUR_VISTO,"1"); cx.remove(); };
  cx.querySelector('[data-c="nao"]').onclick = fim;
  cx.querySelector('[data-c="sim"]').onclick = () => { cx.remove(); tourIr(0); };
  cx.querySelector('[data-c="sim"]').focus();
}

/* ═══════════════════════════════════════════════════════════════
   Roteamento
   ═══════════════════════════════════════════════════════════════ */
const TELAS = {
  painel:      [telaPainel,      "Painel",       "Situação do acervo nos últimos 45 dias"],
  publicacoes: [telaPublicacoes, "Publicações",  "Feed do DJEN com inteiro teor e contagem de prazo"],
  agenda:      [telaAgenda,      "Minha agenda", "Calendário dos prazos sob sua responsabilidade"],
  prazos:      [telaPrazos,      "Prazos",       "Agenda de vencimentos e calculadora processual"],
  carteira:    [telaCarteira,    "Carteira",     "Processos do Município descobertos por nome da parte"],
  processo:    [telaProcesso,    "Processo",     "Histórico de publicações de um feito"],
  avisos:      [telaAvisos,      "Avisos no Telegram", "Hermes: resumo diário no grupo e alerta crítico no privado"],
  conta:       [telaConta,       "Minha conta",  "Sua senha, suas inscrições na OAB e a equipe"],
  fontes:      [telaFontes,      "Fontes e limites", "O que cada fonte entrega e o que ela não entrega"]
};
function rota(){
  const k = (location.hash.slice(1) || "painel");
  const [fn, t, s] = TELAS[k] || TELAS.painel;
  el("vtitle").textContent = t; el("vsub").textContent = s;
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("on", a.dataset.v === k));
  fn();
  view.scrollTop = 0;
}

/** Contadores do rail. Chamado após o shell existir e o acervo carregar. */
function atualizarContadores(){
  el("t-car").textContent = PROCESSOS.length || "";
  el("t-pub").textContent = ESTATISTICAS.sem_triagem || "";
  el("t-prz").textContent =
    PUBS.filter(p => p.prazo.restantes >= 0 && p.prazo.restantes <= 7).length || "";
  // O contador de "Minha agenda" é o único que fala do USUÁRIO, não do acervo:
  // fica visível de qualquer tela, e é o lembrete para quem não abriria a
  // agenda por conta própria. Conta vencido também — some só quando resolver.
  const meus = PUBS.filter(p => p.responsavel_id === USUARIO?.id
    && p.status_triagem !== "concluido" && p.status_triagem !== "sem_providencia"
    && p.prazo.restantes <= 3).length;
  el("t-agd").textContent = meus || "";
  el("t-agd").className = meus ? "tally crit" : "tally";
}
