/* Aba 1 — Comparador SPED x SEFAZ (paridade com o desktop). */

"use strict";

Abas.registrar("comparador", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Arquivos</h2>
      <div class="linha-form">
        <label>Arquivo SPED Fiscal (.txt)
          <input id="cmp-sped" type="file" accept=".txt"></label>
        <label>Relacao da SEFAZ (.xlsx, .xlsm, .xls, .csv ou .txt)
          <input id="cmp-sefaz" type="file" accept=".xlsx,.xlsm,.xls,.csv,.txt"></label>
        <label><input id="cmp-entradas" type="checkbox" checked>
          Considerar apenas documentos de entrada no SPED (recomendado)</label>
        <button id="cmp-comparar" class="botao-primario">Comparar</button>
        <button id="cmp-exportar" disabled>Exportar relatorio (.xlsx)</button>
      </div>
      <p id="cmp-status" class="status"></p>
    </div>

    <div class="caixa">
      <div class="cartoes">
        <div class="cartao"><div class="valor" id="cmp-r-sefaz">-</div>
          <div class="rotulo">Notas na SEFAZ</div></div>
        <div class="cartao"><div class="valor" id="cmp-r-sped">-</div>
          <div class="rotulo">Escrituradas (SPED)</div></div>
        <div class="cartao verde"><div class="valor" id="cmp-r-conciliadas">-</div>
          <div class="rotulo">Conciliadas</div></div>
        <div class="cartao vermelho"><div class="valor" id="cmp-r-faltantes">-</div>
          <div class="rotulo">FALTANTES no SPED</div></div>
        <div class="cartao ambar"><div class="valor" id="cmp-r-canceladas">-</div>
          <div class="rotulo">Canceladas escrit.</div></div>
        <div class="cartao ambar"><div class="valor" id="cmp-r-divergencias">-</div>
          <div class="rotulo">Diverg. de valor</div></div>
      </div>
      <p id="cmp-diagnostico" class="status"></p>
    </div>

    <div class="caixa">
      <h2 id="cmp-t-faltantes">Faltantes no SPED</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Serie</th>
          <th>CNPJ emitente</th><th>Emitente</th><th>Data</th>
          <th>Valor (SEFAZ)</th><th>Situacao</th>
        </tr></thead><tbody id="cmp-b-faltantes"></tbody>
      </table></div>
    </div>

    <div class="caixa">
      <h2 id="cmp-t-canceladas">Canceladas escrituradas</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Emitente</th>
          <th>Situacao na SEFAZ</th>
        </tr></thead><tbody id="cmp-b-canceladas"></tbody>
      </table></div>
    </div>

    <div class="caixa">
      <h2 id="cmp-t-divergencias">Divergencias de valor</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Emitente</th>
          <th>Valor SEFAZ</th><th>Valor SPED</th><th>Diferenca</th>
        </tr></thead><tbody id="cmp-b-divergencias"></tbody>
      </table></div>
    </div>

    <div class="caixa">
      <h2 id="cmp-t-apenas">Apenas no SPED</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Serie</th>
          <th>Fornecedor</th><th>Data</th><th>Valor (SPED)</th>
        </tr></thead><tbody id="cmp-b-apenas"></tbody>
      </table></div>
    </div>`;

  const estado = { sessaoId: null };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("cmp-status").textContent = texto; };

  seNaoPuder($("cmp-exportar"), "comparador.exportar");

  function preencher(tbodyId, linhas, celulas) {
    const corpo = $(tbodyId);
    corpo.innerHTML = "";
    for (const linha of linhas) {
      const tr = document.createElement("tr");
      for (const valor of celulas(linha)) {
        const td = document.createElement("td");
        td.textContent = valor;
        tr.appendChild(td);
      }
      corpo.appendChild(tr);
    }
  }

  function render(r) {
    const resumo = r.resumo;
    $("cmp-r-sefaz").textContent = resumo.notas_na_sefaz;
    $("cmp-r-sped").textContent = resumo.notas_no_sped;
    $("cmp-r-conciliadas").textContent = resumo.conciliadas;
    $("cmp-r-faltantes").textContent = resumo.faltantes_no_sped;
    $("cmp-r-canceladas").textContent = resumo.canceladas_escrituradas;
    $("cmp-r-divergencias").textContent = resumo.divergencias_valor;

    $("cmp-t-faltantes").textContent =
      `Faltantes no SPED (${resumo.faltantes_no_sped})`;
    $("cmp-t-canceladas").textContent =
      `Canceladas escrituradas (${resumo.canceladas_escrituradas})`;
    $("cmp-t-divergencias").textContent =
      `Divergencias de valor (${resumo.divergencias_valor})`;
    $("cmp-t-apenas").textContent =
      `Apenas no SPED (${resumo.apenas_no_sped})`;

    preencher("cmp-b-faltantes", r.faltantes, (f) =>
      [f.chave, f.numero, f.serie, f.cnpj_emitente, f.emitente,
       f.data, f.valor, f.situacao]);
    preencher("cmp-b-canceladas", r.canceladas, (c) =>
      [c.chave, c.numero, c.emitente, c.situacao_sefaz]);
    preencher("cmp-b-divergencias", r.divergencias, (d) =>
      [d.chave, d.numero, d.emitente, d.valor_sefaz, d.valor_sped, d.diferenca]);
    preencher("cmp-b-apenas", r.apenas_no_sped, (n) =>
      [n.chave, n.numero, n.serie, n.fornecedor, n.data, n.valor]);

    const mapa = Object.entries(r.diagnostico.mapa_colunas || {})
      .map(([campo, coluna]) => `${campo}=${coluna}`).join(", ");
    $("cmp-diagnostico").textContent =
      `Leitura SEFAZ — colunas detectadas: ${mapa} | ` +
      `${r.diagnostico.registros_validos} nota(s) lida(s).`;
  }

  $("cmp-comparar").addEventListener("click", async () => {
    const sped = $("cmp-sped").files[0];
    const sefaz = $("cmp-sefaz").files[0];
    if (!sped) { toast("Selecione um arquivo SPED valido.", "erro"); return; }
    if (!sefaz) { toast("Selecione a relacao da SEFAZ.", "erro"); return; }
    const botao = $("cmp-comparar");
    botao.disabled = true;
    $("cmp-exportar").disabled = true;
    try {
      const { sessao_id } = await api("/api/sessoes",
                                      { json: { ferramenta: "comparador" } });
      estado.sessaoId = sessao_id;
      status(`Enviando ${sped.name}...`);
      await apiUpload(`/api/comparador/upload?sessao_id=${sessao_id}&tipo=sped`, sped);
      status(`Enviando ${sefaz.name}...`);
      await apiUpload(`/api/comparador/upload?sessao_id=${sessao_id}&tipo=sefaz`, sefaz);
      status("Comparando pela chave de acesso...");
      const { job_id } = await api("/api/comparador/comparar", { json: {
        sessao_id, apenas_entradas: $("cmp-entradas").checked } });
      const r = await esperarJob(job_id);
      render(r);
      $("cmp-exportar").disabled = false;
      status(`Comparacao concluida — ${r.empresa}.` +
             (r.filtro ? ` ${r.filtro}.` : ""));
      if (r.aviso) toast(r.aviso);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  $("cmp-exportar").addEventListener("click", async () => {
    if (!estado.sessaoId) { toast("Compare os arquivos antes.", "erro"); return; }
    const botao = $("cmp-exportar");
    botao.disabled = true;
    try {
      const nome = await apiDownload(
        `/api/comparador/exportar?sessao_id=${estado.sessaoId}`,
        { method: "POST" });
      toast(`Relatorio gerado: ${nome}`);
    } catch (erro) { toast(erro.message, "erro"); }
    finally { botao.disabled = false; }
  });
});
