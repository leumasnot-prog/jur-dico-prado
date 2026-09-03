/* ═══════════════════════════════════════════════════════════════════
   Painel Jurídico de Pradópolis — camada de dados
   Substitui os dados embutidos por chamadas à API. Sem dependências.
   ═══════════════════════════════════════════════════════════════════ */

const API = "";                       // mesma origem: o backend serve este arquivo
const CHAVE_TOKEN = "pradopolis.sessao.v1";

const guarda = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* modo privado */ } };
const le = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const apaga = (k) => { try { localStorage.removeItem(k); } catch (e) { /* idem */ } };

let sessao = null;
try { sessao = JSON.parse(le(CHAVE_TOKEN) || "null"); } catch (e) { sessao = null; }

/** Chamada autenticada. Renova o token uma vez em 401 antes de desistir. */
async function api(caminho, opcoes = {}, jaRenovou = false) {
  const cabecalhos = { ...(opcoes.headers || {}) };
  if (sessao?.access_token) cabecalhos.Authorization = `Bearer ${sessao.access_token}`;
  if (opcoes.body && !cabecalhos["Content-Type"]) cabecalhos["Content-Type"] = "application/json";

  const r = await fetch(API + caminho, { ...opcoes, headers: cabecalhos });

  if (r.status === 401 && sessao?.refresh_token && !jaRenovou) {
    const renovou = await renovar();
    if (renovou) return api(caminho, opcoes, true);
    sair();
    throw new Error("Sessão expirada. Entre novamente.");
  }
  if (!r.ok) {
    let detalhe = `Erro ${r.status}`;
    try { detalhe = (await r.json()).detail ?? detalhe; } catch (e) { /* resposta sem json */ }
    throw new Error(detalhe);
  }
  return r.status === 204 ? null : r.json();
}

async function renovar() {
  try {
    const r = await fetch(API + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: sessao.refresh_token }),
    });
    if (!r.ok) return false;
    const novo = await r.json();
    sessao = { ...sessao, ...novo };
    guarda(CHAVE_TOKEN, JSON.stringify(sessao));
    return true;
  } catch (e) { return false; }
}

async function entrar(email, senha) {
  const corpo = new URLSearchParams({ username: email, password: senha });
  const r = await fetch(API + "/auth/login", { method: "POST", body: corpo });
  if (!r.ok) throw new Error("E-mail ou senha incorretos.");
  sessao = await r.json();
  guarda(CHAVE_TOKEN, JSON.stringify(sessao));
  sessao.usuario = await api("/auth/eu");
  guarda(CHAVE_TOKEN, JSON.stringify(sessao));
  return sessao.usuario;
}

function sair() {
  sessao = null;
  apaga(CHAVE_TOKEN);
  location.reload();
}

/* ── Tela de login ──────────────────────────────────────────────── */

function telaLogin(mensagem = "") {
  document.body.innerHTML = `
  <div class="login-tela">
    <div class="login-cx">
      <div class="login-marca">
        <div class="crest">PR</div>
        <div>
          <h1>Departamento Jurídico</h1>
          <div class="sub">Pradópolis · SP</div>
        </div>
      </div>
      ${mensagem ? `<div class="login-erro" role="alert">${esc(mensagem)}</div>` : ""}
      <form id="f-login" autocomplete="on">
        <div>
          <label for="email">E-mail funcional</label>
          <input type="email" id="email" name="email" required autocomplete="username"
                 placeholder="nome@pradopolis.sp.gov.br">
        </div>
        <div>
          <label for="senha">Senha</label>
          <input type="password" id="senha" name="senha" required
                 autocomplete="current-password">
        </div>
        <button type="submit" id="b-entrar">Entrar</button>
      </form>
      <p class="login-rodape">
        Acesso restrito aos procuradores e servidores do Departamento Jurídico.
        Toda ação neste sistema é registrada em trilha de auditoria.
      </p>
    </div>
  </div>`;

  document.getElementById("f-login").onsubmit = async (e) => {
    e.preventDefault();
    const b = document.getElementById("b-entrar");
    b.disabled = true; b.textContent = "Entrando…";
    try {
      await entrar(document.getElementById("email").value.trim(),
                   document.getElementById("senha").value);
      location.reload();
    } catch (erro) {
      telaLogin(erro.message);
    }
  };
  document.getElementById("email").focus();
}

/* ── Carga dos dados do acervo ──────────────────────────────────── */

let PUBS = [], PROCESSOS = [], ESTATISTICAS = {}, USUARIO = null;

