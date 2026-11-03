/* Aba 9 — Clientes, cofre de senhas e vencimentos (spec 012).

   Mesma disciplina das outras abas: o que esta tela esconde é conveniência,
   nunca autorização — quem manda é o 403 do servidor. Todo conteúdo vindo do
   servidor entra por `textContent`.

   Cofre: a senha só chega a esta tela quando a pessoa pede UMA, depois de
   confirmar a própria senha. Ela fica 30 segundos na tela e some; não vai
   para variável global, localStorage nem console. */

"use strict";

/* Aviso do topo (certificados vencidos ou na faixa mais curta). O app.js
   chama AvisoVencimentos.mostrar() ao entrar no sistema. */
const AvisoVencimentos = {
  async mostrar() {
    const alvo = document.getElementById("aviso-topo");
    if (!alvo) return;
    alvo.classList.add("oculto");
    if (!Sessao.pode("aba.clientes")) return;
    let r;
    try { r = await api("/api/clientes/avisos"); } catch { return; }
    if (!r.aviso) return;
    alvo.textContent = "";
    const texto = document.createElement("span");
    const partes = [];
    if (r.vencidos) partes.push(`${r.vencidos} vencido(s)`);
    if (r.na_faixa_curta) partes.push(`${r.na_faixa_curta} vencendo em até ${r.faixa_curta} dias`);
    texto.textContent = `Certificados digitais: ${partes.join(" e ")}.`;
    const botao = document.createElement("button");
    botao.type = "button";
    botao.textContent = "Ver vencimentos";
    botao.addEventListener("click", () => {
      Abas.abrir("clientes");
      document.dispatchEvent(new CustomEvent("clientes:vencimentos"));
    });
    alvo.append(texto, botao);
    alvo.classList.remove("oculto");
  },
};

/* Formulário em modal: devolve {campo: valor} ou null se cancelar. Campo de
   senha usa type=password e autocomplete desligado — prompt() mostraria a
   senha em texto aberto e o navegador ofereceria guardá-la. */
function formularioModal(titulo, campos, { textoConfirmar = "Salvar", ajuda = "" } = {}) {
  return new Promise((resolver) => {
    const gatilho = document.activeElement;
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    const modal = document.createElement("form");
    modal.className = "modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", titulo);
    const h = document.createElement("h3");
    h.textContent = titulo;
    modal.appendChild(h);
    if (ajuda) {
      const p = document.createElement("p");
      p.className = "dica";
      p.textContent = ajuda;
      modal.appendChild(p);
    }
    const grade = document.createElement("div");
    grade.className = "cli-grade";
    const entradas = {};
    for (const c of campos) {
      const rotulo = document.createElement("label");
      rotulo.textContent = c.rotulo;
      let entrada;
      if (c.tipo === "select") {
        entrada = document.createElement("select");
        for (const o of c.opcoes) {
          const op = document.createElement("option");
          op.value = o.valor; op.textContent = o.rotulo;
          entrada.appendChild(op);
        }
      } else if (c.tipo === "textarea") {
        entrada = document.createElement("textarea");
        entrada.rows = 3;
      } else {
        entrada = document.createElement("input");
        entrada.type = c.tipo || "text";
        if (c.tipo === "password") entrada.autocomplete = "new-password";
        if (c.tipo === "file" && c.aceitar) entrada.accept = c.aceitar;
        if (c.placeholder) entrada.placeholder = c.placeholder;
      }
      if (c.valor !== undefined && c.tipo !== "file") entrada.value = c.valor ?? "";
      if (c.obrigatorio) entrada.required = true;
      entrada.name = c.nome;
      rotulo.appendChild(entrada);
      grade.appendChild(rotulo);
      entradas[c.nome] = entrada;
    }
    modal.appendChild(grade);
    const acoes = document.createElement("div");
    acoes.className = "acoes";
    const cancelar = document.createElement("button");
    cancelar.type = "button"; cancelar.textContent = "Cancelar";
    const ok = document.createElement("button");
    ok.type = "submit"; ok.className = "botao-primario"; ok.textContent = textoConfirmar;
    acoes.append(cancelar, ok);
    modal.appendChild(acoes);
    fundo.appendChild(modal);

    const fechar = (resposta) => {
      document.removeEventListener("keydown", aoTeclar, true);
      // Limpa os campos antes de soltar o DOM: senha digitada não fica pendurada.
      for (const e of Object.values(entradas)) { if (e.type !== "file") e.value = ""; }
      fundo.remove();
      if (gatilho && gatilho.isConnected) gatilho.focus();
      resolver(resposta);
    };
    const aoTeclar = (evento) => {
      if (evento.key === "Escape") { evento.preventDefault(); fechar(null); }
    };
    document.addEventListener("keydown", aoTeclar, true);
    cancelar.onclick = () => fechar(null);
    modal.addEventListener("submit", (e) => {
      e.preventDefault();
      const valores = {};
      for (const [nome, e2] of Object.entries(entradas)) {
        valores[nome] = e2.type === "file" ? e2.files[0] || null : e2.value;
      }
      fechar(valores);
    });
    document.body.appendChild(fundo);
    (Object.values(entradas)[0] || ok).focus();
  });
}

/* Conferência independente da base Fiscal (spec 017). O resultado vive apenas
   nesta tela, até trocar o arquivo, encerrar a sessão ou limpar a prévia. */
