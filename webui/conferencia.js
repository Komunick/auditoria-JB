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
        <label><span id="conf-arquivos-lbl">Pasta com os XMLs (selecione a
          pasta inteira)</span>
          <input id="conf-arquivos" type="file" multiple webkitdirectory
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
          <th class="col-conf">Conf.</th><th>Numero</th><th>Serie</th><th>Data</th>
          <th>Fornecedor</th><th>CNPJ</th><th>UF</th><th>Valor contabil</th>
          <th>Base ICMS</th><th>Valor ICMS</th><th>CFOP</th><th>CST</th>
          <th>Aliquota</th><th>Observacao</th><th>Data conf.</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <p id="conf-progresso" class="status"></p>
    </div>

    <div class="caixa">
      <h2>Composicao fiscal da nota selecionada (CFOP → CST → Aliquota)
          <span id="conf-comp-dica">— duplo clique em qualquer celula edita</span></h2>
      <div class="rolagem" style="max-height:32vh"><table id="conf-comp">
        <thead><tr>
          <th>CFOP</th><th>CST</th><th>Aliquota</th><th>Valor contabil</th>
          <th>Base ICMS</th><th>Valor ICMS</th><th>ICMS-ST</th><th>Itens</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <p id="conf-alertas" class="status"></p>
    </div>`;

  const estado = { sessaoId: null, notas: [], chave: null, fonte: "",
                   apenasEntradas: true, rotulos: {} };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("conf-status").textContent = texto; };

  // ------------------------------------------------------------------
  // Permissoes deste usuario. Ler as notas e ver a composicao nao exigem
  // permissao propria: so a gravacao e a geracao de documento e que somem.

  const podeConferir = Sessao.pode("conferencia.conferir");
  const podeEditarComposicao = Sessao.pode("conferencia.composicao_editar");
  const classeConf = podeConferir ? "col-conf" : "col-conf oculto";
  const classeObs = podeConferir ? "editavel obs" : "obs";

  seNaoPuder($("conf-corrigir"), "conferencia.corrigir");
  seNaoPuder($("conf-danfe"), "conferencia.danfe");
  seNaoPuder($("conf-livro"), "conferencia.livro_fiscal");
  seNaoPuder($("conf-inconsistencias"), "conferencia.inconsistencias");
  seNaoPuder($("conf-sped"), "conferencia.sped_corrigido");
  // A dica do titulo ensina um duplo clique que nao vai responder.
  seNaoPuder($("conf-comp-dica"), "conferencia.composicao_editar");
  if (!podeConferir) {
    $("conf-tabela").querySelector("th.col-conf").classList.add("oculto");
  }

  // ------------------------------------------------------------------
  // Modo de selecao: fonte "Pasta de XMLs" abre um seletor de PASTA inteira
  // (webkitdirectory, como o "Procurar pasta" do desktop); "SPED" abre o
  // seletor de arquivo. O input e recriado ao trocar de fonte para alternar o
  // modo com seguranca entre navegadores.

  function extRelevante(nome, ehXml) {
    const n = nome.toLowerCase();
    return ehXml ? (n.endsWith(".xml") || n.endsWith(".zip"))
                 : (n.endsWith(".txt") || n.endsWith(".zip"));
  }

  function aplicarModoFonte() {
    const ehXml = $("conf-fonte").value === "xml";
    const antigo = $("conf-arquivos");
    const novo = document.createElement("input");
    novo.type = "file";
    novo.id = "conf-arquivos";
    novo.multiple = true;
    if (ehXml) {
      novo.webkitdirectory = true;
      novo.setAttribute("webkitdirectory", "");
    } else {
      novo.accept = ".txt,.zip";
    }
    novo.addEventListener("change", () => {
      const n = [...novo.files].filter((f) => extRelevante(f.name, ehXml)).length;
      status(n ? `${n} arquivo(s) selecionado(s). Clique em "Enviar e carregar".`
               : "Nenhum XML/SPED encontrado na selecao.");
    });
    antigo.replaceWith(novo);
    $("conf-arquivos-lbl").textContent = ehXml
      ? "Pasta com os XMLs de NF-e/CT-e (selecione a pasta inteira)"
      : "Arquivo SPED (.txt) ou .zip";
  }

  $("conf-fonte").addEventListener("change", aplicarModoFonte);
  aplicarModoFonte();

  // ------------------------------------------------------------------
  // Carga

  async function enviarArquivos(arquivos) {
    for (const [i, arquivo] of arquivos.entries()) {
      status(`Enviando ${i + 1}/${arquivos.length}: ${arquivo.name}...`);
      await apiUpload(
        `/api/conferencia/upload?sessao_id=${estado.sessaoId}`, arquivo);
    }
  }

  /* Recarrega a sessao com os MESMOS parametros da carga anterior: e assim
     que a rota de carga vincula os XMLs novos pela chave de acesso. */
  async function recarregar(fonte, apenasEntradas) {
    status("Carregando notas...");
    const { job_id } = await api("/api/conferencia/carregar", { json: {
      sessao_id: estado.sessaoId, fonte, apenas_entradas: apenasEntradas } });
    const resultado = await esperarJob(job_id);
    await atualizarNotas();
    return resultado;
  }

  /* Seletor de arquivos avulso (o desktop abre um QFileDialog de pasta; no
     navegador o equivalente e o upload). */
  function escolherArquivos(aceita) {
    return new Promise((resolver) => {
      const entrada = document.createElement("input");
      entrada.type = "file";
      entrada.multiple = true;
      entrada.accept = aceita;
      entrada.addEventListener("change", () => resolver([...entrada.files]));
      // Cancelar o seletor nao dispara "change": sem isto a promessa ficaria
      // pendente para sempre.
      entrada.addEventListener("cancel", () => resolver([]));
      entrada.click();
    });
  }

  $("conf-carregar").addEventListener("click", async () => {
    const ehXml = $("conf-fonte").value === "xml";
    // Filtra o que interessa: numa pasta selecionada, ignora arquivos que nao
    // sejam XML/SPED (ex.: .exe, planilhas) para nao subir lixo.
    const arquivos = [...$("conf-arquivos").files]
      .filter((f) => extRelevante(f.name, ehXml));
    if (!arquivos.length) {
      toast(ehXml ? "Selecione a pasta com os XMLs." : "Selecione o SPED (.txt).",
            "erro");
      return;
    }
    const botao = $("conf-carregar");
    botao.disabled = true;
    try {
      const { sessao_id } = await api("/api/sessoes", { json: { ferramenta: "conferencia" } });
      estado.sessaoId = sessao_id;
      await enviarArquivos(arquivos);
      const resultado = await recarregar($("conf-fonte").value,
                                         $("conf-entradas").checked);
      status(`${resultado.total} nota(s) carregada(s) — ${resultado.contexto}.`);
    } catch (erro) {
      status(""); toast(erro.message, "erro");
    } finally { botao.disabled = false; }
  });

  async function atualizarNotas() {
    if (!estado.sessaoId) return;
    const dados = await api(`/api/conferencia/notas?sessao_id=${estado.sessaoId}`);
    estado.notas = dados.itens;
    estado.fonte = dados.fonte;
    estado.apenasEntradas = dados.apenas_entradas;
    estado.rotulos = dados.rotulos_campos || {};
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
      // esc() em todo dado da nota (XML/planilha/observacao digitada): vira
      // innerHTML, entao <img onerror=...> na observacao rodaria script.
      tr.innerHTML = `
        <td class="${classeConf}"><input type="checkbox" ${n.conferida ? "checked" : ""}></td>
        <td>${esc(n.numero)}</td><td>${esc(n.serie)}</td><td>${esc(n.data)}</td>
        <td>${esc(n.fornecedor)}</td><td>${esc(n.cnpj)}</td><td>${esc(n.uf)}</td>
        <td>${esc(n.valor_contabil)}</td>
        <td>${esc(n.base_icms)}</td><td>${esc(n.valor_icms)}</td>
        <td data-campo="cfop">${esc(n.cfop)}</td>
        <td data-campo="cst_icms">${esc(n.cst)}</td>
        <td data-campo="aliq_icms">${esc(n.aliquota)}</td>
        <td class="${classeObs}">${esc(n.observacao)}</td>
        <td>${esc(n.data_conferencia)}</td>`;
      // Destaque POR CAMPO corrigido, como no desktop: so a coluna que mudou
      // fica dourada, e o tooltip conta de qual valor ela veio. Via DOM
      // porque o valor original vai num atributo (title).
      for (const [campo, original] of Object.entries(n.corrigido_de || {})) {
        const td = tr.querySelector(`td[data-campo="${campo}"]`);
        if (!td) continue;
        td.classList.add("corrigido");
        td.title = `${estado.rotulos[campo] || campo} corrigido — ` +
          `valor original: ${original}`;
      }
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
  if (podeConferir) {
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
  }

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
        if (celula.edicao && podeEditarComposicao) {
          td.classList.add("editavel"); td.dataset.edicao = celula.edicao;
        }
        if (celula.original) td.dataset.original = celula.original;
        if (celula.corrigido_de) {
          td.classList.add("corrigido");
          td.title = `Corrigido — valor original: ${celula.corrigido_de}`;
        }
        if (celula.override) {
          td.classList.add("sobrescrito");
          // Quem nao edita a composicao continua LENDO de onde veio o valor,
          // mas nao e ensinado a apagar a celula — gesto que nao responde.
          td.title = `Editado manualmente — valor calculado: ${celula.override.calculado || "(vazio)"}` +
            ` (por ${celula.override.usuario} em ${celula.override.data}).` +
            (podeEditarComposicao ? ` Apague o texto para voltar ao calculado.` : "");
        }
        tr.appendChild(td);
      }
      corpo.appendChild(tr);
    }
    $("conf-alertas").textContent = comp.alertas.length
      ? "Alertas: " + comp.alertas.join(" | ") : "";
  }

  if (podeEditarComposicao) {
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
  }

  // ------------------------------------------------------------------
  // Correcao manual (dialogo) e documentos

  $("conf-corrigir").addEventListener("click", async () => {
    if (!estado.chave) { toast("Selecione uma nota na tabela.", "erro"); return; }
    let dados;
    try {
      dados = await api("/api/conferencia/valores-corrigiveis" +
        `?sessao_id=${estado.sessaoId}&chave=${estado.chave}`);
    } catch (erro) { toast(erro.message, "erro"); return; }
    // O desktop avisa ANTES de abrir o dialogo; a web so mostrava o 422 depois.
    if (!dados.tem_itens) {
      toast("Esta nota nao tem itens detalhados (sem C170/det) — nao ha " +
            "CFOP/CST/aliquota por item para corrigir.", "erro");
      return;
    }
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    fundo.innerHTML = `
      <div class="modal">
        <h3>Corrigir campo fiscal — NF ${esc(dados.numero)}</h3>
        <div class="linha-form" style="flex-direction:column;align-items:stretch">
          <label>Campo
            <select id="cor-campo">
              <option value="cfop">CFOP</option>
              <option value="cst_icms">CST</option>
              <option value="aliq_icms">Aliquota ICMS</option>
            </select></label>
          <label>Valor original <select id="cor-original"></select></label>
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
    // Quem so corrige uma nota nem enxerga a opcao de lote (o checkbox segue
    // desmarcado e a chamada vai com lote: false).
    seNaoPuder(fundo.querySelector("#cor-lote").closest("label"),
               "conferencia.corrigir_lote");

    // Valor original e ESCOLHIDO entre os que a nota realmente tem (como o
    // combo do desktop): nao ha como digitar um valor que nao existe.
    const campoSel = fundo.querySelector("#cor-campo");
    const origSel = fundo.querySelector("#cor-original");
    const preencherOriginais = () => {
      origSel.innerHTML = "";
      for (const valor of dados.valores[campoSel.value] || []) {
        const opcao = document.createElement("option");
        opcao.value = valor;
        opcao.textContent = valor;
        origSel.appendChild(opcao);
      }
    };
    campoSel.addEventListener("change", preencherOriginais);
    preencherOriginais();

    fundo.querySelector(".cancelar").onclick = () => fundo.remove();
    fundo.querySelector(".confirmar").onclick = async () => {
      const campo = campoSel.value;
      const rotulo = campoSel.selectedOptions[0].textContent;
      const original = origSel.value;
      const novo = fundo.querySelector("#cor-novo").value;
      const lote = fundo.querySelector("#cor-lote").checked;
      const quantas = (dados.notas_por_valor[campo] || {})[original] || 0;
      const alvo = lote
        ? `TODAS as ${quantas} nota(s) carregadas com este valor`
        : `a NF ${dados.numero}`;
      const ok = await confirmar("Confirmar correcao",
        `Alterar ${rotulo} de ${original} para ${novo} em ${alvo}? ` +
        "O valor original sera preservado no historico de auditoria e a " +
        "correcao valera para a tela, o Livro Fiscal, o relatorio de " +
        "inconsistencias e o SPED corrigido.");
      if (!ok) return;
      try {
        const r = await api("/api/conferencia/corrigir", { json: {
          sessao_id: estado.sessaoId, chave: estado.chave, campo,
          original, novo, lote,
          motivo: fundo.querySelector("#cor-motivo").value } });
        fundo.remove();
        toast(r.mensagem);
        await atualizarNotas();
        await carregarComposicao();
      } catch (erro) { toast(erro.message, "erro"); }
    };
    document.body.appendChild(fundo);
  });

  /* Nota do SPED sem XML: em vez de so devolver o 422, oferece enviar os
     XMLs agora — a rota de carga e que vincula pela chave de acesso. */
  async function vincularXmls(nota) {
    const ok = await confirmar("DANFE precisa do XML",
      "O DANFE e gerado a partir do XML da NF-e, e esta nota (carregada do " +
      "SPED) ainda nao tem XML vinculado. Deseja enviar agora os XMLs " +
      "(.xml ou .zip)? Todas as notas serao vinculadas pela chave de acesso.");
    if (!ok) return false;
    const arquivos = await escolherArquivos(".xml,.zip");
    if (!arquivos.length) return false;
    try {
      await enviarArquivos(arquivos);
      status("Vinculando XMLs pela chave de acesso...");
      await recarregar(estado.fonte, estado.apenasEntradas);
    } catch (erro) { status(""); toast(erro.message, "erro"); return false; }
    const semXml = estado.notas.filter((n) => !n.tem_xml).length;
    status(`${estado.notas.length - semXml} nota(s) vinculadas ao XML` +
           (semXml ? ` (${semXml} ainda sem XML).` : "."));
    const atual = estado.notas.find((n) => n.chave === nota.chave);
    if (!atual || !atual.tem_xml) {
      toast("O XML desta nota nao veio no envio. Chave de acesso: " +
            nota.chave, "erro");
      return false;
    }
    return true;
  }

  $("conf-danfe").addEventListener("click", async () => {
    if (!estado.chave) { toast("Selecione uma nota na tabela.", "erro"); return; }
    const nota = estado.notas.find((n) => n.chave === estado.chave);
    if (nota && !nota.tem_xml && !(await vincularXmls(nota))) return;
    try {
      const resposta = await api(
        `/api/conferencia/danfe?sessao_id=${estado.sessaoId}&chave=${estado.chave}`);
      const blob = await resposta.blob();
      window.open(URL.createObjectURL(blob), "_blank");
    } catch (erro) { toast(erro.message, "erro"); }
  });

  /* Resumo do SPED corrigido antes do download: a rota de download devolve o
     arquivo, entao o que aconteceu (e o que NAO entrou) vem da pre-checagem. */
  function blocoLista(titulo, mensagens) {
    if (!mensagens.length) return null;
    const div = document.createElement("div");
    const h4 = document.createElement("h4");
    h4.className = "aviso";
    h4.textContent = titulo;
    div.appendChild(h4);
    const ul = document.createElement("ul");
    for (const msg of mensagens) {
      const li = document.createElement("li");
      li.textContent = msg;   // texto do SPED: nunca como HTML
      ul.appendChild(li);
    }
    div.appendChild(ul);
    return div;
  }

  function confirmarSped(resumo) {
    return new Promise((resolver) => {
      const fundo = document.createElement("div");
      fundo.className = "modal-fundo";
      fundo.innerHTML = `
        <div class="modal largo">
          <h3>Gerar SPED corrigido</h3>
          <p class="mensagem"></p>
          <div class="rolagem" style="max-height:40vh;padding:0 12px"></div>
          <div class="acoes">
            <button class="cancelar">Cancelar</button>
            <button class="confirmar botao-primario">Baixar</button>
          </div>
        </div>`;
      fundo.querySelector(".mensagem").textContent =
        `Itens C170 alterados: ${resumo.itens_c170_alterados} — ` +
        `registros C190 remontados: ${resumo.c190_mesclados} — ` +
        `notas alteradas: ${resumo.notas_alteradas}.`;
      const corpo = fundo.querySelector(".rolagem");
      const naoEntraram = blocoLista("Correcoes NAO levadas ao SPED:",
                                     resumo.ignoradas);
      const avisos = blocoLista("Avisos:", resumo.avisos);
      if (naoEntraram) corpo.appendChild(naoEntraram);
      if (avisos) corpo.appendChild(avisos);
      if (!naoEntraram && !avisos) {
        const p = document.createElement("p");
        p.textContent = "Todas as correcoes registradas entram no arquivo.";
        corpo.appendChild(p);
      }
      fundo.querySelector(".cancelar").onclick =
        () => { fundo.remove(); resolver(false); };
      fundo.querySelector(".confirmar").onclick =
        () => { fundo.remove(); resolver(true); };
      document.body.appendChild(fundo);
    });
  }

  const baixar = (botaoId, caminho, rotulo, antes) => {
    $(botaoId).addEventListener("click", async () => {
      if (!estado.sessaoId) { toast("Carregue as notas antes.", "erro"); return; }
      const botao = $(botaoId);
      botao.disabled = true;
      try {
        if (!antes || await antes()) {
          const nome = await apiDownload(
            `${caminho}?sessao_id=${estado.sessaoId}`, { method: "POST" });
          toast(`${rotulo} gerado: ${nome}`);
        }
      } catch (erro) { toast(erro.message, "erro"); }
      finally { botao.disabled = false; }
    });
  };
  baixar("conf-livro", "/api/conferencia/livro-fiscal", "Livro Fiscal");
  baixar("conf-inconsistencias", "/api/conferencia/inconsistencias", "Relatorio de Inconsistencias");
  baixar("conf-sped", "/api/conferencia/sped-corrigido", "SPED corrigido",
         async () => {
    const resumo = await api("/api/conferencia/sped-corrigido/resumo" +
                             `?sessao_id=${estado.sessaoId}`);
    if (!resumo.tem_correcoes) {
      toast("Nenhuma correcao registrada — o arquivo gerado seria identico " +
            "ao original.", "erro");
      return false;
    }
    return confirmarSped(resumo);
  });
});
