/* Aba 5 — Auditoria de Produtos (paridade com o desktop). */

"use strict";

Abas.registrar("produtos", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Cadastro de produtos</h2>
      <div class="linha-form">
        <label>Planilha do cadastro (xlsx, xlsm, xls, csv ou txt)
          <input id="prod-arquivo" type="file" accept=".xlsx,.xlsm,.xls,.csv,.txt">
        </label>
        <button id="prod-auditar" class="botao-primario">Importar e auditar</button>
        <label>Exibir
          <select id="prod-filtro">
            <option value="todos">Todos</option>
            <option value="inconsistentes">Somente inconsistentes</option>
            <option value="alertas">Somente alertas</option>
            <option value="alta_confianca">Alta confianca (auto-corrigiveis)</option>
          </select>
        </label>
      </div>
      <p id="prod-status" class="status"></p>
    </div>

    <div class="caixa">
      <div class="cartoes" id="prod-indicadores"></div>
    </div>

    <div class="caixa">
      <div class="linha-form">
        <button id="prod-corrigir-sel" disabled>Corrigir selecionados</button>
        <button id="prod-corrigir-alta" disabled>Corrigir alta confianca</button>
        <button id="prod-relatorio" disabled>Exportar relatorio (.xlsx)</button>
        <button id="prod-nova-base" disabled>Gerar nova base</button>
      </div>
      <div class="rolagem"><table id="prod-tabela">
        <thead><tr>
          <th></th><th>Codigo</th><th>Descricao</th><th>NCM</th><th>CEST</th>
          <th>CFOP</th><th>CST</th><th>Aliq</th><th>Trib. atual</th>
          <th>Trib. sugerida</th><th>Confianca</th><th>Situacao</th>
          <th>Inconsistencias</th><th>Correcao sugerida</th><th>Status</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <p id="prod-previa" class="status"></p>
    </div>`;

  const INDICADORES = [
    ["total", "Total", ""],
    ["corretos", "Corretos", "verde"],
    ["inconsistentes", "Inconsistentes", "vermelho"],
    ["alertas", "Alertas", "ambar"],
    ["percentual_inconsistencias", "% inconsistencias", "vermelho"],
    ["sujeitos_st", "Sujeitos a ST", ""],
    ["corrigidos", "Corrigidos", "verde"],
  ];

  const estado = { sessaoId: null, itens: [] };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("prod-status").textContent = texto; };
  const botoes = ["prod-corrigir-sel", "prod-corrigir-alta",
                  "prod-relatorio", "prod-nova-base"];
  const habilitar = (sim) => botoes.forEach((id) => { $(id).disabled = !sim; });

  function renderIndicadores(ind) {
    const caixa = $("prod-indicadores");
    caixa.innerHTML = "";
    for (const [chave, rotulo, cor] of INDICADORES) {
      let valor = ind ? ind[chave] : "-";
      if (chave === "percentual_inconsistencias" && ind) {
        valor = String(valor).replace(".", ",") + "%";
      }
      const cartao = document.createElement("div");
      cartao.className = "cartao" + (cor ? ` ${cor}` : "");
      cartao.innerHTML = `<div class="valor"></div><div class="rotulo"></div>`;
      cartao.querySelector(".valor").textContent = valor;
      cartao.querySelector(".rotulo").textContent = rotulo;
      caixa.appendChild(cartao);
    }
  }
  renderIndicadores(null);

  // ------------------------------------------------------------------
  // Importar e auditar (upload + job)

  $("prod-auditar").addEventListener("click", async () => {
    const arquivo = $("prod-arquivo").files[0];
    if (!arquivo) { toast("Selecione a planilha do cadastro.", "erro"); return; }
    const botao = $("prod-auditar");
    botao.disabled = true;
    habilitar(false);
    try {
      const { sessao_id } = await api("/api/sessoes", { json: { ferramenta: "produtos" } });
      estado.sessaoId = sessao_id;
      status(`Enviando ${arquivo.name}...`);
      await apiUpload(`/api/produtos/upload?sessao_id=${sessao_id}`, arquivo);
      status("Importando e auditando produtos...");
      const { job_id } = await api("/api/produtos/auditar", { json: { sessao_id } });
      const resultado = await esperarJob(job_id);
      for (const aviso of resultado.avisos || []) toast(aviso);
      await atualizarResultados();
      const ind = resultado.indicadores;
      status(`${ind.total} produto(s) auditado(s): ${ind.inconsistentes} ` +
        `inconsistente(s), ${ind.alertas} alerta(s).`);
      habilitar(ind.total > 0);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  $("prod-filtro").addEventListener("change", () => {
    if (estado.sessaoId) {
      atualizarResultados().catch((erro) => toast(erro.message, "erro"));
    }
  });

  // ------------------------------------------------------------------
  // Tabela (previa com indice estavel por produto)

  async function atualizarResultados() {
    const dados = await api(
      `/api/produtos/resultados?sessao_id=${estado.sessaoId}` +
      `&filtro=${$("prod-filtro").value}`);
    estado.itens = dados.itens;
    renderIndicadores(dados.indicadores);
    renderTabela(dados);
  }

  function classeSituacao(situacao) {
    if (situacao === "INCONSISTENTE") return "erro";
    if (situacao === "ALERTA") return "aviso";
    return "";
  }

  function renderTabela(dados) {
    const corpo = $("prod-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    for (const p of dados.itens) {
      const tr = document.createElement("tr");
      tr.dataset.indice = p.indice;
      const marcavel = p.tem_correcao && p.status !== "Corrigido";
      tr.innerHTML = `
        <td>${marcavel ? '<input type="checkbox">' : ""}</td>
        <td>${p.codigo}</td><td>${p.descricao}</td><td>${p.ncm}</td>
        <td>${p.cest}</td><td>${p.cfop}</td><td>${p.cst}</td>
        <td>${p.aliquota}</td><td>${p.trib_atual}</td><td>${p.trib_sugerida}</td>
        <td>${p.confianca}</td>
        <td class="${classeSituacao(p.situacao)}">${p.situacao}</td>
        <td>${p.inconsistencias}</td>
        <td>${p.correcao}</td>
        <td class="${p.status === "Corrigido" ? "corrigido" : ""}">${p.status}</td>`;
      corpo.appendChild(tr);
    }
    const aviso = dados.total_filtrado > dados.itens.length
      ? ` (previa: ${dados.itens.length} de ${dados.total_filtrado}` +
        " — exportacao inclui tudo)" : "";
    $("prod-previa").textContent = dados.itens.length
      ? `${dados.itens.length} produto(s) na tela — ${dados.contexto}.${aviso}`
      : "Nenhum produto para o filtro selecionado.";
  }

  // ------------------------------------------------------------------
  // Correcoes (com confirmacao, como o desktop)

  async function corrigir(corpo, pergunta) {
    const ok = await confirmar("Confirmar correcao",
      `${pergunta} As alteracoes ficam registradas no historico e so vao ` +
      "para o arquivo ao usar Gerar nova base.");
    if (!ok) return;
    try {
      const r = await api("/api/produtos/corrigir", { json: {
        sessao_id: estado.sessaoId, ...corpo } });
      toast(r.mensagem);
      await atualizarResultados();
    } catch (erro) { toast(erro.message, "erro"); }
  }

  $("prod-corrigir-sel").addEventListener("click", async () => {
    const indices = [...$("prod-tabela").querySelectorAll("tbody input:checked")]
      .map((c) => Number(c.closest("tr").dataset.indice));
    if (!indices.length) {
      toast("Marque na primeira coluna os produtos com correcao sugerida " +
        "que deseja corrigir.", "erro");
      return;
    }
    await corrigir({ indices },
      `Aplicar correcoes sugeridas em ${indices.length} produto(s)?`);
  });

  $("prod-corrigir-alta").addEventListener("click", async () => {
    await corrigir({ alta_confianca: true },
      "Aplicar TODAS as correcoes de alta confianca pendentes?");
  });

  // ------------------------------------------------------------------
  // Downloads (relatorio e nova base)

  const baixar = (botaoId, caminho, rotulo) => {
    $(botaoId).addEventListener("click", async () => {
      if (!estado.sessaoId) { toast("Audite o cadastro antes.", "erro"); return; }
      const botao = $(botaoId);
      botao.disabled = true;
      try {
        const nome = await apiDownload(
          `${caminho}?sessao_id=${estado.sessaoId}`, { method: "POST" });
        toast(`${rotulo} gerado: ${nome}`);
      } catch (erro) { toast(erro.message, "erro"); }
      finally { botao.disabled = false; }
    });
  };
  baixar("prod-relatorio", "/api/produtos/relatorio", "Relatorio de auditoria");
  baixar("prod-nova-base", "/api/produtos/nova-base", "Nova base corrigida");
});