const BaseFiscalUI = {
  normalizar(valor) {
    return String(valor ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  },
  colunaAusente(linha, campo) {
    return (linha.campos_ausentes_no_layout || []).includes(campo);
  },
  selecionar(linhas, filtros = {}) {
    const texto = this.normalizar(filtros.texto);
    return linhas.filter(l => {
      if (filtros.aba && l.aba !== filtros.aba) return false;
      const condicoes = {
        pendencias: !!l.pendencias?.length,
        documentos: !["valido", "zero_inicial_recuperado"].includes(l.documento_status),
        duplicados: !!l.duplicado,
        sem_movimento: l.sem_movimento === true,
        sem_responsavel: !this.colunaAusente(l, "responsavel_fiscal") && !l.responsavel_fiscal_informado,
        sem_regime: !this.colunaAusente(l, "regime") && !l.regime,
      };
      if (filtros.situacao && !condicoes[filtros.situacao]) return false;
      return !texto || this.normalizar([l.nome, l.documento, l.documento_informado, l.regime,
        l.regime_informado, l.responsavel_fiscal_informado, l.contato_nome, l.aba].join(" ")).includes(texto);
    });
  },
  montar(alvo) {
    const permitido = () => Sessao.pode("aba.clientes") && Sessao.pode("clientes.importar");
    const podeBaixar = () => permitido() && Sessao.pode("clientes.exportar");
    if (!permitido()) return;
    const criar = (tag, texto = "", classe = "") => {
      const e = document.createElement(tag);
      e.textContent = texto;
      if (classe) e.className = classe;
      return e;
    };
    const botao = (texto, id, acao) => {
      const b = criar("button", texto); b.type = "button"; b.id = id;
      if (acao) b.addEventListener("click", acao);
      return b;
    };
    const campo = (rotulo, entrada) => {
      const label = criar("label", rotulo); label.append(entrada); return label;
    };
    const opcoes = (entrada, itens) => {
      entrada.textContent = "";
      for (const [valor, texto] of itens) {
        const o = criar("option", texto); o.value = valor; entrada.append(o);
      }
    };
    alvo.className = "base-fiscal";
    alvo.append(criar("h3", "Conferência da base Fiscal", "pat-titulo"),
      criar("p", "Sem gravação na conferência: a prévia da base é somente leitura. A inclusão de empresas exige preparar a importação e confirmar as quantidades com a permissão específica.", "dica"),
      criar("p", "A aba ZERADAS indica empresas sem movimento que continuam na carteira. Não significa inatividade, baixa ou dispensa de obrigações.", "dica"));
    const entrada = criar("input"); entrada.type = "file"; entrada.accept = ".xlsx"; entrada.id = "bf-arquivo";
    const ler = botao("Conferir base Fiscal", "bf-ler", carregar); ler.className = "botao-primario";
    const limpar = botao("Limpar prévia", "bf-limpar", () => invalidar("Prévia removida da tela. Escolha um arquivo XLSX.", true));
    const envio = criar("div", "", "linha-form");
    envio.append(campo("Arquivo XLSX (até 20 MB)", entrada), ler, limpar);
    const status = criar("p", "Escolha uma planilha para conferir.", "status"); status.id = "bf-status";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const statusDescarte = criar("p", "", "status"); statusDescarte.id = "bf-descarte-status";
    statusDescarte.setAttribute("role", "status"); statusDescarte.setAttribute("aria-live", "polite");
    statusDescarte.hidden = true;
    const avisoConfirmacao = criar("p", "", "status conc-erro"); avisoConfirmacao.id = "bf-descarte-confirmacao";
    avisoConfirmacao.setAttribute("role", "status"); avisoConfirmacao.hidden = true;
    const resultado = criar("div"); resultado.id = "bf-resultado";
    alvo.append(envio, status, statusDescarte, avisoConfirmacao, resultado);
    let consulta = 0, previa = null, arquivoConferido = null, pessoaConferida = null;
    let baixando = false, relatorio = null, limparRevisao = () => {};
    // Manter apenas metadados em memória até o servidor confirmar o descarte.
    // Uma preparação em trânsito também precisa ser descartada quando responder.
    const preparacoes = new Set();
    function atualizarDescarte() {
      const pendentes = [...preparacoes].filter(p => p.descartar);
      statusDescarte.hidden = false; statusDescarte.className = "status";
      if (pendentes.some(p => p.falha || p.incerta)) {
        statusDescarte.className = "status conc-erro";
        statusDescarte.textContent = pendentes.some(p => p.incerta)
          ? "Não foi possível confirmar o cancelamento: a resposta da preparação não trouxe uma referência válida. Aguarde a expiração da preparação no servidor."
          : "Não foi possível confirmar o cancelamento no servidor. Verifique sua conexão e sessão e clique em Limpar prévia para tentar novamente.";
      } else if (pendentes.length) {
        statusDescarte.textContent = pendentes.some(p => p.pendente)
          ? "Aguardando a resposta da preparação para cancelar no servidor…"
          : "Cancelando a preparação no servidor…";
      } else {
        statusDescarte.textContent = "Cancelamento confirmado: as preparações anteriores não estão disponíveis para confirmar no servidor.";
      }
    }
    async function descartarPreparacao(p) {
      p.descartar = true;
      if (p.confirmacaoEnviada) {
        avisoConfirmacao.hidden = false;
        avisoConfirmacao.textContent = "Uma confirmação de importação já foi enviada. Cancelar a preparação não desfaz uma importação que tenha sido concluída. Confira o cadastro antes de continuar.";
      }
      if (p.cancelando || p.pendente || p.incerta) { atualizarDescarte(); return; }
      // Nunca enviar o token de uma identidade anterior usando a nova sessão.
      if (Sessao.usuario !== p.pessoa || !permitido() || !Sessao.pode("clientes.importar_base_fiscal")) {
        p.falha = true; atualizarDescarte(); return;
      }
      p.cancelando = true; p.falha = false; atualizarDescarte();
      try {
        const resposta = await api(`/api/clientes/base-fiscal/importacao/${encodeURIComponent(p.token)}`, {method: "DELETE"});
        if (resposta?.ok !== true) throw new Error("Descarte não confirmado.");
        preparacoes.delete(p);
      } catch (erro) {
        // 404 pode ser um token de outra sessão; só 410 garante indisponibilidade.
        if (erro.status === 410 && erro.codigo === "BASE_FISCAL_TOKEN_EXPIRADO") preparacoes.delete(p);
        else p.falha = true;
      } finally {
        p.cancelando = false; atualizarDescarte();
      }
    }
    function descartarPreparacoes() {
      for (const p of preparacoes) void descartarPreparacao(p);
    }
    function invalidar(mensagem, limparArquivo = false) {
      limparRevisao(); limparRevisao = () => {};
      descartarPreparacoes();
      consulta += 1; previa = null; resultado.textContent = "";
      arquivoConferido = null; pessoaConferida = null; baixando = false; relatorio = null;
      status.textContent = mensagem; status.className = "status";
      resultado.setAttribute("aria-busy", "false"); ler.disabled = !permitido();
      if (limparArquivo) entrada.value = "";
    }
    entrada.addEventListener("change", () => invalidar(entrada.files[0]
      ? "Arquivo selecionado. Clique em Conferir base Fiscal para ler a nova prévia."
      : "Escolha uma planilha para conferir."));
    document.addEventListener("sessao:encerrada", () => invalidar("Sessão encerrada. A prévia foi limpa.", true));

    async function carregar() {
      invalidar("");
      if (!permitido()) { status.textContent = "Você não tem permissão para conferir a base Fiscal."; return; }
      const arquivo = entrada.files[0];
      if (!arquivo) { status.textContent = "Escolha um arquivo XLSX."; entrada.focus(); return; }
      if (!/\.xlsx$/i.test(arquivo.name) || arquivo.size > 20 * 1024 * 1024) {
        status.textContent = "Escolha um arquivo XLSX de até 20 MB."; return;
      }
      const geracao = consulta, pessoa = Sessao.usuario;
      const atual = () => geracao === consulta && Sessao.usuario === pessoa && permitido() && entrada.files[0] === arquivo;
      status.textContent = "Lendo a base Fiscal…"; ler.disabled = true;
      resultado.setAttribute("aria-busy", "true");
      try {
        const resposta = await apiUpload("/api/clientes/base-fiscal/previa", arquivo);
        if (!atual()) return;
        if (resposta.somente_leitura !== true || !Array.isArray(resposta.linhas) || !resposta.contagens) {
          throw new Error("Não foi possível conferir a resposta da prévia. Tente novamente.");
        }
        previa = resposta;
        arquivoConferido = arquivo; pessoaConferida = pessoa;
        desenhar();
        status.textContent = "Leitura concluída. Nenhum cadastro ou vínculo foi gravado.";
      } catch (erro) {
        if (!atual()) return;
        previa = null; resultado.textContent = "";
        status.textContent = erro.message || "Não foi possível ler a planilha.";
        status.className = "status conc-erro";
      } finally {
        if (geracao === consulta) {
          if (!atual()) invalidar("A sessão mudou. Escolha o arquivo novamente.", true);
          else { ler.disabled = false; resultado.setAttribute("aria-busy", "false"); }
        }
      }
    }

    async function baixarRelatorio() {
      if (baixando) return;
      if (!previa || !arquivoConferido || entrada.files[0] !== arquivoConferido ||
          Sessao.usuario !== pessoaConferida || !permitido()) {
        invalidar("A sessão ou o arquivo mudou. Confira a base novamente.", true);
        return;
      }
      if (!podeBaixar()) {
        relatorio.disabled = true;
        status.textContent = "Você não tem permissão para exportar clientes.";
        return;
      }
      const geracao = consulta, pessoa = pessoaConferida, arquivo = arquivoConferido;
      const atual = () => geracao === consulta && Sessao.usuario === pessoa &&
        entrada.files[0] === arquivo && podeBaixar();
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      corpo.append("hash_esperado", previa.hash_arquivo);
      baixando = true; relatorio.disabled = true;
      status.textContent = "Gerando o relatório completo…"; status.className = "status";
      try {
        const resposta = await api("/api/clientes/base-fiscal/relatorio", {method: "POST", body: corpo});
        if (!atual()) return;
        if (typeof resposta.blob !== "function") throw new Error("Não foi possível receber o relatório. Tente novamente.");
        const blob = await resposta.blob();
        if (!atual()) return;
        const url = URL.createObjectURL(blob);
        try {
          const link = document.createElement("a");
          link.href = url; link.download = "conferencia-base-fiscal.xlsx"; link.click();
        } finally {
          URL.revokeObjectURL(url);
        }
        status.textContent = "Relatório completo preparado para download. Nenhum cadastro ou vínculo foi gravado.";
      } catch (erro) {
        if (!atual()) return;
        if (erro.codigo === "BASE_FISCAL_DIVERGENTE") {
          invalidar("O arquivo diverge da prévia. Escolha o arquivo e confira novamente.", true);
          return;
        }
        status.textContent = erro.message || "Não foi possível gerar o relatório. Tente novamente.";
        status.className = "status conc-erro";
      } finally {
        if (geracao === consulta) {
          if (!atual()) invalidar("A sessão, o arquivo ou as permissões mudaram. Confira a base novamente.", true);
          else { baixando = false; relatorio.disabled = false; }
        }
      }
    }

    function desenhar() {
      resultado.textContent = "";
      resultado.append(criar("h4", previa.nome_arquivo, "base-fiscal-arquivo"));
      relatorio = botao("Baixar relatório completo (.xlsx)", "bf-relatorio", baixarRelatorio);
      relatorio.disabled = !podeBaixar();
      const acoes = criar("div", "", "linha-form"); acoes.append(relatorio);
      resultado.append(acoes, criar("p", "O relatório inclui todos os registros, independentemente dos filtros. Preencha a aba Correções e envie o relatório abaixo para preparar a prévia de importação. Nenhuma alteração será gravada.", "dica"));
      if (!podeBaixar()) resultado.append(criar("p", "Para baixar o relatório, é necessária a permissão de exportar clientes.", "dica"));
      montarRevisao();
      const contadores = criar("div", "", "base-fiscal-contadores");
      for (const [chave, rotulo] of [["linhas", "Registros no arquivo"], ["cnpjs_distintos", "CNPJs válidos distintos"],
        ["documentos_pendentes", "Documentos pendentes"], ["grupos_duplicados", "Grupos repetidos"],
        ["sem_movimento", "Sem movimento"], ["com_pendencias", "Com pendências"]]) {
        const card = criar("div"), n = criar("strong", previa.contagens[chave] ?? "—");
        n.id = `bf-total-${chave}`;
        card.append(n, criar("span", rotulo)); contadores.append(card);
      }
      resultado.append(contadores, criar("p", "Totais do arquivo inteiro. As categorias podem se sobrepor; busca e filtros alteram apenas a lista abaixo.", "dica"));
      if (previa.avisos?.length) {
        const avisos = criar("ul", "", "base-fiscal-avisos");
        for (const aviso of previa.avisos) avisos.append(criar("li", aviso));
        resultado.append(avisos);
      }
      const detalhes = criar("details", "", "base-fiscal-arquivo-detalhes");
      detalhes.append(criar("summary", "Detalhes do arquivo e das abas"));
      const abas = criar("ul");
      for (const aba of previa.abas || []) {
        abas.append(criar("li", `${aba.nome}: ${aba.total} registro(s), cabeçalho na linha ${aba.linha_cabecalho}` +
          (aba.tipo === "zeradas" ? ", sem movimento" : ", base principal") + (aba.oculta ? ", aba oculta" : "")));
      }
      detalhes.append(abas, criar("p", `Identificação do arquivo (SHA-256): ${previa.hash_arquivo}`, "base-fiscal-hash"));
      resultado.append(detalhes);
      const filtros = criar("div", "", "linha-form base-fiscal-filtros");
      const busca = criar("input"); busca.type = "search"; busca.id = "bf-busca";
      busca.placeholder = "Empresa, CNPJ, responsável, contato ou regime";
      const situacao = criar("select"); situacao.id = "bf-situacao";
      opcoes(situacao, [["", "Todos os registros"], ["pendencias", "Com pendências"], ["documentos", "Documentos pendentes"],
        ["duplicados", "CNPJ repetido"], ["sem_movimento", "Sem movimento"], ["sem_responsavel", "Sem responsável Fiscal"], ["sem_regime", "Sem regime reconhecido"]]);
      const aba = criar("select"); aba.id = "bf-aba";
      opcoes(aba, [["", "Todas as abas"], ...(previa.abas || []).map(a => [a.nome, a.nome])]);
      const tamanho = criar("select"); tamanho.id = "bf-tamanho";
      opcoes(tamanho, [["25", "25"], ["50", "50"]]); tamanho.value = "25";
      let pagina = 1;
      const resetar = () => { pagina = 1; listar(); };
      busca.addEventListener("input", resetar);
      for (const e of [situacao, aba, tamanho]) e.addEventListener("change", resetar);
      filtros.append(campo("Buscar na base", busca), campo("Conferência", situacao), campo("Aba", aba), campo("Por página", tamanho),
        botao("Limpar filtros", "bf-limpar-filtros", () => { busca.value = ""; situacao.value = ""; aba.value = ""; resetar(); }));
      resultado.append(filtros);
      const rolagem = criar("div", "", "rolagem base-fiscal-rolagem");
      rolagem.tabIndex = 0; rolagem.setAttribute("role", "region"); rolagem.setAttribute("aria-label", "Registros da base Fiscal");
      const tabela = criar("table", "", "base-fiscal-tabela"), cabecalho = criar("thead"), tr = criar("tr");
      for (const nome of ["Empresa / CNPJ", "Regime", "Responsável Fiscal", "Contato da empresa", "Conferência / origem"]) {
        const th = criar("th", nome); th.setAttribute("scope", "col"); tr.append(th);
      }
      cabecalho.append(tr);
      const corpo = criar("tbody"); corpo.id = "bf-corpo";
      tabela.append(cabecalho, corpo); rolagem.append(tabela); resultado.append(rolagem);
      const navegacao = criar("div", "", "conc-paginacao base-fiscal-paginacao");
      const anterior = botao("‹ Anterior", "bf-anterior", () => { if (pagina > 1) { pagina -= 1; listar(); } });
      const proxima = botao("Próxima ›", "bf-proxima", () => { if (!proxima.disabled) { pagina += 1; listar(); } });
      const info = criar("span"); info.id = "bf-pagina"; info.setAttribute("aria-live", "polite");
      navegacao.append(anterior, info, proxima); resultado.append(navegacao);
      const porId = new Map(previa.linhas.map(l => [l.id, l]));
      function listar() {
        if (!previa) return;
        const linhas = BaseFiscalUI.selecionar(previa.linhas, {texto: busca.value, situacao: situacao.value, aba: aba.value});
        const limite = tamanho.value === "50" ? 50 : 25;
        pagina = Math.min(pagina, Math.max(1, Math.ceil(linhas.length / limite)));
        const inicio = (pagina - 1) * limite;
        corpo.textContent = "";
        if (!linhas.length) {
          const vazio = criar("tr"), td = criar("td", previa.linhas.length
            ? "Nenhum registro corresponde aos filtros. Tente limpar a busca ou os filtros."
            : "Nenhum registro no arquivo.", "base-fiscal-vazio");
          td.colSpan = 5; vazio.append(td); corpo.append(vazio);
        }
        for (const [indice, l] of linhas.slice(inicio, inicio + limite).entries()) {
          const linha = criar("tr"); linha.setAttribute("data-registro", l.id);
          const empresa = criar("td"); empresa.append(criar("strong", l.nome || "Nome ausente"),
            criar("span", l.documento || l.documento_informado || "CNPJ ausente", "base-fiscal-secundario"));
          if (l.documento_status === "zero_inicial_recuperado") empresa.append(criar("span", "Zero inicial recuperado", "base-fiscal-secundario"));
          const valorCampo = (campo, valor, ausente) => BaseFiscalUI.colunaAusente(l, campo) ? "Coluna ausente no layout" : valor || ausente;
          const regime = criar("td", valorCampo("regime", l.regime, "Regime pendente"));
          if (l.regime_informado && l.regime_informado !== l.regime) regime.append(criar("span", `Informado: ${l.regime_informado}`, "base-fiscal-secundario"));
          const conferencia = criar("td");
          if (l.sem_movimento === true) conferencia.append(criar("span", "Sem movimento · permanece na carteira", "base-fiscal-marcador"));
          if (l.duplicado) conferencia.append(criar("span", "CNPJ repetido", "base-fiscal-marcador"));
          if (l.pendencias?.length) conferencia.append(criar("p", l.pendencias.join("; "), "base-fiscal-pendencias"));
          else conferencia.append(criar("span", "Sem pendências de leitura", "base-fiscal-secundario"));
          if (l.oculta || l.aba_oculta) conferencia.append(criar("span", l.aba_oculta ? "Aba oculta na planilha" : "Linha oculta na planilha", "base-fiscal-secundario"));
          const origemLinha = criar("tr", "", "base-fiscal-origem-linha"); origemLinha.hidden = true;
          const origemCelula = criar("td"); origemCelula.colSpan = 5;
          origemLinha.id = `bf-origem-${indice}`;
          const origem = botao(`Ver origem: ${l.aba} · linha ${l.linha}`, "", () => {
            origemLinha.hidden = !origemLinha.hidden;
            origem.setAttribute("aria-expanded", !origemLinha.hidden);
            if (!origemLinha.hidden && !origemCelula.children.length) desenharOrigem(origemCelula, l, porId);
          });
          origem.className = "base-fiscal-origem-botao";
          origem.setAttribute("aria-expanded", "false"); origem.setAttribute("aria-controls", origemLinha.id);
          conferencia.append(origem);
          linha.append(empresa, regime, criar("td", valorCampo("responsavel_fiscal", l.responsavel_fiscal_informado, "Não informado")),
            criar("td", valorCampo("contato_nome", l.contato_nome, "Não informado")), conferencia);
          origemLinha.append(origemCelula); corpo.append(linha, origemLinha);
        }
        info.textContent = linhas.length ? `${inicio + 1}–${Math.min(inicio + limite, linhas.length)} de ${linhas.length} registro(s) filtrado(s) · ${previa.contagens.linhas} no arquivo`
          : `0 registro(s) na lista · ${previa.contagens.linhas} no arquivo`;
        anterior.disabled = pagina <= 1; proxima.disabled = inicio + limite >= linhas.length;
      }
      listar();
    }

    function montarRevisao() {
      const bloco = criar("section", "", "base-fiscal-revisao");
      bloco.setAttribute("aria-label", "Correções e prévia de importação");
      bloco.append(criar("h4", "Correções e prévia de importação"),
        criar("p", "No relatório baixado, edite somente a aba Correções: G a K contêm as propostas; campo vazio preserva o original. Não altere as seis colunas originais nem remova registros.", "dica"),
        criar("p", "Para CNPJs repetidos, escreva manter em uma ocorrência e ignorar nas demais, na coluna L. Preencha a justificativa de cada ignorar na coluna M. Também é possível ignorar todas as ocorrências, justificando cada uma. Corrigir um CNPJ pode resolver ou criar uma duplicidade.", "dica"),
        criar("p", "A prévia não grava empresas. Responsáveis permanecem sem vínculo com usuários; regime e sem movimento não são aplicados ao cadastro ou à agenda.", "dica"));
      const correcoes = criar("input"); correcoes.type = "file"; correcoes.accept = ".xlsx"; correcoes.id = "bf-correcoes";
      const gerar = botao("Gerar prévia de importação", "bf-importacao-gerar", gerarPrevia);
      gerar.disabled = true;
      const acoes = criar("div", "", "linha-form");
      acoes.append(campo("Relatório com correções (XLSX, até 20 MB)", correcoes), gerar);
      const mensagem = criar("p", "Escolha o relatório com as propostas para conferir.", "status");
      mensagem.id = "bf-importacao-status"; mensagem.setAttribute("role", "status"); mensagem.setAttribute("aria-live", "polite");
      const saida = criar("div"); saida.id = "bf-importacao-resultado";
      bloco.append(acoes, mensagem, saida); resultado.append(bloco);
      let versao = 0, ocupada = false;
      const fonte = arquivoConferido, pessoa = pessoaConferida, geracao = consulta, hashFonte = previa.hash_arquivo;
      const fonteAtual = () => geracao === consulta && arquivoConferido === fonte && entrada.files[0] === fonte &&
        Sessao.usuario === pessoa && permitido();
      const podeImportar = () => permitido() && Sessao.pode("clientes.importar_base_fiscal");
      const arquivoValido = arquivo => arquivo && /\.xlsx$/i.test(arquivo.name) && arquivo.size <= 20 * 1024 * 1024;
      const tipos = ["incluir", "existente", "conflito", "pendente", "ignorar"];
      function previaValida(dados, hashCorrecoes) {
        const contagens = Object.fromEntries(tipos.map(tipo => [tipo, 0]));
        if (Array.isArray(dados?.linhas)) for (const linha of dados.linhas) if (tipos.includes(linha?.status)) contagens[linha.status]++;
        return dados?.somente_leitura === true && dados.formato === "base_fiscal_importacao_v1" &&
          dados.hash_arquivo === hashFonte && /^[a-f0-9]{64}$/.test(dados.hash_correcoes || "") &&
          (!hashCorrecoes || dados.hash_correcoes === hashCorrecoes) && Array.isArray(dados.linhas) &&
          dados.contagens?.linhas === dados.linhas.length && tipos.every(tipo => dados.contagens[tipo] === contagens[tipo]) &&
          dados.linhas.every(l => tipos.includes(l?.status));
      }
      const apta = dados => dados.contagens.incluir > 0 && !dados.contagens.conflito && !dados.contagens.pendente &&
        !dados.linhas.some(l => l.status === "conflito" || l.status === "pendente");
      function limpar() {
        versao += 1; ocupada = false; saida.textContent = ""; saida.setAttribute("aria-busy", "false");
        descartarPreparacoes();
        gerar.disabled = !fonteAtual() || !arquivoValido(correcoes.files[0]);
      }
      limparRevisao = () => { limpar(); correcoes.value = ""; gerar.disabled = true; };
      correcoes.addEventListener("change", () => {
        limpar(); mensagem.className = "status";
        mensagem.textContent = !correcoes.files[0] ? "Escolha o relatório com as propostas para conferir."
          : arquivoValido(correcoes.files[0]) ? "Relatório selecionado. Gere uma nova prévia para conferir as propostas."
            : "Escolha um relatório XLSX de até 20 MB.";
      });
      async function gerarPrevia() {
        if (ocupada) return;
        if (!fonteAtual()) { invalidar("A sessão ou o arquivo mudou. Confira a base novamente.", true); return; }
        const arquivo = correcoes.files[0];
        if (!arquivoValido(arquivo)) {
          mensagem.textContent = "Escolha um relatório XLSX de até 20 MB."; correcoes.focus(); return;
        }
        limpar(); ocupada = true; gerar.disabled = true;
        const revisao = versao;
        const atual = () => fonteAtual() && revisao === versao && correcoes.files[0] === arquivo;
        saida.setAttribute("aria-busy", "true"); mensagem.className = "status";
        mensagem.textContent = "Conferindo correções e comparando com o cadastro…";
        const corpo = new FormData(); corpo.append("arquivo", fonte); corpo.append("correcoes", arquivo); corpo.append("hash_esperado", hashFonte);
        try {
          const dados = await api("/api/clientes/base-fiscal/importacao/previa", {method: "POST", body: corpo});
          if (!atual()) return;
          if (!previaValida(dados)) {
            throw new Error("Não foi possível conferir a resposta da prévia de importação. Tente novamente.");
          }
          desenharRevisao(saida, dados);
          oferecerPreparacao(dados, arquivo, revisao);
          mensagem.textContent = "Prévia de importação concluída. Nenhum cadastro ou vínculo foi gravado.";
        } catch (erro) {
          if (!atual()) return;
          if (erro.codigo === "BASE_FISCAL_DIVERGENTE") {
            invalidar("O arquivo diverge da prévia. Escolha a fonte e confira novamente.", true); return;
          }
          saida.textContent = ""; mensagem.className = "status conc-erro";
          mensagem.textContent = erro.message || "Não foi possível conferir as correções. Tente novamente.";
        } finally {
          if (geracao === consulta && !fonteAtual()) invalidar("A sessão ou as permissões mudaram. Confira a base novamente.", true);
          else if (atual()) { ocupada = false; gerar.disabled = false; saida.setAttribute("aria-busy", "false"); }
        }
      }

      function oferecerPreparacao(dados, arquivo, revisao) {
        if (!podeImportar()) return;
        const carga = criar("section"); carga.setAttribute("aria-label", "Preparar inclusão de empresas");
        saida.append(carga);
        if (!apta(dados)) {
          carga.append(criar("p", dados.contagens.conflito || dados.contagens.pendente
            ? "Resolva os conflitos e as pendências e gere uma nova prévia antes de preparar a importação."
            : "Não há empresas novas para incluir nesta prévia.", "dica"));
          return;
        }
        const preparar = botao("Preparar importação", "bf-importacao-preparar", prepararCarga);
        carga.append(criar("p", "Preparar consulta novamente o cadastro. A gravação só acontece depois de conferir a nova prévia e confirmar a inclusão.", "dica"), preparar);
        const atual = () => fonteAtual() && podeImportar() && revisao === versao && correcoes.files[0] === arquivo;
        async function prepararCarga() {
          if (ocupada) return;
          if (!atual()) {
            if (geracao === consulta && (!fonteAtual() || !podeImportar())) invalidar("A sessão ou as permissões mudaram. Confira a base novamente.", true);
            return;
          }
          ocupada = true; preparar.disabled = true; gerar.disabled = true;
          saida.setAttribute("aria-busy", "true"); mensagem.className = "status";
          mensagem.textContent = "Revalidando os arquivos e o cadastro para preparar a confirmação…";
          const corpo = new FormData(); corpo.append("arquivo", fonte); corpo.append("correcoes", arquivo);
          corpo.append("hash_esperado", dados.hash_arquivo); corpo.append("hash_correcoes_esperado", dados.hash_correcoes);
          const controle = {pessoa, pendente: true, token: null, descartar: false};
          preparacoes.add(controle);
          try {
            const resposta = await api("/api/clientes/base-fiscal/importacao/preparar", {method: "POST", body: corpo});
            controle.pendente = false;
            if (typeof resposta?.token === "string" && resposta.token.trim() && resposta.token.length <= 512) controle.token = resposta.token;
            else controle.incerta = true;
            if (!atual() || controle.descartar) { await descartarPreparacao(controle); return; }
            if (resposta?.formato !== "base_fiscal_confirmacao_v1" || !controle.token || !Number.isInteger(resposta.expira_em_minutos) ||
                resposta.expira_em_minutos <= 0 || !previaValida(resposta.previa, dados.hash_correcoes) || !apta(resposta.previa)) {
              throw new Error("Não foi possível conferir a preparação recebida. Gere uma nova prévia.");
            }
            desenharRevisao(saida, resposta.previa);
            oferecerConfirmacao(resposta, arquivo, revisao, controle);
            mensagem.textContent = "Cadastro revalidado. Confira a prévia atualizada e as quantidades antes de confirmar. Nenhuma empresa foi gravada nesta preparação.";
          } catch (erro) {
            controle.pendente = false;
            if (!controle.token && erro.status >= 400 && erro.status < 500) {
              preparacoes.delete(controle);
              if (controle.descartar) atualizarDescarte();
            } else {
              if (!controle.token) controle.incerta = true;
              await descartarPreparacao(controle);
            }
            if (!atual()) return;
            carga.textContent = ""; mensagem.className = "status conc-erro";
            mensagem.textContent = `${erro.message || "Não foi possível preparar a importação."} Gere uma nova prévia antes de tentar novamente.`;
          } finally {
            if (geracao === consulta && (!fonteAtual() || !podeImportar())) invalidar("A sessão ou as permissões mudaram. Confira a base novamente.", true);
            else if (atual()) { ocupada = false; gerar.disabled = false; saida.setAttribute("aria-busy", "false"); }
          }
        }
      }

      function oferecerConfirmacao(preparacao, arquivo, revisao, controle) {
        const dados = preparacao.previa, totais = dados.contagens;
        const carga = criar("section"); carga.setAttribute("aria-label", "Confirmar inclusão de empresas");
        const aceite = criar("input"); aceite.type = "checkbox"; aceite.id = "bf-importacao-aceite";
        const gravar = botao(`Confirmar inclusão de ${totais.incluir} empresa(s)`, "bf-importacao-confirmar", confirmarCarga);
        gravar.disabled = true;
        const rotulo = `Conferi a prévia atualizada e autorizo incluir ${totais.incluir} empresa(s), preservar ${totais.existente} já cadastrada(s) e ignorar ${totais.ignorar} ocorrência(s).`;
        carga.append(criar("h4", "Confirmação da importação"),
          criar("p", `Esta preparação vale por ${preparacao.expira_em_minutos} minutos. O cadastro será conferido novamente antes da gravação.`, "dica"),
          criar("p", "Serão incluídos somente os dados cadastrais das novas empresas. Responsáveis, carteira, características fiscais e tarefas exigem configuração separada.", "dica"),
          campo(rotulo, aceite), gravar);
        saida.append(carga);
        let ativa = true;
        const atual = () => ativa && fonteAtual() && podeImportar() && revisao === versao && correcoes.files[0] === arquivo;
        aceite.addEventListener("change", () => { gravar.disabled = ocupada || !atual() || !aceite.checked; });
        async function confirmarCarga() {
          if (ocupada || !ativa) return;
          if (!atual()) {
            if (geracao === consulta && (!fonteAtual() || !podeImportar())) invalidar("A sessão ou as permissões mudaram. Confira a base novamente.", true);
            return;
          }
          if (!aceite.checked) return;
          ocupada = true; gravar.disabled = true; aceite.disabled = true; gerar.disabled = true;
          saida.setAttribute("aria-busy", "true"); mensagem.className = "status";
          mensagem.textContent = "Conferindo e registrando a importação…";
          const corpo = new FormData(); corpo.append("arquivo", fonte); corpo.append("correcoes", arquivo);
          corpo.append("confirmacao", "IMPORTAR EMPRESAS");
          controle.confirmacaoEnviada = true;
          try {
            const resposta = await api(`/api/clientes/base-fiscal/importacao/${encodeURIComponent(preparacao.token)}/confirmar`, {method: "POST", body: corpo});
            if (!atual()) return;
            const id = resposta?.importacao_id, contagens = resposta?.contagens;
            if (resposta?.formato !== "base_fiscal_resultado_v1" ||
                !(Number.isInteger(id) && id > 0 || typeof id === "string" && id.trim() && id.length <= 128) ||
                typeof resposta.repetida !== "boolean" || resposta.hash_arquivo !== dados.hash_arquivo || resposta.hash_correcoes !== dados.hash_correcoes ||
                !contagens || contagens.incluidas !== totais.incluir || contagens.existentes !== totais.existente || contagens.ignoradas !== totais.ignorar) {
              throw new Error("O retorno recebido não corresponde à preparação conferida.");
            }
            ativa = false; aceite.checked = false; carga.textContent = "";
            const recibo = criar("section"); recibo.id = "bf-importacao-recibo"; recibo.setAttribute("role", "status");
            recibo.append(criar("h4", resposta.repetida ? "Importação já concluída anteriormente" : "Importação concluída"),
              criar("p", `Registro da importação: ${id}.`),
              criar("p", `${contagens.incluidas} empresa(s) incluída(s), ${contagens.existentes} preservada(s) e ${contagens.ignoradas} ocorrência(s) ignorada(s).`),
              criar("p", "A carteira, os responsáveis, as características fiscais e as tarefas permanecem para configuração separada.", "dica"));
            carga.append(recibo);
            mensagem.textContent = resposta.repetida ? "Resultado da importação anterior recuperado. Nenhuma empresa foi duplicada." : "Importação concluída. Confira o resumo abaixo.";
          } catch (erro) {
            if (!atual()) return;
            aceite.checked = false; mensagem.className = "status conc-erro";
            if ([403, 404, 409, 410].includes(erro.status) ||
                ["BASE_FISCAL_DIVERGENTE", "BASE_FISCAL_DESATUALIZADA", "BASE_FISCAL_TOKEN_EXPIRADO"].includes(erro.codigo)) {
              ativa = false; carga.textContent = "";
              mensagem.textContent = `${erro.message || "A preparação não está mais disponível."} Gere uma nova prévia e prepare novamente a importação.`;
            } else {
              mensagem.textContent = `Não foi possível confirmar o resultado da importação. A operação pode ter sido concluída. Confira novamente o aceite para consultar ou repetir esta mesma confirmação com segurança. ${erro.message || "Tente novamente."}`;
            }
          } finally {
            if (geracao === consulta && (!fonteAtual() || !podeImportar())) invalidar("A sessão ou as permissões mudaram. Confira a base novamente.", true);
            else if (fonteAtual() && revisao === versao && correcoes.files[0] === arquivo) {
              ocupada = false; gerar.disabled = false; aceite.disabled = false;
              gravar.disabled = !ativa || !aceite.checked; saida.setAttribute("aria-busy", "false");
            }
          }
        }
      }
    }

    function desenharRevisao(alvoRevisao, dados) {
      alvoRevisao.textContent = "";
      const rotulos = {incluir: "Novas empresas", existente: "Já cadastradas", conflito: "Conflitos com o cadastro", pendente: "Pendências", ignorar: "Ignoradas na proposta"};
      const campos = {nome: "Empresa", documento: "CNPJ", regime: "Regime", responsavel_fiscal: "Responsável Fiscal", contato_nome: "Contato"};
      alvoRevisao.append(criar("h4", "Resultado da prévia"),
        criar("p", `${dados.contagens.linhas} registro(s) conferido(s) · ${dados.contagens.alteradas} com propostas de alteração.`, "dica"),
        criar("p", "Novas empresas são candidatas a uma futura inclusão. Já cadastradas não serão recriadas; conflitos e pendências exigem revisão. Ignorar não exclui clientes existentes. Esta prévia precisa ser revalidada antes de qualquer futura gravação.", "dica"));
      const contadores = criar("div", "", "base-fiscal-contadores");
      for (const [chave, rotulo] of Object.entries(rotulos)) {
        const card = criar("div"), total = criar("strong", dados.contagens[chave] ?? "—");
        total.id = `bf-importacao-total-${chave}`; card.append(total, criar("span", rotulo)); contadores.append(card);
      }
      alvoRevisao.append(contadores);
      if (dados.cadastro_disponivel === false) alvoRevisao.append(criar("p", "Ainda não existe banco cadastral neste ambiente. A comparação considera um cadastro vazio.", "dica"));
      function horarioConsulta(valor) {
        const data = typeof valor === "string" && valor.trim() ? new Date(valor) : null;
        if (!data || Number.isNaN(data.getTime())) return "Horário da consulta cadastral indisponível.";
        const texto = new Intl.DateTimeFormat("pt-BR", {
          dateStyle: "short", timeStyle: "medium", timeZone: "America/Bahia",
        }).format(data);
        return `Cadastro consultado em: ${texto} (horário de Salvador).`;
      }
      alvoRevisao.append(criar("p", horarioConsulta(dados.cadastro_consultado_em), "dica"));
      for (const aviso of dados.avisos || []) alvoRevisao.append(criar("p", aviso, "dica"));
      const identificacao = criar("details", "", "base-fiscal-arquivo-detalhes");
      identificacao.append(criar("summary", "Identificação dos arquivos"),
        criar("p", `Fonte (SHA-256): ${dados.hash_arquivo}`, "base-fiscal-hash"),
        criar("p", `Correções (SHA-256): ${dados.hash_correcoes}`, "base-fiscal-hash"));
      alvoRevisao.append(identificacao);
      const filtros = criar("div", "", "linha-form base-fiscal-filtros");
      const busca = criar("input"); busca.type = "search"; busca.id = "bf-importacao-busca";
      const filtro = criar("select"); filtro.id = "bf-importacao-filtro";
      opcoes(filtro, [["", "Todos os resultados"], ...Object.entries(rotulos)]);
      const tamanho = criar("select"); tamanho.id = "bf-importacao-tamanho";
      opcoes(tamanho, [["25", "25"], ["50", "50"]]); tamanho.value = "25";
      let pagina = 1;
      const resetar = () => { pagina = 1; listar(); };
      busca.addEventListener("input", resetar); filtro.addEventListener("change", resetar); tamanho.addEventListener("change", resetar);
      filtros.append(campo("Buscar nas propostas", busca), campo("Resultado", filtro), campo("Registros por página", tamanho),
        botao("Limpar filtros da prévia", "bf-importacao-limpar-filtros", () => { busca.value = ""; filtro.value = ""; resetar(); }));
      const rolagem = criar("div", "", "rolagem base-fiscal-rolagem"); rolagem.tabIndex = 0;
      rolagem.setAttribute("role", "region"); rolagem.setAttribute("aria-label", "Prévia de importação das empresas");
      const tabela = criar("table", "", "base-fiscal-tabela"), cabecalho = criar("thead"), titulos = criar("tr");
      for (const nome of ["Empresa / CNPJ propostos", "Resultado", "Revisão / origem"]) {
        const th = criar("th", nome); th.setAttribute("scope", "col"); titulos.append(th);
      }
      cabecalho.append(titulos); const corpo = criar("tbody"); corpo.id = "bf-importacao-corpo";
      tabela.append(cabecalho, corpo); rolagem.append(tabela);
      const navegacao = criar("div", "", "conc-paginacao base-fiscal-paginacao");
      const anterior = botao("‹ Anterior", "bf-importacao-anterior", () => { if (pagina > 1) { pagina--; listar(); } });
      const proxima = botao("Próxima ›", "bf-importacao-proxima", () => { if (!proxima.disabled) { pagina++; listar(); } });
      const info = criar("span"); info.id = "bf-importacao-pagina"; info.setAttribute("aria-live", "polite");
      navegacao.append(anterior, info, proxima); alvoRevisao.append(filtros, rolagem, navegacao);
      function listar() {
        const termo = BaseFiscalUI.normalizar(busca.value);
        const linhas = dados.linhas.filter(l => (!filtro.value || l.status === filtro.value) && (!termo ||
          BaseFiscalUI.normalizar([l.id, l.aba, ...Object.values(l.original || {}), ...Object.values(l.proposto || {}),
            ...Object.values(l.efetivo || {}), l.observacao].join(" ")).includes(termo)));
        const limite = tamanho.value === "50" ? 50 : 25;
        pagina = Math.min(pagina, Math.max(1, Math.ceil(linhas.length / limite))); const inicio = (pagina - 1) * limite;
        corpo.textContent = "";
        if (!linhas.length) {
          const tr = criar("tr"), td = criar("td", "Nenhum registro corresponde aos filtros.", "base-fiscal-vazio"); td.colSpan = 3; tr.append(td); corpo.append(tr);
        }
        for (const [indice, l] of linhas.slice(inicio, inicio + limite).entries()) {
          const tr = criar("tr"); tr.setAttribute("data-registro", l.id);
          const empresa = criar("td"), efetivo = l.efetivo || {};
          empresa.append(criar("strong", efetivo.nome || "Nome pendente"), criar("span", efetivo.documento || "CNPJ pendente", "base-fiscal-secundario"));
          if (efetivo.sem_movimento === true) empresa.append(criar("span", "Sem movimento · permanece na carteira", "base-fiscal-marcador"));
          const revisao = criar("td"); revisao.append(criar("p", `${l.aba} · linha ${l.linha} · ID ${l.id}`));
          for (const pendencia of l.pendencias || []) revisao.append(criar("p", pendencia, "base-fiscal-pendencias"));
          if (l.observacao) revisao.append(criar("p", `Justificativa / observação: ${l.observacao}`));
          const detalhe = criar("tr", "", "base-fiscal-origem-linha"); detalhe.hidden = true; detalhe.id = `bf-importacao-detalhe-${indice}`;
          const conteudo = criar("td"); conteudo.colSpan = 3; detalhe.append(conteudo);
          const abrir = botao(`Conferir proposta: ${l.aba} · linha ${l.linha}`, "", () => {
            detalhe.hidden = !detalhe.hidden; abrir.setAttribute("aria-expanded", !detalhe.hidden);
            if (!detalhe.hidden && !conteudo.children.length) mostrarDetalhes(conteudo, l);
          });
          abrir.setAttribute("aria-expanded", "false"); abrir.setAttribute("aria-controls", detalhe.id); revisao.append(abrir);
          tr.append(empresa, criar("td", rotulos[l.status]), revisao); corpo.append(tr, detalhe);
        }
        info.textContent = linhas.length ? `${inicio + 1}–${Math.min(inicio + limite, linhas.length)} de ${linhas.length} registro(s) filtrado(s) · ${dados.contagens.linhas} na prévia`
          : `0 registro(s) filtrado(s) · ${dados.contagens.linhas} na prévia`;
        anterior.disabled = pagina <= 1; proxima.disabled = inicio + limite >= linhas.length;
      }
      function mostrarDetalhes(conteudo, linha) {
        conteudo.append(criar("strong", `Origem: ${linha.aba} · linha ${linha.linha} · ID ${linha.id}`));
        const grade = criar("div", "", "base-fiscal-origem-grade");
        for (const [chave, rotulo] of Object.entries(campos)) {
          const campo = criar("div");
          campo.append(criar("strong", rotulo), criar("p", `Original: ${linha.original?.[chave] || "Não informado"}`),
            criar("p", `Proposta: ${linha.proposto?.[chave] || "Preservar original"}`), criar("p", `Efetivo: ${linha.efetivo?.[chave] || "Não informado"}`));
          for (const alteracao of (linha.alteracoes || []).filter(a => a.campo === chave)) campo.append(criar("p", `Célula da correção: ${alteracao.celula}`));
          grade.append(campo);
        }
        conteudo.append(grade, criar("p", `Decisão sobre duplicidade: ${linha.decisao || "Não informada"}`));
        for (const aviso of linha.avisos || []) conteudo.append(criar("p", aviso, "dica"));
        if (linha.cadastro) {
          const c = linha.cadastro;
          conteudo.append(criar("strong", `Cadastro encontrado · ID ${c.id} · revisão ${c.revision}`),
            criar("p", `Empresa: ${c.nome}; CNPJ: ${c.documento}; contato: ${c.contato_nome || "Não informado"}; situação: ${c.situacao}.`),
            criar("p", "Nenhum dado desse cadastro será substituído nesta prévia.", "dica"));
        } else conteudo.append(criar("p", "Nenhum cadastro associado a esta linha na prévia.", "dica"));
      }
      listar();
    }

    function desenharOrigem(alvoOrigem, linha, porId) {
      alvoOrigem.append(criar("strong", `${linha.aba} · linha ${linha.linha}`));
      if (linha.duplicado_em?.length) {
        const locais = linha.duplicado_em.map(id => porId.get(id)).filter(Boolean).map(l => `${l.aba} · linha ${l.linha}`);
        alvoOrigem.append(criar("p", `CNPJ também presente em: ${locais.join("; ")}.`));
      }
      const grade = criar("div", "", "base-fiscal-origem-grade");
      for (const [chave, rotulo] of [["nome", "Empresa"], ["documento", "CNPJ"], ["regime", "Regime"],
        ["responsavel_fiscal", "Responsável Fiscal (escritório)"], ["contato_nome", "Contato da empresa"]]) {
        const origem = linha.origem?.[chave];
        if (!origem) continue;
        const bloco = criar("div");
        bloco.append(criar("strong", rotulo), criar("p", `Célula: ${origem.celula}; origem: ${origem.celula_origem}`),
          criar("p", `Informado: ${origem.formula ? "[fórmula não lida]" : origem.valor_informado || "(vazio)"}`),
          criar("p", `Formato da célula: ${origem.formato || "Não informado"}`));
        if (origem.intervalo_mesclado) bloco.append(criar("p", `Mesclagem: ${origem.intervalo_mesclado}`));
        if (origem.propagado) bloco.append(criar("p", "Contato propagado da célula de origem na mesclagem."));
        if (origem.formula) bloco.append(criar("p", "Fórmula não executada nem usada como valor."));
        grade.append(bloco);
      }
      alvoOrigem.append(grade);
    }
  },
};

Abas.registrar("clientes", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Clientes</h2>
      <p class="dica">O cadastro dos clientes do escritório, no lugar da
         planilha de senhas. As senhas ficam <b>criptografadas</b>: aparecem
         uma por vez, para quem tem permissão, depois de confirmar a própria
         senha — e cada consulta fica registrada.</p>
      <p id="cli-status" class="status"></p>
    </div>

    <div class="cartoes" id="cli-cartoes"></div>

    <div class="caixa">
      <nav class="conc-subtelas" id="cli-subtelas">
        <button data-sub="clientes" class="ativa" type="button">Clientes</button>
        <button data-sub="vencimentos" type="button">Vencimentos</button>
        <button data-sub="importar" type="button">Importar</button>
        <button data-sub="acessos" type="button">Quem viu senhas</button>
      </nav>

      <section id="cli-sub-clientes" class="conc-sub">
        <div id="cli-novo" class="oculto">
          <div class="linha-form">
            <label>Nome do cliente <input id="cli-n-nome" type="text"></label>
            <label>CNPJ ou CPF <input id="cli-n-doc" type="text" maxlength="18"></label>
            <label>Município <input id="cli-n-municipio" type="text"></label>
            <label>Contato <input id="cli-n-contato" type="text"></label>
            <label>E-mail <input id="cli-n-email" type="email"></label>
            <button id="cli-criar" class="botao-primario" type="button">Cadastrar cliente</button>
          </div>
          <hr class="conc-divisor">
        </div>
        <div class="linha-form">
          <label>Buscar <input id="cli-f-texto" type="search" placeholder="Nome, CNPJ, IE ou IM"></label>
          <label>Situação <select id="cli-f-situacao"><option value="">Todas</option></select></label>
          <label>Município <select id="cli-f-municipio"><option value="">Todos</option></select></label>
          <label class="pat-checkbox"><span>Só com pendência</span>
            <input id="cli-f-pendencia" type="checkbox"></label>
          <button id="cli-limpar" type="button">Limpar</button>
          <button id="cli-exportar" type="button" class="oculto">Exportar (.xlsx)</button>
        </div>
        <div class="rolagem"><table id="cli-lista">
          <thead><tr><th>Cliente</th><th>CNPJ/CPF</th><th>Situação</th>
            <th>Município</th><th>Certificado vence</th><th>Pendências</th></tr></thead>
          <tbody></tbody>
        </table></div>
        <div class="conc-paginacao">
          <button id="cli-anterior" type="button">&#8249; Anterior</button>
          <span id="cli-pagina"></span>
          <button id="cli-proxima" type="button">Próxima &#8250;</button>
        </div>
        <div id="cli-detalhe" class="oculto"></div>
      </section>

      <section id="cli-sub-vencimentos" class="conc-sub oculto">
        <p class="dica">Certificados vigentes de clientes que não estão baixados,
           do que vence primeiro para o último. "Renovação em andamento" tira o
           certificado do aviso do topo, mas não desta lista.</p>
        <div class="linha-form">
          <label>Faixa <select id="cli-v-faixa"></select></label>
          <label>Cliente <input id="cli-v-texto" type="search"></label>
        </div>
        <div class="rolagem"><table id="cli-vencimentos">
          <thead><tr><th>Cliente</th><th>Titular</th><th>Tipo</th><th>Vence em</th>
            <th class="conc-num">Dias</th><th>Faixa</th><th>Renovação</th><th>Onde está</th></tr></thead>
          <tbody></tbody>
        </table></div>
        <div id="cli-faixas" class="linha-form oculto">
          <label>Avisar com antecedência de (dias, separados por vírgula)
            <input id="cli-faixas-valor" type="text" placeholder="15, 20, 30"></label>
          <button id="cli-faixas-salvar" type="button">Salvar prazos</button>
        </div>
      </section>

      <section id="cli-sub-importar" class="conc-sub oculto">
        <div id="cli-imp-area">
          <section id="cli-base-fiscal" aria-label="Conferência da base Fiscal"></section>
          <hr class="conc-divisor">
          <h3 class="pat-titulo">Planilha de senhas atual</h3>
          <p class="dica">Envie a planilha (.xlsx). Nada é gravado antes de
             você conferir a prévia. A cor da linha vira a situação do cliente
             (vermelho = baixada, laranja = inativa, cinza = não é cliente,
             rosa = Lauro de Freitas). O arquivo é apagado do servidor assim
             que é lido.</p>
          <div class="linha-form">
            <label>Planilha <input id="cli-imp-planilha" type="file" accept=".xlsx"></label>
            <button id="cli-imp-planilha-enviar" class="botao-primario" type="button">Ver prévia</button>
          </div>
          <div id="cli-imp-planilha-previa"></div>
          <hr class="conc-divisor">
          <h3 class="pat-titulo">Certificados da pasta da rede</h3>
          <p class="dica">Num computador do escritório que enxerga a pasta,
             rode <code>coletar-certificados.py "X:\\CERTIFICADOS DIGITAIS
             ATUALIZADOS"</code> e envie aqui o arquivo .json que ele gravar.
             O arquivo não leva senha nem certificado; cada certificado é
             ligado ao cliente pelo CNPJ que está dentro dele.</p>
          <div class="linha-form">
            <label>Arquivo de coleta <input id="cli-imp-coleta" type="file" accept=".json"></label>
            <button id="cli-imp-coleta-enviar" class="botao-primario" type="button">Ver prévia</button>
          </div>
          <div id="cli-imp-coleta-previa"></div>
        </div>
        <p id="cli-imp-sem" class="dica oculto">Você não tem permissão para
           importar. Fale com o administrador.</p>
      </section>

      <section id="cli-sub-acessos" class="conc-sub oculto">
        <div class="linha-form">
          <label>Usuário <input id="cli-a-usuario" type="text"></label>
          <label>De <input id="cli-a-de" type="date"></label>
          <label>Até <input id="cli-a-ate" type="date"></label>
          <button id="cli-a-buscar" type="button">Buscar</button>
        </div>
        <div class="rolagem"><table id="cli-acessos">
          <thead><tr><th>Quando</th><th>Usuário</th><th>Cliente</th><th>Senha</th>
            <th>Ação</th><th>Resultado</th><th>IP</th></tr></thead>
          <tbody></tbody>
        </table></div>
      </section>
    </div>`;

  const $ = (id) => document.getElementById(id);
  const status = (t) => { $("cli-status").textContent = t; };
  const estado = { pagina: 1, catalogo: null, desbloqueadoAte: null, detalheId: null };
  const pode = {
    editar: Sessao.pode("clientes.editar"),
    importar: Sessao.pode("clientes.importar"),
    exportar: Sessao.pode("clientes.exportar"),
    ver: Sessao.pode("cofre.ver"),
    gravar: Sessao.pode("cofre.editar"),
    faixas: Sessao.pode("vencimentos.configurar"),
    acessos: Sessao.pode("admin.historico"),
  };

  // ------------------------------------------------------------------
  // Helpers

  function celula(texto, classe) {
    const td = document.createElement("td");
    td.textContent = texto ?? "";
    if (classe) td.className = classe;
    return td;
  }

  function tabela(cabecalhos, linhas) {
    const wrap = document.createElement("div");
    wrap.className = "rolagem";
    const t = document.createElement("table");
    const tr = document.createElement("tr");
    for (const c of cabecalhos) {
      const th = document.createElement("th"); th.textContent = c; tr.appendChild(th);
    }
    const thead = document.createElement("thead"); thead.appendChild(tr);
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

  function bloco(titulo) {
    const div = document.createElement("div");
    div.className = "caixa conc-bloco";
    const h = document.createElement("h3"); h.textContent = titulo;
    div.appendChild(h);
    return div;
  }

  function botao(rotulo, aoClicar, classe) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = rotulo;
    if (classe) b.className = classe;
    b.addEventListener("click", aoClicar);
    return b;
  }

  function opcoes(select, itens, vazio) {
    select.textContent = "";
    if (vazio) {
      const o = document.createElement("option"); o.value = ""; o.textContent = vazio;
      select.appendChild(o);
    }
    for (const i of itens) {
      const o = document.createElement("option"); o.value = i.chave; o.textContent = i.rotulo;
      select.appendChild(o);
    }
  }

  const data = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
  /* O servidor grava em UTC ("...+00:00"); a tela mostra no horário local.
     Carimbo sem fuso (coleta, gerada no computador do escritório) já é local. */
  const quando = (iso) => {
    if (!iso) return "";
    if (/[+-]\d\d:\d\d$|Z$/.test(iso)) {
      return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit",
        year: "numeric", hour: "2-digit", minute: "2-digit" }).replace(",", "");
    }
    return `${data(iso)} ${iso.slice(11, 16)}`;
  };
  const rotuloCampo = (valor, situacao) => valor ||
    (estado.catalogo.situacoes_campo.find((s) => s.chave === situacao)?.rotulo ?? "—");

  function classeFaixa(faixa) {
    if (faixa === "vencido") return "cli-faixa vencido";
    if (faixa && faixa.startsWith("ate_")) return "cli-faixa perto";
    if (faixa === "em_dia") return "cli-faixa em-dia";
    return "";
  }

  function chipFaixa(faixa, rotulo) {
    const td = document.createElement("td");
    if (!faixa) { td.textContent = "—"; return td; }
    const s = document.createElement("span");
    s.className = classeFaixa(faixa);
    s.textContent = rotulo;
    td.appendChild(s);
    return td;
  }

  // ------------------------------------------------------------------
  // Subtelas

  const SUBS = ["clientes", "vencimentos", "importar", "acessos"];
  function abrirSub(nome) {
    $("cli-subtelas").querySelectorAll("button[data-sub]").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    SUBS.forEach((s) => $(`cli-sub-${s}`).classList.toggle("oculto", s !== nome));
    if (nome === "clientes") carregarLista();
    if (nome === "vencimentos") carregarVencimentos();
    if (nome === "acessos") carregarAcessos();
  }
  $("cli-subtelas").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-sub]");
    if (b) abrirSub(b.dataset.sub);
  });
  if (!pode.acessos) $("cli-subtelas").querySelector('[data-sub="acessos"]').classList.add("oculto");
  document.addEventListener("clientes:vencimentos", () => abrirSub("vencimentos"));

  // ------------------------------------------------------------------
  // Resumo

  function cartao(valor, rotulo, cor) {
    const caixa = document.createElement("div");
    caixa.className = cor ? `cartao ${cor}` : "cartao";
    const v = document.createElement("div"); v.className = "valor"; v.textContent = valor;
    const r = document.createElement("div"); r.className = "rotulo"; r.textContent = rotulo;
    caixa.append(v, r);
    return caixa;
  }

  async function atualizarResumo() {
    try {
      const r = await api("/api/clientes/resumo");
      const alvo = $("cli-cartoes");
      alvo.textContent = "";
      const ps = r.por_situacao;
      const venc = r.vencimentos.contagem;
      const perto = Object.entries(venc).filter(([k]) => k.startsWith("ate_"))
        .reduce((s, [, n]) => s + n, 0);
      alvo.append(
        cartao(String(ps.ativo || 0), "Ativos", ""),
        cartao(String(ps.inativo || 0), "Inativos", ""),
        cartao(String((ps.baixado || 0) + (ps.nao_cliente || 0)), "Baixados ou ex-clientes", ""),
        cartao(String(r.com_pendencia), "Com pendência", r.com_pendencia ? "ambar" : ""),
        cartao(String(venc.vencido || 0), "Certificados vencidos", venc.vencido ? "vermelho" : ""),
        cartao(String(perto), `Vencem em até ${r.vencimentos.faixas.at(-1)} dias`, perto ? "ambar" : ""));
      const municipio = $("cli-f-municipio");
      const atual = municipio.value;
      opcoes(municipio, r.municipios.map((m) => ({ chave: m, rotulo: m })), "Todos");
      municipio.value = atual;
    } catch (erro) { status(erro.message); }
  }

  // ------------------------------------------------------------------
  // Lista

  function filtros() {
    const p = {};
    const texto = $("cli-f-texto").value.trim();
    if (texto) p.texto = texto;
    if ($("cli-f-situacao").value) p.situacao = $("cli-f-situacao").value;
    if ($("cli-f-municipio").value) p.municipio = $("cli-f-municipio").value;
    if ($("cli-f-pendencia").checked) p.com_pendencia = "true";
    return p;
  }

  async function carregarLista() {
    try {
      const pagina = await api("/api/clientes?" + new URLSearchParams({
        ...filtros(), pagina: estado.pagina }));
      const corpo = $("cli-lista").querySelector("tbody");
      corpo.textContent = "";
      for (const c of pagina.itens) {
        const tr = document.createElement("tr");
        tr.className = "conc-clicavel";
        tr.tabIndex = 0;
        tr.append(
          celula(c.nome), celula(c.documento || c.documento_informado || "—"),
          celula(c.situacao_rotulo, c.situacao === "baixado" ? "conc-erro"
            : c.situacao === "inativo" ? "conc-alerta" : ""),
          celula(c.municipio || "—"), celula(data(c.certificado_fim) || "—"),
          celula(c.pendencias.length ? String(c.pendencias.length) : "",
                 c.pendencias.length ? "conc-alerta" : ""));
        tr.addEventListener("click", () => abrirDetalhe(c.id));
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter") abrirDetalhe(c.id); });
        corpo.appendChild(tr);
      }
      estado.pagina = pagina.pagina;
      $("cli-pagina").textContent = pagina.total
        ? `Página ${pagina.pagina} de ${pagina.paginas} — ${pagina.total} cliente(s)`
        : "Nenhum cliente com esses filtros.";
      $("cli-anterior").disabled = pagina.pagina <= 1;
      $("cli-proxima").disabled = pagina.pagina >= pagina.paginas;
      await atualizarResumo();
    } catch (erro) { status(erro.message); }
  }

  let debounce = null;
  function recarregar() {
    estado.pagina = 1;
    clearTimeout(debounce);
    debounce = setTimeout(carregarLista, 250);
  }
  $("cli-f-texto").addEventListener("input", recarregar);
  for (const id of ["cli-f-situacao", "cli-f-municipio", "cli-f-pendencia"]) {
    $(id).addEventListener("change", recarregar);
  }
  $("cli-limpar").addEventListener("click", () => {
    $("cli-f-texto").value = ""; $("cli-f-situacao").value = "";
    $("cli-f-municipio").value = ""; $("cli-f-pendencia").checked = false;
    recarregar();
  });
  $("cli-anterior").addEventListener("click", () => {
    estado.pagina = Math.max(1, estado.pagina - 1); carregarLista();
  });
  $("cli-proxima").addEventListener("click", () => { estado.pagina += 1; carregarLista(); });

  if (pode.exportar) {
    $("cli-exportar").classList.remove("oculto");
    $("cli-exportar").addEventListener("click", async () => {
      try {
        await apiDownload("/api/clientes/exportar?" + new URLSearchParams(filtros()),
                          { method: "POST" });
      } catch (erro) { toast(erro.message, "erro"); }
    });
  }

  if (pode.editar) {
    $("cli-novo").classList.remove("oculto");
    $("cli-criar").addEventListener("click", async () => {
      const nome = $("cli-n-nome").value.trim();
      if (!nome) { toast("Informe o nome do cliente.", "erro"); return; }
      try {
        const r = await api("/api/clientes", { json: {
          nome, documento: $("cli-n-doc").value.trim(),
          municipio: $("cli-n-municipio").value.trim(),
          contato_nome: $("cli-n-contato").value.trim(), contato_email: $("cli-n-email").value.trim() } });
        toast("Cliente cadastrado.");
        for (const id of ["cli-n-nome", "cli-n-doc", "cli-n-municipio", "cli-n-contato", "cli-n-email"]) $(id).value = "";
        await carregarLista();
        await abrirDetalhe(r.id);
      } catch (erro) { toast(erro.message, "erro"); }
    });
  }

  // ------------------------------------------------------------------
  // Cofre: desbloqueio e revelação

  function cofreAberto() {
    return estado.desbloqueadoAte && new Date(estado.desbloqueadoAte) > new Date();
  }

  const textoCofreAberto = () =>
    `Cofre aberto até ${new Date(estado.desbloqueadoAte).toLocaleTimeString("pt-BR",
      { hour: "2-digit", minute: "2-digit" })}. Cada senha vista fica registrada.`;

  async function desbloquear() {
    const r = await formularioModal("Abrir o cofre de senhas", [
      { nome: "senha", rotulo: "Sua senha de acesso ao sistema", tipo: "password",
        obrigatorio: true }],
      { textoConfirmar: "Abrir cofre",
        ajuda: `Confirme a sua senha para ver senhas de clientes. O cofre fica
                aberto por ${estado.catalogo.desbloqueio_minutos} minutos nesta sessão.` });
    if (!r) return false;
    try {
      const resposta = await api("/api/clientes/cofre/desbloquear", { json: { senha: r.senha } });
      estado.desbloqueadoAte = resposta.desbloqueado_ate;
      const aviso = $("cli-cofre-aviso");
      if (aviso) aviso.textContent = textoCofreAberto();
      return true;
    } catch (erro) { toast(erro.message, "erro"); return false; }
  }

  async function revelar(senha, celulaValor) {
    if (!cofreAberto() && !(await desbloquear())) return;
    let r;
    try {
      r = await api(`/api/clientes/senhas/${senha.id}/revelar`, { method: "POST" });
    } catch (erro) {
      if (erro.codigo === "COFRE_BLOQUEADO") {
        estado.desbloqueadoAte = null;
        if (await desbloquear()) return revelar(senha, celulaValor);
        return;
      }
      toast(erro.message, "erro");
      return;
    }
    celulaValor.textContent = "";
    const valor = document.createElement("code");
    valor.className = "cli-senha";
    celulaValor.classList.add("cli-acoes");
    valor.textContent = r.valor;
    const copiar = botao("Copiar", async () => {
      try { await navigator.clipboard.writeText(valor.textContent); toast("Senha copiada."); }
      catch { toast("Não foi possível copiar. Selecione e copie à mão.", "erro"); }
    });
    celulaValor.append(valor, copiar);
    r.valor = "";
    setTimeout(() => {
      if (!celulaValor.isConnected) return;
      celulaValor.textContent = "••••••••";
      celulaValor.classList.remove("cli-acoes");
    }, 30000);
  }

  async function editarSenha(cliente, senha) {
    const campos = [];
    if (!senha) {
      campos.push({ nome: "portal", rotulo: "Portal", obrigatorio: true,
                    placeholder: "e-CAC, Domínio, ..." });
      campos.push({ nome: "usuario_portal", rotulo: "Usuário no portal" });
    }
    campos.push({ nome: "valor", rotulo: "Senha (deixe em branco para marcar só a situação)",
                  tipo: "password" });
    campos.push({ nome: "situacao", rotulo: "Situação, se não houver senha", tipo: "select",
                  opcoes: [{ valor: "", rotulo: "—" }, ...estado.catalogo.situacoes_senha
                    .map((s) => ({ valor: s.chave, rotulo: s.rotulo }))] });
    const r = await formularioModal(senha ? `Trocar: ${senha.rotulo}${senha.portal ? " — " + senha.portal : ""}`
                                          : "Adicionar outro portal", campos);
    if (!r) return;
    try {
      await api(`/api/clientes/${cliente.id}/senhas`, { method: "PUT", json: {
        campo: senha ? senha.campo : "outro",
        portal: senha ? senha.portal : r.portal,
        usuario_portal: senha ? senha.usuario_portal : r.usuario_portal,
        segredo_id: senha && senha.campo === "outro" ? senha.id : null,
        valor: r.valor, situacao: r.situacao } });
      toast("Senha gravada.");
      await abrirDetalhe(cliente.id);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  // ------------------------------------------------------------------
  // Detalhe

  async function editarCliente(d) {
    const situacoes = [{ valor: "", rotulo: "— (usar o valor)" },
      ...estado.catalogo.situacoes_campo.map((s) => ({ valor: s.chave, rotulo: s.rotulo }))];
    const r = await formularioModal("Editar cliente", [
      { nome: "nome", rotulo: "Nome", valor: d.nome, obrigatorio: true },
      { nome: "documento", rotulo: "CNPJ ou CPF", valor: d.documento_digitos },
      { nome: "municipio", rotulo: "Município", valor: d.municipio },
      { nome: "contato_nome", rotulo: "Contato", valor: d.contato_nome },
      { nome: "contato_email", rotulo: "E-mail do contato", tipo: "email", valor: d.contato_email },
      { nome: "ie", rotulo: "Inscrição estadual", valor: d.ie },
      { nome: "ie_situacao", rotulo: "Situação da IE", tipo: "select", opcoes: situacoes },
      { nome: "im", rotulo: "Inscrição municipal", valor: d.im },
      { nome: "im_situacao", rotulo: "Situação da IM", tipo: "select", opcoes: situacoes },
      { nome: "iptu", rotulo: "IPTU", valor: d.iptu },
      { nome: "observacao", rotulo: "Observação", tipo: "textarea", valor: d.observacao },
    ]);
    if (!r) return;
    try {
      await api(`/api/clientes/${d.id}`, { method: "PUT", json: {
        ...r, iptu_situacao: r.iptu ? "" : d.iptu_situacao, revision: d.revision } });
      toast("Cliente atualizado.");
      await carregarLista();
      await abrirDetalhe(d.id);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  async function mudarSituacao(d) {
    const r = await formularioModal("Mudar situação", [
      { nome: "situacao", rotulo: "Nova situação", tipo: "select", valor: d.situacao,
        opcoes: estado.catalogo.situacoes.map((s) => ({ valor: s.chave, rotulo: s.rotulo })) },
      { nome: "motivo", rotulo: "Motivo (obrigatório)", obrigatorio: true },
    ]);
    if (!r) return;
    try {
      await api(`/api/clientes/${d.id}/situacao`, { json: r });
      toast("Situação alterada.");
      await carregarLista();
      await abrirDetalhe(d.id);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  async function certificadoPorArquivo(d) {
    const r = await formularioModal("Ler certificado do arquivo", [
      { nome: "arquivo", rotulo: "Arquivo (.pfx, .p12, .cer, .crt)", tipo: "file",
        aceitar: ".pfx,.p12,.cer,.crt", obrigatorio: true },
      { nome: "senha", rotulo: "Senha do .pfx (não é guardada)", tipo: "password" },
      { nome: "local_guarda", rotulo: "Onde o certificado está guardado" },
    ], { textoConfirmar: "Ler e cadastrar",
         ajuda: "O arquivo e a senha só são usados para ler a validade e o titular. " +
                "Nenhum dos dois fica no sistema." });
    if (!r || !r.arquivo) return;
    const corpo = new FormData();
    corpo.append("arquivo", r.arquivo);
    corpo.append("senha", r.senha || "");
    corpo.append("local_guarda", r.local_guarda || "");
    try {
      const resposta = await api(`/api/clientes/${d.id}/certificados/arquivo`,
                                 { method: "POST", body: corpo });
      toast(`Certificado de ${resposta.titular_nome || "?"} até ${data(resposta.fim)}.`);
      await abrirDetalhe(d.id);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  async function certificadoManual(d) {
    const r = await formularioModal("Cadastrar certificado à mão", [
      { nome: "tipo", rotulo: "Tipo", tipo: "select",
        opcoes: estado.catalogo.tipos_certificado.map((t) => ({ valor: t, rotulo: t })) },
      { nome: "titular_nome", rotulo: "Titular" },
      { nome: "titular_documento", rotulo: "CNPJ/CPF do titular" },
      { nome: "inicio", rotulo: "Início da validade", tipo: "date" },
      { nome: "fim", rotulo: "Fim da validade", tipo: "date", obrigatorio: true },
      { nome: "local_guarda", rotulo: "Onde está (token, pasta...)" },
    ]);
    if (!r) return;
    try {
      await api(`/api/clientes/${d.id}/certificados`, { json: r });
      toast("Certificado cadastrado.");
      await abrirDetalhe(d.id);
    } catch (erro) { toast(erro.message, "erro"); }
  }

  function linhaCertificado(d, k) {
    const acoes = document.createElement("td");
    acoes.className = "cli-acoes";
    if (pode.editar && k.situacao === "vigente") {
      acoes.append(
        botao(k.renovacao_em_andamento ? "Desmarcar renovação" : "Renovação em andamento",
              async () => {
                try {
                  await api(`/api/clientes/certificados/${k.id}/renovacao`,
                            { json: { em_andamento: !k.renovacao_em_andamento } });
                  await abrirDetalhe(d.id); AvisoVencimentos.mostrar();
                } catch (erro) { toast(erro.message, "erro"); }
              }),
        botao("Não renovar", async () => {
          if (!(await confirmar("Não renovar", "Marcar este certificado para não ser renovado? Ele sai do painel de vencimentos."))) return;
          try {
            await api(`/api/clientes/certificados/${k.id}`, { method: "PUT",
                      json: { situacao: "nao_renovar" } });
            await abrirDetalhe(d.id);
          } catch (erro) { toast(erro.message, "erro"); }
        }));
    }
    return [k.tipo || "—", k.titular_nome || "—", k.titular_documento || "—",
            k.emissor || "—", data(k.fim), chipFaixa(k.faixa, k.faixa_rotulo),
            k.situacao_rotulo + (k.renovacao_em_andamento ? " · renovando" : ""),
            k.local_guarda || "—", acoes];
  }

  async function abrirDetalhe(id) {
    const alvo = $("cli-detalhe");
    alvo.classList.remove("oculto");
    alvo.textContent = "Carregando...";
    estado.detalheId = id;
    let d;
    try { d = await api(`/api/clientes/${id}`); }
    catch (erro) { alvo.textContent = erro.message; return; }
    alvo.textContent = "";

    const topo = bloco(d.nome);
    const linha = document.createElement("p");
    linha.className = "dica";
    linha.textContent = [d.documento || d.documento_informado || "sem CNPJ/CPF",
                         d.situacao_rotulo, d.municipio].filter(Boolean).join(" · ");
    topo.appendChild(linha);
    if (pode.editar) {
      const acoes = document.createElement("div");
      acoes.className = "linha-form conc-acoes";
      acoes.append(botao("Editar", () => editarCliente(d)),
                   botao("Mudar situação", () => mudarSituacao(d)));
      topo.appendChild(acoes);
    }
    topo.appendChild(tabela(["Inscrição estadual", "Inscrição municipal", "IPTU"], [[
      rotuloCampo(d.ie, d.ie_situacao), rotuloCampo(d.im, d.im_situacao),
      rotuloCampo(d.iptu, d.iptu_situacao)]]));
    const contato = document.createElement("p");
    contato.textContent = `Contato: ${d.contato_nome || "não informado"} · E-mail: ${d.contato_email || "não informado"}`;
    topo.appendChild(contato);
    if (d.observacao) {
      const obs = document.createElement("p"); obs.textContent = d.observacao;
      topo.appendChild(obs);
    }
    alvo.appendChild(topo);
    if (typeof TarefasCliente !== "undefined") {
      TarefasCliente.montar(alvo, d, () => abrirDetalhe(d.id)).catch(erro => toast(erro.message, "erro"));
    }

    if (d.pendencias.length) {
      const p = bloco("Pendências da importação");
      const ul = document.createElement("ul");
      for (const texto of d.pendencias) {
        const li = document.createElement("li"); li.textContent = texto; ul.appendChild(li);
      }
      p.appendChild(ul);
      alvo.appendChild(p);
    }

    // Senhas
    const cofre = bloco("Senhas de portais");
    const aviso = document.createElement("p");
    aviso.className = "dica";
    aviso.id = "cli-cofre-aviso";
    if (!estado.catalogo.cofre_disponivel) {
      aviso.className = "conc-erro";
      aviso.textContent = "Cofre desligado: falta a chave no servidor. As senhas " +
        "não podem ser vistas nem gravadas até o administrador configurá-la.";
    } else if (!pode.ver) {
      aviso.textContent = "Você vê quais senhas existem, mas não o valor. Fale com o " +
        "administrador se precisar.";
    } else {
      aviso.textContent = cofreAberto() ? textoCofreAberto()
        : "Para ver uma senha, clique em Ver e confirme a sua senha de acesso.";
    }
    cofre.appendChild(aviso);
    const linhasSenha = d.senhas.map((s) => {
      const valor = celula(s.presente ? "••••••••" : s.situacao_rotulo || "—",
                           s.presente ? "" : "conc-alerta");
      const acoes = document.createElement("td");
      acoes.className = "cli-acoes";
      if (s.presente && pode.ver && estado.catalogo.cofre_disponivel) {
        acoes.appendChild(botao("Ver", () => revelar(s, valor)));
      }
      if (pode.gravar && estado.catalogo.cofre_disponivel) {
        acoes.appendChild(botao("Trocar", () => editarSenha(d, s)));
        if (s.campo === "outro" && s.presente) {
          acoes.appendChild(botao("Remover", async () => {
            if (!(await confirmar("Remover senha", "Apagar esta senha do cofre?"))) return;
            try { await api(`/api/clientes/senhas/${s.id}`, { method: "DELETE" });
                  await abrirDetalhe(d.id); }
            catch (erro) { toast(erro.message, "erro"); }
          }));
        }
      }
      return [s.portal ? `${s.rotulo} — ${s.portal}` : s.rotulo, s.usuario_portal || "—",
              valor, quando(s.atualizado_em), s.atualizado_por || "—", acoes];
    });
    if (linhasSenha.length) {
      cofre.appendChild(tabela(["Senha", "Usuário", "Valor", "Atualizada em", "Por", ""],
                               linhasSenha));
    } else {
      const p = document.createElement("p"); p.textContent = "Nenhuma senha cadastrada.";
      cofre.appendChild(p);
    }
    if (pode.gravar && estado.catalogo.cofre_disponivel) {
      const acoes = document.createElement("div");
      acoes.className = "linha-form conc-acoes";
      const fixos = ["sefaz", "prefeitura", "codigo_acesso"]
        .filter((c) => !d.senhas.some((s) => s.campo === c));
      for (const campo of fixos) {
        const rotulo = estado.catalogo.campos_senha.find((c) => c.chave === campo).rotulo;
        acoes.appendChild(botao(`Cadastrar ${rotulo}`, () =>
          editarSenha(d, { campo, rotulo, portal: "", usuario_portal: "", id: null })));
      }
      acoes.appendChild(botao("Adicionar outro portal", () => editarSenha(d, null)));
      cofre.appendChild(acoes);
    }
    if (cofreAberto()) {
      cofre.appendChild(botao("Fechar o cofre agora", async () => {
        await api("/api/clientes/cofre/bloquear", { method: "POST" }).catch(() => {});
        estado.desbloqueadoAte = null;
        await abrirDetalhe(d.id);
      }));
    }
    alvo.appendChild(cofre);

    // Certificados
    const certs = bloco("Certificados digitais");
    if (d.certificados.length) {
      certs.appendChild(tabela(["Tipo", "Titular", "CNPJ/CPF", "Emissor", "Vence em",
                                "Faixa", "Situação", "Onde está", ""],
                               d.certificados.map((k) => linhaCertificado(d, k))));
    } else {
      const p = document.createElement("p"); p.textContent = "Nenhum certificado cadastrado.";
      certs.appendChild(p);
    }
    if (pode.editar) {
      const acoes = document.createElement("div");
      acoes.className = "linha-form conc-acoes";
      acoes.append(botao("Ler do arquivo (.pfx / .cer)", () => certificadoPorArquivo(d)),
                   botao("Cadastrar à mão", () => certificadoManual(d)));
      certs.appendChild(acoes);
    }
    alvo.appendChild(certs);

    if (d.licencas.length) {
      const lic = bloco("Licenças (da planilha)");
      lic.appendChild(tabela(["Licença", "Número", "Vencimento", "Situação"],
        d.licencas.map((l) => [l.rotulo, l.numero || "—", data(l.vencimento) || "—",
                               l.situacao_rotulo || (l.texto_original || "—")])));
      alvo.appendChild(lic);
    }

    const hist = bloco("Histórico");
    hist.appendChild(tabela(["Quando", "Campo", "Antes", "Depois", "Por"],
      d.alteracoes.map((a) => [quando(a.criada_em), a.campo, a.antes || "—",
                               a.depois || "—", a.usuario_login])));
    alvo.appendChild(hist);
    alvo.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------
  // Vencimentos

  async function carregarVencimentos() {
    try {
      const params = {};
      if ($("cli-v-faixa").value) params.faixa = $("cli-v-faixa").value;
      if ($("cli-v-texto").value.trim()) params.texto = $("cli-v-texto").value.trim();
      const r = await api("/api/clientes/vencimentos/lista?" + new URLSearchParams(params));
      const corpo = $("cli-vencimentos").querySelector("tbody");
      corpo.textContent = "";
      for (const k of r.itens) {
        const tr = document.createElement("tr");
        tr.className = "conc-clicavel";
        tr.append(celula(k.cliente_nome), celula(k.titular_nome || "—"),
                  celula(k.tipo || "—"), celula(data(k.fim)),
                  celula(String(k.dias), "conc-num"), chipFaixa(k.faixa, k.faixa_rotulo),
                  celula(k.renovacao_em_andamento ? `Em andamento (${k.renovacao_por})` : ""),
                  celula(k.local_guarda || "—"));
        tr.addEventListener("click", () => { abrirSub("clientes"); abrirDetalhe(k.cliente_id); });
        corpo.appendChild(tr);
      }
      if (!r.itens.length) {
        const tr = document.createElement("tr");
        const td = celula("Nenhum certificado nesta faixa."); td.colSpan = 8;
        tr.appendChild(td); corpo.appendChild(tr);
      }
      $("cli-faixas-valor").value = r.faixas.join(", ");
    } catch (erro) { status(erro.message); }
  }
  $("cli-v-faixa").addEventListener("change", carregarVencimentos);
  $("cli-v-texto").addEventListener("input", () => {
    clearTimeout(debounce); debounce = setTimeout(carregarVencimentos, 250);
  });
  if (pode.faixas) {
    $("cli-faixas").classList.remove("oculto");
    $("cli-faixas-salvar").addEventListener("click", async () => {
      const faixas = $("cli-faixas-valor").value.split(/[,;\s]+/).filter(Boolean).map(Number);
      try {
        await api("/api/clientes/vencimentos/faixas", { method: "PUT", json: { faixas } });
        toast("Prazos de aviso salvos.");
        estado.catalogo = await api("/api/clientes/catalogo");
        montarFaixas();
        await carregarVencimentos();
        AvisoVencimentos.mostrar();
      } catch (erro) { toast(erro.message, "erro"); }
    });
  }

  function montarFaixas() {
    const itens = [{ chave: "vencido", rotulo: "Vencidos" },
      ...estado.catalogo.faixas.map((f) => ({ chave: `ate_${f}`, rotulo: `Vencem em até ${f} dias` })),
      { chave: "em_dia", rotulo: "Em dia" }];
    opcoes($("cli-v-faixa"), itens, "Todas");
  }

  // ------------------------------------------------------------------
  // Importação

  function seletorDecisao(linha) {
    const td = document.createElement("td");
    const s = document.createElement("select");
    for (const [v, r] of [["incluir", "Incluir"], ["ignorar", "Ignorar"]]) {
      const o = document.createElement("option"); o.value = v; o.textContent = r;
      s.appendChild(o);
    }
    s.value = linha.acao;
    s.dataset.linha = String(linha.linha);
    s.dataset.sugerida = linha.acao;
    td.appendChild(s);
    return td;
  }

  async function previaPlanilha() {
    const arquivo = $("cli-imp-planilha").files[0];
    if (!arquivo) { toast("Escolha a planilha.", "erro"); return; }
    const alvo = $("cli-imp-planilha-previa");
    alvo.textContent = "Lendo a planilha...";
    let p;
    try { p = await apiUpload("/api/clientes/importar/planilha", arquivo); }
    catch (erro) { alvo.textContent = ""; toast(erro.message, "erro"); return; }
    $("cli-imp-planilha").value = "";
    alvo.textContent = "";
    const c = p.contagens;
    const resumo = document.createElement("p");
    resumo.textContent = `${c.total} linha(s): ${c.incluir} para incluir, ${c.ignorar} para ` +
      `ignorar, ${c.com_pendencia} com pendência. Colunas sem cabeçalho ignoradas: ` +
      `${p.colunas_sem_cabecalho.join(", ") || "nenhuma"}. A prévia vale ${p.expira_em_minutos} minutos.`;
    alvo.appendChild(resumo);
    const filtro = document.createElement("label");
    filtro.className = "pat-checkbox";
    const so = document.createElement("input"); so.type = "checkbox"; so.checked = true;
    const sp = document.createElement("span"); sp.textContent = "Mostrar só o que precisa de atenção";
    filtro.append(sp, so);
    alvo.appendChild(filtro);
    const linhas = p.linhas.map((l) => {
      const senhas = Object.values(l.segredos).filter((v) => v === "presente").length;
      const tr = [String(l.linha), l.nome || "—", l.documento || l.documento_informado || "—",
        l.situacao_rotulo + (l.municipio ? ` · ${l.municipio}` : ""),
        l.resultado === "novo" ? "Novo" : l.resultado === "atualiza" ? "Atualiza" : "—",
        senhas ? `${senhas} senha(s)` : "—",
        [l.motivo, ...l.pendencias].filter(Boolean).join(" ") || "—", seletorDecisao(l)];
      return tr;
    });
    const t = tabela(["Linha", "Cliente", "CNPJ/CPF", "Situação", "No sistema", "Senhas",
                      "Atenção", "Decisão"], linhas);
    alvo.appendChild(t);
    const corpo = t.querySelector("tbody");
    const aplicarFiltro = () => {
      [...corpo.rows].forEach((row, i) => {
        const l = p.linhas[i];
        const atencao = l.acao === "ignorar" || l.pendencias.length;
        row.classList.toggle("oculto", so.checked && !atencao);
      });
    };
    so.addEventListener("change", aplicarFiltro);
    aplicarFiltro();
    const acoes = document.createElement("div");
    acoes.className = "linha-form conc-acoes";
    acoes.append(
      botao("Confirmar importação", async () => {
        const decisoes = {};
        corpo.querySelectorAll("select[data-linha]").forEach((s) => {
          if (s.value !== s.dataset.sugerida) decisoes[s.dataset.linha] = s.value;
        });
        if (!(await confirmar("Importar planilha",
              "Gravar os clientes e as senhas desta prévia? As senhas serão criptografadas."))) return;
        try {
          const r = await api(`/api/clientes/importar/planilha/${p.token}/confirmar`,
                              { json: { decisoes } });
          alvo.textContent = "";
          toast(`Importado: ${r.criados} novo(s), ${r.atualizados} atualizado(s), ` +
                `${r.ignorados} ignorado(s).`);
          status("Importação concluída. Tire a planilha original de circulação: " +
                 "ela tem as senhas em texto aberto.");
          await carregarLista();
        } catch (erro) { toast(erro.message, "erro"); }
      }, "botao-primario"),
      botao("Descartar prévia", async () => {
        await api(`/api/clientes/importar/${p.token}`, { method: "DELETE" }).catch(() => {});
        alvo.textContent = "";
      }));
    alvo.appendChild(acoes);
  }

  const ROTULO_COLETA = { casou: "Liga ao cliente", sem_cliente: "Sem cliente com este CNPJ",
                          nao_lido: "Não foi lido" };
  const ROTULO_PROBLEMA = {
    SEM_CERTIFICADO: "sem .pfx/.cer", SEM_INFO: "sem _info", SEM_SENHA: "sem senha no _info",
    SENHA_NAO_ABRE: "senha do _info não abre", CERTIFICADO_INVALIDO: "arquivo inválido",
    VARIOS_CERTIFICADOS: "mais de um certificado", VALIDADE_DIVERGENTE: "validade do _info diferente",
    DOCUMENTO_DIVERGENTE: "CNPJ do _info diferente" };

  async function previaColeta() {
    const arquivo = $("cli-imp-coleta").files[0];
    if (!arquivo) { toast("Escolha o arquivo de coleta.", "erro"); return; }
    const alvo = $("cli-imp-coleta-previa");
    alvo.textContent = "Lendo a coleta...";
    let p;
    try { p = await apiUpload("/api/clientes/importar/coleta", arquivo); }
    catch (erro) { alvo.textContent = ""; toast(erro.message, "erro"); return; }
    $("cli-imp-coleta").value = "";
    alvo.textContent = "";
    const resumo = document.createElement("p");
    resumo.textContent = `Coleta de ${quando(p.gerada_em)}: ` + Object.entries(p.contagens)
      .map(([k, n]) => `${n} ${ROTULO_COLETA[k] ? ROTULO_COLETA[k].toLowerCase() : k}`).join(", ") + ".";
    alvo.appendChild(resumo);
    alvo.appendChild(tabela(["Pasta", "Titular", "CNPJ/CPF", "Vence em", "Resultado", "Cliente",
                             "Problemas"],
      p.itens.map((i) => [i.pasta, i.titular_nome || "—", i.titular_documento || "—",
        data(i.fim) || "—", ROTULO_COLETA[i.resultado] || i.resultado, i.cliente_nome || "—",
        i.problemas.map((x) => ROTULO_PROBLEMA[x] || x).join(", ") || "—"])));
    const acoes = document.createElement("div");
    acoes.className = "linha-form conc-acoes";
    acoes.append(
      botao("Confirmar certificados", async () => {
        try {
          const r = await api(`/api/clientes/importar/coleta/${p.token}/confirmar`,
                              { method: "POST" });
          alvo.textContent = "";
          toast(`Certificados: ${r.novos} novo(s), ${r.atualizados} atualizado(s), ` +
                `${r.sem_cliente} sem cliente, ${r.nao_lidos} não lido(s).`);
          AvisoVencimentos.mostrar();
          await atualizarResumo();
        } catch (erro) { toast(erro.message, "erro"); }
      }, "botao-primario"),
      botao("Descartar prévia", async () => {
        await api(`/api/clientes/importar/${p.token}`, { method: "DELETE" }).catch(() => {});
        alvo.textContent = "";
      }));
    alvo.appendChild(acoes);
  }

  if (pode.importar) {
    BaseFiscalUI.montar($("cli-base-fiscal"));
    $("cli-imp-planilha-enviar").addEventListener("click", previaPlanilha);
    $("cli-imp-coleta-enviar").addEventListener("click", previaColeta);
  } else {
    $("cli-imp-area").classList.add("oculto");
    $("cli-imp-sem").classList.remove("oculto");
  }

  // ------------------------------------------------------------------
  // Quem viu senhas

  const ROTULO_RESULTADO = { ok: "Feito", negado: "Negado (sem permissão)",
                             limite: "Bloqueado pelo limite por hora" };
  const ROTULO_ACAO = { revelar: "Viu", gravar: "Gravou/trocou", remover: "Removeu" };

  async function carregarAcessos() {
    if (!pode.acessos) return;
    const params = {};
    if ($("cli-a-usuario").value.trim()) params.usuario_filtro = $("cli-a-usuario").value.trim();
    if ($("cli-a-de").value) params.de = $("cli-a-de").value;
    if ($("cli-a-ate").value) params.ate = $("cli-a-ate").value;
    try {
      const r = await api("/api/clientes/cofre/acessos?" + new URLSearchParams(params));
      const corpo = $("cli-acessos").querySelector("tbody");
      corpo.textContent = "";
      for (const a of r.itens) {
        const tr = document.createElement("tr");
        tr.append(celula(quando(a.quando)), celula(a.usuario), celula(a.cliente_nome || "—"),
                  celula(a.portal ? `${a.campo} — ${a.portal}` : a.campo || "—"),
                  celula(ROTULO_ACAO[a.acao] || a.acao),
                  celula(ROTULO_RESULTADO[a.resultado] || a.resultado,
                         a.resultado === "ok" ? "" : "conc-erro"),
                  celula(a.ip || "—"));
        corpo.appendChild(tr);
      }
    } catch (erro) { status(erro.message); }
  }
  $("cli-a-buscar").addEventListener("click", carregarAcessos);

  // ------------------------------------------------------------------
  // Início

  (async () => {
    try {
      estado.catalogo = await api("/api/clientes/catalogo");
    } catch (erro) { status(erro.message); return; }
    estado.desbloqueadoAte = estado.catalogo.desbloqueado_ate || null;
    opcoes($("cli-f-situacao"), estado.catalogo.situacoes, "Todas");
    montarFaixas();
    if (!estado.catalogo.cofre_disponivel) {
      status("Cofre de senhas desligado: falta a chave no servidor. O cadastro " +
             "funciona; as senhas não podem ser vistas nem gravadas.");
    }
    await carregarLista();
  })();
});
