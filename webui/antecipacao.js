/* Aba 11 — Antecipação e DIFAL do ICMS-BA (spec 027).

   Mesma disciplina das outras abas: o que esta tela esconde é conveniência,
   nunca autorização — quem manda é o 403 do servidor. Descrição de produto e
   nome de fornecedor vêm de XML de terceiros: tudo que entra por innerHTML
   passa por esc().

   A tela não calcula nada. Os números vêm prontos do servidor (memória de
   cálculo gravada por item); aqui só se formata. */

"use strict";

Abas.registrar("antecipacao", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Antecipação e DIFAL — ICMS Bahia</h2>
      <p class="dica">Lê os XML das compras de fora do estado, separa os
         produtos por <b>CFOP e alíquota</b> e calcula o ICMS a recolher para a
         Bahia, com a memória de cálculo de cada item. Toda nota nasce
         <b>em revisão</b>: item com exceção (ST, isenção, redução de base, FCP,
         dado faltante) só entra na soma depois que alguém decide.</p>
      <p class="dica aviso" id="ant-aviso"></p>
      <p id="ant-status" class="status" role="status"></p>
    </div>

    <div class="caixa">
      <nav class="conc-subtelas" id="ant-subtelas">
        <button data-sub="notas" class="ativa" type="button">Notas</button>
        <button data-sub="importar" type="button">Importar</button>
        <button data-sub="totais" type="button">Totais por empresa</button>
        <button data-sub="calculadora" type="button">Calculadora</button>
        <button data-sub="tabela" type="button">Alíquotas e parâmetros</button>
      </nav>

      <section id="ant-sub-notas" class="conc-sub">
        <div class="linha-form">
          <label>Buscar
            <input id="ant-f-texto" type="search" placeholder="Número, chave, fornecedor ou empresa">
          </label>
          <label>Empresa
            <select id="ant-f-empresa"><option value="">Todas</option></select>
          </label>
          <label>Competência
            <input id="ant-f-competencia" type="text" placeholder="mm/aaaa" maxlength="7" size="8">
          </label>
          <label>Situação
            <select id="ant-f-estado"><option value="">Todas</option></select>
          </label>
          <button id="ant-f-limpar" type="button">Limpar</button>
        </div>
        <div class="rolagem"><table id="ant-lista">
          <thead><tr>
            <th>Emissão</th><th>Nota</th><th>Fornecedor</th><th>UF</th>
            <th>Empresa</th><th>Competência</th><th>Itens</th>
            <th class="conc-num">A recolher</th><th>Situação</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
        <div class="conc-paginacao">
          <button id="ant-anterior" type="button">&#8249; Anterior</button>
          <span id="ant-pagina"></span>
          <button id="ant-proxima" type="button">Próxima &#8250;</button>
        </div>
        <div id="ant-detalhe" class="oculto"></div>
      </section>

      <section id="ant-sub-importar" class="conc-sub oculto">
        <div id="ant-importar-area" class="oculto">
          <p class="dica">Selecione um ou vários XML de NF-e (até
             <span id="ant-lim-arquivos"></span> por envio). O
             <b>método</b> é escolha sua e fica gravado em cada nota; a memória
             mostra quanto daria pelo outro método.</p>
          <div class="linha-form">
            <label>Método de cálculo
              <select id="ant-i-metodo"></select>
            </label>
            <label>Finalidade da compra
              <select id="ant-i-finalidade"><option value="">Definir na revisão</option></select>
            </label>
            <label class="pat-checkbox" title="Sem ICMS destacado, calcula o crédito pela alíquota interestadual da tabela">
              <span>Autorizar crédito de referência quando não houver destaque</span>
              <input id="ant-i-presuncao" type="checkbox">
            </label>
          </div>
          <div class="linha-form">
            <label>Arquivos XML
              <input id="ant-i-arquivos" type="file" accept=".xml,text/xml,application/xml" multiple>
            </label>
            <button id="ant-importar" class="botao-primario" type="button">Importar XML</button>
            <span id="ant-i-status" class="status"></span>
          </div>
          <div class="rolagem oculto" id="ant-i-resultado-caixa"><table id="ant-i-resultado">
            <thead><tr><th>Arquivo</th><th>Resultado</th><th>Itens</th>
              <th class="conc-num">A recolher</th><th>Observação</th></tr></thead>
            <tbody></tbody>
          </table></div>
          <hr class="conc-divisor">
        </div>
        <h3 class="pat-titulo">Conferir chaves de acesso</h3>
        <p class="dica">Cole várias chaves (linha, espaço ou vírgula). O sistema
           valida os 44 dígitos e diz quais já foram importadas e de quais
           falta o XML. A chave não traz os produtos: buscar a nota na SEFAZ
           pela chave exige o certificado da empresa e não faz parte desta
           versão.</p>
        <div class="linha-form">
          <label>Chaves
            <textarea id="ant-chaves" rows="4" cols="60" spellcheck="false"></textarea>
          </label>
          <button id="ant-conferir" type="button">Conferir chaves</button>
        </div>
        <div class="rolagem oculto" id="ant-chaves-caixa"><table id="ant-chaves-resultado">
          <thead><tr><th>Chave</th><th>UF</th><th>Mês</th><th>Nota</th>
            <th>Situação</th></tr></thead>
          <tbody></tbody>
        </table></div>
      </section>

      <section id="ant-sub-totais" class="conc-sub oculto">
        <p class="dica">Só nota <b>aprovada</b> entra no valor a recolher. O que
           ainda está em revisão aparece à parte e não está liberado.
           <span id="ant-aviso-reducao"></span></p>
        <div class="linha-form">
          <label>Empresa
            <select id="ant-t-empresa"><option value="">Todas</option></select>
          </label>
          <label>Competência
            <input id="ant-t-competencia" type="text" placeholder="mm/aaaa" maxlength="7" size="8">
          </label>
          <button id="ant-t-atualizar" type="button">Atualizar</button>
          <button id="ant-exportar" class="botao-primario oculto" type="button">Exportar apuração (.xlsx)</button>
          <span id="ant-t-status" class="status"></span>
        </div>
        <div class="rolagem"><table id="ant-totais">
          <thead><tr>
            <th>Competência</th><th>Empresa</th><th>Regime</th><th>Notas</th>
            <th class="conc-num">A recolher (aprovado)</th>
            <th class="conc-num">Em revisão</th>
            <th class="conc-num">Redução simulada</th>
            <th class="conc-num">Com redução</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
      </section>

      <section id="ant-sub-calculadora" class="conc-sub oculto">
        <p class="dica">Lançamento manual para conferência: nada é gravado.
           Sem ICMS destacado, o crédito sai da alíquota interestadual da
           tabela. O resultado mostra os dois métodos lado a lado.</p>
        <div class="linha-form">
          <label>Valor da operação
            <input id="ant-c-valor" type="text" inputmode="decimal" placeholder="1.000,00">
          </label>
          <label>UF de origem
            <select id="ant-c-uf"></select>
          </label>
          <label>Mercadoria
            <select id="ant-c-origem">
              <option value="0">Nacional</option>
              <option value="1">Importada ou com mais de 40% de conteúdo importado</option>
            </select>
          </label>
          <label>ICMS destacado (opcional)
            <input id="ant-c-icms" type="text" inputmode="decimal" placeholder="sem destaque">
          </label>
          <label>NCM (opcional)
            <input id="ant-c-ncm" type="text" maxlength="10" size="10">
          </label>
          <label>Data da operação
            <input id="ant-c-data" type="date">
          </label>
          <button id="ant-calcular" class="botao-primario" type="button">Calcular</button>
        </div>
        <p id="ant-c-status" class="status"></p>
        <div id="ant-c-resultado"></div>
      </section>

      <section id="ant-sub-tabela" class="conc-sub oculto">
        <div id="ant-config-area" class="oculto">
          <h3 class="pat-titulo">Parâmetros de cálculo</h3>
          <div class="linha-form">
            <label>Método sugerido na importação
              <select id="ant-p-metodo"></select>
            </label>
            <label>Redução simulada (%)
              <input id="ant-p-reducao" type="text" size="5">
            </label>
            <label>Dia do vencimento de referência
              <input id="ant-p-dia" type="number" min="1" max="28" style="width:5em">
            </label>
          </div>
          <div class="linha-form" id="ant-p-componentes"></div>
          <div class="linha-form">
            <button id="ant-p-salvar" type="button">Salvar parâmetros</button>
            <span id="ant-p-status" class="status"></span>
          </div>
          <h3 class="pat-titulo">Nova alíquota</h3>
          <p class="dica">O percentual de uma linha nunca é alterado: cadastre
             a nova vigência e a anterior é encerrada na véspera. Notas já
             aprovadas guardam a alíquota usada e não mudam.</p>
          <div class="linha-form">
            <label>Tipo
              <select id="ant-a-tipo">
                <option value="interna">Interna (BA)</option>
                <option value="interestadual">Interestadual</option>
              </select>
            </label>
            <label id="ant-a-uf-rotulo" class="oculto">UF de origem
              <select id="ant-a-uf"></select>
            </label>
            <label id="ant-a-ncm-rotulo">NCM (vazio = geral)
              <input id="ant-a-ncm" type="text" maxlength="10" size="10">
            </label>
            <label>Alíquota (%)
              <input id="ant-a-percentual" type="text" size="6" placeholder="20,5">
            </label>
            <label>Vigência a partir de
              <input id="ant-a-inicio" type="date">
            </label>
            <label>Base legal
              <input id="ant-a-base" type="text" size="34" placeholder="Lei, decreto ou resolução">
            </label>
            <button id="ant-a-criar" class="botao-primario" type="button">Cadastrar</button>
          </div>
          <p id="ant-a-status" class="status"></p>
        </div>
        <h3 class="pat-titulo">Tabela de alíquotas</h3>
        <div class="rolagem"><table id="ant-aliquotas">
          <thead><tr><th>Tipo</th><th>UF</th><th>NCM</th>
            <th class="conc-num">Alíquota</th><th>Vigência</th>
            <th>Base legal</th><th></th></tr></thead>
          <tbody></tbody>
        </table></div>
        <h3 class="pat-titulo">Alterações da tabela, dos parâmetros e exclusões</h3>
        <div class="rolagem"><table id="ant-eventos">
          <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Detalhe</th></tr></thead>
          <tbody></tbody>
        </table></div>
      </section>
    </div>`;

  const $ = (id) => document.getElementById(id);
  const pode = {
    importar: Sessao.pode("antecipacao.importar"),
    revisar: Sessao.pode("antecipacao.revisar"),
    aprovar: Sessao.pode("antecipacao.aprovar"),
    configurar: Sessao.pode("antecipacao.configurar"),
    exportar: Sessao.pode("antecipacao.exportar"),
  };
  let catalogo = null;
  let pagina = 1;
  let notaAberta = null;

  // ------------------------------------------------------------------
  // Formatação (os números chegam prontos; aqui só mudam de roupa)

  function reais(texto) {
    if (texto === null || texto === undefined || texto === "") return "—";
    const numero = Number(texto);
    if (!Number.isFinite(numero)) return "—";
    return numero.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  const dinheiro = (objeto) => (objeto ? objeto.texto : "—");
  const pct = (texto) => (texto === null || texto === undefined || texto === ""
    ? "—" : `${String(texto).replace(".", ",")}%`);
  function dataBr(iso) {
    const partes = String(iso || "").slice(0, 10).split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : (iso || "");
  }
  function compBr(competencia) {
    const partes = String(competencia || "").split("-");
    return partes.length === 2 ? `${partes[1]}/${partes[0]}` : (competencia || "");
  }
  function quandoBr(iso) {
    const data = new Date(iso);
    return Number.isNaN(data.getTime()) ? (iso || "")
      : data.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }
  function cnpjBr(cnpj) {
    const d = String(cnpj || "");
    return d.length === 14
      ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}` : d;
  }
  const rotulo = (lista, chave, padrao) =>
    (lista.find((i) => i.chave === chave) || {}).rotulo || padrao || chave || "";
  function opcoes(select, lista, { vazio } = {}) {
    select.innerHTML = (vazio !== undefined ? `<option value="">${esc(vazio)}</option>` : "")
      + lista.map((i) => `<option value="${esc(i.chave)}">${esc(i.rotulo)}</option>`).join("");
  }
  function status(id, texto, tipo) {
    const alvo = $(id);
    alvo.textContent = texto || "";
    alvo.classList.toggle("conc-erro", tipo === "erro");
    alvo.classList.toggle("conc-ok", tipo === "ok");
  }
  const classeSituacao = (s) => ({
    importada: "conc-ok", aprovada: "conc-ok", duplicada: "conc-alerta",
    em_revisao: "conc-alerta", recusada: "conc-erro", invalido: "conc-erro",
    invalida: "conc-erro", repetida: "conc-alerta", falta_xml: "conc-alerta",
    fora_do_escopo: "conc-erro",
  }[s] || "");

  // ------------------------------------------------------------------
  // Subtelas

  function abrirSub(nome) {
    $("ant-subtelas").querySelectorAll("button[data-sub]").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    container.querySelectorAll(".conc-sub").forEach((s) =>
      s.classList.toggle("oculto", s.id !== `ant-sub-${nome}`));
    if (nome === "notas") carregarNotas();
    if (nome === "totais") carregarTotais();
    if (nome === "tabela") carregarTabela();
  }
  $("ant-subtelas").addEventListener("click", (e) => {
    const botao = e.target.closest("button[data-sub]");
    if (botao) abrirSub(botao.dataset.sub);
  });

  // ------------------------------------------------------------------
  // Notas: lista

  function filtrosNotas() {
    const p = new URLSearchParams();
    if ($("ant-f-texto").value.trim()) p.set("texto", $("ant-f-texto").value.trim());
    if ($("ant-f-empresa").value) p.set("cnpj", $("ant-f-empresa").value);
    if ($("ant-f-competencia").value.trim()) p.set("competencia", $("ant-f-competencia").value.trim());
    if ($("ant-f-estado").value) p.set("estado", $("ant-f-estado").value);
    return p;
  }

  async function carregarNotas() {
    const p = filtrosNotas();
    p.set("pagina", pagina);
    let dados;
    try {
      dados = await api(`/api/antecipacao/notas?${p}`);
    } catch (erro) { status("ant-status", erro.message, "erro"); return; }
    status("ant-status", "");
    const corpo = $("ant-lista").querySelector("tbody");
    corpo.innerHTML = dados.itens.map((n) => `
      <tr class="conc-clicavel" data-id="${n.id}" tabindex="0">
        <td>${esc(dataBr(n.dt_emissao))}</td>
        <td>${esc(n.numero)}/${esc(n.serie)}</td>
        <td>${esc(n.nome_emit)}</td><td>${esc(n.uf_origem)}</td>
        <td>${esc(n.nome_dest)}</td><td>${esc(compBr(n.competencia))}</td>
        <td>${n.itens}${n.pendentes ? ` <span class="conc-alerta">(${n.pendentes} aguardando)</span>` : ""}</td>
        <td class="conc-num">${esc(dinheiro(n.a_recolher))}</td>
        <td class="${classeSituacao(n.estado)}">${esc(n.estado_rotulo)}</td>
      </tr>`).join("")
      || `<tr><td colspan="9">Nenhuma nota. Importe os XML na subtela "Importar".</td></tr>`;
    $("ant-pagina").textContent =
      `Página ${dados.pagina} de ${dados.paginas} — ${dados.total} nota(s)`;
    $("ant-anterior").disabled = dados.pagina <= 1;
    $("ant-proxima").disabled = dados.pagina >= dados.paginas;
  }

  let espera = null;
  function aoFiltrar() {
    clearTimeout(espera);
    espera = setTimeout(() => { pagina = 1; carregarNotas(); }, 300);
  }
  ["ant-f-texto", "ant-f-competencia"].forEach((id) =>
    $(id).addEventListener("input", aoFiltrar));
  ["ant-f-empresa", "ant-f-estado"].forEach((id) =>
    $(id).addEventListener("change", aoFiltrar));
  $("ant-f-limpar").addEventListener("click", () => {
    ["ant-f-texto", "ant-f-competencia"].forEach((id) => { $(id).value = ""; });
    ["ant-f-empresa", "ant-f-estado"].forEach((id) => { $(id).value = ""; });
    pagina = 1; carregarNotas();
  });
  $("ant-anterior").addEventListener("click", () => { pagina -= 1; carregarNotas(); });
  $("ant-proxima").addEventListener("click", () => { pagina += 1; carregarNotas(); });
  $("ant-lista").addEventListener("click", (e) => {
    const linha = e.target.closest("tr[data-id]");
    if (linha) abrirNota(Number(linha.dataset.id));
  });
  $("ant-lista").addEventListener("keydown", (e) => {
    const linha = e.target.closest("tr[data-id]");
    if (linha && e.key === "Enter") abrirNota(Number(linha.dataset.id));
  });

  async function carregarEmpresas() {
    let dados;
    try { dados = await api("/api/antecipacao/empresas"); } catch { return; }
    ["ant-f-empresa", "ant-t-empresa"].forEach((id) => {
      const atual = $(id).value;
      $(id).innerHTML = `<option value="">Todas</option>` + dados.itens.map((e) =>
        `<option value="${esc(e.cnpj)}">${esc(e.nome || cnpjBr(e.cnpj))}</option>`).join("");
      $(id).value = atual;
    });
  }

  // ------------------------------------------------------------------
  // Notas: detalhe e revisão

  async function abrirNota(id) {
    try {
      desenharNota(await api(`/api/antecipacao/notas/${id}`));
    } catch (erro) { status("ant-status", erro.message, "erro"); }
  }

  function linhaMemoria(item) {
    const m = item.memoria;
    const outro = m.comparativo
      ? `${reais(m.comparativo.a_recolher)}` : "—";
    const pendencias = item.pendencias.map((p) =>
      `<div class="${p.tipo === "aviso" ? "" : p.tipo === "impede" ? "conc-erro" : "conc-alerta"}">${esc(p.mensagem)}</div>`).join("");
    const decisao = item.decisao
      ? `<span class="${item.decisao === "calcular" ? "conc-ok" : ""}">${esc(item.decisao_rotulo)}</span>`
        + (item.decisao_origem === "revisor"
          ? `<div class="dica">por ${esc(item.decisao_por)}${item.decisao_motivo ? `: ${esc(item.decisao_motivo)}` : ""}</div>` : "")
      : `<span class="conc-alerta">Aguardando decisão</span>`;
    return `
      <tr>
        <td><input type="checkbox" class="ant-marca" value="${item.id}" aria-label="Selecionar item ${esc(item.num_item)}"></td>
        <td>${esc(item.num_item)}</td>
        <td class="ant-produto">${esc(item.descricao)}
          <div class="dica">NCM ${esc(item.ncm)} · CFOP ${esc(item.cfop)} · CST ${esc(item.cst)} · origem ${esc(item.origem_mercadoria)}</div>
          <div class="dica ${item.finalidade ? "" : "conc-alerta"}">${esc(item.finalidade_rotulo)}</div></td>
        <td class="conc-num">${reais(m.valor_operacao)}</td>
        <td class="conc-num">${reais(m.credito)}<div class="dica">${esc(item.tipo_credito === "calculado" ? "calculado" : item.tipo_credito === "destacado" ? "destacado" : "sem crédito")}${item.aliquota_credito ? ` · ${pct(item.aliquota_credito)}` : ""}</div></td>
        <td class="conc-num">${reais(m.base_calculo)}<div class="dica">interna ${pct(m.aliquota_interna)}${m.divisor ? `<br>÷ ${esc(String(m.divisor).replace(".", ","))}` : ""}</div></td>
        <td class="conc-num">${reais(m.icms_interno)}</td>
        <td class="conc-num">${item.decisao === "calcular" ? `<b>${reais(m.a_recolher)}</b>`
          : `${reais(m.a_recolher)}<div class="dica conc-alerta">não entra na soma</div>`}<div class="dica" title="Quanto daria pelo outro método de cálculo">outro método:<br>${outro}</div></td>
        <td class="ant-situacao">${decisao}${pendencias}</td>
      </tr>`;
  }

  function desenharNota(nota) {
    notaAberta = nota;
    const emRevisao = nota.estado === "em_revisao";
    const editavel = emRevisao && pode.revisar;
    const caixa = $("ant-detalhe");
    caixa.classList.remove("oculto");
    caixa.innerHTML = `
      <div class="caixa conc-bloco">
        <h3>Nota ${esc(nota.numero)}/${esc(nota.serie)} —
          <span class="${classeSituacao(nota.estado)}">${esc(nota.estado_rotulo)}</span></h3>
        <p class="dica">
          Fornecedor: <b>${esc(nota.nome_emit)}</b> (${esc(cnpjBr(nota.cnpj_emit))}, ${esc(nota.uf_origem)}) ·
          Empresa: <b>${esc(nota.nome_dest)}</b> (${esc(cnpjBr(nota.cnpj_dest))}) ·
          Emissão ${esc(dataBr(nota.dt_emissao))} · Valor da nota ${esc(dinheiro(nota.valor_total))}<br>
          Chave ${esc(nota.chave)}<br>
          Importada por ${esc(nota.importada_por)} em ${esc(quandoBr(nota.importada_em))}${nota.aprovada_por
            ? ` · Aprovada por ${esc(nota.aprovada_por)} em ${esc(quandoBr(nota.aprovada_em))}` : ""}
        </p>
        <div class="cartoes">
          <div class="cartao"><span class="valor">${esc(dinheiro(nota.a_recolher))}</span><span class="rotulo">A recolher (itens decididos)</span></div>
          <div class="cartao ${nota.pendentes ? "vermelho" : "verde"}"><span class="valor">${nota.pendentes}</span><span class="rotulo">Itens aguardando decisão</span></div>
        </div>

        <div class="linha-form conc-acoes">
          <label>Método
            <select id="ant-n-metodo" ${editavel ? "" : "disabled"}></select>
          </label>
          <label>Competência
            <input id="ant-n-competencia" type="text" size="8" maxlength="7" value="${esc(compBr(nota.competencia))}" ${editavel ? "" : "disabled"}>
          </label>
          <label class="pat-checkbox">
            <span>Crédito de referência autorizado</span>
            <input id="ant-n-presuncao" type="checkbox" ${nota.presuncao ? "checked" : ""} ${editavel ? "" : "disabled"}>
          </label>
          <button id="ant-n-aplicar" type="button" class="${editavel ? "" : "oculto"}">Aplicar e recalcular</button>
          <label>Regime da empresa
            <select id="ant-n-regime" ${pode.revisar ? "" : "disabled"}></select>
          </label>
          <button id="ant-n-regime-salvar" type="button" class="${pode.revisar ? "" : "oculto"}">Salvar regime</button>
        </div>

        <h3 class="pat-titulo">Produtos por CFOP e alíquota</h3>
        <div class="rolagem"><table>
          <thead><tr><th>CFOP</th><th>Alíquota</th><th>Crédito</th><th>Itens</th>
            <th class="conc-num">Valor da operação</th>
            <th class="conc-num">A recolher</th><th>Aguardando</th><th>Fora</th><th></th></tr></thead>
          <tbody>${nota.grupos.map((g, i) => `
            <tr>
              <td>${esc(g.cfop)}</td><td>${g.aliquota ? pct(g.aliquota) : "sem destaque"}</td>
              <td>${esc(g.tipo_credito_rotulo)}</td><td>${g.itens}</td>
              <td class="conc-num">${esc(dinheiro(g.valor_operacao))}</td>
              <td class="conc-num">${esc(dinheiro(g.a_recolher))}</td>
              <td class="${g.pendentes ? "conc-alerta" : ""}">${g.pendentes}</td><td>${g.fora}</td>
              <td>${editavel ? `<button type="button" data-grupo="${i}">Selecionar itens</button>` : ""}</td>
            </tr>`).join("")}</tbody>
        </table></div>

        <h3 class="pat-titulo">Memória de cálculo por item</h3>
        <div class="linha-form conc-acoes ${editavel ? "" : "oculto"}" id="ant-lote">
          <label>Finalidade
            <select id="ant-l-finalidade"></select>
          </label>
          <label>Decisão
            <select id="ant-l-decisao">
              <option value="">Não mudar</option>
              <option value="calcular">Calcular</option>
              <option value="excluir">Fora do cálculo</option>
              <option value="auto">Voltar à regra automática</option>
            </select>
          </label>
          <label>Motivo (obrigatório para exceção ou exclusão)
            <input id="ant-l-motivo" type="text" size="40" maxlength="500">
          </label>
          <button id="ant-l-aplicar" class="botao-primario" type="button">Aplicar aos selecionados</button>
          <span id="ant-l-status" class="status"></span>
        </div>
        <div class="rolagem"><table id="ant-itens" class="ant-itens">
          <thead><tr>
            <th><input type="checkbox" id="ant-marcar-todos" aria-label="Selecionar todos" ${editavel ? "" : "disabled"}></th>
            <th>#</th><th>Produto e finalidade</th>
            <th class="conc-num">Valor da operação</th><th class="conc-num">Crédito</th>
            <th class="conc-num">Base de cálculo</th>
            <th class="conc-num">ICMS interno</th><th class="conc-num">A recolher</th>
            <th>Decisão, pendências e avisos</th>
          </tr></thead>
          <tbody>${nota.lista_itens.map(linhaMemoria).join("")}</tbody>
        </table></div>

        <div class="linha-form conc-acoes">
          <button id="ant-n-aprovar" class="botao-primario ${emRevisao && pode.aprovar ? "" : "oculto"}" type="button">Aprovar nota</button>
          <button id="ant-n-danfe" type="button" class="${nota.tem_xml ? "" : "oculto"}">Abrir DANFE</button>
          <label class="${(emRevisao && pode.revisar) || (!emRevisao && pode.aprovar) ? "" : "oculto"}">Motivo
            <input id="ant-n-motivo" type="text" size="36" maxlength="500">
          </label>
          <button id="ant-n-reabrir" type="button" class="${!emRevisao && pode.aprovar ? "" : "oculto"}">Reabrir nota</button>
          <button id="ant-n-excluir" type="button" class="${emRevisao && pode.revisar ? "" : "oculto"}">Excluir nota</button>
          <span id="ant-n-status" class="status"></span>
        </div>

        <details>
          <summary>Histórico desta nota (${nota.eventos.length})</summary>
          <div class="rolagem"><table>
            <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Detalhe</th></tr></thead>
            <tbody>${nota.eventos.map((e) => `
              <tr><td>${esc(quandoBr(e.criado_em))}</td><td>${esc(e.usuario_login)}</td>
                <td>${esc(e.tipo.replace(/_/g, " "))}</td><td>${esc(e.detalhe)}</td></tr>`).join("")}</tbody>
          </table></div>
        </details>
      </div>`;

    opcoes($("ant-n-metodo"), catalogo.metodos);
    $("ant-n-metodo").value = nota.metodo;
    opcoes($("ant-n-regime"), catalogo.regimes, { vazio: "Não informado" });
    $("ant-n-regime").value = nota.regime;
    opcoes($("ant-l-finalidade"), catalogo.finalidades, { vazio: "Não mudar" });

    const marcas = () => [...caixa.querySelectorAll(".ant-marca")];
    if (!editavel) marcas().forEach((m) => { m.disabled = true; });
    $("ant-marcar-todos").addEventListener("change", (e) =>
      marcas().forEach((m) => { m.checked = e.target.checked; }));
    caixa.querySelectorAll("button[data-grupo]").forEach((botao) =>
      botao.addEventListener("click", () => {
        const ids = new Set(nota.grupos[Number(botao.dataset.grupo)].item_ids);
        marcas().forEach((m) => { m.checked = ids.has(Number(m.value)); });
        $("ant-lote").scrollIntoView({ block: "nearest" });
      }));

    const refazer = async (acao, idStatus) => {
      try {
        desenharNota(await acao());
        carregarNotas();
      } catch (erro) {
        status(idStatus, erro.message, "erro");
        // A nota mudou em outra sessão: mostra o estado atual em vez de
        // deixar a pessoa insistindo numa versão velha.
        if (erro.codigo === "REVISION_DESATUALIZADA") abrirNota(nota.id);
      }
    };

    $("ant-n-aplicar").addEventListener("click", () => refazer(() =>
      api(`/api/antecipacao/notas/${nota.id}`, { method: "PUT", json: {
        revision: nota.revision, metodo: $("ant-n-metodo").value,
        presuncao: $("ant-n-presuncao").checked,
        competencia: $("ant-n-competencia").value.trim() } }), "ant-n-status"));

    $("ant-n-regime-salvar").addEventListener("click", async () => {
      if (!$("ant-n-regime").value) { status("ant-n-status", "Escolha o regime.", "erro"); return; }
      try {
        await api(`/api/antecipacao/empresas/${nota.cnpj_dest}`, {
          method: "PUT", json: { regime: $("ant-n-regime").value } });
        abrirNota(nota.id);
      } catch (erro) { status("ant-n-status", erro.message, "erro"); }
    });

    $("ant-l-aplicar").addEventListener("click", () => {
      const ids = marcas().filter((m) => m.checked).map((m) => Number(m.value));
      const finalidade = $("ant-l-finalidade").value;
      const decisao = $("ant-l-decisao").value;
      if (!ids.length) { status("ant-l-status", "Selecione ao menos um item.", "erro"); return; }
      if (!finalidade && !decisao) { status("ant-l-status", "Escolha a finalidade ou a decisão.", "erro"); return; }
      const corpo = { revision: nota.revision, item_ids: ids,
                      motivo: $("ant-l-motivo").value };
      if (finalidade) corpo.finalidade = finalidade;
      if (decisao) corpo.decisao = decisao === "auto" ? "" : decisao;
      refazer(() => api(`/api/antecipacao/notas/${nota.id}/itens`,
        { method: "PUT", json: corpo }), "ant-l-status");
    });

    $("ant-n-aprovar").addEventListener("click", async () => {
      const sim = await confirmar("Aprovar a nota",
        `O valor de ${dinheiro(nota.a_recolher)} passa a contar no total a recolher da empresa. Confirma?`);
      if (sim) refazer(() => api(`/api/antecipacao/notas/${nota.id}/aprovar`,
        { json: { revision: nota.revision } }), "ant-n-status");
    });
    $("ant-n-reabrir").addEventListener("click", () => refazer(() =>
      api(`/api/antecipacao/notas/${nota.id}/reabrir`, { json: {
        revision: nota.revision, motivo: $("ant-n-motivo").value } }), "ant-n-status"));
    $("ant-n-excluir").addEventListener("click", async () => {
      const sim = await confirmar("Excluir a nota",
        "A nota e o XML guardado saem do sistema; o registro da exclusão fica. Confirma?");
      if (!sim) return;
      try {
        await api(`/api/antecipacao/notas/${nota.id}/excluir`, { json: {
          revision: nota.revision, motivo: $("ant-n-motivo").value } });
        caixa.classList.add("oculto"); caixa.innerHTML = ""; notaAberta = null;
        toast("Nota excluída.");
        carregarNotas(); carregarEmpresas();
      } catch (erro) { status("ant-n-status", erro.message, "erro"); }
    });
    $("ant-n-danfe").addEventListener("click", async () => {
      try { await apiDownload(`/api/antecipacao/notas/${nota.id}/danfe`); }
      catch (erro) { status("ant-n-status", erro.message, "erro"); }
    });
    caixa.scrollIntoView({ block: "nearest" });
  }

  // ------------------------------------------------------------------
  // Importar

  $("ant-importar").addEventListener("click", async () => {
    const arquivos = [...$("ant-i-arquivos").files];
    if (!arquivos.length) { status("ant-i-status", "Selecione os arquivos XML.", "erro"); return; }
    if (arquivos.length > catalogo.limites.arquivos) {
      status("ant-i-status", `Envie no máximo ${catalogo.limites.arquivos} arquivos por vez.`, "erro");
      return;
    }
    const corpo = new FormData();
    corpo.append("metodo", $("ant-i-metodo").value);
    corpo.append("finalidade", $("ant-i-finalidade").value);
    corpo.append("presuncao", $("ant-i-presuncao").checked ? "1" : "");
    arquivos.forEach((a) => corpo.append("arquivos", a));
    status("ant-i-status", `Enviando ${arquivos.length} arquivo(s)…`);
    $("ant-importar").disabled = true;
    try {
      const dados = await api("/api/antecipacao/importar", { method: "POST", body: corpo });
      const rotulos = { importada: "Importada", duplicada: "Já importada",
                        recusada: "Fora do escopo", invalido: "Arquivo inválido" };
      $("ant-i-resultado-caixa").classList.remove("oculto");
      $("ant-i-resultado").querySelector("tbody").innerHTML = dados.itens.map((l) => `
        <tr>
          <td>${esc(l.arquivo)}</td>
          <td class="${classeSituacao(l.situacao)}">${esc(rotulos[l.situacao] || l.situacao)}</td>
          <td>${l.itens ?? ""}${l.pendentes ? ` <span class="conc-alerta">(${l.pendentes} aguardando)</span>` : ""}</td>
          <td class="conc-num">${l.a_recolher ? esc(l.a_recolher.texto) : ""}</td>
          <td>${esc(l.mensagem || "")}</td>
        </tr>`).join("");
      const c = dados.contagem;
      status("ant-i-status",
        `${c.importada || 0} importada(s), ${c.duplicada || 0} já existente(s), `
        + `${(c.recusada || 0) + (c.invalido || 0)} fora.`, "ok");
      $("ant-i-arquivos").value = "";
      carregarEmpresas();
    } catch (erro) {
      status("ant-i-status", erro.message, "erro");
    } finally {
      $("ant-importar").disabled = false;
    }
  });

  $("ant-conferir").addEventListener("click", async () => {
    try {
      const dados = await api("/api/antecipacao/chaves/conferir",
        { json: { texto: $("ant-chaves").value } });
      const rotulos = { importada: "Já importada", falta_xml: "Falta o XML",
                        repetida: "Repetida", invalida: "Inválida",
                        fora_do_escopo: "Fora do escopo" };
      $("ant-chaves-caixa").classList.remove("oculto");
      $("ant-chaves-resultado").querySelector("tbody").innerHTML = dados.itens.map((l) => `
        <tr>
          <td>${esc(l.chave)}</td><td>${esc(l.uf || "")}</td>
          <td>${esc(compBr(l.ano_mes || ""))}</td>
          <td>${l.numero ? `${esc(l.numero)}/${esc(l.serie)}` : ""}</td>
          <td class="${classeSituacao(l.situacao)}">${esc(rotulos[l.situacao] || l.situacao)}
            <div class="dica">${esc(l.mensagem || "")}</div></td>
        </tr>`).join("") || `<tr><td colspan="5">Nenhuma chave no texto.</td></tr>`;
    } catch (erro) { toast(erro.message, "erro"); }
  });

  // ------------------------------------------------------------------
  // Totais

  function filtrosTotais() {
    const p = new URLSearchParams();
    if ($("ant-t-empresa").value) p.set("cnpj", $("ant-t-empresa").value);
    if ($("ant-t-competencia").value.trim()) p.set("competencia", $("ant-t-competencia").value.trim());
    return p;
  }

  async function carregarTotais() {
    let dados;
    try {
      dados = await api(`/api/antecipacao/resumo?${filtrosTotais()}`);
    } catch (erro) { status("ant-t-status", erro.message, "erro"); return; }
    status("ant-t-status", "");
    $("ant-totais").querySelector("tbody").innerHTML = dados.itens.map((l) => `
      <tr>
        <td>${esc(compBr(l.competencia))}<div class="dica">venc. de referência ${esc(dataBr(l.vencimento_referencia))}</div></td>
        <td>${esc(l.nome)}<div class="dica">${esc(cnpjBr(l.cnpj))}</div></td>
        <td class="${l.regime ? "" : "conc-alerta"}">${esc(l.regime_rotulo)}</td>
        <td>${l.aprovadas} de ${l.notas} aprovada(s)${l.itens_pendentes
          ? `<div class="conc-alerta">${l.itens_pendentes} item(ns) aguardando</div>` : ""}</td>
        <td class="conc-num"><b>${esc(dinheiro(l.aprovado))}</b></td>
        <td class="conc-num">${esc(dinheiro(l.em_revisao))}</td>
        <td class="conc-num">${l.reducao_simulada ? `${esc(l.reducao_simulada.texto)}<div class="dica">${pct(l.reducao_percentual)}</div>` : "—"}</td>
        <td class="conc-num">${esc(dinheiro(l.aprovado_com_reducao))}</td>
      </tr>`).join("") || `<tr><td colspan="8">Nenhuma nota no filtro.</td></tr>`;
  }
  $("ant-t-atualizar").addEventListener("click", carregarTotais);
  $("ant-t-empresa").addEventListener("change", carregarTotais);
  $("ant-exportar").addEventListener("click", async () => {
    status("ant-t-status", "Gerando a planilha…");
    try {
      const nome = await apiDownload(`/api/antecipacao/exportar?${filtrosTotais()}`,
        { method: "POST" });
      status("ant-t-status", `Planilha gerada: ${nome}`, "ok");
    } catch (erro) { status("ant-t-status", erro.message, "erro"); }
  });

  // ------------------------------------------------------------------
  // Calculadora

  $("ant-calcular").addEventListener("click", async () => {
    let r;
    try {
      r = await api("/api/antecipacao/simular", { json: {
        valor_operacao: $("ant-c-valor").value, uf_origem: $("ant-c-uf").value,
        icms_destacado: $("ant-c-icms").value,
        origem_mercadoria: $("ant-c-origem").value,
        ncm: $("ant-c-ncm").value, data: $("ant-c-data").value } });
    } catch (erro) {
      status("ant-c-status", erro.message, "erro");
      $("ant-c-resultado").innerHTML = "";
      return;
    }
    status("ant-c-status", "");
    const coluna = (chave) => r.metodos[chave];
    const linha = (titulo, campo, formato = reais) => `
      <tr><td>${titulo}</td>${catalogo.metodos.map((m) =>
        `<td class="conc-num">${coluna(m.chave)[campo] === null ? "—" : formato(coluna(m.chave)[campo])}</td>`).join("")}</tr>`;
    $("ant-c-resultado").innerHTML = `
      <p class="dica">Crédito <b>${esc(rotulo([{ chave: "destacado", rotulo: "destacado" },
        { chave: "calculado", rotulo: "calculado pela tabela" }], r.tipo_credito))}</b>:
        ${reais(r.credito)} · alíquota interestadual de referência ${pct(r.aliquota_interestadual)}
        (${esc(r.aliquota_interestadual_base_legal || "sem linha na tabela")}) ·
        alíquota interna ${pct(r.aliquota_interna)} (${esc(r.aliquota_interna_base_legal || "")}).</p>
      <div class="rolagem"><table>
        <thead><tr><th>Memória de cálculo</th>${catalogo.metodos.map((m) =>
          `<th class="conc-num">${esc(m.rotulo)}</th>`).join("")}</tr></thead>
        <tbody>
          <tr><td>Valor da operação</td>${catalogo.metodos.map(() =>
            `<td class="conc-num">${reais(r.valor_operacao)}</td>`).join("")}</tr>
          <tr><td>Crédito</td>${catalogo.metodos.map(() =>
            `<td class="conc-num">${reais(r.credito)}</td>`).join("")}</tr>
          ${linha("Divisor", "divisor", (v) => esc(String(v).replace(".", ",")))}
          ${linha("Valor sem ICMS", "valor_sem_icms")}
          ${linha("Base de cálculo", "base_calculo")}
          ${linha("ICMS interno", "icms_interno")}
          ${linha("<b>A recolher</b>", "a_recolher")}
        </tbody>
      </table></div>`;
  });

  // ------------------------------------------------------------------
  // Alíquotas e parâmetros

  async function carregarTabela() {
    let aliquotas, eventos;
    try {
      [aliquotas, eventos] = await Promise.all([
        api("/api/antecipacao/aliquotas"), api("/api/antecipacao/eventos")]);
    } catch (erro) { status("ant-status", erro.message, "erro"); return; }
    $("ant-aliquotas").querySelector("tbody").innerHTML = aliquotas.itens.map((l) => `
      <tr>
        <td>${l.tipo === "interna" ? "Interna" : "Interestadual"}</td>
        <td>${esc(l.uf === "IMPORTADO" ? "Importado (qualquer UF)" : l.uf)}</td>
        <td>${esc(l.ncm || "geral")}</td>
        <td class="conc-num">${pct(l.percentual)}</td>
        <td>${esc(dataBr(l.vigencia_inicio))} ${l.vigencia_fim
          ? `a ${esc(dataBr(l.vigencia_fim))}` : `<span class="conc-ok">em vigor</span>`}</td>
        <td>${esc(l.base_legal)}</td>
        <td>${pode.configurar && !l.vigencia_fim
          ? `<button type="button" data-encerrar="${l.id}">Encerrar</button>` : ""}</td>
      </tr>`).join("");
    $("ant-eventos").querySelector("tbody").innerHTML = eventos.itens.map((e) => `
      <tr><td>${esc(quandoBr(e.criado_em))}</td><td>${esc(e.usuario_login)}</td>
        <td>${esc(e.tipo.replace(/_/g, " "))}</td>
        <td>${esc(e.detalhe)}${e.chave ? `<div class="dica">${esc(e.chave)}</div>` : ""}</td></tr>`).join("")
      || `<tr><td colspan="4">Nenhuma alteração registrada.</td></tr>`;
  }

  $("ant-aliquotas").addEventListener("click", async (e) => {
    const botao = e.target.closest("button[data-encerrar]");
    if (!botao) return;
    const hoje = new Date().toISOString().slice(0, 10);
    const sim = await confirmar("Encerrar a vigência",
      `A alíquota deixa de valer depois de hoje (${dataBr(hoje)}). Notas com data posterior ficarão sem alíquota até haver uma nova linha. Confirma?`);
    if (!sim) return;
    try {
      await api(`/api/antecipacao/aliquotas/${botao.dataset.encerrar}/encerrar`,
        { json: { vigencia_fim: hoje } });
      carregarTabela();
    } catch (erro) { status("ant-a-status", erro.message, "erro"); }
  });

  $("ant-a-tipo").addEventListener("change", () => {
    const interna = $("ant-a-tipo").value === "interna";
    $("ant-a-uf-rotulo").classList.toggle("oculto", interna);
    $("ant-a-ncm-rotulo").classList.toggle("oculto", !interna);
  });
  $("ant-a-criar").addEventListener("click", async () => {
    try {
      await api("/api/antecipacao/aliquotas", { json: {
        tipo: $("ant-a-tipo").value, uf: $("ant-a-uf").value,
        ncm: $("ant-a-ncm").value, percentual: $("ant-a-percentual").value,
        vigencia_inicio: $("ant-a-inicio").value,
        base_legal: $("ant-a-base").value } });
      status("ant-a-status", "Alíquota cadastrada.", "ok");
      ["ant-a-ncm", "ant-a-percentual", "ant-a-base"].forEach((id) => { $(id).value = ""; });
      carregarTabela();
    } catch (erro) { status("ant-a-status", erro.message, "erro"); }
  });

  function preencherParametros(config) {
    $("ant-p-metodo").value = config.metodo_padrao;
    $("ant-p-reducao").value = String(config.reducao_percentual).replace(".", ",");
    $("ant-p-dia").value = config.dia_vencimento;
    $("ant-p-componentes").innerHTML = `<span class="dica">Entram no valor da operação:</span>`
      + catalogo.componentes.map((c) => `
        <label class="pat-checkbox"><span>${esc(c.rotulo)}</span>
          <input type="checkbox" data-componente="${esc(c.chave)}" ${config.componentes[c.chave] ? "checked" : ""}>
        </label>`).join("");
  }
  $("ant-p-salvar").addEventListener("click", async () => {
    const componentes = {};
    $("ant-p-componentes").querySelectorAll("input[data-componente]").forEach((c) => {
      componentes[c.dataset.componente] = c.checked;
    });
    try {
      catalogo.configuracao = await api("/api/antecipacao/configuracao", {
        method: "PUT", json: {
          metodo_padrao: $("ant-p-metodo").value, componentes,
          reducao_percentual: $("ant-p-reducao").value,
          dia_vencimento: Number($("ant-p-dia").value) } });
      preencherParametros(catalogo.configuracao);
      $("ant-i-metodo").value = catalogo.configuracao.metodo_padrao;
      status("ant-p-status", "Parâmetros salvos. Valem para as próximas importações.", "ok");
      carregarTabela();
    } catch (erro) { status("ant-p-status", erro.message, "erro"); }
  });

  // ------------------------------------------------------------------
  // Partida

  (async () => {
    try {
      catalogo = await api("/api/antecipacao/catalogo");
    } catch (erro) { status("ant-status", erro.message, "erro"); return; }
    $("ant-aviso").textContent = catalogo.avisos.homologacao;
    $("ant-aviso-reducao").textContent = catalogo.avisos.reducao;
    $("ant-lim-arquivos").textContent = catalogo.limites.arquivos;
    opcoes($("ant-f-estado"), catalogo.estados, { vazio: "Todas" });
    opcoes($("ant-i-metodo"), catalogo.metodos);
    $("ant-i-metodo").value = catalogo.configuracao.metodo_padrao;
    $("ant-i-finalidade").innerHTML = `<option value="">Definir na revisão</option>`
      + catalogo.finalidades.map((f) =>
        `<option value="${esc(f.chave)}">${esc(f.rotulo)}</option>`).join("");
    const ufs = catalogo.ufs_origem.map((uf) => ({ chave: uf, rotulo: uf }));
    opcoes($("ant-c-uf"), ufs);
    opcoes($("ant-a-uf"), ufs.concat([{ chave: "IMPORTADO", rotulo: "Importado (qualquer UF)" }]));
    opcoes($("ant-p-metodo"), catalogo.metodos);
    preencherParametros(catalogo.configuracao);
    $("ant-importar-area").classList.toggle("oculto", !pode.importar);
    $("ant-config-area").classList.toggle("oculto", !pode.configurar);
    $("ant-exportar").classList.toggle("oculto", !pode.exportar);
    await carregarEmpresas();
    carregarNotas();
  })();
});
