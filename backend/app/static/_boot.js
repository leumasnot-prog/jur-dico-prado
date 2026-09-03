/* ═══════════════════════════════════════════════════════════════
   Arranque
   ═══════════════════════════════════════════════════════════════ */
async function iniciar(){
  if(!sessao?.access_token){ telaLogin(); return; }
  document.body.innerHTML = SHELL;

  try {
    USUARIO = sessao.usuario ?? await api("/auth/eu");
    await carregarAcervo();
  } catch (erro) {
    if(String(erro.message).includes("Sessão")) return;   // sair() já recarregou
    document.getElementById("view").innerHTML =
      `<div class="empty"><strong>Não foi possível carregar o acervo</strong>
       ${esc(erro.message)}
       <button class="btn sm" onclick="location.reload()">Tentar de novo</button></div>`;
    return;
  }

  el("quem").innerHTML =
    `${esc(USUARIO.nome)} <span class="papel">${esc(USUARIO.papel)}</span>`;
  el("sair").onclick = sair;
  el("tour").onclick = () => tourIr(0);
  if(!leu(TOUR_VISTO)) setTimeout(tourConvite, 700);

  // Varredura manual é de chefe e procurador; para os demais o botão nem aparece.
  const bv = el("varrer");
  if(!["chefe","procurador"].includes(USUARIO.papel)) bv.remove();
  else bv.onclick = async () => {
    bv.disabled = true; bv.textContent = "Varrendo…";
    try {
      const r = await dispararVarredura();
      await carregarAcervo();
      atualizarContadores();
      rota();
      alert(`Varredura concluída.\n\n${r.processos} processos`
        + `\n${r.publicacoes_novas} publicações novas`
        + `\n${r.descartadas_por_homonimia} descartadas por homonímia`
        + `\n${r.atribuidas_por_oab} atribuídas por OAB`);
    } catch (erro) {
      alert(`Falha na varredura: ${erro.message}`);
    } finally {
      bv.disabled = false; bv.textContent = "Varrer o diário";
    }
  };

  el("theme").onclick = () => {
    const atual = document.documentElement.getAttribute("data-theme");
    const escuro = atual ? atual === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", escuro ? "light" : "dark");
  };

  el("sweep-t").textContent = "atualizado " + new Date().toLocaleString("pt-BR",
    { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" });

  atualizarContadores();
  addEventListener("hashchange", rota);
  rota();
}

iniciar();
