const iso = d => d.toISOString().slice(0,10);
const parseD = s => { const [y,m,d] = s.slice(0,10).split("-").map(Number); return new Date(Date.UTC(y,m-1,d)); };
const addD = (d,n) => new Date(d.getTime()+n*864e5);





/* Tabela de prazos e ritos — espelha _PRAZOS_CPC / _PRAZOS_PROPRIOS */
const PRAZOS = {
  "Contestação":15,"Apelação":15,"Embargos de Declaração":5,"Agravo de Instrumento":15,
  "Contrarrazões":15,"Manifestação":15,"Recurso Especial":15,"Recurso Extraordinário":15,
  "Recurso Ordinário":8,"Embargos à Execução Fiscal":30,"Recurso Inominado":10,
  "Impugnação ao Cumprimento de Sentença":30
};
const PRAZO_PROPRIO = new Set(["Embargos à Execução Fiscal","Recurso Inominado",
  "Impugnação ao Cumprimento de Sentença"]);
// Atos de defesa na Justiça do Trabalho: quádruplo pelo DL 779/69, art. 1º, II.
const DEFESA_TRABALHISTA = new Set(["Contestação","Manifestação"]);

/**
 * Calcula o prazo processual.
 * @param dispIso data de DISPONIBILIZAÇÃO no DJEN
 * @param ato     rótulo do ato (chave de PRAZOS)
 * @param fazenda parte é Fazenda Pública (art. 183)
 * @param rito    "comum" | "jefp" | "trabalhista"
 */
function calcPrazo(dispIso, ato, fazenda, rito){
  const simples = PRAZOS[ato] ?? 15;
  let mult = 1, fundamento, regra = "simples";
  if(!fazenda){ regra = "nao_fazenda"; fundamento = "Prazo simples — parte não é Fazenda Pública."; }
  else if(rito === "trabalhista"){
    // O prazo diferenciado do ente público na Justiça do Trabalho NÃO vem do
    // art. 183 do CPC, e sim do Decreto-Lei 779/69.
    if(DEFESA_TRABALHISTA.has(ato)){
      mult = 4; regra = "quadruplo";
      fundamento = `Prazo em QUÁDRUPLO (art. 1º, II, do Decreto-Lei 779/69): na Justiça do Trabalho o ente público tem prazo quadruplicado para contestar. O art. 183 do CPC não se aplica a este rito. ${simples} dias úteis multiplicados para ${simples*4}.`;
    } else {
      mult = 2; regra = "dobro_clt";
      fundamento = `Prazo em DOBRO (art. 1º, III, do Decreto-Lei 779/69): na Justiça do Trabalho o ente público tem prazo em dobro para recorrer. O art. 183 do CPC não se aplica a este rito. ${simples} dias úteis dobrados para ${simples*2}.`;
    }
  }
  else if(rito === "jefp"){ regra = "jefp"; fundamento = "Prazo SIMPLES: no Juizado Especial da Fazenda Pública não há prazo diferenciado (art. 7º da Lei 12.153/2009), o que afasta o dobro do art. 183 do CPC."; }
  else if(PRAZO_PROPRIO.has(ato)){ regra = "proprio"; fundamento = `Prazo SIMPLES: “${ato}” tem prazo próprio fixado em lei — o dobro não incide (art. 183, §2º, do CPC).`; }
  else { mult = 2; regra = "dobro_cpc"; fundamento = `Prazo EM DOBRO (art. 183, caput, do CPC): o Município goza de prazo em dobro para todas as suas manifestações. ${simples} dias úteis dobrados para ${simples*2}.`; }
  const dias = simples * mult;
  const dobro = mult > 1;

  const disp = parseD(dispIso);
  const publicacao = proxUtil(disp);              // art. 224, §2º
  const termo = proxUtil(publicacao);             // art. 224, caput
  let n = 0, cur = termo, fim = termo;
  const obstaculos = [];
  while(n < dias){
    if(diaUtil(cur)){ n++; fim = cur; }
    cur = addD(cur,1);
  }
  let scan = addD(publicacao,1);
  while(scan <= fim){
    if(scan.getUTCDay()!==0 && scan.getUTCDay()!==6){
      if(emRecesso(scan)) obstaculos.push([iso(scan),"Recesso forense (art. 220 do CPC)"]);
      else { const n2 = nomeFeriado(scan); if(n2) obstaculos.push([iso(scan),n2]); }
    }
    scan = addD(scan,1);
  }
  const hoje = parseD(iso(new Date()));
  const restantes = Math.round((fim - hoje)/864e5);
  return { simples, dias, dobro, mult, regra, fundamento, ato, rito,
    disponibilizacao: iso(disp), publicacao: iso(publicacao),
    termo: iso(termo), fim: iso(fim), obstaculos, restantes,
    recesso: obstaculos.filter(o=>o[1].startsWith("Recesso")).length };
}

// Movidos das telas: o login (em _app.js) usa esc() antes delas.
const el = id => document.getElementById(id);

// Nome do ente, para destacar o Município na lista de partes. O backend também
// marca `e_o_ente` em cada parte; aqui é só apresentação.
const ENTE = /MUNICIPIO DE PRADOPOLIS|PREFEITURA MUNICIPAL DE PRAD/i;

// Recuperados do painel da Task 1.
const esc = s => String(s??"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const sev = r => r < 0 ? "crit" : r <= 3 ? "crit" : r <= 7 ? "warn" : "ok";
const sevTxt = r => r < 0 ? `vencido há ${-r}d` : r === 0 ? "vence hoje" : `${r} dias`;
const semAcento = s => (s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"");
const POLO = {A:"ativo", P:"passivo"};
const ehEnte = n => ENTE.test(semAcento(n||"").toUpperCase());
const fmtD = s => s ? s.slice(0,10).split("-").reverse().join("/") : "—";
// Title-case para os rótulos vindos das APIs, que chegam em caixa alta.
// Detectar sigla pelo formato falha ("RECURSO" e "RITO" são caixa alta e não são
// siglas), então a lista é explícita: siglas de tribunal, unidades judiciárias e
// tudo que contenha dígito ou ordinal (1ª Vara, EXE4, CON2).
const SIGLAS = new Set(["TJSP","TRT15","TST","STJ","STF","TRF3","TRT","TRF","CNJ","OAB","MP","MPT",
  "CEJUSC","SEF","JEF","UPJ","SDI","SPF","DAM","RAJ","DEECRIM","PJE","CLT","CPC","LEF","INSS",
  "CON1","CON2","LIQ1","LIQ2","EXE1","EXE2","EXE3","EXE4","ROT","AIRR","II","III","IV"]);
const LIGA = new Set(["de","da","do","das","dos","e","em","a","o","no","na","ao","à","com","para"]);
const temDigito = t => /[0-9]/.test(t);
const titulo = s => (s||"").split(/(\s+)/).map((tk,i) => {
  if(/^\s+$/.test(tk)) return tk;
  const nu = tk.replace(/[^0-9A-Za-zÀ-ÿ]/g,"").toUpperCase();
  if(SIGLAS.has(nu) || temDigito(tk)) return tk.toUpperCase() === tk ? tk : tk;
  const low = tk.toLocaleLowerCase("pt-BR");
  if(i > 0 && LIGA.has(low)) return low;
  return low.replace(/(^|[\-–/(])([a-zà-ÿ])/g,(m,a,b)=>a+b.toLocaleUpperCase("pt-BR"));
}).join("");
