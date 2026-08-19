/* Aba 7 — Patrimônio (bens, responsabilidade e inventário).

   Mesma disciplina das outras abas: o que esta tela esconde é conveniência,
   nunca autorização — quem manda é o 403 do servidor. Todo conteúdo vindo do
   servidor entra por `textContent`, porque descrição de bem e nome de pessoa
   são texto digitado por gente. */

"use strict";

Abas.registrar("patrimonio", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Patrimônio</h2>
      <p class="dica">O que a empresa tem, <b>com quem está</b> e o que já
         aconteceu com cada item. A etiqueta é impressa e colada no
         equipamento — ela nunca muda. Bens não são excluídos: registra-se a
         <b>baixa</b>, que encerra o ciclo e preserva o histórico.</p>
      <p id="pat-status" class="status"></p>
    </div>

    <div class="cartoes" id="pat-cartoes"></div>

    <div class="caixa">
      <nav class="conc-subtelas" id="pat-subtelas">
        <button data-sub="bens" class="ativa" type="button">Bens</button>
        <button data-sub="pessoas" type="button">Pessoas e locais</button>
        <button data-sub="inventario" type="button">Inventário</button>
        <button data-sub="relatorios" type="button">Relatórios</button>
      </nav>

      <section id="pat-sub-bens" class="conc-sub">
        <div id="pat-novo" class="oculto">
          <div class="linha-form">
            <label>Descrição
              <input id="pat-b-descricao" type="text" placeholder="Notebook Dell Latitude">
            </label>
            <label>Tipo
              <select id="pat-b-tipo"></select>
            </label>
            <label>Conservação
              <select id="pat-b-conservacao"></select>
            </label>
            <label>Marca
              <input id="pat-b-marca" type="text">
            </label>
            <label>Nº de série
              <input id="pat-b-serie" type="text">
            </label>
            <label>Valor
              <input id="pat-b-valor" type="text" placeholder="0,00">
            </label>
            <label>Local
              <select id="pat-b-local"></select>
            </label>
            <button id="pat-cadastrar" class="botao-primario">Cadastrar bem</button>
          </div>
          <hr class="conc-divisor">
        </div>

        <div class="linha-form" id="pat-filtros">
          <label>Buscar
            <input id="pat-f-texto" type="search" placeholder="Descrição, etiqueta, série ou marca">
          </label>
          <label>Tipo
            <select id="pat-f-tipo"><option value="">Todos</option></select>
          </label>
          <label>Situação
            <select id="pat-f-situacao"><option value="">Todas</option></select>
          </label>
          <label>Responsável
            <select id="pat-f-pessoa"><option value="">Todos</option></select>
          </label>
          <label>Local
            <select id="pat-f-local"><option value="">Todos</option></select>
          </label>
          <label class="pat-checkbox">
            <span>Incluir baixados</span>
            <input id="pat-f-baixados" type="checkbox">
          </label>
          <button id="pat-limpar" type="button">Limpar</button>
        </div>

        <div class="rolagem"><table id="pat-lista">
          <thead><tr>
            <th>Etiqueta</th><th>Descrição</th><th>Tipo</th><th>Situação</th>
            <th>Responsável</th><th>Local</th><th class="conc-num">Valor</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
        <div class="conc-paginacao">
          <button id="pat-anterior" type="button">&#8249; Anterior</button>
          <span id="pat-pagina"></span>
          <button id="pat-proxima" type="button">Próxima &#8250;</button>
        </div>

        <div id="pat-detalhe" class="oculto"></div>
      </section>

      <section id="pat-sub-pessoas" class="conc-sub oculto">
        <div id="pat-cadastros" class="oculto">
          <div class="linha-form">
            <label>Nome do colaborador
              <input id="pat-p-nome" type="text">
            </label>
            <label>CPF (opcional)
              <input id="pat-p-cpf" type="text" maxlength="14">
            </label>
            <label>Setor
              <input id="pat-p-setor" type="text">
            </label>
            <button id="pat-nova-pessoa" class="botao-primario">Cadastrar pessoa</button>
          </div>
          <div class="linha-form">
            <label>Nome do local
              <input id="pat-l-nome" type="text" placeholder="Sala Fiscal">
            </label>
            <button id="pat-novo-local">Cadastrar local</button>
          </div>
          <hr class="conc-divisor">
        </div>
        <div class="rolagem"><table id="pat-pessoas">
          <thead><tr><th>Colaborador</th><th>Setor</th><th>Situação</th>
            <th>Bens sob responsabilidade</th></tr></thead>
          <tbody></tbody>
        </table></div>
        <h3 class="pat-titulo">Locais</h3>
        <div class="rolagem"><table id="pat-locais">
          <thead><tr><th>Local</th><th>Descrição</th><th>Bens</th></tr></thead>
          <tbody></tbody>
        </table></div>
      </section>

      <section id="pat-sub-inventario" class="conc-sub oculto">
        <p class="dica">O inventário congela a lista de bens no momento da
           abertura. Item cadastrado depois entra só na conferência seguinte —
           senão a taxa de localização mudaria sozinha no meio do trabalho.</p>
        <div class="linha-form" id="pat-inv-acoes"></div>
        <div id="pat-inv-resumo"></div>
      </section>

      <section id="pat-sub-relatorios" class="conc-sub oculto">
        <div id="pat-exportar-area" class="oculto">
          <p class="dica">A relação usa os <b>mesmos filtros</b> da aba Bens.
             O termo de responsabilidade sai do detalhe de cada bem que tenha
             responsável.</p>
          <div class="linha-form">
            <button id="pat-exportar" class="botao-primario">
              Exportar relação (.xlsx)</button>
            <span id="pat-exp-status" class="status"></span>
          </div>
        </div>
        <p id="pat-sem-exportar" class="dica oculto">Você não tem permissão
           para exportar. Fale com o administrador.</p>
      </section>
    </div>`;

  const estado = { pagina: 1, catalogo: null, pessoas: [], locais: [] };
  const $ = (id) => document.getElementById(id);
  const status = (t) => { $("pat-status").textContent = t; };

  const pode = {
    cadastrar: Sessao.pode("patrimonio.cadastrar"),
    movimentar: Sessao.pode("patrimonio.movimentar"),
    baixar: Sessao.pode("patrimonio.baixar"),
    inventariar: Sessao.pode("patrimonio.inventariar"),
    exportar: Sessao.pode("patrimonio.exportar"),
  };

  // ------------------------------------------------------------------
  // Subtelas

  function mostrarSub(nome) {
    $("pat-subtelas").querySelectorAll("button[data-sub]").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    ["bens", "pessoas", "inventario", "relatorios"].forEach((s) =>
      $(`pat-sub-${s}`).classList.toggle("oculto", s !== nome));
  }

  function abrirSub(nome) {
    mostrarSub(nome);
    if (nome === "bens") carregarLista();
    if (nome === "pessoas") carregarCadastros();
    if (nome === "inventario") carregarInventario();
  }

  $("pat-subtelas").addEventListener("click", (e) => {
    const botao = e.target.closest("button[data-sub]");
    if (botao) abrirSub(botao.dataset.sub);
  });

  // ------------------------------------------------------------------
  // Helpers de tabela

  function celula(texto, classe) {
    const td = document.createElement("td");
    td.textContent = texto ?? "";
    if (classe) td.className = classe;
    return td;
  }

  const moeda = (v) => (v ? v.texto : "—");

  function opcoes(select, itens, { vazio = "" } = {}) {
    select.textContent = "";
    if (vazio) {
      const o = document.createElement("option");
      o.value = ""; o.textContent = vazio;
      select.appendChild(o);
    }
    for (const item of itens) {
      const o = document.createElement("option");
      o.value = item.valor; o.textContent = item.rotulo;
      select.appendChild(o);
    }
  }

  function tabela(cabecalhos, linhas) {
    const wrap = document.createElement("div");
    wrap.className = "rolagem";
    const t = document.createElement("table");
    const thead = document.createElement("thead");
    const tr = document.createElement("tr");
    for (const c of cabecalhos) {
      const th = document.createElement("th");
      th.textContent = c;
      tr.appendChild(th);
    }
    thead.appendChild(tr);
    const tbody = document.createElement("tbody");
    for (const linha of linhas) {
      const l = document.createElement("tr");
      for (const v of linha) l.appendChild(v instanceof Node ? v : celula(v));
      tbody.appendChild(l);
    }
    t.append(thead, tbody);
    wrap.appendChild(t);
    return wrap;
  }

  // ------------------------------------------------------------------
  // Indicadores

  const INDICADORES = [
    { campo: "total", rotulo: "Bens ativos", cor: "" },
    { campo: "disponiveis", rotulo: "Disponíveis", cor: "verde" },
    { campo: "em_uso", rotulo: "Em uso", cor: "" },
    { campo: "emprestados", rotulo: "Em home office", cor: "" },
    { campo: "manutencao", rotulo: "Em manutenção", cor: "ambar" },
    { campo: "baixados", rotulo: "Baixados", cor: "" },
  ];

  function cartao(valor, rotulo, cor) {
    const caixa = document.createElement("div");
    caixa.className = cor ? `cartao ${cor}` : "cartao";
    const v = document.createElement("div");
    v.className = "valor"; v.textContent = valor;
    const r = document.createElement("div");
    r.className = "rotulo"; r.textContent = rotulo;
    caixa.append(v, r);
    return caixa;
  }

  async function atualizarResumo() {
    try {
      const resumo = await api("/api/patrimonio/resumo?" +
                               new URLSearchParams(filtrosAtuais()));
      const alvo = $("pat-cartoes");
      alvo.textContent = "";
      for (const ind of INDICADORES) {
        const n = resumo[ind.campo] ?? 0;
        alvo.appendChild(cartao(String(n), ind.rotulo, n ? ind.cor : ""));
      }
      alvo.appendChild(cartao(resumo.valor_total.texto,
                              "Valor de aquisição", ""));
    } catch (erro) { status(erro.message); }
  }

  // ------------------------------------------------------------------
  // Lista

  function filtrosAtuais() {
    const p = {};
    const texto = $("pat-f-texto").value.trim();
    if (texto) p.texto = texto;
    for (const [campo, chave] of [["tipo", "tipo"], ["situacao", "situacao"],
                                  ["pessoa", "pessoa_id"], ["local", "local_id"]]) {
      const v = $(`pat-f-${campo}`).value;
      if (v) p[chave] = v;
    }
    if ($("pat-f-baixados").checked) p.incluir_baixados = "true";
    return p;
  }

  async function carregarLista() {
    try {
      const pagina = await api("/api/patrimonio/bens?" + new URLSearchParams({
        ...filtrosAtuais(), pagina: estado.pagina }));
      const corpo = $("pat-lista").querySelector("tbody");
      corpo.textContent = "";
      for (const bem of pagina.itens) {
        const tr = document.createElement("tr");
        tr.className = "conc-clicavel";
        tr.append(
          celula(bem.etiqueta), celula(bem.descricao), celula(bem.tipo),
          celula(bem.situacao_rotulo,
                 bem.situacao === "baixado" ? "conc-erro"
                 : bem.situacao === "manutencao" ? "conc-alerta" : ""),
          celula(bem.responsavel_nome || "—"),
          celula(bem.local_nome || "—"),
          celula(moeda(bem.valor_aquisicao), "conc-num"));
        tr.addEventListener("click", () => abrirDetalhe(bem.id));
        corpo.appendChild(tr);
      }
      estado.pagina = pagina.pagina;
      $("pat-pagina").textContent = pagina.total
        ? `Página ${pagina.pagina} de ${pagina.paginas} — ${pagina.total} bem(ns)`
        : "Nenhum bem encontrado com esses filtros.";
      $("pat-anterior").disabled = pagina.pagina <= 1;
      $("pat-proxima").disabled = pagina.pagina >= pagina.paginas;
      await atualizarResumo();
    } catch (erro) { status(erro.message); }
  }

  let debounce = null;
  function recarregar() {
    estado.pagina = 1;
    clearTimeout(debounce);
    debounce = setTimeout(carregarLista, 250);
  }
  $("pat-f-texto").addEventListener("input", recarregar);
  for (const c of ["tipo", "situacao", "pessoa", "local", "baixados"]) {
    $(`pat-f-${c}`).addEventListener("change", recarregar);
  }
  $("pat-limpar").addEventListener("click", () => {
    for (const c of ["texto", "tipo", "situacao", "pessoa", "local"]) {
      $(`pat-f-${c}`).value = "";
    }
    $("pat-f-baixados").checked = false;
    recarregar();
  });
  $("pat-anterior").addEventListener("click", () => {
    estado.pagina = Math.max(1, estado.pagina - 1); carregarLista();
  });
  $("pat-proxima").addEventListener("click", () => {
    estado.pagina += 1; carregarLista();
  });

  // ------------------------------------------------------------------
  // Detalhe e movimentações

  function bloco(titulo) {
    const div = document.createElement("div");
    div.className = "caixa conc-bloco";
    const h = document.createElement("h3");
    h.textContent = titulo;
    div.appendChild(h);
    return div;
  }

  /* Toda movimentação leva `revision`: sem ela, duas pessoas mexendo no mesmo
     bem sobrescreveriam uma à outra em silêncio. */
  async function movimentar(bem, tipo, { pedirPessoa, pedirLocal,
                                         exigeJustificativa, pergunta }) {
    const corpo = { tipo, revision: bem.revision };
    if (pedirPessoa) {
      const nomes = estado.pessoas.filter((p) => p.ativo)
        .map((p, i) => `${i + 1}. ${p.nome}`).join("\n");
      const escolha = prompt(`${pergunta}\n\n${nomes}\n\nNúmero:`, "");
      if (escolha === null) return;
      const indice = parseInt(escolha, 10) - 1;
      const ativas = estado.pessoas.filter((p) => p.ativo);
      if (!(indice >= 0 && indice < ativas.length)) {
        toast("Escolha inválida.", "erro"); return;
      }
      corpo.pessoa_id = ativas[indice].id;
    }
    if (pedirLocal) {
      const nomes = estado.locais.map((l, i) => `${i + 1}. ${l.nome}`).join("\n");
      const escolha = prompt(`${pergunta}\n\n${nomes}\n\nNúmero:`, "");
      if (escolha === null) return;
      const indice = parseInt(escolha, 10) - 1;
      if (!(indice >= 0 && indice < estado.locais.length)) {
        toast("Escolha inválida.", "erro"); return;
      }
      corpo.local_id = estado.locais[indice].id;
    }
    const obs = prompt(exigeJustificativa
      ? "Justificativa (obrigatória — a baixa é definitiva):"
      : "Observação (opcional):", "");
    if (obs === null) return;
    if (exigeJustificativa && !obs.trim()) {
      toast("A justificativa é obrigatória.", "erro"); return;
    }
    corpo.observacao = obs.trim();
    try {
      await api(`/api/patrimonio/bens/${bem.id}/movimentar`, { json: corpo });
      toast("Movimentação registrada.");
      await carregarLista();
      await abrirDetalhe(bem.id);
    } catch (erro) {
      toast(erro.message, "erro");
      await abrirDetalhe(bem.id);
    }
  }

  async function abrirDetalhe(id) {
    const alvo = $("pat-detalhe");
    alvo.classList.remove("oculto");
    alvo.textContent = "Carregando...";
    let d;
    try { d = await api(`/api/patrimonio/bens/${id}`); }
    catch (erro) { alvo.textContent = erro.message; return; }
    alvo.textContent = "";

    const cabecalho = bloco(`${d.etiqueta} — ${d.descricao}`);
    const linha = document.createElement("p");
    linha.className = "dica";
    linha.textContent =
      `${d.tipo} · ${d.situacao_rotulo} · conservação ${d.conservacao_rotulo}` +
      (d.numero_serie ? ` · série ${d.numero_serie}` : "") +
      (d.local_nome ? ` · ${d.local_nome}` : "") +
      ` · valor ${moeda(d.valor_aquisicao)}`;
    cabecalho.appendChild(linha);

    const resp = document.createElement("p");
    resp.textContent = d.responsavel
      ? `Sob responsabilidade de ${d.responsavel.nome}` +
        (d.responsavel.setor ? ` (${d.responsavel.setor})` : "")
      : "Sem responsável no momento.";
    cabecalho.appendChild(resp);

    // Ações conforme a situação e a permissão.
    const acoes = document.createElement("div");
    acoes.className = "linha-form conc-acoes";
    const add = (rotulo, tipo, opcoesMov) => {
      const b = document.createElement("button");
      b.textContent = rotulo;
      b.addEventListener("click", () => movimentar(d, tipo, opcoesMov));
      acoes.appendChild(b);
    };
    if (d.situacao !== "baixado") {
      if (pode.movimentar) {
        if (d.situacao === "disponivel") {
          add("Atribuir", "atribuicao",
              { pedirPessoa: true, pergunta: "Atribuir a quem?" });
        }
        if (d.situacao === "em_uso") {
          add("Devolver", "devolucao", { pedirPessoa: true,
                                         pergunta: "Devolvido por quem?" });
          add("Emprestar (home office)", "emprestimo",
              { pedirPessoa: true, pergunta: "Empréstimo para quem?" });
        }
        if (d.situacao === "emprestado") {
          add("Retornar do empréstimo", "retorno_emprestimo",
              { pedirPessoa: true, pergunta: "Retorno de quem?" });
        }
        if (d.situacao === "manutencao") {
          add("Retornar da manutenção", "retorno_manutencao", {});
        } else {
          add("Enviar para manutenção", "manutencao", {});
        }
        add("Transferir de local", "transferencia",
            { pedirLocal: true, pergunta: "Transferir para qual local?" });
      }
      if (pode.baixar) {
        const b = document.createElement("button");
        b.textContent = "Dar baixa";
        b.className = "conc-erro";
        b.title = "Irreversível: o histórico fica, mas o bem não volta.";
        b.addEventListener("click", () => movimentar(d, "baixa",
          { exigeJustificativa: true }));
        acoes.appendChild(b);
      }
      if (pode.exportar && d.responsavel) {
        const b = document.createElement("button");
        b.textContent = "Termo de responsabilidade (PDF)";
        b.addEventListener("click", async () => {
          try { await apiDownload(`/api/patrimonio/bens/${d.id}/termo`,
                                  { method: "POST" }); }
          catch (erro) { toast(erro.message, "erro"); }
        });
        acoes.appendChild(b);
      }
    } else {
      const aviso = document.createElement("span");
      aviso.className = "conc-erro";
      aviso.textContent = "Bem baixado: o histórico permanece, mas não há " +
        "mais movimentação possível.";
      acoes.appendChild(aviso);
    }
    if (acoes.children.length) cabecalho.appendChild(acoes);
    alvo.appendChild(cabecalho);

    if (d.perifericos.length) {
      const p = bloco("Periféricos vinculados");
      p.appendChild(tabela(["Etiqueta", "Descrição", "Situação"],
        d.perifericos.map((x) => [x.etiqueta, x.descricao, x.situacao])));
      alvo.appendChild(p);
    }

    if (d.responsabilidades.length) {
      const h = bloco("Histórico de responsabilidade");
      h.appendChild(tabela(["Colaborador", "De", "Até", "Registrado por"],
        d.responsabilidades.map((r) => [
          r.pessoa_nome, r.iniciada_em.slice(0, 10),
          r.encerrada_em ? r.encerrada_em.slice(0, 10) : "— (atual)",
          r.registrada_por])));
      alvo.appendChild(h);
    }

    const trilha = bloco("Movimentações");
    trilha.appendChild(tabela(["Quando", "O que", "Pessoa", "Quem registrou",
                               "Observação"],
      d.movimentacoes.map((m) => [
        m.criada_em.slice(0, 16).replace("T", " "), m.tipo_rotulo,
        m.pessoa_nome || "—", m.usuario, m.observacao])));
    alvo.appendChild(trilha);
    alvo.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------
  // Cadastros

  async function carregarCadastros() {
    try {
      const [pessoas, locais] = await Promise.all([
        api("/api/patrimonio/pessoas"), api("/api/patrimonio/locais")]);
      estado.pessoas = pessoas.itens;
      estado.locais = locais.itens;

      const corpoP = $("pat-pessoas").querySelector("tbody");
      corpoP.textContent = "";
      for (const p of pessoas.itens) {
        const tr = document.createElement("tr");
        tr.append(celula(p.nome), celula(p.setor || "—"),
                  celula(p.ativo ? "Ativo" : "Desligado",
                         p.ativo ? "" : "conc-alerta"),
                  celula(String(p.bens_ativos),
                         !p.ativo && p.bens_ativos ? "conc-erro" : ""));
        corpoP.appendChild(tr);
      }
      const corpoL = $("pat-locais").querySelector("tbody");
      corpoL.textContent = "";
      for (const l of locais.itens) {
        const tr = document.createElement("tr");
        tr.append(celula(l.nome), celula(l.descricao || "—"),
                  celula(String(l.bens)));
        corpoL.appendChild(tr);
      }

      opcoes($("pat-f-pessoa"),
             pessoas.itens.map((p) => ({ valor: p.id, rotulo: p.nome })),
             { vazio: "Todos" });
      for (const alvo of [$("pat-f-local"), $("pat-b-local")]) {
        opcoes(alvo, locais.itens.map((l) => ({ valor: l.id, rotulo: l.nome })),
               { vazio: alvo.id === "pat-b-local" ? "Sem local" : "Todos" });
      }
    } catch (erro) { status(erro.message); }
  }

  function montarCadastros() {
    if (!pode.cadastrar) return;
    $("pat-novo").classList.remove("oculto");
    $("pat-cadastros").classList.remove("oculto");

    $("pat-cadastrar").addEventListener("click", async () => {
      const corpo = {
        descricao: $("pat-b-descricao").value.trim(),
        tipo: $("pat-b-tipo").value,
        conservacao: $("pat-b-conservacao").value,
        marca: $("pat-b-marca").value.trim(),
        numero_serie: $("pat-b-serie").value.trim(),
        valor_aquisicao: $("pat-b-valor").value.trim(),
        local_id: $("pat-b-local").value ? Number($("pat-b-local").value) : null,
      };
      if (!corpo.descricao) { toast("Informe a descrição.", "erro"); return; }
      try {
        const criado = await api("/api/patrimonio/bens", { json: corpo });
        toast(`Cadastrado: ${criado.etiqueta}`);
        status(`Etiqueta ${criado.etiqueta} gerada — imprima e cole no bem.`);
        $("pat-b-descricao").value = "";
        $("pat-b-serie").value = "";
        $("pat-b-valor").value = "";
        await carregarLista();
      } catch (erro) { toast(erro.message, "erro"); }
    });

    $("pat-nova-pessoa").addEventListener("click", async () => {
      const nome = $("pat-p-nome").value.trim();
      if (!nome) { toast("Informe o nome.", "erro"); return; }
      try {
        await api("/api/patrimonio/pessoas", { json: {
          nome, cpf: $("pat-p-cpf").value.trim(),
          setor: $("pat-p-setor").value.trim() } });
        toast("Pessoa cadastrada.");
        $("pat-p-nome").value = ""; $("pat-p-cpf").value = "";
        await carregarCadastros();
      } catch (erro) { toast(erro.message, "erro"); }
    });

    $("pat-novo-local").addEventListener("click", async () => {
      const nome = $("pat-l-nome").value.trim();
      if (!nome) { toast("Informe o nome do local.", "erro"); return; }
      try {
        await api("/api/patrimonio/locais", { json: { nome } });
        toast("Local cadastrado.");
        $("pat-l-nome").value = "";
        await carregarCadastros();
      } catch (erro) { toast(erro.message, "erro"); }
    });
  }

  // ------------------------------------------------------------------
  // Inventário

  async function carregarInventario() {
    const acoes = $("pat-inv-acoes");
    const resumo = $("pat-inv-resumo");
    acoes.textContent = ""; resumo.textContent = "";
    let atual;
    try { atual = await api("/api/patrimonio/inventario"); }
    catch (erro) { status(erro.message); return; }

    if (!atual.aberto) {
      const p = document.createElement("p");
      p.className = "dica";
      p.textContent = "Nenhum inventário aberto.";
      resumo.appendChild(p);
      if (pode.inventariar) {
        const b = document.createElement("button");
        b.className = "botao-primario";
        b.textContent = "Abrir inventário";
        b.addEventListener("click", async () => {
          try {
            await api("/api/patrimonio/inventario", { json: { observacao: "" } });
            toast("Inventário aberto.");
            carregarInventario();
          } catch (erro) { toast(erro.message, "erro"); }
        });
        acoes.appendChild(b);
      }
      return;
    }

    const sessao = atual.aberto;
    const info = document.createElement("p");
    info.textContent =
      `Aberto em ${sessao.aberto_em.slice(0, 10)} por ${sessao.aberto_por_login}` +
      ` · ${sessao.total} bem(ns) na conferência.`;
    resumo.appendChild(info);
    const contagens = sessao.contagens || {};
    resumo.appendChild(tabela(["Resultado", "Quantidade"],
      Object.entries(contagens).map(([k, v]) => [k, String(v)])));

    if (pode.inventariar) {
      const b = document.createElement("button");
      b.textContent = "Fechar inventário";
      b.addEventListener("click", async () => {
        if (!confirm("Fechar o inventário? O resultado fica congelado.")) return;
        try {
          await api(`/api/patrimonio/inventario/${sessao.id}/fechar`,
                    { json: {} });
          toast("Inventário fechado.");
          carregarInventario();
        } catch (erro) { toast(erro.message, "erro"); }
      });
      acoes.appendChild(b);
    }
  }

  // ------------------------------------------------------------------
  // Relatórios

  if (pode.exportar) {
    $("pat-exportar-area").classList.remove("oculto");
    $("pat-exportar").addEventListener("click", async () => {
      $("pat-exp-status").textContent = "Gerando...";
      try {
        const nome = await apiDownload(
          "/api/patrimonio/exportar?" + new URLSearchParams(filtrosAtuais()),
          { method: "POST" });
        $("pat-exp-status").textContent = `Baixado: ${nome}`;
      } catch (erro) {
        $("pat-exp-status").textContent = erro.message;
        toast(erro.message, "erro");
      }
    });
  } else {
    $("pat-sem-exportar").classList.remove("oculto");
  }

  // ------------------------------------------------------------------
  // Arranque

  // O que depende SO de permissao e montado antes de qualquer await: se a
  // chamada do catalogo falhar (rede, servidor reiniciando), a aba nao pode
  // ficar aleijada — sem formulario de cadastro e sem botao de exportar.
  montarCadastros();

  (async () => {
    try {
      estado.catalogo = await api("/api/patrimonio/catalogo");
      opcoes($("pat-b-tipo"),
             estado.catalogo.tipos.map((t) => ({ valor: t, rotulo: t })));
      opcoes($("pat-f-tipo"),
             estado.catalogo.tipos.map((t) => ({ valor: t, rotulo: t })),
             { vazio: "Todos" });
      opcoes($("pat-b-conservacao"),
             estado.catalogo.conservacoes.map((c) => ({ valor: c.chave,
                                                        rotulo: c.rotulo })));
      opcoes($("pat-f-situacao"),
             estado.catalogo.situacoes.map((s) => ({ valor: s.chave,
                                                     rotulo: s.rotulo })),
             { vazio: "Todas" });
      await carregarCadastros();
      await carregarLista();
    } catch (erro) { status(erro.message); }
  })();

  container.patrimonio = { estado, pode, abrirSub, abrirDetalhe,
                           carregarLista };
});
