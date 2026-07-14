/* Aba 3 — Livro de Conferencia Fiscal (paridade com o desktop). */

"use strict";

Abas.registrar("conferencia", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Origem das notas</h2>
      <div class="linha-form">
        <label>Fonte
          <select id="conf-fonte">
            <option value="xml">Pasta de XMLs de NF-e</option>
            <option value="sped">Arquivo SPED Fiscal (.txt)</option>
          </select>
        </label>
        <label>Arquivos (.txt, .xml ou .zip — pode enviar o ano inteiro)
          <input id="conf-arquivos" type="file" multiple
                 accept=".txt,.xml,.zip">
        </label>
        <label><input id="conf-entradas" type="checkbox" checked>
          Considerar apenas documentos de entrada no SPED</label>
        <button id="conf-carregar" class="botao-primario">Enviar e carregar</button>
      </div>
      <p id="conf-status" class="status"></p>
    </div>

    <div class="caixa">
      <div class="linha-form">
        <label>Filtro
          <select id="conf-filtro">
            <option>Todas</option><option>Pendentes</option><option>Conferidas</option>
          </select>
        </label>
        <label>Busca <input id="conf-busca" placeholder="numero, fornecedor, CNPJ, chave"></label>
        <button id="conf-corrigir">Corrigir campo fiscal...</button>
        <button id="conf-danfe">Abrir DANFE</button>
        <button id="conf-livro">Livro Fiscal (PDF)</button>
        <button id="conf-inconsistencias">Inconsistencias (PDF)</button>
        <button id="conf-sped">SPED corrigido</button>
      </div>
      <div class="rolagem"><table id="conf-tabela">
        <thead><tr>
          <th>Conf.</th><th>Numero</th><th>Serie</th><th>Data</th>
          <th>Fornecedor</th><th>CNPJ</th><th>UF</th><th>Valor contabil</th>
          <th>Base ICMS</th><th>Valor ICMS</th><th>CFOP</th><th>CST</th>
          <th>Aliquota</th><th>Observacao</th><th>Data conf.</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <p id="conf-progresso" class="status"></p>
    </div>

    <div class="caixa">
      <h2>Composicao fiscal da nota selecionada (CFOP → CST → Aliquota) —
          duplo clique em qualquer celula edita</h2>
      <div class="rolagem" style="max-height:32vh"><table id="conf-comp">
        <thead><tr>
          <th>CFOP</th><th>CST</th><th>Aliquota</th><th>Valor contabil</th>
          <th>Base ICMS</th><th>Valor ICMS</th><th>ICMS-ST</th><th>Itens</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <p id="conf-alertas" class="status"></p>
    </div>`;

  const estado = { sessaoId: null, notas: [], chave: null };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("conf-status").textContent = texto; };

  // ------------------------------------------------------------------
  // Carga

  $("conf-carregar").addEventListener("click", async () => {
    const arquivos = [...$("conf-arquivos").files];
    if (!arquivos.length) { toast("Selecione os arquivos.", "erro"); return; }
    const botao = $("conf-carregar");
    botao.disabled = true;
    try {
      const { sessao_id } = await api("/api/sessoes", { json: { ferramenta: "conferencia" } });
      estado.sessaoId = sessao_id;
      for (const [i, arquivo] of arquivos.entries()) {
        status(`Enviando ${i + 1}/${arquivos.length}: ${arquivo.name}...`);
        await apiUpload(`/api/conferencia/upload?sessao_id=${sessao_id}`, arquivo);
      }
      status("Carregando notas...");
      const { job_id } = await api("/api/conferencia/carregar", { json: {
        sessao_id, fonte: $("conf-fonte").value,
        apenas_entradas: $("conf-entradas").checked } });
      const resultado = await esperarJob(job_id);
      await atualizarNotas();
      status(`${resultado.total} nota(s) carregada(s) — ${resultado.contexto}.`);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  async function atualizarNotas() {
    if (!estado.sessaoId) return;
    const dados = await api(`/api/conferencia/notas?sessao_id=${estado.sessaoId}`);
    estado.notas = dados.itens;
    renderNotas();
  }

  // ------------------------------------------------------------------
  // Tabela de notas

  function filtradas() {
    const filtro = $("conf-filtro").value;
    const busca = $("conf-busca").value.trim().toLowerCase();
    return estado.notas.filter((n) => {
      if (filtro === "Pendentes" && n.conferida) return false;
      if (filtro === "Conferidas" && !n.conferida) return false;
      if (busca) {
        const alvo = `${n.numero} ${n.fornecedor} ${n.cnpj} ${n.chave}`.toLowerCase();
        if (!alvo.includes(busca)) return false;
      }
      return true;
    });
  }

  function renderNotas() {
    const corpo = $("conf-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    const visiveis = filtradas();
    for (const n of visiveis) {
      const tr = document.createElement("tr");
      tr.dataset.chave = n.chave;
      if (n.conferida) tr.classList.add("conferida");
      if (n.chave === estado.chave) tr.classList.add("selecionada");
      tr.innerHTML = `
        <td><input type="checkbox" ${n.conferida ? "checked" : ""}></td>
        <td>${n.numero}</td><td>${n.serie}</td><td>${n.data}</td>
        <td>${n.fornecedor}</td><td>${n.cnpj}</td><td>${n.uf}</td>
        <td class="${n.tem_correcao ? "corrigido" : ""}">${n.valor_contabil}</td>
        <td>${n.base_icms}</td><td>${n.valor_icms}</td>
        <td class="${n.tem_correcao ? "corrigido" : ""}">${n.cfop}</td>
        <td class="${n.tem_correcao ? "corrigido" : ""}">${n.cst}</td>
        <td class="${n.tem_correcao ? "corrigido" : ""}">${n.aliquota}</td>
        <td class="editavel obs">${n.observacao}</td>
        <td>${n.data_conferencia}</td>`;
      corpo.appendChild(tr);
    }
    const total = estado.notas.length;
    const conferidas = estado.notas.filter((n) => n.conferida).length;
    $("conf-progresso").textContent = total
      ? `${conferidas}/${total} conferida(s) — ${visiveis.length} na tela.` : "";
  }

  $("conf-filtro").addEventListener("change", renderNotas);
  $("conf-busca").addEventListener("input", renderNotas);

  $("conf-tabela").addEventListener("click", async (e) => {
    const tr = e.target.closest("tr[data-chave]");
    if (!tr) return;
    const chave = tr.dataset.chave;
    if (e.target.matches("input[type=checkbox]")) {
      const nota = estado.notas.find((n) => n.chave === chave);
      try {
        const r = await api("/api/conferencia/conferir", { json: {
          sessao_id: estado.sessaoId, chave, conferida: e.target.checked,
          observacao: nota.observacao } });
        nota.conferida = e.target.checked;
        nota.data_conferencia = r.data_conferencia;
        renderNotas();
      } catch (erro) { toast(erro.message, "erro"); }
      return;
    }
    estado.chave = chave;
    renderNotas();
    await carregarComposicao();
  });

  // Observacao editavel por duplo clique
  $("conf-tabela").addEventListener("dblclick", (e) => {
    const celula = e.target.closest("td.obs");
    const tr = e.target.closest("tr[data-chave]");
    if (!celula || !tr) return;
    const nota = estado.notas.find((n) => n.chave === tr.dataset.chave);
    editarCelula(celula, nota.observacao, async (texto) => {
      await api("/api/conferencia/conferir", { json: {
        sessao_id: estado.sessaoId, chave: nota.chave,
        conferida: nota.conferida, observacao: texto } });
      nota.observacao = texto;
      renderNotas();
    });
  });

  function editarCelula(celula, valorAtual, salvar) {
    const entrada = document.createElement("input");
    entrada.value = valorAtual;
    celula.textContent = "";
    celula.appendChild(entrada);
    entrada.focus(); entrada.select();
    let terminado = false;
    const concluir = async (confirmarEdicao) => {
      if (terminado) return;
      terminado = true;
      const texto = entrada.value;
      entrada.remove();
      celula.textContent = valorAtual;
      if (confirmarEdicao && texto !== valorAtual) {
        try { await salvar(texto); }
        catch (erro) { toast(erro.message, "erro"); }
      }
    };
    entrada.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") concluir(true);
      if (ev.key === "Escape") concluir(false);
    });
    entrada.addEventListener("blur", () => concluir(true));
  }

  // ------------------------------------------------------------------
  // Composicao fiscal

  async function carregarComposicao() {
    const corpo = $("conf-comp").querySelector("tbody");
    corpo.innerHTML = "";
    $("conf-alertas").textContent = "";
    if (!estado.chave) return;
    try {
      const comp = await api(
        `/api/conferencia/composicao?sessao_id=${estado.sessaoId}&chave=${estado.chave}`);
      renderComposicao(comp);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  function renderComposicao(comp) {
    const corpo = $("conf-comp").querySelector("tbody");
    corpo.innerHTML = "";
    for (const linha of comp.linhas) {
      const tr = document.createElement("tr");
      tr.dataset.grupo = linha.grupo;
      for (const celula of linha.celulas) {
        const td = document.createElement("td");
        td.textContent = celula.texto;
        td.dataset.coluna = celula.coluna;
        if (celula.edicao) { td.classList.add("editavel"); td.dataset.edicao = celula.edicao; }
        if (celula.original) td.dataset.original = celula.original;
        if (celula.corrigido_de) {
          td.classList.add("corrigido");
          td.title = `Corrigido — valor original: ${celula.corrigido_de}`;
        }
        if (celula.override) {
          td.classList.add("sobrescrito");
          td.title = `Editado manualmente — valor calculado: ${celula.override.calculado || "(vazio)"}` +
            ` (por ${celula.override.usuario} em ${celula.override.data}).` +
            ` Apague o texto para voltar ao calculado.`;
        }
        tr.appendChild(td);
      }
      corpo.appendChild(tr);
    }
    $("conf-alertas").textContent = comp.alertas.length
      ? "Alertas: " + comp.alertas.join(" | ") : "";
  }

  $("conf-comp").addEventListener("dblclick", (e) => {
    const td = e.target.closest("td.editavel");
    const tr = e.target.closest("tr[data-grupo]");
    if (!td || !tr) return;
    const coluna = Number(td.dataset.coluna);
    const ehCorrecao = td.dataset.edicao === "correcao";
    editarCelula(td, td.textContent, async (texto) => {
      if (ehCorrecao) {
        const ok = await confirmar("Confirmar correcao",
          `Alterar de ${td.dataset.original} para ${texto}? O valor original ` +
          "fica no historico de auditoria e a correcao vale para a tela, o " +
          "Livro Fiscal, o relatorio de inconsistencias e o SPED corrigido.");
        if (!ok) { await carregarComposicao(); return; }
      }
      const comp = await api("/api/conferencia/composicao/editar", { json: {
        sessao_id: estado.sessaoId, chave: estado.chave,
        grupo: tr.dataset.grupo, coluna, texto } });
      renderComposicao(comp);
      if (ehCorrecao) await atualizarNotas();
    });
  });

  // ------------------------------------------------------------------
  // Correcao manual (dialogo) e documentos

  $("conf-corrigir").addEventListener("click", () => {
    if (!estado.chave) { toast("Selecione uma nota na tabela.", "erro"); return; }
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    fundo.innerHTML = `
      <div class="modal">
        <h3>Corrigir campo fiscal</h3>
        <div class="linha-form" style="flex-direction:column;align-items:stretch">
          <label>Campo
            <select id="cor-campo">
              <option value="cfop">CFOP</option>
              <option value="cst_icms">CST</option>
              <option value="aliq_icms">Aliquota ICMS</option>
            </select></label>
          <label>Valor original <input id="cor-original" placeholder="ex.: 1102"></label>
          <label>Valor corrigido <input id="cor-novo" placeholder="ex.: 1403"></label>
          <label>Motivo <input id="cor-motivo" placeholder="justificativa (auditoria)"></label>
          <label><input id="cor-lote" type="checkbox">
            Aplicar em TODAS as notas carregadas com este valor</label>
        </div>
        <div class="acoes">
          <button class="cancelar">Cancelar</button>
          <button class="confirmar botao-primario">Corrigir</button>
        </div>
      </div>`;
    fundo.querySelector(".cancelar").onclick = () => fundo.remove();
    fundo.querySelector(".confirmar").onclick = async () => {
      try {
        const r = await api("/api/conferencia/corrigir", { json: {
          sessao_id: estado.sessaoId, chave: estado.chave,
          campo: fundo.querySelector("#cor-campo").value,
          original: fundo.querySelector("#cor-original").value,
          novo: fundo.querySelector("#cor-novo").value,
          motivo: fundo.querySelector("#cor-motivo").value,
          lote: fundo.querySelector("#cor-lote").checked } });
        fundo.remove();
        toast(r.mensagem);
        await atualizarNotas();
        await carregarComposicao();
      } catch (erro) { toast(erro.message, "erro"); }
    };
    document.body.appendChild(fundo);
  });

  $("conf-danfe").addEventListener("click", async () => {
    if (!estado.chave) { toast("Selecione uma nota na tabela.", "erro"); return; }
    try {
      const resposta = await api(
        `/api/conferencia/danfe?sessao_id=${estado.sessaoId}&chave=${estado.chave}`);
      const blob = await resposta.blob();
      window.open(URL.createObjectURL(blob), "_blank");
    } catch (erro) { toast(erro.message, "erro"); }
  });

  const baixar = (botaoId, caminho, rotulo) => {
    $(botaoId).addEventListener("click", async () => {
      if (!estado.sessaoId) { toast("Carregue as notas antes.", "erro"); return; }
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
  baixar("conf-livro", "/api/conferencia/livro-fiscal", "Livro Fiscal");
  baixar("conf-inconsistencias", "/api/conferencia/inconsistencias", "Relatorio de Inconsistencias");
  baixar("conf-sped", "/api/conferencia/sped-corrigido", "SPED corrigido");
});
