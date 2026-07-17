/* Aba 2 — Comparar versoes de SPED (SPED x SPED, paridade com o desktop). */

"use strict";

Abas.registrar("diff", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Arquivos SPED</h2>
      <div class="linha-form">
        <label>Arquivo A — contabilidade / corrigido (.txt)
          <input id="dif-a" type="file" accept=".txt"></label>
        <label>Arquivo B — cliente / sistema (.txt)
          <input id="dif-b" type="file" accept=".txt"></label>
        <label title="Marcado: somente as notas de entrada dos dois SPEDs entram na comparacao (IND_OPER = 0; sem IND_OPER, decide pelo CFOP dos itens). Desmarcado: comportamento padrao, todas as operacoes.">
          <input id="dif-entradas" type="checkbox">
          Considerar apenas documentos de entrada no SPED</label>
        <button id="dif-comparar" class="botao-primario">Comparar</button>
        <button id="dif-exportar" disabled>Exportar relatorio (.xlsx)</button>
      </div>
      <p id="dif-status" class="status">Selecione os dois SPEDs (ex.: contabilidade x cliente).</p>
    </div>

    <div class="caixa">
      <div class="cartoes">
        <div class="cartao"><div class="valor" id="dif-r-a">-</div>
          <div class="rotulo">Notas em A</div></div>
        <div class="cartao"><div class="valor" id="dif-r-b">-</div>
          <div class="rotulo">Notas em B</div></div>
        <div class="cartao verde"><div class="valor" id="dif-r-iguais">-</div>
          <div class="rotulo">Identicas</div></div>
        <div class="cartao vermelho"><div class="valor" id="dif-r-divergentes">-</div>
          <div class="rotulo">DIVERGENTES</div></div>
        <div class="cartao ambar"><div class="valor" id="dif-r-so-a">-</div>
          <div class="rotulo">So em A</div></div>
        <div class="cartao ambar"><div class="valor" id="dif-r-so-b">-</div>
          <div class="rotulo">So em B</div></div>
      </div>
    </div>

    <div class="caixa">
      <h2 id="dif-t-divergencias">Divergencias (campo a campo)</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Fornecedor</th>
          <th>Nivel</th><th>Item</th><th>Campo</th>
          <th>Valor A</th><th>Valor B</th>
        </tr></thead><tbody id="dif-b-divergencias"></tbody>
      </table></div>
      <p id="dif-previa" class="status"></p>
    </div>

    <div class="caixa">
      <h2 id="dif-t-so-a">So em A</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Serie</th>
          <th>Fornecedor</th><th>Valor</th>
        </tr></thead><tbody id="dif-b-so-a"></tbody>
      </table></div>
    </div>

    <div class="caixa">
      <h2 id="dif-t-so-b">So em B</h2>
      <div class="rolagem"><table>
        <thead><tr>
          <th>Chave de acesso</th><th>Numero</th><th>Serie</th>
          <th>Fornecedor</th><th>Valor</th>
        </tr></thead><tbody id="dif-b-so-b"></tbody>
      </table></div>
    </div>`;

  const estado = { sessaoId: null };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("dif-status").textContent = texto; };

  /* Comparar e ler a tabela vem junto com aba.diff; so a exportacao e
     recortada a parte. */
  const podeExportar = seNaoPuder($("dif-exportar"), "diff.exportar");

  /* Primeira coluna da divergencia em si (Campo, Valor A, Valor B): dali em
     diante o desktop pinta a celula de rosa. As colunas antes dela apenas
     identificam a nota, e ficam sem realce. */
  const COL_DIVERGENCIA = 5;

  function preencher(tbodyId, linhas, celulas, realceDe) {
    const corpo = $(tbodyId);
    corpo.innerHTML = "";
    for (const linha of linhas) {
      const tr = document.createElement("tr");
      celulas(linha).forEach((valor, col) => {
        const td = document.createElement("td");
        td.textContent = valor;
        if (realceDe !== undefined && col >= realceDe) {
          td.classList.add("divergente");
        }
        tr.appendChild(td);
      });
      corpo.appendChild(tr);
    }
  }

  function render(r) {
    const resumo = r.resumo;
    $("dif-r-a").textContent = resumo.total_a;
    $("dif-r-b").textContent = resumo.total_b;
    $("dif-r-iguais").textContent = resumo.iguais;
    $("dif-r-divergentes").textContent = resumo.divergentes;
    $("dif-r-so-a").textContent = resumo.apenas_em_a;
    $("dif-r-so-b").textContent = resumo.apenas_em_b;

    $("dif-t-divergencias").textContent =
      `Divergencias (${resumo.total_diferencas} campos)`;
    $("dif-t-so-a").textContent = `So em A (${resumo.apenas_em_a})`;
    $("dif-t-so-b").textContent = `So em B (${resumo.apenas_em_b})`;

    preencher("dif-b-divergencias", r.divergencias, (d) =>
      [d.chave, d.numero, d.fornecedor, d.nivel, d.item, d.campo,
       d.valor_a, d.valor_b], COL_DIVERGENCIA);
    preencher("dif-b-so-a", r.apenas_em_a, (n) =>
      [n.chave, n.numero, n.serie, n.fornecedor, n.valor]);
    preencher("dif-b-so-b", r.apenas_em_b, (n) =>
      [n.chave, n.numero, n.serie, n.fornecedor, n.valor]);

    /* Sem a permissao de exportar nao ha botao na tela: mandar o usuario
       usar a exportacao seria apontar para um controle que nao existe. */
    $("dif-previa").textContent =
      r.divergencias.length < resumo.total_diferencas
        ? `Exibindo ${r.divergencias.length} de ${resumo.total_diferencas} ` +
          "diferencas" +
          (podeExportar ? " (a exportacao inclui tudo)." : ".")
        : "";
  }

  $("dif-comparar").addEventListener("click", async () => {
    const arquivoA = $("dif-a").files[0];
    const arquivoB = $("dif-b").files[0];
    if (!arquivoA || !arquivoB) {
      toast("Selecione os dois arquivos SPED.", "erro"); return;
    }
    const botao = $("dif-comparar");
    botao.disabled = true;
    $("dif-exportar").disabled = true;
    try {
      const { sessao_id } = await api("/api/sessoes",
                                      { json: { ferramenta: "diff" } });
      estado.sessaoId = sessao_id;
      status(`Enviando ${arquivoA.name}...`);
      await apiUpload(`/api/diff/upload?sessao_id=${sessao_id}&lado=a`, arquivoA);
      status(`Enviando ${arquivoB.name}...`);
      await apiUpload(`/api/diff/upload?sessao_id=${sessao_id}&lado=b`, arquivoB);
      status("Comparando as duas versoes...");
      const { job_id } = await api("/api/diff/comparar", { json: {
        sessao_id, apenas_entradas: $("dif-entradas").checked } });
      const r = await esperarJob(job_id);
      render(r);
      $("dif-exportar").disabled = false;
      status(`Comparacao concluida: ${r.resumo.divergentes} nota(s) ` +
             `divergente(s), ${r.resumo.total_diferencas} campo(s) com ` +
             "diferenca." + (r.filtro ? ` ${r.filtro}.` : ""));
      if (r.aviso) toast(r.aviso);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  $("dif-exportar").addEventListener("click", async () => {
    if (!estado.sessaoId) { toast("Compare os arquivos antes.", "erro"); return; }
    const botao = $("dif-exportar");
    botao.disabled = true;
    try {
      const nome = await apiDownload(
        `/api/diff/exportar?sessao_id=${estado.sessaoId}`, { method: "POST" });
      toast(`Relatorio gerado: ${nome}`);
    } catch (erro) { toast(erro.message, "erro"); }
    finally { botao.disabled = false; }
  });
});
