/* Aba 4 — Extracao de Itens (paridade com o desktop). */

"use strict";

Abas.registrar("extracao", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Origem das notas</h2>
      <p class="dica">Importe o <b>SPED</b> e, opcionalmente, a <b>pasta de
         XMLs</b> das notas no mesmo envio. O sistema lê o SPED, identifica as
         notas declaradas e lê automaticamente apenas os XMLs correspondentes,
         pela chave de acesso — sem forçar escolher entre um ou outro. (Sem
         SPED, você ainda pode extrair só dos XMLs.)</p>
      <div class="linha-form">
        <label>Arquivo SPED Fiscal (.txt)
          <input id="ext-sped-arq" type="file" accept=".txt">
        </label>
        <label>Pasta de XMLs de NF-e/CT-e (opcional — selecione a pasta inteira)
          <input id="ext-xml-arq" type="file" multiple webkitdirectory
                 accept=".xml,.zip">
        </label>
        <label>Operação
          <select id="ext-operacao" title="No SPED filtra pelo IND_OPER do C100">
            <option value="">Todas</option>
            <option value="0">Apenas entradas</option>
            <option value="1">Apenas saídas</option>
          </select>
        </label>
        <button id="ext-extrair" class="botao-primario">Enviar e extrair</button>
        <button id="ext-exportar" disabled>Exportar Excel (.xlsx)</button>
      </div>
      <p id="ext-status" class="status"></p>
    </div>

    <div class="caixa">
      <h2>Itens extraídos (um por linha da nota)</h2>
      <div class="rolagem"><table id="ext-tabela">
        <thead><tr></tr></thead><tbody></tbody>
      </table></div>
    </div>`;

  const estado = { sessaoId: null, total: 0 };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("ext-status").textContent = texto; };

  const podeExportar = seNaoPuder($("ext-exportar"), "extracao.exportar");

  // ------------------------------------------------------------------
  // Selecao combinada: SPED (.txt) + pasta de XMLs (opcional) no MESMO envio,
  // como no Livro de Conferencia. O fluxo e decidido pelo que veio: SPED
  // presente => o SPED define as notas e os XMLs correspondentes completam;
  // so XMLs => extrai de todos os XMLs.

  const spedsSelecionados = () => [...($("ext-sped-arq").files || [])]
    .filter((f) => /\.txt$/i.test(f.name));
  const xmlsSelecionados = () => [...($("ext-xml-arq").files || [])]
    .filter((f) => /\.(xml|zip)$/i.test(f.name));

  function resumoSelecao() {
    const nSped = spedsSelecionados().length;
    const nXml = xmlsSelecionados().length;
    if (!nSped && !nXml) { status(""); return; }
    const partes = [];
    if (nSped) partes.push("SPED selecionado");
    if (nXml) partes.push(`${nXml} XML(s)`);
    status(`${partes.join(" + ")}. Clique em "Enviar e extrair".`);
  }
  $("ext-sped-arq").addEventListener("change", resumoSelecao);
  $("ext-xml-arq").addEventListener("change", resumoSelecao);

  /* Contadores do vinculo pela chave de acesso (fluxo combinado): conta o
     que casou, o que o XML completou e o que ficou de fora. */
  function textoVinculo(v) {
    if (!v) return "";
    const partes = [`${v.com_xml} nota(s) com XML vinculado`];
    if (v.completadas) partes.push(`${v.completadas} completada(s) com itens do XML`);
    if (v.sem_xml) partes.push(`${v.sem_xml} sem XML correspondente`);
    let texto = ` Vínculo pela chave de acesso: ${partes.join(", ")}.`;
    if (v.ignorados) {
      texto += ` ${v.ignorados} XML(s) fora do SPED ficaram de fora.`;
    }
    return texto;
  }

  $("ext-extrair").addEventListener("click", async () => {
    const speds = spedsSelecionados();
    const xmls = xmlsSelecionados();
    if (!speds.length && !xmls.length) {
      toast("Selecione o arquivo SPED (.txt) e/ou a pasta de XMLs.", "erro");
      return;
    }
    const fonte = speds.length ? "sped" : "xml";
    const arquivos = [...speds, ...xmls];
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
        sessao_id, fonte, operacao: $("ext-operacao").value } });
      const resultado = await esperarJob(job_id);
      estado.total = resultado.total;
      renderPrevia(resultado);
      $("ext-exportar").disabled = resultado.total === 0;
      let texto = `${resultado.total} item(ns) extraído(s) de ${resultado.contexto}.`;
      if (resultado.total > resultado.previa.length) {
        /* Sem a permissao de exportar nao ha botao na tela: mandar o usuario
           usar a exportacao seria apontar para um controle que nao existe. */
        texto += ` (prévia: ${resultado.previa.length} de ${resultado.total}` +
          (podeExportar ? " — exportação inclui tudo)" : ")");
      }
      if (resultado.filtro) texto += ` ${resultado.filtro}.`;
      texto += textoVinculo(resultado.vinculo);
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