/** Converte a resposta da API no formato que as telas já consomem. */
function adaptar(p) {
  const venc = p.vencimento ? parseD(p.vencimento) : null;
  const hoje = parseD(iso(new Date()));
  const restantes = venc ? Math.round((venc - hoje) / 864e5) : 999;
  return {
    id: String(p.id),
    numero: p.numero_formatado || p.numero_processo,
    data: p.data_disponibilizacao,
    tribunal: p.tribunal,
    orgao: p.orgao,
    classe: p.classe,
    documento: p.tipo_documento,
    tipo: p.tipo_documento,
    meio: p.meio,
    link: p.link_validacao,
    texto: p.texto,
    partes: (p.partes || []).map((x) => ({
      nome: x.nome,
      polo: x.polo === "ativo" ? "A" : x.polo === "passivo" ? "P" : "",
    })),
    advogados: p.advogados || [],
    declarado: p.prazo_no_texto ? { dias: p.prazo_no_texto } : null,
    poloEnte: (p.partes || []).find((x) => x.e_o_ente)?.polo ?? "não informado",
    contra: (p.partes || []).filter((x) => !x.e_o_ente).map((x) => x.nome),
    status_triagem: p.status_triagem,
    responsavel_id: p.responsavel_id,
    anotacao: p.anotacao,
    // O prazo vem inteiro do backend, que delega ao MCP — a interface não
    // recalcula nada. Uma única fonte de verdade para a regra.
    prazo: {
      ...(p.prazo || {}),
      ato: p.prazo?.ato ?? p.ato,
      rito: p.prazo?.rito ?? p.rito,
      fim: p.prazo?.fim ?? p.vencimento,
      restantes,
      dobro: (p.prazo?.mult ?? 1) > 1,
      regra: p.prazo?.regra ?? "nao_fazenda",
      obstaculos: p.prazo?.obstaculos ?? [],
      fundamento: p.prazo?.fundamento ?? "",
    },
  };
}

async function carregarAcervo() {
  const [pubs, procs, stats] = await Promise.all([
    api("/acervo/publicacoes?dias=45&limite=500"),
    api("/acervo/processos"),
    api("/acervo/estatisticas"),
  ]);
  PUBS = pubs.map(adaptar);
  PROCESSOS = procs.map((p) => ({
    numero: p.numero_formatado || p.numero_processo,
    numero_processo: p.numero_processo,
    tribunal: p.tribunal, orgao: p.orgao, classe: p.classe,
    polo: p.polo_do_ente, ultima: p.ultima_publicacao,
    proximo: p.proximo_vencimento
      ? { fim: p.proximo_vencimento,
          restantes: Math.round((parseD(p.proximo_vencimento) - parseD(iso(new Date()))) / 864e5) }
      : null,
    pubs: PUBS.filter((x) => x.numero === (p.numero_formatado || p.numero_processo)),
    contra: p.partes_contrarias || [], advogados: p.advogados || [],
    total_publicacoes: p.total_publicacoes,
  }));
  ESTATISTICAS = stats;
}

/** Triagem: otimista na tela, revertida se a API recusar. */
async function salvarTriagem(pub, campos) {
  const antes = { status_triagem: pub.status_triagem, anotacao: pub.anotacao };
  Object.assign(pub, campos);
  try {
    await api(`/acervo/publicacoes/${pub.id}/triagem`, {
      method: "PATCH",
      body: JSON.stringify({
        status: pub.status_triagem,
        anotacao: pub.anotacao ?? null,
      }),
    });
    return true;
  } catch (erro) {
    Object.assign(pub, antes);
    alert(`Não foi possível salvar: ${erro.message}`);
    return false;
  }
}

async function dispararVarredura() {
  return api("/acervo/varredura?dias=30", { method: "POST" });
}


/* ── Hermes: opt-in de avisos no Telegram ────────────────────────── */

const hermes = {
  ver:         () => api("/hermes/vinculo"),
  pedirCodigo: () => api("/hermes/vinculo/codigo", { method: "POST" }),
  desvincular: () => api("/hermes/vinculo", { method: "DELETE" }),
};


/* ── Agenda pessoal e acompanhamento ─────────────────────────────── */

const agenda = {
  mes:        (m) => api(`/acervo/agenda${m ? `?mes=${m}` : ""}`),
  pendencias: ()  => api("/acervo/pendencias?limite_dias_uteis=3"),
  equipe:     ()  => api("/acervo/equipe"),
  seguir:     (numero, dias = 3) =>
    api(`/acervo/processos/${encodeURIComponent(numero)}/acompanhar`,
        { method: "PUT", body: JSON.stringify({ dias_antecedencia: dias }) }),
  largar:     (numero) =>
    api(`/acervo/processos/${encodeURIComponent(numero)}/acompanhar`, { method: "DELETE" }),
};


/* ── Conta e equipe ──────────────────────────────────────────────── */

const minhaConta = {
  eu:       ()   => api("/auth/eu"),
  trocar:   (atual, nova) => api("/auth/senha",
              { method: "POST",
                body: JSON.stringify({ senha_atual: atual, senha_nova: nova }) }),
  usuarios: ()   => api("/auth/usuarios"),
  criar:    (u)  => api("/auth/usuarios", { method: "POST", body: JSON.stringify(u) }),
  redefinir:(id, nova) => api(`/auth/usuarios/${id}/senha`,
              { method: "POST", body: JSON.stringify({ senha_nova: nova }) }),
};

/** Senha provisória legível: fácil de ditar por telefone, difícil de adivinhar. */
function senhaProvisoria(){
  const abc = "abcdefghijkmnopqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bloco = () => Array.from(crypto.getRandomValues(new Uint8Array(5)))
    .map(n => abc[n % abc.length]).join("");
  return `${bloco()}-${bloco()}-${bloco()}`;
}
