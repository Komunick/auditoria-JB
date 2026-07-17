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
      <p id="prod-bases" class="status"></p>
      <p id="prod-status" class="status"></p>
    </div>

    <div class="caixa">
      <div class="cartoes" id="prod-indicadores"></div>
    </div>

    <div class="caixa">
      <div class="linha-form" id="prod-acoes">
        <button id="prod-corrigir-sel" disabled>Corrigir selecionados</button>
        <button id="prod-corrigir-alta" disabled>Corrigir alta confianca</button>
        <button id="prod-relatorio" disabled>Exportar relatorio (.xlsx)</button>
        <button id="prod-nova-base" disabled>Gerar nova base</button>
      </div>
      <div class="rolagem"><table id="prod-tabela">
        <thead><tr>
          <th class="col-sel"></th>
          <th>Codigo</th><th>Descricao</th><th>NCM</th><th>CEST</th>
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

  const estado = { sessaoId: null, itens: [], altaPendentes: 0 };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("prod-status").textContent = texto; };
  const botoes = ["prod-corrigir-sel", "prod-corrigir-alta",
                  "prod-relatorio", "prod-nova-base"];
  const habilitar = (sim) => botoes.forEach((id) => { $(id).disabled = !sim; });

  /* Acoes sem permissao nao sao desenhadas: o servidor barra com 403 e o
     clique so viraria erro. Importar/auditar e ler a tabela dependem so da
     aba, entao ficam. */
  const podeCorrigir = seNaoPuder($("prod-corrigir-sel"), "produtos.corrigir");
  seNaoPuder($("prod-corrigir-alta"), "produtos.corrigir");
  const podeRelatorio = seNaoPuder($("prod-relatorio"), "produtos.relatorio");
  const podeNovaBase = seNaoPuder($("prod-nova-base"), "produtos.nova_base");
  if (!podeCorrigir && !podeRelatorio && !podeNovaBase) {
    $("prod-acoes").classList.add("oculto");
  }
  /* A coluna de selecao so alimenta "Corrigir selecionados": sem a permissao
     ela vira caixa que marca e nao faz nada. Mesmo tratamento da coluna
     "Conf." do Livro de Conferencia. */
  const classeSel = podeCorrigir ? "col-sel" : "col-sel oculto";
  if (!podeCorrigir) {
    $("prod-tabela").querySelector("th.col-sel").classList.add("oculto");
  }

  /* O core JA arredonda o percentual (round(x, 1) em calcular_indicadores);
     aqui so se RENDERIZA. O desktop imprime o float do Python — str(50.0) e
     "50.0" -> "50,0%". Em JS o JSON.parse descarta o ".0" e String(50.0)
     devolve "50" ("50%"), divergindo do desktop em TODO percentual inteiro
     (0%, 30%, 50%, 100%). toFixed(1) apenas reimprime a casa decimal que o
     core ja fixou; nao arredonda nada por conta propria. */
  const textoPercentual = (valor) => {
    const numero = Number(valor);
    if (!Number.isFinite(numero)) return String(valor);
    return numero.toFixed(1).replace(".", ",") + "%";
  };

  function renderIndicadores(ind) {
    const caixa = $("prod-indicadores");
    caixa.innerHTML = "";
    for (const [chave, rotulo, cor] of INDICADORES) {
      let valor = ind ? ind[chave] : "-";
      if (chave === "percentual_inconsistencias" && ind) {
        valor = textoPercentual(valor);
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

  /* Como no desktop, a pasta das bases legais aparece ANTES de auditar: sem
     ela as validacoes legais ficam limitadas, e isso muda o que o usuario
     espera do resultado. Falhar aqui nao pode travar a aba. */
  (async () => {
    const alvo = $("prod-bases");
    try {
      const { pasta } = await api("/api/produtos/bases-legais");
      alvo.className = pasta ? "status" : "aviso";
      alvo.textContent = pasta
        ? `Bases legais em uso: ${pasta}`
        : "Pasta dados/ nao encontrada - as validacoes legais (Anexo I, " +
          "TIPI) ficarao limitadas.";
    } catch (erro) { alvo.textContent = ""; }
  })();

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
    estado.altaPendentes = dados.alta_confianca_pendentes;
    renderIndicadores(dados.indicadores);
    renderTabela(dados);
  }

  /* O desktop pinta o fundo da LINHA inteira por situacao (rosa/amarelo),
     nao so a celula "Situacao". */
  function classeSituacao(situacao) {
    if (situacao === "INCONSISTENTE") return "inconsistente";
    if (situacao === "ALERTA") return "alerta";
    return "";
  }

  /* Todo valor de p.* vem da planilha do cliente (incluindo texto livre) e cai
     em innerHTML: passa por esc() para nao virar XSS armazenado. classeSel e a
     classe "corrigido" sao calculadas aqui, nao vem do servidor. */
  function renderTabela(dados) {
    const corpo = $("prod-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    for (const p of dados.itens) {
      const tr = document.createElement("tr");
      tr.dataset.indice = p.indice;
      tr.className = classeSituacao(p.situacao);
      const marcavel = p.tem_correcao && p.status !== "Corrigido";
      tr.innerHTML = `
        <td class="${classeSel}">${marcavel ? '<input type="checkbox">' : ""}</td>
        <td>${esc(p.codigo)}</td><td>${esc(p.descricao)}</td><td>${esc(p.ncm)}</td>
        <td>${esc(p.cest)}</td><td>${esc(p.cfop)}</td><td>${esc(p.cst)}</td>
        <td>${esc(p.aliquota)}</td><td>${esc(p.trib_atual)}</td><td>${esc(p.trib_sugerida)}</td>
        <td>${esc(p.confianca)}</td>
        <td>${esc(p.situacao)}</td>
        <td>${esc(p.inconsistencias)}</td>
        <td>${esc(p.correcao)}</td>
        <td class="${p.status === "Corrigido" ? "corrigido" : ""}">${esc(p.status)}</td>`;
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

  /* Como no desktop: apura os candidatos ANTES de perguntar, para avisar de
     graca quando nao ha nada pendente e mostrar o N real na confirmacao. A
     contagem vem da rota de resultados, apurada pela mesma funcao do core
     que a correcao usa. */
  $("prod-corrigir-alta").addEventListener("click", async () => {
    const pendentes = estado.altaPendentes;
    if (!pendentes) {
      toast("Nenhuma correcao de alta confianca pendente.", "erro");
      return;
    }
    await corrigir({ alta_confianca: true },
      `Aplicar correcoes sugeridas em ${pendentes} produto(s)?`);
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
