/* Aba 4 — Extracao de Itens (paridade com o desktop). */

"use strict";

Abas.registrar("extracao", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Origem das notas</h2>
      <div class="linha-form">
        <label>Fonte
          <select id="ext-fonte">
            <option value="sped">SPED Fiscal (.txt)</option>
            <option value="xml">Pasta de XMLs de NF-e</option>
          </select>
        </label>
        <label>Arquivos (.txt, .xml ou .zip — pode enviar a pasta zipada)
          <input id="ext-arquivos" type="file" multiple accept=".txt,.xml,.zip">
        </label>
        <label>Operacao
          <select id="ext-operacao" title="No SPED filtra pelo IND_OPER do C100">
            <option value="">Todas</option>
            <option value="0">Apenas entradas</option>
            <option value="1">Apenas saidas</option>
          </select>
        </label>
        <button id="ext-extrair" class="botao-primario">Enviar e extrair</button>
        <button id="ext-exportar" disabled>Exportar Excel (.xlsx)</button>
      </div>
      <p id="ext-status" class="status"></p>
    </div>

    <div class="caixa">
      <h2>Itens extraidos (um por linha da nota)</h2>
      <div class="rolagem"><table id="ext-tabela">
        <thead><tr></tr></thead><tbody></tbody>
      </table></div>
    </div>`;

  const estado = { sessaoId: null, total: 0 };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("ext-status").textContent = texto; };

  const podeExportar = seNaoPuder($("ext-exportar"), "extracao.exportar");

  // Trocar a fonte limpa a selecao de arquivos (mesmo comportamento do desktop).
  $("ext-fonte").addEventListener("change", () => { $("ext-arquivos").value = ""; });

  $("ext-extrair").addEventListener("click", async () => {
    const arquivos = [...$("ext-arquivos").files];
    if (!arquivos.length) { toast("Selecione os arquivos.", "erro"); return; }
    const botao = $("ext-extrair");
    botao.disabled = true;
    $("ext-exportar").disabled = true;
    try {
      const { sessao_id } = await api("/api/sessoes", { json: { ferramenta: "extracao" } });
      estado.sessaoId = sessao_id;
      for (const [i, arquivo] of arquivos.entries()) {
        status(`Enviando ${i + 1}/${arquivos.length}: ${arquivo.name}...`);
        await apiUpload(`/api/extracao/upload?sessao_id=${sessao_id}`, arquivo);
      }
      status("Extraindo itens...");
      const { job_id } = await api("/api/extracao/extrair", { json: {
        sessao_id, fonte: $("ext-fonte").value,
        operacao: $("ext-operacao").value } });
      const resultado = await esperarJob(job_id);
      estado.total = resultado.total;
      renderPrevia(resultado);
      $("ext-exportar").disabled = resultado.total === 0;
      let texto = `${resultado.total} item(ns) extraido(s) de ${resultado.contexto}.`;
      if (resultado.total > resultado.previa.length) {
        /* Sem a permissao de exportar nao ha botao na tela: mandar o usuario
           usar a exportacao seria apontar para um controle que nao existe. */
        texto += ` (previa: ${resultado.previa.length} de ${resultado.total}` +
          (podeExportar ? " — exportacao inclui tudo)" : ")");
      }
      if (resultado.filtro) texto += ` ${resultado.filtro}.`;
      status(texto);
      if (resultado.aviso) toast(resultado.aviso);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  function renderPrevia(resultado) {
    const cabeca = $("ext-tabela").querySelector("thead tr");
    cabeca.innerHTML = "";
    for (const titulo of resultado.titulos) {
      const th = document.createElement("th");
      th.textContent = titulo;
      cabeca.appendChild(th);
    }
    const corpo = $("ext-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    for (const linha of resultado.previa) {
      const tr = document.createElement("tr");
      for (const valor of linha) {
        const td = document.createElement("td");
        td.textContent = valor;
        tr.appendChild(td);
      }
      corpo.appendChild(tr);
    }
  }

  if (podeExportar) {
    $("ext-exportar").addEventListener("click", async () => {
      if (!estado.sessaoId) { toast("Extraia os itens antes.", "erro"); return; }
      const botao = $("ext-exportar");
      botao.disabled = true;
      try {
        const nome = await apiDownload(
          `/api/extracao/exportar?sessao_id=${estado.sessaoId}`, { method: "POST" });
        toast(`Planilha gerada: ${nome}`);
      } catch (erro) { toast(erro.message, "erro"); }
      finally { botao.disabled = false; }
    });
  }
});
