/* Aba 6 — Conciliacao Fiscal (Receita e DIMP).

   Shell da ferramenta: indicadores do painel e a navegacao entre as subtelas
   Visao geral, Conciliacoes, Excecoes e Exportar. As subtelas nascem vazias e
   sao preenchidas pelas fases seguintes (importacao em T031, lista e detalhe
   em T036, decisoes em T042/T046, exportacoes em T052/T059, filtros em T061).

   Regra que vale para tudo que for acrescentado aqui: o que esta tela esconde
   e' conveniencia, nunca autorizacao — quem manda e' o 403 do servidor
   (constituicao, principio III). Todo conteudo vindo do servidor entra por
   `textContent`/`esc`, porque razao social e nome de arquivo sao texto de
   terceiro. */

"use strict";

Abas.registrar("conciliacao", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Conciliação Fiscal — Receita e DIMP</h2>
      <p class="dica">Importe os relatórios da Malha Fiscal da SEFAZ/BA
         (<b>Quadro 50-5</b> e <b>Quadro 50-3/DIMP</b>) e acompanhe a
         diferença entre a receita <b>declarada</b> e a <b>calculada</b>, os
         movimentos DIMP por instituição, as exceções e as versões
         conflitantes. Cada valor exibido pode ser rastreado até a célula do
         arquivo de origem.</p>
      <p id="conc-status" class="status"></p>
    </div>

    <div class="cartoes" id="conc-cartoes"></div>

    <div class="caixa">
      <nav class="conc-subtelas" id="conc-subtelas">
        <button data-sub="visao" class="ativa" type="button">Visão geral</button>
        <button data-sub="conciliacoes" type="button">Conciliações</button>
        <button data-sub="excecoes" type="button">Exceções</button>
        <button data-sub="exportar" type="button">Exportar</button>
      </nav>

      <section id="conc-sub-visao" class="conc-sub">
        <p class="dica">Os cartões acima refletem os <b>mesmos filtros</b> da
           aba Conciliações. Clique num atalho para ir direto ao que precisa
           de decisão.</p>
        <div class="linha-form" id="conc-atalhos">
          <button data-atalho="bloqueio" type="button">Com bloqueio</button>
          <button data-atalho="conflito" type="button">Com conflito</button>
          <button data-atalho="aviso" type="button">Com aviso</button>
          <button data-atalho="em_revisao" type="button">Em revisão</button>
          <button data-atalho="" type="button">Ver todas</button>
        </div>
        <p id="conc-visao-vazio" class="dica oculto">Nenhuma competência
           importada ainda. Use <b>Conciliações</b> para enviar os
           relatórios.</p>
      </section>
      <section id="conc-sub-conciliacoes" class="conc-sub oculto">
        <div id="conc-importar" class="oculto">
          <p class="dica">Selecione um ou vários relatórios <b>.xlsx</b> da
             SEFAZ/BA. O layout, o CNPJ e a competência saem do
             <b>conteúdo</b> do arquivo — o nome não decide nada. Arquivo
             repetido é reconhecido pelo conteúdo; arquivo diferente para uma
             competência que já existe entra como <b>versão candidata</b> e
             abre conflito, sem substituir a vigente.</p>
          <div class="linha-form">
            <label>Relatórios (.xlsx)
              <input id="conc-arquivos" type="file" multiple accept=".xlsx">
            </label>
            <button id="conc-processar" class="botao-primario" disabled>
              Enviar e processar</button>
          </div>
          <div class="rolagem"><table id="conc-fila">
            <thead><tr><th>Arquivo</th><th>Situação</th><th>Detalhe</th></tr></thead>
            <tbody></tbody>
          </table></div>
        </div>
        <p id="conc-sem-importar" class="dica oculto">Você não tem permissão
           para importar relatórios. Fale com o administrador.</p>

        <hr class="conc-divisor">

        <div class="linha-form" id="conc-filtros">
          <label>Empresa ou CNPJ
            <input id="conc-f-texto" type="search" placeholder="Razão social ou CNPJ">
          </label>
          <label>Competência de
            <input id="conc-f-de" type="text" placeholder="AAAAMM" maxlength="6">
          </label>
          <label>até
            <input id="conc-f-ate" type="text" placeholder="AAAAMM" maxlength="6">
          </label>
          <label>Estado
            <select id="conc-f-estado">
              <option value="">Todos</option>
              <option value="em_revisao">Em revisão</option>
              <option value="aprovada">Aprovada</option>
              <option value="rejeitada">Rejeitada</option>
            </select>
          </label>
          <label>Layout
            <select id="conc-f-layout">
              <option value="">Todos</option>
              <option value="quadro_50_5">Quadro 50-5</option>
              <option value="quadro_50_3_dimp">Quadro 50-3/DIMP</option>
            </select>
          </label>
          <label>Pendência
            <select id="conc-f-excecao">
              <option value="">Todas</option>
              <option value="aviso">Com aviso</option>
              <option value="bloqueio">Com bloqueio</option>
              <option value="conflito">Com conflito</option>
            </select>
          </label>
          <label>Ordem
            <select id="conc-f-ordenar">
              <option value="competencia_desc">Competência (mais recente)</option>
              <option value="competencia_asc">Competência (mais antiga)</option>
              <option value="empresa_asc">Empresa (A-Z)</option>
              <option value="diferenca_desc">Maior diferença</option>
            </select>
          </label>
          <button id="conc-limpar" type="button">Limpar filtros</button>
        </div>

        <div class="rolagem"><table id="conc-lista">
          <thead><tr>
            <th>Competência</th><th>Empresa</th><th>CNPJ</th><th>Layout</th>
            <th>Estado</th><th class="conc-num">Declarada</th>
            <th class="conc-num">Calculada</th><th class="conc-num">Diferença</th>
            <th>Pendências</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
        <div class="conc-paginacao">
          <button id="conc-anterior" type="button">&#8249; Anterior</button>
          <span id="conc-pagina"></span>
          <button id="conc-proxima" type="button">Próxima &#8250;</button>
        </div>

        <div id="conc-detalhe" class="oculto"></div>
      </section>
      <section id="conc-sub-excecoes" class="conc-sub oculto">
        <div class="linha-form">
          <label>Situação
            <select id="conc-e-estado">
              <option value="aberta">Abertas</option>
              <option value="resolvida">Resolvidas</option>
            </select>
          </label>
          <label>Severidade
            <select id="conc-e-severidade">
              <option value="">Todas</option>
              <option value="bloqueio">Bloqueio</option>
              <option value="aviso">Aviso</option>
            </select>
          </label>
        </div>
        <div class="rolagem"><table id="conc-excecoes">
          <thead><tr>
            <th>Competência</th><th>Empresa</th><th>Severidade</th>
            <th>Código</th><th>Mensagem</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
      </section>
      <section id="conc-sub-exportar" class="conc-sub oculto">
        <div id="conc-exp-consolidado" class="oculto">
          <h3>Consolidado auditável</h3>
          <p class="dica">Gera uma planilha com <b>conciliações, versões,
             movimentos DIMP, proveniência, exceções, conflitos, revisões e
             metadados</b>. Usa os <b>mesmos filtros</b> da aba Conciliações —
             ajuste-os lá antes de exportar. Conforme os filtros, o arquivo
             pode conter competências ainda não aprovadas; a coluna
             <i>Estado da revisão</i> diz quais.</p>
          <div class="linha-form">
            <button id="conc-exportar" class="botao-primario">
              Exportar consolidado (.xlsx)</button>
            <span id="conc-exp-status" class="status"></span>
          </div>
        </div>

        <div id="conc-exp-modelo" class="oculto">
          <hr class="conc-divisor">
          <h3>Preencher a planilha-mestre</h3>
          <p class="dica">Envie o <b>modelo</b> e receba uma <b>cópia</b>
             preenchida. O arquivo enviado nunca é alterado. Uma empresa por
             vez: só entram as competências <b>vigentes e aprovadas</b> deste
             CNPJ. Rejeitadas nunca entram, e competências com bloqueio ou
             conflito aberto também não.</p>
          <div class="linha-form">
            <label>CNPJ (obrigatório)
              <input id="conc-m-cnpj" type="text" placeholder="00.000.000/0000-00"
                     maxlength="18">
            </label>
            <label>Competência de
              <input id="conc-m-de" type="text" placeholder="AAAAMM" maxlength="6">
            </label>
            <label>até
              <input id="conc-m-ate" type="text" placeholder="AAAAMM" maxlength="6">
            </label>
            <label>Modelo (.xlsx)
              <input id="conc-m-arquivo" type="file" accept=".xlsx">
            </label>
            <label id="conc-m-pendentes-campo" class="oculto">
              <span>Incluir Em revisão</span>
              <input id="conc-m-pendentes" type="checkbox">
            </label>
            <button id="conc-preencher" class="botao-primario">
              Enviar e preencher</button>
          </div>
          <p id="conc-m-status" class="status"></p>
        </div>

        <p id="conc-sem-exportar" class="dica oculto">Você não tem permissão
           para exportar nem preencher o modelo. Fale com o administrador.</p>
      </section>
    </div>`;

  const estado = { sessaoId: null, sub: "visao", pagina: 1 };
  const $ = (id) => document.getElementById(id);
  const status = (texto) => { $("conc-status").textContent = texto; };

  /* Cada acao tem o seu proprio portao. Guardar aqui evita espalhar
     `Sessao.pode(...)` pelas subtelas quando elas forem escritas. */
  const pode = {
    importar: Sessao.pode("conciliacao.importar"),
    revisar: Sessao.pode("conciliacao.revisar"),
    aprovar: Sessao.pode("conciliacao.aprovar"),
    resolver: Sessao.pode("conciliacao.resolver_excecao"),
    exportar: Sessao.pode("conciliacao.exportar"),
    preencherModelo: Sessao.pode("conciliacao.preencher_modelo"),
    incluirPendentes: Sessao.pode("conciliacao.incluir_pendentes"),
  };

  // ------------------------------------------------------------------
  // Subtelas

  function mostrarSub(nome) {
    estado.sub = nome;
    $("conc-subtelas").querySelectorAll("button[data-sub]").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    ["visao", "conciliacoes", "excecoes", "exportar"].forEach((s) =>
      $(`conc-sub-${s}`).classList.toggle("oculto", s !== nome));
  }

  /* Trocar de subtela carrega o dado daquela subtela: nao adianta buscar
     lista e excecoes de uma vez se a pessoa esta olhando so uma. */
  function abrirSub(nome) {
    mostrarSub(nome);
    if (nome === "conciliacoes") carregarLista();
    if (nome === "excecoes") carregarExcecoes();
  }

  $("conc-subtelas").addEventListener("click", (e) => {
    const botao = e.target.closest("button[data-sub]");
    if (botao) abrirSub(botao.dataset.sub);
  });

  // ------------------------------------------------------------------
  // Indicadores do painel

  /* Reusa os cartoes-resumo (.cartoes/.cartao) das outras abas: mesma
     linguagem visual, tema claro/escuro e tela estreita ja resolvidos. */
  const INDICADORES = [
    { campo: "total", rotulo: "Competências", cor: "" },
    { campo: "em_revisao", rotulo: "Em revisão", cor: "ambar" },
    { campo: "aprovadas", rotulo: "Aprovadas", cor: "verde" },
    { campo: "rejeitadas", rotulo: "Rejeitadas", cor: "" },
    { campo: "avisos", rotulo: "Com avisos", cor: "ambar" },
    { campo: "bloqueios", rotulo: "Com bloqueios", cor: "vermelho" },
    { campo: "conflitos", rotulo: "Com conflitos", cor: "vermelho" },
  ];

  function cartao(valor, rotulo, cor) {
    const caixa = document.createElement("div");
    caixa.className = cor ? `cartao ${cor}` : "cartao";
    const v = document.createElement("div");
    v.className = "valor";
    v.textContent = valor;            // textContent: nada vindo do servidor
    const r = document.createElement("div");  // vira HTML por interpolacao
    r.className = "rotulo";
    r.textContent = rotulo;
    caixa.append(v, r);
    return caixa;
  }

  function renderIndicadores(resumo) {
    const alvo = $("conc-cartoes");
    alvo.textContent = "";
    for (const ind of INDICADORES) {
      const quantos = resumo[ind.campo] ?? 0;
      // Cor de alerta so quando ha o que alertar: zero bloqueio nao pinta a
      // tela de vermelho.
      alvo.appendChild(cartao(String(quantos), ind.rotulo,
                              quantos ? ind.cor : ""));
    }
    // Money: o servidor manda centavos exatos e o texto ja formatado. A tela
    // usa o texto; qualquer conta usa os centavos, nunca o texto reconvertido.
    const dif = resumo.diferenca_total;
    if (dif) {
      alvo.appendChild(cartao(dif.texto, "Diferença (calculado − declarado)",
                              dif.centavos ? "ambar" : ""));
    }
  }

  async function atualizarResumo() {
    try {
      renderIndicadores(await api("/api/conciliacao/resumo"));
    } catch (erro) {
      status(erro.message);
    }
  }

  // ------------------------------------------------------------------
  // Sessao de trabalho: criada sob demanda, so por quem pode importar.
  // Quem so consulta nao precisa de sessao nem de pasta em disco.

  async function garantirSessao() {
    if (estado.sessaoId) return estado.sessaoId;
    const { sessao_id } = await api("/api/sessoes",
                                    { json: { ferramenta: "conciliacao" } });
    estado.sessaoId = sessao_id;
    return sessao_id;
  }

  // ------------------------------------------------------------------
  // Importacao em lote

  const SITUACAO = {
    processado: { rotulo: "Processado", classe: "ok" },
    duplicado: { rotulo: "Duplicado", classe: "" },
    conflitante: { rotulo: "Conflito de versão", classe: "alerta" },
    rejeitado: { rotulo: "Rejeitado", classe: "erro" },
    enviando: { rotulo: "Enviando...", classe: "" },
    erro: { rotulo: "Falhou no envio", classe: "erro" },
  };

  /* Linha da fila. Nome de arquivo e mensagem vem de fora (o nome, do
     usuario; a mensagem, do servidor), entao vao por textContent — nunca por
     interpolacao em innerHTML. */
  function linhaFila(nome, situacao, detalhe) {
    const tr = document.createElement("tr");
    const tdNome = document.createElement("td");
    tdNome.textContent = nome;
    const tdSituacao = document.createElement("td");
    const marca = SITUACAO[situacao] || { rotulo: situacao, classe: "" };
    tdSituacao.textContent = marca.rotulo;
    if (marca.classe) tdSituacao.className = `conc-${marca.classe}`;
    const tdDetalhe = document.createElement("td");
    tdDetalhe.textContent = detalhe || "";
    tr.append(tdNome, tdSituacao, tdDetalhe);
    return tr;
  }

  function montarImportacao() {
    if (!pode.importar) {
      $("conc-sem-importar").classList.remove("oculto");
      return;
    }
    $("conc-importar").classList.remove("oculto");

    const entrada = $("conc-arquivos");
    const botao = $("conc-processar");
    const corpo = $("conc-fila").querySelector("tbody");

    const selecionados = () => [...(entrada.files || [])]
      .filter((f) => /\.xlsx$/i.test(f.name));

    entrada.addEventListener("change", () => {
      const arquivos = selecionados();
      botao.disabled = arquivos.length === 0;
      corpo.textContent = "";
      for (const arquivo of arquivos) {
        corpo.appendChild(linhaFila(arquivo.name, "enviando", "aguardando"));
      }
      status(arquivos.length
        ? `${arquivos.length} arquivo(s) selecionado(s).`
        : "Selecione ao menos um .xlsx.");
    });

    botao.addEventListener("click", async () => {
      const arquivos = selecionados();
      if (!arquivos.length) return;
      botao.disabled = true;
      try {
        const sessaoId = await garantirSessao();
        corpo.textContent = "";
        for (const [i, arquivo] of arquivos.entries()) {
          const linha = linhaFila(arquivo.name, "enviando", "");
          corpo.appendChild(linha);
          status(`Enviando ${i + 1} de ${arquivos.length}...`);
          try {
            await apiUpload(
              `/api/conciliacao/upload?sessao_id=${encodeURIComponent(sessaoId)}`,
              arquivo);
            linha.replaceWith(linhaFila(arquivo.name, "enviando", "na fila"));
          } catch (erro) {
            linha.replaceWith(linhaFila(arquivo.name, "erro", erro.message));
          }
        }

        status("Processando os relatórios...");
        const { job_id } = await api("/api/conciliacao/processar",
                                     { json: { sessao_id: sessaoId } });
        const resultado = await esperarJob(job_id, "conciliacao");

        // O resultado por arquivo vem da rota persistente: o job some no
        // reinicio, o lote nao.
        const lote = await api(`/api/conciliacao/lotes/${resultado.lote_id}`);
        corpo.textContent = "";
        for (const item of lote.itens) {
          corpo.appendChild(linhaFila(item.nome_recebido, item.resultado,
                                      item.mensagem));
        }
        status(`Lote concluído: ${lote.processados} processado(s), ` +
               `${lote.duplicados} duplicado(s), ` +
               `${lote.conflitantes} com conflito, ` +
               `${lote.rejeitados} rejeitado(s).`);
        // A sessao foi consumida pelo processamento; a proxima remessa abre
        // outra.
        estado.sessaoId = null;
        entrada.value = "";
        await atualizarResumo();
      } catch (erro) {
        toast(erro.message, "erro");
        status(erro.message);
      } finally {
        botao.disabled = selecionados().length === 0;
      }
    });
  }

  montarImportacao();

  // ------------------------------------------------------------------
  // Lista, filtros e paginacao

  const LAYOUTS = {
    quadro_50_5: "Quadro 50-5",
    quadro_50_3_dimp: "Quadro 50-3/DIMP",
  };
  const ESTADOS = {
    em_revisao: "Em revisão", aprovada: "Aprovada", rejeitada: "Rejeitada",
  };

  const F = ["texto", "de", "ate", "estado", "layout", "excecao"];

  /* Um unico lugar monta os filtros: indicadores e lista PRECISAM enxergar o
     mesmo universo. Contar 40 no topo e mostrar 12 na tabela e' o jeito mais
     rapido de alguem decidir sobre um numero que nao existe. */
  function filtrosAtuais() {
    const p = {};
    const texto = $("conc-f-texto").value.trim();
    if (texto) p.texto = texto;
    const de = $("conc-f-de").value.trim();
    if (de) p.competencia_de = de;
    const ate = $("conc-f-ate").value.trim();
    if (ate) p.competencia_ate = ate;
    for (const campo of ["estado", "layout", "excecao"]) {
      const valor = $(`conc-f-${campo}`).value;
      if (valor) p[campo] = valor;
    }
    return p;
  }

  function celula(texto, classe) {
    const td = document.createElement("td");
    td.textContent = texto ?? "";
    if (classe) td.className = classe;
    return td;
  }

  function moeda(valor) {
    // Money nulo NAO vira "R$ 0,00": no Quadro 50-5 a DIMP nao existe, e
    // mostrar zero afirmaria que a empresa nao teve movimento eletronico.
    return valor ? valor.texto : "—";
  }

  function pendencias(linha) {
    const partes = [];
    if (linha.bloqueios_abertos) partes.push(`${linha.bloqueios_abertos} bloqueio(s)`);
    if (linha.conflitos_abertos) partes.push(`${linha.conflitos_abertos} conflito(s)`);
    if (linha.avisos_abertos) partes.push(`${linha.avisos_abertos} aviso(s)`);
    return partes.join(", ") || "—";
  }

  async function carregarLista() {
    const filtros = filtrosAtuais();
    try {
      const [resumo, pagina] = await Promise.all([
        api("/api/conciliacao/resumo?" + new URLSearchParams(filtros)),
        api("/api/conciliacao/conciliacoes?" + new URLSearchParams({
          ...filtros, pagina: estado.pagina,
          ordenar: $("conc-f-ordenar").value,
        })),
      ]);
      renderIndicadores(resumo);
      const corpo = $("conc-lista").querySelector("tbody");
      corpo.textContent = "";
      for (const linha of pagina.itens) {
        const tr = document.createElement("tr");
        tr.className = "conc-clicavel";
        tr.append(
          celula(linha.competencia),
          celula(linha.razao_social || "—"),
          celula(linha.cnpj),
          celula(LAYOUTS[linha.versao.layout] || linha.versao.layout),
          celula(ESTADOS[linha.estado] || linha.estado),
          celula(moeda(linha.versao.receita_declarada), "conc-num"),
          celula(moeda(linha.versao.receita_calculada), "conc-num"),
          celula(moeda(linha.versao.diferenca_receita), "conc-num"),
          celula(pendencias(linha),
                 linha.bloqueios_abertos || linha.conflitos_abertos
                   ? "conc-erro" : ""));
        tr.addEventListener("click", () => abrirDetalhe(linha.id));
        corpo.appendChild(tr);
      }
      estado.pagina = pagina.pagina;
      $("conc-pagina").textContent = pagina.total
        ? `Página ${pagina.pagina} de ${pagina.paginas} — ${pagina.total} competência(s)`
        : "Nenhuma competência encontrada com esses filtros.";
      $("conc-anterior").disabled = pagina.pagina <= 1;
      $("conc-proxima").disabled = pagina.pagina >= pagina.paginas;
    } catch (erro) {
      status(erro.message);
    }
  }

  let debounce = null;
  function recarregar(zerarPagina = true) {
    if (zerarPagina) estado.pagina = 1;
    clearTimeout(debounce);
    debounce = setTimeout(carregarLista, 250);
  }

  $("conc-f-texto").addEventListener("input", () => recarregar());
  for (const campo of ["de", "ate", "estado", "layout", "excecao", "ordenar"]) {
    $(`conc-f-${campo}`).addEventListener("change", () => recarregar());
  }
  $("conc-limpar").addEventListener("click", () => {
    for (const campo of F) $(`conc-f-${campo}`).value = "";
    $("conc-f-ordenar").value = "competencia_desc";
    recarregar();
  });
  $("conc-anterior").addEventListener("click", () => {
    estado.pagina = Math.max(1, estado.pagina - 1);
    carregarLista();
  });
  $("conc-proxima").addEventListener("click", () => {
    estado.pagina += 1;
    carregarLista();
  });

  // ------------------------------------------------------------------
  // Detalhe: valores, DIMP e proveniencia

  const CAMPOS_COMPARAVEIS = [
    { chave: "receita_declarada", rotulo: "Receita declarada" },
    { chave: "declarada_com_st", rotulo: "Declarada com ST" },
    { chave: "declarada_sem_st", rotulo: "Declarada sem ST" },
    { chave: "receita_calculada", rotulo: "Receita calculada" },
    { chave: "calculada_com_st", rotulo: "Calculada com ST" },
    { chave: "calculada_sem_st", rotulo: "Calculada sem ST" },
    { chave: "diferenca_receita", rotulo: "Diferença de receita" },
    { chave: "total_pix", rotulo: "PIX" },
    { chave: "total_nao_pix", rotulo: "Não PIX" },
  ];

  /* Toda decisão passa por aqui: confirmação explícita, justificativa
     obrigatória e `revision` no corpo. O 409 de revisão desatualizada NÃO é
     erro do usuário — é outra pessoa tendo decidido antes; a tela recarrega o
     estado atual em vez de insistir. */
  async function decidir(detalhe, caminho, pergunta, montarCorpo) {
    const justificativa = prompt(
      `${pergunta}\n\nJustificativa (obrigatória):`, "");
    if (justificativa === null) return;
    if (!justificativa.trim()) {
      toast("A justificativa é obrigatória.", "erro");
      return;
    }
    try {
      await api(caminho, { json: montarCorpo(justificativa.trim()) });
      toast("Decisão registrada.");
      await Promise.all([atualizarResumo(), carregarLista()]);
      await abrirDetalhe(detalhe.id);
    } catch (erro) {
      toast(erro.message, "erro");
      // Estado mudou por baixo: recarrega para a pessoa decidir sobre o que
      // está valendo agora.
      await abrirDetalhe(detalhe.id);
    }
  }

  function bloco(titulo) {
    const div = document.createElement("div");
    div.className = "caixa conc-bloco";
    const h = document.createElement("h3");
    h.textContent = titulo;
    div.appendChild(h);
    return div;
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
      for (const valor of linha) {
        l.appendChild(valor instanceof Node ? valor : celula(valor));
      }
      tbody.appendChild(l);
    }
    t.append(thead, tbody);
    wrap.appendChild(t);
    return wrap;
  }

  async function abrirDetalhe(id) {
    const alvo = $("conc-detalhe");
    alvo.classList.remove("oculto");
    alvo.textContent = "Carregando...";
    let d;
    try {
      d = await api(`/api/conciliacao/conciliacoes/${id}`);
    } catch (erro) {
      alvo.textContent = erro.message;
      return;
    }
    alvo.textContent = "";
    const v = d.versao_vigente;

    const cabecalho = bloco(
      `${d.competencia} — ${d.razao_social || d.cnpj}`);
    const resumoLinha = document.createElement("p");
    resumoLinha.className = "dica";
    resumoLinha.textContent =
      `CNPJ ${d.cnpj} · ${ESTADOS[d.estado] || d.estado} · ` +
      `versão ${v.numero} (${LAYOUTS[v.layout] || v.layout}) · ` +
      `revisão ${d.revision}`;
    cabecalho.appendChild(resumoLinha);

    // Declarado x calculado, com a diferenca sempre calculado MENOS declarado.
    cabecalho.appendChild(tabela(
      ["", "Declarado", "Calculado", "Diferença"],
      [
        ["Total", moeda(v.receita_declarada), moeda(v.receita_calculada),
         moeda(v.diferenca_receita)],
        ["Com ST", moeda(v.declarada_com_st), moeda(v.calculada_com_st),
         moeda(v.diferenca_com_st)],
        ["Sem ST", moeda(v.declarada_sem_st), moeda(v.calculada_sem_st),
         moeda(v.diferenca_sem_st)],
      ]));
    alvo.appendChild(cabecalho);

    // DIMP: agregado por instituicao + linhas originais com a celula de origem.
    if (d.movimentos.length) {
      const dimp = bloco("Movimentos DIMP");
      const nota = document.createElement("p");
      nota.className = "dica";
      nota.textContent = `PIX ${moeda(v.total_pix)} · ` +
        `Cartão/outros — não PIX ${moeda(v.total_nao_pix)}. ` +
        "Não-PIX é o total DIMP menos o PIX: inclui voucher, transferência " +
        "e outras operações, não apenas cartão.";
      dimp.appendChild(nota);
      dimp.appendChild(tabela(
        ["Instituição", "Linhas somadas", "PIX", "Não PIX", "Total DIMP"],
        d.instituicoes.map((i) => [
          i.instituicao, String(i.linhas), moeda(i.pix),
          moeda(i.total_nao_pix), moeda(i.total_dimp)])));
      const detalhado = document.createElement("details");
      const sumario = document.createElement("summary");
      sumario.textContent = `Linhas originais do arquivo (${d.movimentos.length})`;
      detalhado.appendChild(sumario);
      detalhado.appendChild(tabela(
        ["Linha", "Instituição", "Débito", "Crédito", "Transf.", "PIX",
         "Voucher", "Outras", "Total", "Célula"],
        d.movimentos.map((m) => [
          String(m.linha_origem), m.instituicao, moeda(m.debito),
          moeda(m.credito), moeda(m.transferencia), moeda(m.pix),
          moeda(m.voucher), moeda(m.outras), moeda(m.total_dimp),
          `${m.proveniencia.aba}!${m.proveniencia.celulas.total_dimp}`])));
      dimp.appendChild(detalhado);
      alvo.appendChild(dimp);
    }

    // Proveniencia: de onde saiu cada numero.
    const origem = bloco("Proveniência");
    const fonte = document.createElement("p");
    fonte.className = "dica";
    fonte.textContent =
      `Arquivo: ${v.fonte.arquivo} · SHA-256 ${v.fonte.sha256.slice(0, 16)}… · ` +
      `aba ${v.aba_origem}, linha ${v.linha_resumo} · parser ${v.fonte.versao_parser}`;
    origem.appendChild(fonte);
    const baixar = document.createElement("button");
    baixar.textContent = "Baixar o arquivo original (.xlsx)";
    baixar.addEventListener("click", async () => {
      try {
        await apiDownload(`/api/conciliacao/fontes/${v.fonte.id}/download`);
      } catch (erro) { toast(erro.message, "erro"); }
    });
    origem.appendChild(baixar);
    origem.appendChild(tabela(
      ["Métrica", "Valor", "Origem", "Regra"],
      d.fatos.map((f) => [
        f.metrica, moeda(f.valor),
        f.tipo_origem === "celula"
          ? `${f.aba}!${f.celula}${f.rotulo ? ` (${f.rotulo})` : ""}`
          : `fórmula: ${f.formula}`,
        f.regra_parser])));
    alvo.appendChild(origem);

    if (d.excecoes.length) {
      const exc = bloco("Exceções");
      exc.appendChild(tabela(
        ["Severidade", "Código", "Mensagem", "Situação"],
        d.excecoes.map((e) => [
          e.severidade, e.codigo, e.mensagem, e.estado])));
      alvo.appendChild(exc);
    }

    if (d.versoes.length > 1) {
      const versoes = bloco("Versões desta competência");
      versoes.appendChild(tabela(
        ["Nº", "Situação", "Declarada", "Calculada", "Arquivo"],
        d.versoes.map((x) => [
          String(x.numero), x.estado, moeda(x.receita_declarada),
          moeda(x.receita_calculada), x.fonte ? x.fonte.arquivo : "—"])));
      alvo.appendChild(versoes);
    }

    // Ações de decisão. O que esta tela esconde é conveniência: quem manda é
    // o 403 do servidor. E `revision` viaja em toda decisão — sem ela, dois
    // revisores sobrescreveriam um ao outro em silêncio.
    const acoes = document.createElement("div");
    acoes.className = "linha-form conc-acoes";
    const impedido = d.bloqueios_abertos || d.conflitos_abertos;

    if (pode.aprovar) {
      const b = document.createElement("button");
      b.className = "botao-primario";
      b.textContent = "Aprovar competência";
      b.disabled = impedido || d.estado !== "em_revisao";
      b.title = impedido
        ? "Resolva os bloqueios e conflitos abertos antes de aprovar."
        : d.estado !== "em_revisao"
          ? "Só é possível aprovar a partir de Em revisão."
          : "";
      b.addEventListener("click", () => decidir(d,
        `/api/conciliacao/conciliacoes/${d.id}/aprovar`,
        "Aprovar esta competência?",
        (justificativa) => ({ justificativa, revision: d.revision })));
      acoes.appendChild(b);
    }
    if (pode.revisar) {
      for (const [rotulo, alvoEstado, pergunta] of [
        ["Rejeitar", "rejeitada", "Rejeitar esta competência?"],
        ["Devolver para revisão", "em_revisao",
         "Devolver esta competência para Em revisão?"],
      ]) {
        if (d.estado === alvoEstado) continue;
        const b = document.createElement("button");
        b.textContent = rotulo;
        b.addEventListener("click", () => decidir(d,
          `/api/conciliacao/conciliacoes/${d.id}/revisar`, pergunta,
          (justificativa) => ({ estado: alvoEstado, justificativa,
                                revision: d.revision })));
        acoes.appendChild(b);
      }
    }
    if (impedido) {
      const aviso = document.createElement("span");
      aviso.className = "conc-erro";
      aviso.textContent =
        `Aprovação bloqueada: ${d.bloqueios_abertos} bloqueio(s) e ` +
        `${d.conflitos_abertos} conflito(s) em aberto.`;
      acoes.appendChild(aviso);
    }
    if (acoes.children.length) {
      const caixaAcoes = bloco("Decisão");
      caixaAcoes.appendChild(acoes);
      alvo.appendChild(caixaAcoes);
    }

    // Exceções abertas: resolver exige justificativa.
    if (pode.resolver) {
      const abertas = d.excecoes.filter((e) => e.estado === "aberta");
      if (abertas.length) {
        const caixaExc = bloco("Resolver exceções");
        for (const e of abertas) {
          const linha = document.createElement("div");
          linha.className = "linha-form";
          const texto = document.createElement("span");
          texto.textContent = `[${e.severidade}] ${e.codigo}: ${e.mensagem}`;
          const b = document.createElement("button");
          b.textContent = "Resolver";
          b.addEventListener("click", () => decidir(d,
            `/api/conciliacao/excecoes/${e.id}/resolver`,
            `Resolver "${e.codigo}"?`,
            (resolucao) => ({ resolucao })));
          linha.append(texto, b);
          caixaExc.appendChild(linha);
        }
        alvo.appendChild(caixaExc);
      }
    }

    // Conflito aberto: comparação campo a campo e as duas decisões possíveis.
    const abertos = d.conflitos.filter((k) => k.estado === "aberto");
    if (abertos.length) {
      const caixaConf = bloco("Conflito de versão");
      const nota = document.createElement("p");
      nota.className = "dica";
      nota.textContent =
        "Chegou outro arquivo para esta mesma competência. A versão vigente " +
        "foi preservada e a nova entrou como candidata. Nenhuma competência " +
        "é aprovada enquanto o conflito estiver aberto.";
      caixaConf.appendChild(nota);
      for (const k of abertos) {
        const vigente = d.versoes.find((v) => v.id === k.versao_vigente_id);
        const candidata = d.versoes.find((v) => v.id === k.versao_candidata_id);
        caixaConf.appendChild(tabela(
          ["Campo", "Vigente (nº " + (vigente ? vigente.numero : "?") + ")",
           "Candidata (nº " + (candidata ? candidata.numero : "?") + ")"],
          CAMPOS_COMPARAVEIS
            .filter((c) => vigente && candidata &&
                    JSON.stringify(vigente[c.chave]) !== JSON.stringify(candidata[c.chave]))
            .map((c) => [c.rotulo, moeda(vigente[c.chave]),
                         moeda(candidata[c.chave])])));
        if (pode.resolver) {
          const linha = document.createElement("div");
          linha.className = "linha-form conc-acoes";
          for (const [rotulo, decisao, pergunta] of [
            ["Manter a vigente", "manter_vigente",
             "Manter a versão vigente e descartar a candidata?"],
            ["Promover a candidata", "promover_candidata",
             "Promover a candidata? A versão anterior fica preservada como " +
             "substituída e a competência volta para Em revisão."],
          ]) {
            const b = document.createElement("button");
            b.textContent = rotulo;
            b.addEventListener("click", () => decidir(d,
              `/api/conciliacao/conflitos/${k.id}/resolver`, pergunta,
              (justificativa) => ({ decisao, justificativa,
                                    revision: d.revision })));
            linha.appendChild(b);
          }
          caixaConf.appendChild(linha);
        }
      }
      alvo.appendChild(caixaConf);
    }

    if (d.revisoes.length) {
      const hist = bloco("Histórico de decisões");
      hist.appendChild(tabela(
        ["Quando", "Quem", "De", "Para", "Justificativa"],
        d.revisoes.map((r) => [
          r.criada_em, r.usuario, r.estado_anterior || "—", r.estado_novo,
          r.justificativa])));
      alvo.appendChild(hist);
    }
    alvo.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------
  // Fila de excecoes

  async function carregarExcecoes() {
    const params = new URLSearchParams({ estado: $("conc-e-estado").value });
    const sev = $("conc-e-severidade").value;
    if (sev) params.set("severidade", sev);
    try {
      const pagina = await api("/api/conciliacao/excecoes?" + params);
      const corpo = $("conc-excecoes").querySelector("tbody");
      corpo.textContent = "";
      for (const e of pagina.itens) {
        const tr = document.createElement("tr");
        tr.className = "conc-clicavel";
        tr.append(
          celula(e.competencia), celula(e.razao_social || e.cnpj),
          celula(e.severidade, e.severidade === "bloqueio" ? "conc-erro" : "conc-alerta"),
          celula(e.codigo), celula(e.mensagem));
        tr.addEventListener("click", () => {
          abrirSub("conciliacoes");
          abrirDetalhe(e.conciliacao_id);
        });
        corpo.appendChild(tr);
      }
    } catch (erro) {
      status(erro.message);
    }
  }
  $("conc-e-estado").addEventListener("change", carregarExcecoes);
  $("conc-e-severidade").addEventListener("change", carregarExcecoes);


  // ------------------------------------------------------------------
  // Exportacoes

  function montarExportacoes() {
    if (!pode.exportar && !pode.preencherModelo) {
      $("conc-sem-exportar").classList.remove("oculto");
      return;
    }
    if (pode.exportar) {
      $("conc-exp-consolidado").classList.remove("oculto");
      const botao = $("conc-exportar");
      botao.addEventListener("click", async () => {
        botao.disabled = true;
        $("conc-exp-status").textContent = "Gerando o consolidado...";
        try {
          // Os mesmos filtros da lista: o arquivo tem de conter exatamente o
          // que a pessoa está vendo na tela.
          const nome = await apiDownload("/api/conciliacao/exportar",
                                         { json: filtrosAtuais() });
          $("conc-exp-status").textContent = `Baixado: ${nome}`;
        } catch (erro) {
          $("conc-exp-status").textContent = erro.message;
          toast(erro.message, "erro");
        } finally {
          botao.disabled = false;
        }
      });
    }
    if (!pode.preencherModelo) return;

    $("conc-exp-modelo").classList.remove("oculto");
    if (pode.incluirPendentes) {
      $("conc-m-pendentes-campo").classList.remove("oculto");
    }
    const botao = $("conc-preencher");
    botao.addEventListener("click", async () => {
      const arquivo = ($("conc-m-arquivo").files || [])[0];
      const cnpj = $("conc-m-cnpj").value.replace(/\D/g, "");
      if (!arquivo) { toast("Selecione o modelo (.xlsx).", "erro"); return; }
      if (cnpj.length !== 14) {
        toast("Informe um CNPJ com 14 dígitos.", "erro");
        return;
      }
      const incluir = pode.incluirPendentes && $("conc-m-pendentes").checked;
      botao.disabled = true;
      $("conc-m-status").textContent = "Enviando o modelo...";
      try {
        const nome = await enviarModelo(arquivo, cnpj, incluir, false);
        $("conc-m-status").textContent = `Baixado: ${nome}`;
      } catch (erro) {
        // 409 CONFIRMACAO_PENDENTES não é falha: é o servidor exigindo que a
        // pessoa assuma, explicitamente, que vai levar número não aprovado.
        if (erro.codigo === "CONFIRMACAO_PENDENTES") {
          if (confirm(`${erro.message}\n\nIncluir mesmo assim? As ` +
                      "competências não aprovadas ficarão sinalizadas numa " +
                      "aba de aviso do arquivo.")) {
            try {
              const nome = await enviarModelo(arquivo, cnpj, true, true);
              $("conc-m-status").textContent = `Baixado: ${nome}`;
            } catch (segundo) {
              $("conc-m-status").textContent = segundo.message;
              toast(segundo.message, "erro");
            }
          } else {
            $("conc-m-status").textContent = "Cancelado.";
          }
        } else {
          $("conc-m-status").textContent = erro.message;
          toast(erro.message, "erro");
        }
      } finally {
        botao.disabled = false;
      }
    });
  }

  async function enviarModelo(arquivo, cnpj, incluir, confirmado) {
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    corpo.append("cnpj", cnpj);
    corpo.append("competencia_de", $("conc-m-de").value.trim());
    corpo.append("competencia_ate", $("conc-m-ate").value.trim());
    corpo.append("incluir_em_revisao", incluir ? "true" : "false");
    corpo.append("confirmacao_pendentes", confirmado ? "true" : "false");
    return apiDownload("/api/conciliacao/preencher-modelo",
                       { method: "POST", body: corpo });
  }

  montarExportacoes();

  /* Atalhos da visão geral: cada um aplica o filtro correspondente e leva
     para a lista já filtrada — o caminho que a pessoa faria à mão. */
  $("conc-atalhos").addEventListener("click", (e) => {
    const botao = e.target.closest("button[data-atalho]");
    if (!botao) return;
    const alvoFiltro = botao.dataset.atalho;
    for (const campo of F) $(`conc-f-${campo}`).value = "";
    if (alvoFiltro === "em_revisao") $("conc-f-estado").value = "em_revisao";
    else if (alvoFiltro) $("conc-f-excecao").value = alvoFiltro;
    abrirSub("conciliacoes");
  });

  // Exposto para as subtelas das proximas fases.
  container.conciliacao = { estado, pode, garantirSessao, atualizarResumo,
                            abrirSub, status, linhaFila, carregarLista,
                            abrirDetalhe };

  atualizarResumo();
  carregarLista();
});
