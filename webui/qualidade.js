/* Gestão da qualidade: mesma sessão, clientes e setores; autorização no servidor. */
"use strict";

const QualidadeUI = {
  rotulos: {aberta: "Aberta", em_tratamento: "Em tratamento", resolvida: "Resolvida", encerrada: "Encerrada",
    aberto: "Aberto", em_andamento: "Em andamento", aguardando_validacao: "Aguardando validação", validado: "Validado",
    a_fazer: "A fazer", aguardando_cliente: "Aguardando cliente", concluida: "Concluída", conferida: "Conferida",
    devolvida: "Devolvida", dispensada: "Dispensada", corretiva: "Corretiva", preventiva: "Preventiva",
    baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica", erro: "Erro", atraso: "Atraso",
    comunicacao: "Comunicação", reclamacao: "Reclamação", retrabalho: "Retrabalho", pendencia: "Pendência",
    procedimento: "Procedimento", nao_conformidade: "Não conformidade", criacao: "Registro criado",
    edicao: "Dados atualizados", transicao: "Mudança de situação", situacao: "Mudança de situação",
    comentario: "Acompanhamento", anexo: "Evidência anexada", evidencia: "Evidência anexada", cancelamento: "Cancelamento"},
  el(tag, texto = "", classe = "") {
    const e = document.createElement(tag); e.textContent = texto;
    if (classe) e.className = classe;
    return e;
  },
  data(valor) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(valor || "");
    return m ? `${m[3]}/${m[2]}/${m[1]}` : "Não informado";
  },
  instante(valor) {
    const d = new Date(valor);
    return !valor || Number.isNaN(d.getTime()) ? "Não informado" : new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short", timeStyle: "short", timeZone: "America/Bahia",
    }).format(d);
  },
  hoje() {
    const partes = new Intl.DateTimeFormat("en", {timeZone: "America/Bahia", year: "numeric", month: "2-digit", day: "2-digit"}).formatToParts(new Date());
    const p = Object.fromEntries(partes.map(v => [v.type, v.value])); return `${p.year}-${p.month}-${p.day}`;
  },
  intervalo(periodo, referencia) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(referencia || "")) throw new Error("Informe a data de referência.");
    const d = new Date(referencia + "T12:00:00Z");
    if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== referencia) throw new Error("Data de referência inválida.");
    const iso = data => data.toISOString().slice(0, 10);
    if (periodo === "diario") return {de: referencia, ate: referencia};
    if (periodo === "semanal") {
      d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); const de = iso(d);
      d.setUTCDate(d.getUTCDate() + 6); return {de, ate: iso(d)};
    }
    if (periodo === "mensal") return {de: `${referencia.slice(0, 7)}-01`, ate: iso(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0, 12)))};
    throw new Error("Período desconhecido.");
  },
  moeda(valor) {
    if (valor === null || valor === undefined || valor === "") return "Sem dados";
    const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(String(valor));
    return m ? `R$ ${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${(m[3] || "").padEnd(2, "0")}` : "Indisponível";
  },
  numero(valor, unidade = "numero") {
    if (valor === null || valor === undefined || valor === "") return "Sem dados";
    const texto = String(valor).replace(".", ",");
    return texto + ({percentual: "%", horas: " h", dias: " dias"}[unidade] || "");
  },
  async montar(container) {
    const u = this, identidade = Sessao.usuario;
    if (!Sessao.pode("aba.qualidade")) return;
    const estado = {catalogo: null, visao: "painel", consulta: 0, detalhe: 0, encerrada: false, fecharForm: null};
    const valida = () => !estado.encerrada && Sessao.usuario === identidade && Sessao.pode("aba.qualidade");
    const pode = acao => valida() && Sessao.pode(`qualidade.${acao}`) && estado.catalogo?.permissoes?.[acao] === true;
    const exigir = acao => {
      if (!valida() || acao && !pode(acao)) throw new Error("A sessão ou as permissões mudaram. Entre novamente e atualize esta tela.");
    };
    const exigirAlteracao = permitido => {
      exigir();
      if (!permitido || !(pode("registrar") || pode("gerir"))) throw new Error("Você não pode alterar este registro. Atualize a tela para conferir o acesso.");
    };
    function botao(texto, id, acao, classe = "") {
      const b = u.el("button", texto, classe); b.type = "button";
      if (id) b.id = id;
      b.addEventListener("click", async () => {
        if (b.disabled) return;
        try { await acao(); } catch (e) { if (valida()) informar(e.message || "Não foi possível concluir a ação.", true); }
      });
      return b;
    }
    function campo(rotulo, input) {
      const l = u.el("label", "", "qua-campo"); l.append(u.el("span", rotulo), input); return l;
    }
    function opcoes(select, itens, vazio = "Todos", selecionado = "") {
      select.textContent = "";
      if (vazio !== null) { const o = u.el("option", vazio); o.value = ""; select.append(o); }
      for (const item of itens) { const o = u.el("option", item.rotulo ?? item.nome ?? String(item.id)); o.value = String(item.valor ?? item.id); select.append(o); }
      select.value = selecionado === null || selecionado === undefined ? "" : String(selecionado);
    }
    function select(id, itens = [], vazio = "Todos") {
      const e = u.el("select"); e.id = id; opcoes(e, itens, vazio); return e;
    }
    function input(id, tipo = "text", valor = "") { const e = u.el("input"); e.id = id; e.type = tipo; e.value = valor; return e; }
    const status = u.el("p", "Carregando gestão da qualidade…", "qua-status"); status.id = "qua-status";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    function informar(texto, erro = false) { status.textContent = texto; status.className = "qua-status" + (erro ? " qua-erro" : ""); }
    container.classList.add("qualidade-app");
    const cabecalho = u.el("header", "", "qua-cabecalho");
    const intro = u.el("div"); intro.append(u.el("p", "GESTÃO DA QUALIDADE", "qua-sobretitulo"),
      u.el("h2", "Uma visão clara. Uma operação melhor."),
      u.el("p", "Acompanhe a entrega, trate os desvios e registre a evolução de cada cliente.", "qua-subtitulo"));
    const atalhos = u.el("div", "", "qua-acoes");
    const atualizar = botao("Atualizar", "qua-atualizar", () => estado.catalogo ? carregar() : iniciar());
    atalhos.append(atualizar); cabecalho.append(intro, atalhos);
    const filtros = u.el("section", "", "qua-filtros"); filtros.setAttribute("aria-label", "Filtrar a gestão da qualidade");
    const cliente = select("qua-f-cliente"), setor = select("qua-f-setor"), responsavel = select("qua-f-responsavel");
    const periodo = select("qua-f-periodo", [{valor: "diario", rotulo: "Diário"}, {valor: "semanal", rotulo: "Semanal"},
      {valor: "mensal", rotulo: "Mensal"}, {valor: "personalizado", rotulo: "Personalizado"}], null); periodo.value = "mensal";
    const referencia = input("qua-f-referencia", "date", u.hoje());
    const de = input("qua-f-de", "date"), ate = input("qua-f-ate", "date"), situacao = select("qua-f-situacao");
    const moverPeriodo = () => {
      if (periodo.value !== "personalizado") {
        const intervalo = u.intervalo(periodo.value, referencia.value); de.value = intervalo.de; ate.value = intervalo.ate;
      }
    };
    moverPeriodo(); periodo.addEventListener("change", moverPeriodo); referencia.addEventListener("change", moverPeriodo);
    for (const e of [de, ate]) e.addEventListener("change", () => { periodo.value = "personalizado"; });
    filtros.append(campo("Cliente", cliente), campo("Setor", setor), campo("Colaborador", responsavel), campo("Período", periodo),
      campo("Referência", referencia), campo("De", de), campo("Até", ate), campo("Situação", situacao),
      botao("Aplicar filtros", "qua-aplicar", carregar, "botao-primario"),
      botao("Limpar filtros", "qua-limpar", async () => {
        cliente.value = ""; setor.value = ""; responsavel.value = ""; situacao.value = ""; periodo.value = "mensal";
        referencia.value = u.hoje(); moverPeriodo(); await carregar();
      }));
    const nav = u.el("nav", "", "qua-nav"); nav.setAttribute("aria-label", "Áreas da gestão da qualidade");
    const botoes = {};
    for (const [nome, rotulo] of [["painel", "Visão geral"], ["ocorrencias", "Ocorrências"], ["planos", "Planos de ação"],
      ["horas", "Tempo e custo"], ["relatorios", "Relatórios"], ["modelos", "Rotinas por setor"]]) {
      botoes[nome] = botao(rotulo, `qua-tab-${nome}`, () => trocar(nome)); nav.append(botoes[nome]);
    }
    const resumo = u.el("p", "", "qua-contexto"); resumo.id = "qua-contexto";
    const conteudo = u.el("div", "", "qua-conteudo"); conteudo.id = "qua-conteudo";
    const detalhe = u.el("aside", "", "qua-detalhe"); detalhe.id = "qua-detalhe"; detalhe.hidden = true;
    detalhe.setAttribute("aria-label", "Detalhes do registro");
    container.append(cabecalho, filtros, nav, status, resumo, conteudo, detalhe);

    const filtroAtual = () => {
      const valores = {cliente_id: cliente.value, setor_id: setor.value, responsavel_usuario_id: responsavel.value,
        de: de.value, ate: ate.value, situacao: estado.visao === "horas" ? "" : situacao.value};
      if (!valores.de || !valores.ate || valores.de > valores.ate) throw new Error("Informe um intervalo válido, com início anterior ou igual ao fim.");
      return Object.fromEntries(Object.entries(valores).filter(([, valor]) => valor !== ""));
    };
    const query = () => new URLSearchParams(filtroAtual()).toString();
    async function baixarArquivo(caminho, permissao) {
      exigir(permissao);
      const resposta = await api(caminho);
      exigir(permissao);
      const blob = await resposta.blob();
      exigir(permissao);
      const cabecalho = resposta.headers.get("content-disposition") || "";
      let arquivo = cabecalho.match(/filename="?([^";]+)"?/i)?.[1] || "arquivo";
      const codificado = cabecalho.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      if (codificado) { try { arquivo = decodeURIComponent(codificado); } catch (_) { /* Mantém o nome simples. */ } }
      const url = URL.createObjectURL(blob);
      try {
        const a = u.el("a"); a.href = url; a.download = arquivo; a.click();
      } finally { URL.revokeObjectURL(url); }
    }
    const nome = (lista, id, padrao = "Não atribuído") => (estado.catalogo?.[lista] || []).find(p => p.id === Number(id))?.nome || padrao;
    const rotulo = v => u.rotulos[v] || v || "Não informado";
    function badge(texto, cor) {
      return u.el("span", texto, `qua-badge qua-${["verde", "amarelo", "vermelho", "neutro"].includes(cor) ? cor : "neutro"}`);
    }
    const corRegistro = r => ["encerrada", "resolvida", "validado"].includes(r.situacao) ? "verde"
      : r.criticidade === "critica" || r.prazo && r.prazo < u.hoje() ? "vermelho" : "amarelo";
    function vazio(alvo, titulo, texto) {
      const caixa = u.el("div", "", "qua-vazio"); caixa.append(u.el("strong", titulo), u.el("p", texto)); alvo.append(caixa);
    }
    function tabela(alvo, cabecalhos, linhas, render) {
      if (!linhas.length) { vazio(alvo, "Nenhum registro neste recorte", "Ajuste os filtros ou registre a primeira atividade do período."); return; }
      const regiao = u.el("div", "", "qua-tabela-wrap"); regiao.tabIndex = 0; regiao.setAttribute("role", "region");
      regiao.setAttribute("aria-label", cabecalhos.join(", "));
      const t = u.el("table", "", "qua-tabela"), head = u.el("thead"), tr = u.el("tr"), body = u.el("tbody");
      for (const texto of cabecalhos) { const th = u.el("th", texto); th.setAttribute("scope", "col"); tr.append(th); }
      head.append(tr); for (const linha of linhas) { const row = u.el("tr"); render(linha, row); body.append(row); }
      t.append(head, body); regiao.append(t); alvo.append(regiao);
    }
    function celula(linha, texto, secundario) {
      const c = u.el("td", texto);
      if (secundario) c.append(u.el("small", secundario, "qua-secundario")); linha.append(c); return c;
    }
    function atualizarNav() {
      for (const [v, b] of Object.entries(botoes)) { b.classList.toggle("ativa", v === estado.visao); b.setAttribute("aria-current", v === estado.visao ? "page" : "false"); }
      const situacoes = estado.visao === "ocorrencias" ? ["aberta", "em_tratamento", "resolvida", "encerrada"]
        : estado.visao === "planos" ? ["aberto", "em_andamento", "aguardando_validacao", "validado"]
          : ["a_fazer", "em_andamento", "aguardando_cliente", "concluida", "conferida", "devolvida", "dispensada",
            "aberta", "em_tratamento", "resolvida", "encerrada", "aberto", "aguardando_validacao", "validado"];
      const anterior = situacao.value; opcoes(situacao, situacoes.map(v => ({valor: v, rotulo: rotulo(v)})), "Todas", situacoes.includes(anterior) ? anterior : "");
      situacao.disabled = estado.visao === "horas" || estado.visao === "modelos";
    }
    async function trocar(visao) {
      exigir(); estado.visao = visao; estado.detalhe++; detalhe.hidden = true; detalhe.textContent = "";
      estado.fecharForm?.(); atualizarNav(); await carregar();
    }
    async function carregar() {
      exigir(); if (!estado.catalogo) return;
      const versao = ++estado.consulta, visao = estado.visao;
      estado.detalhe++; detalhe.hidden = true; detalhe.textContent = "";
      const atual = () => valida() && versao === estado.consulta && estado.visao === visao;
      conteudo.setAttribute("aria-busy", "true"); informar("Atualizando o conjunto autorizado…");
      try {
        const filtrosEnviados = filtroAtual();
        const dados = ["relatorios", "modelos"].includes(visao) ? null : await api(`/api/qualidade/${visao}?${new URLSearchParams(filtrosEnviados)}`);
        if (!atual()) return;
        conteudo.textContent = "";
        resumo.textContent = `${u.data(filtrosEnviados.de)} a ${u.data(filtrosEnviados.ate)} · ${cliente.value ? nome("clientes", cliente.value) : "Todos os clientes no seu acesso"} · ${setor.value ? nome("setores", setor.value) : "Todos os setores no seu acesso"}`;
        if (visao === "painel") desenharPainel(dados);
        else if (visao === "relatorios") desenharRelatorios();
        else if (visao === "modelos") desenharModelos();
        else desenharLista(visao, dados);
        informar("Atualizado. As informações respeitam seus filtros e permissões.");
        return true;
      } catch (e) { if (atual()) informar(e.message || "Não foi possível carregar os dados.", true); }
      finally { if (atual()) conteudo.setAttribute("aria-busy", "false"); }
    }
    function desenharPainel(p) {
      if (p?.formato !== "qualidade_painel_v1" || !Array.isArray(p.kpis)) throw new Error("Resposta do painel inválida. Atualize novamente.");
      const painel = u.el("section"); painel.id = "qua-painel"; painel.setAttribute("aria-label", "Indicadores da qualidade"); conteudo.append(painel);
      const foco = u.el("div", "", "qua-foco");
      const texto = u.el("div"); texto.append(u.el("p", "PANORAMA DO PERÍODO", "qua-sobretitulo"),
        u.el("h3", "Do acompanhamento à melhoria contínua"),
        u.el("p", "Prazos, qualidade e ações no mesmo lugar. Cada indicador mostra sua origem e o que precisa de atenção."));
      const progresso = u.el("div", "", "qua-progresso");
      progresso.append(u.el("strong", u.numero(p.dimensoes?.progresso?.percentual, "percentual")),
        u.el("span", "de tarefas finalizadas"), u.el("small", `${p.dimensoes?.progresso?.concluidas ?? 0} de ${p.dimensoes?.progresso?.total ?? 0} no recorte`));
      foco.append(texto, progresso); painel.append(foco);
      const dimensoes = u.el("div", "", "qua-dimensoes");
      for (const [titulo, valor, desc] of [["Operação", p.dimensoes?.operacao?.pendentes, "atividades pendentes"],
        ["Risco", p.dimensoes?.risco?.ocorrencias_criticas, "ocorrências críticas"],
        ["Engajamento", p.dimensoes?.engajamento?.aguardando_cliente, "tarefas aguardando o cliente"],
        ["Progresso", p.dimensoes?.progresso?.concluidas, "tarefas finalizadas"]]) {
        const c = u.el("article", "", "qua-dimensao"); c.append(u.el("span", titulo), u.el("strong", u.numero(valor)), u.el("small", desc)); dimensoes.append(c);
      }
      painel.append(dimensoes);
      const semaforo = u.el("div", "", "qua-semaforo");
      for (const [cor, texto] of [["verde", "Concluídas no prazo"], ["amarelo", "Em acompanhamento"], ["vermelho", "Exigem atenção"], ["neutro", "Sem classificação de prazo"]])
        semaforo.append(badge(`${p.semaforo?.[cor] ?? 0} · ${texto}`, cor));
      painel.append(semaforo);
      const grade = u.el("div", "", "qua-kpis");
      for (const k of p.kpis) {
        const c = u.el("article", "", "qua-kpi"); c.id = `qua-kpi-${String(k.chave).replace(/[^a-z0-9_-]/gi, "")}`;
        c.append(u.el("span", k.rotulo), u.el("strong", u.numero(k.valor, k.unidade)));
        if (k.denominador !== null && k.denominador !== undefined) {
          const amostra = k.numerador !== null && k.numerador !== undefined
            ? `${k.numerador} de ${k.denominador} registros`
            : `${k.denominador} ${Number(k.denominador) === 1 ? "registro" : "registros"} na amostra`;
          c.append(u.el("small", amostra));
        }
        const metodo = u.el("details"); metodo.append(u.el("summary", "Como é calculado"), u.el("p", k.formula || "Fórmula não informada."));
        c.append(metodo); grade.append(c);
      }
      painel.append(grade);
      const colunas = u.el("div", "", "qua-painel-colunas"), alertas = u.el("section", "", "qua-bloco"), custos = u.el("section", "", "qua-bloco");
      alertas.append(u.el("h3", "Prioridades para acompanhar"));
      const ativos = (p.alertas || []).filter(a => a.quantidade > 0);
      if (!ativos.length) vazio(alertas, "Nenhum alerta neste recorte", "Continue acompanhando os prazos e registrando a evolução das atividades.");
      for (const alerta of ativos) {
        const d = u.el("details", "", "qua-alerta"), s = u.el("summary");
        s.append(badge(alerta.quantidade, alerta.cor), u.el("span", alerta.rotulo)); d.append(s);
        for (const item of alerta.itens || []) {
          const li = u.el("div", "", "qua-alerta-item"); li.append(u.el("span", item.titulo), u.el("small", `Prazo: ${u.data(item.prazo)}`));
          if (["ocorrencia", "plano"].includes(item.entidade)) li.append(botao("Ver registro", "", () => abrirDetalhe(item.entidade, item.id), "qua-link"));
          else if (item.entidade === "tarefa" && Sessao.pode("aba.tarefas")) li.append(botao("Ver tarefa", "", () => { exigir(); TarefasUI.abrirContexto({tarefa_id: item.id, filtros: {cliente_id: item.cliente_id, setor_id: item.setor_id, visao: "cliente"}}); }, "qua-link"));
          d.append(li);
        }
        alertas.append(d);
      }
      custos.append(u.el("h3", "Tempo e custo da operação"));
      custos.append(u.el("strong", u.numero(p.custos?.horas, "horas"), "qua-custo-total"), u.el("p", "Horas registradas no período"));
      if (pode("custos") && p.custos?.permitido) {
        custos.append(u.el("strong", u.moeda(p.custos.custo_total), "qua-custo-total"), u.el("p", p.custos.formula || "Minutos / 60 × custo/hora informado"));
        if (p.custos.lancamentos_sem_custo) custos.append(u.el("p", `${p.custos.lancamentos_sem_custo} lançamento(s) sem custo informado. O custo total não está completo.`, "qua-aviso"));
      } else custos.append(u.el("p", "Os valores de custo exigem permissão específica.", "qua-subtitulo"));
      custos.append(botao("Consultar apontamentos", "qua-ver-horas", () => trocar("horas"), "qua-link"));
      colunas.append(alertas, custos); painel.append(colunas);
      const equipe = u.el("section", "", "qua-bloco"); equipe.append(u.el("h3", "Entregas por colaborador"), u.el("p", "Conclusões são atribuídas a quem executou a atividade; não representam uma avaliação automática de pessoas.", "qua-subtitulo"));
      const mostraCusto = pode("custos") && p.custos?.permitido;
      tabela(equipe, ["Colaborador", "Concluídas", "Pendentes", "Horas", ...(mostraCusto ? ["Custo registrado"] : [])], p.por_colaborador || [], (r, tr) => {
        celula(tr, r.nome); celula(tr, r.tarefas_concluidas); celula(tr, r.tarefas_pendentes); celula(tr, u.numero(r.horas, "horas")); if (mostraCusto) celula(tr, u.moeda(r.custo_total));
      }); painel.append(equipe);
      const setores = u.el("section", "", "qua-bloco"); setores.append(u.el("h3", "Qualidade por setor"));
      tabela(setores, ["Setor", "Atividades", "Concluídas", "Pendentes", "Atrasadas", "Ocorrências", "Não conformidades abertas"], p.por_setor || [], (r, tr) => {
        for (const v of [r.nome, r.tarefas, r.concluidas, r.pendentes, r.atrasadas, r.ocorrencias, r.nao_conformidades_abertas]) celula(tr, v);
      }); painel.append(setores);
      const metodologia = u.el("details", "", "qua-metodologia"); metodologia.append(u.el("summary", "Critérios e limites dos indicadores"));
      for (const texto of p.metodologia || []) metodologia.append(u.el("p", texto)); painel.append(metodologia);
    }
    function desenharLista(visao, dados) {
      if (!Array.isArray(dados?.itens)) throw new Error("Resposta de listagem inválida. Atualize novamente.");
      const topo = u.el("div", "", "qua-lista-topo");
      const rotulos = {ocorrencias: "Ocorrências de qualidade", planos: "Planos de ação", horas: "Apontamentos de tempo"};
      topo.append(u.el("div", `${dados.total ?? dados.itens.length} registro(s) no recorte`, "qua-subtitulo"));
      if (pode("registrar")) topo.append(botao(visao === "ocorrencias" ? "+ Registrar ocorrência" : visao === "planos" ? "+ Abrir plano de ação" : "+ Registrar tempo",
        visao === "ocorrencias" ? "qua-nova-ocorrencia" : visao === "planos" ? "qua-novo-plano" : "qua-novas-horas",
        () => visao === "ocorrencias" ? formOcorrencia() : visao === "planos" ? formPlano() : formHoras(), "botao-primario"));
      conteudo.append(u.el("h3", rotulos[visao]), topo);
      if (visao === "horas") {
        const custos = pode("custos");
        tabela(conteudo, ["Data / cliente", "Atividade", "Colaborador", "Tempo", ...(custos ? ["Custo"] : []), "Registro"], dados.itens, (r, tr) => {
          celula(tr, u.data(r.data), r.cliente_nome || nome("clientes", r.cliente_id)); celula(tr, r.descricao, r.setor_nome || nome("setores", r.setor_id));
          celula(tr, r.usuario_nome || r.responsavel_nome || nome("usuarios", r.usuario_id ?? r.responsavel_usuario_id)); celula(tr, `${r.minutos} min`);
          if (custos) celula(tr, u.moeda(r.custo_total));
          const a = celula(tr, r.cancelado || r.cancelado_em ? "Cancelado" : "Registrado");
          if (r.pode_cancelar) a.append(botao("Cancelar lançamento", `qua-cancelar-horas-${r.id}`, () => formCancelarHoras(r), "qua-link"));
        });
      } else {
        const entidade = visao === "ocorrencias" ? "ocorrencia" : "plano";
        tabela(conteudo, [visao === "ocorrencias" ? "Ocorrência / cliente" : "Ação / cliente", "Setor / responsável", "Prioridade", "Prazo", "Situação", ""], dados.itens, (r, tr) => {
          celula(tr, r.descricao, r.cliente_nome || nome("clientes", r.cliente_id));
          celula(tr, r.setor_nome || nome("setores", r.setor_id), r.responsavel_nome || nome("usuarios", r.responsavel_usuario_id));
          celula(tr, visao === "ocorrencias" ? rotulo(r.criticidade) : rotulo(r.tipo)); celula(tr, u.data(r.prazo));
          celula(tr, "").append(badge(rotulo(r.situacao), corRegistro(r)));
          celula(tr, "").append(botao("Ver detalhes", `qua-abrir-${entidade}-${r.id}`, () => abrirDetalhe(entidade, r.id), "qua-link"));
        });
      }
    }
    async function abrirDetalhe(entidade, id) {
      exigir(); const numero = ++estado.detalhe, consulta = estado.consulta;
      const plural = entidade === "ocorrencia" ? "ocorrencias" : "planos";
      const registro = await api(`/api/qualidade/${plural}/${Number(id)}`);
      if (!valida() || numero !== estado.detalhe || consulta !== estado.consulta) return;
      detalhe.textContent = ""; detalhe.hidden = false;
      detalhe.append(botao("Fechar detalhes", "qua-fechar-detalhe", () => { estado.detalhe++; detalhe.hidden = true; detalhe.textContent = ""; }, "qua-fechar"),
        u.el("p", `${entidade === "ocorrencia" ? "OCORRÊNCIA" : "PLANO DE AÇÃO"} #${registro.id}`, "qua-sobretitulo"),
        u.el("h3", registro.descricao), badge(rotulo(registro.situacao), corRegistro(registro)));
      const info = u.el("dl", "", "qua-ficha");
      for (const [chave, valor] of [["Cliente", registro.cliente_nome || nome("clientes", registro.cliente_id)],
        ["Setor", registro.setor_nome || nome("setores", registro.setor_id)], ["Responsável", registro.responsavel_nome || nome("usuarios", registro.responsavel_usuario_id)],
        ["Prazo", u.data(registro.prazo)], ["Tipo", rotulo(registro.tipo)], [entidade === "ocorrencia" ? "Criticidade" : "Causa", entidade === "ocorrencia" ? rotulo(registro.criticidade) : registro.causa]]) {
        info.append(u.el("dt", chave), u.el("dd", valor || "Não informado"));
      }
      detalhe.append(info);
      const acoes = u.el("div", "", "qua-acoes");
      if (registro.pode_editar) acoes.append(botao("Editar", "qua-editar", () => entidade === "ocorrencia" ? formOcorrencia(registro) : formPlano(registro)));
      if (transicoes(entidade, registro).length) acoes.append(botao("Atualizar situação", "qua-transicao", () => formTransicao(entidade, registro), "botao-primario"));
      if (registro.pode_comentar) acoes.append(botao("Registrar acompanhamento", "qua-comentar", () => formComentario(entidade, registro)));
      if (entidade === "ocorrencia" && pode("registrar") && registro.pode_comentar && !["resolvida", "encerrada"].includes(registro.situacao))
        acoes.append(botao("Abrir plano de ação", "qua-plano-ocorrencia", () => formPlano(null, registro)));
      if (registro.tarefa_id && Sessao.pode("aba.tarefas")) acoes.append(botao("Abrir tarefa vinculada", "qua-tarefa-vinculada", () => {
        exigir(); TarefasUI.abrirContexto({tarefa_id: registro.tarefa_id, filtros: {cliente_id: registro.cliente_id, setor_id: registro.setor_id, visao: "cliente"}});
      }));
      detalhe.append(acoes);
      if (entidade === "ocorrencia" && registro.planos?.length) {
        detalhe.append(u.el("h4", "Planos vinculados"));
        for (const plano of registro.planos) detalhe.append(botao(`#${plano.id} · ${plano.descricao}`, `qua-plano-${plano.id}`, () => abrirDetalhe("plano", plano.id), "qua-vinculo"));
      }
      desenharAnexos(entidade, registro);
      const historico = u.el("section", "", "qua-historico"); historico.append(u.el("h4", "Histórico do registro"));
      for (const evento of registro.historico || []) {
        const linha = u.el("article"); linha.append(u.el("strong", evento.usuario_nome || evento.usuario_login || "Sistema"),
          u.el("small", `${u.instante(evento.criado_em)} · ${rotulo(evento.tipo)}`),
          u.el("p", evento.comentario || evento.descricao ||
            (evento.antes?.situacao && evento.depois?.situacao ? `${rotulo(evento.antes.situacao)} → ${rotulo(evento.depois.situacao)}` : rotulo(evento.tipo))));
        const mudancas = u.el("details"); mudancas.append(u.el("summary", "Alterações registradas")); let quantidade = 0;
        for (const [chave, titulo] of Object.entries({data: "Data", descricao: "Descrição", causa: "Causa", tipo: "Tipo", criticidade: "Criticidade", prazo: "Prazo", situacao: "Situação", responsavel_usuario_id: "Responsável"})) {
          if (!evento.antes || !evento.depois || !(chave in evento.depois) || evento.antes[chave] === evento.depois[chave]) continue;
          const descrever = valor => chave === "responsavel_usuario_id" ? nome("usuarios", valor) : ["data", "prazo"].includes(chave) ? u.data(valor) : rotulo(valor);
          mudancas.append(u.el("p", `${titulo}: ${descrever(evento.antes[chave])} → ${descrever(evento.depois[chave])}`)); quantidade++;
        }
        if (quantidade) linha.append(mudancas);
        historico.append(linha);
      }
      if (!registro.historico?.length) historico.append(u.el("p", "Ainda não há movimentos neste registro."));
      detalhe.append(historico); detalhe.tabIndex = -1; detalhe.focus();
    }
    function desenharAnexos(entidade, registro) {
      const secao = u.el("section", "", "qua-evidencias"); secao.append(u.el("h4", "Documentos e evidências"));
      for (const anexo of registro.anexos || []) secao.append(botao(`${anexo.nome} · ${Math.ceil(anexo.tamanho / 1024)} KB`, `qua-anexo-${anexo.id}`, async () => {
        await baixarArquivo(`/api/qualidade/anexos/${anexo.id}/download`);
      }, "qua-vinculo"));
      if (!registro.anexos?.length) secao.append(u.el("p", "Nenhuma evidência anexada.", "qua-subtitulo"));
      if (!estado.catalogo.anexos?.disponivel) secao.append(u.el("p", "O armazenamento de evidências ainda precisa ser configurado pelo administrador.", "qua-aviso"));
      else if (registro.pode_comentar) {
        const arquivo = input("qua-anexo-arquivo", "file"); arquivo.accept = ".png,.jpg,.jpeg,.pdf,.eml";
        const enviar = botao("Anexar evidência", "qua-anexo-enviar", async () => {
          exigirAlteracao(registro.pode_comentar); const escolhido = arquivo.files[0];
          if (!escolhido) throw new Error("Escolha um arquivo para anexar.");
          if (escolhido.size > estado.catalogo.anexos.limite_bytes || !/\.(png|jpe?g|pdf|eml)$/i.test(escolhido.name)) throw new Error("Use PNG, JPEG, PDF ou EML de até 10 MB.");
          const versao = estado.detalhe, corpo = new FormData(); corpo.append("arquivo", escolhido); enviar.disabled = true;
          try {
            await api(`/api/qualidade/${entidade === "ocorrencia" ? "ocorrencias" : "planos"}/${registro.id}/anexos`, {method: "POST", body: corpo});
            if (valida() && versao === estado.detalhe) { informar("Evidência anexada e registrada no histórico."); await abrirDetalhe(entidade, registro.id); }
          } finally { enviar.disabled = false; }
        });
        secao.append(campo("Arquivo (PNG, JPEG, PDF ou EML; até 10 MB)", arquivo), enviar);
      }
      detalhe.append(secao);
    }
    function formulario(titulo, campos, salvar, {rotuloSalvar = "Salvar alterações", ajuda = "", reabrir, aoMontar} = {}) {
      exigir(); estado.fecharForm?.();
      const identidadeForm = Sessao.usuario, gatilho = document.activeElement;
      const fundo = u.el("div", "", "qua-modal-fundo"), form = u.el("form", "", "qua-modal"); form.id = "qua-form";
      form.setAttribute("role", "dialog"); form.setAttribute("aria-modal", "true"); form.setAttribute("aria-label", titulo);
      form.append(u.el("h3", titulo)); if (ajuda) form.append(u.el("p", ajuda, "qua-subtitulo"));
      const grade = u.el("div", "", "qua-form-grade"), controles = {};
      for (const c of campos) {
        let e;
        if (c.tipo === "select") e = select(`qua-campo-${c.nome}`, c.opcoes || [], c.vazio ?? "Selecione");
        else if (c.tipo === "textarea") { e = u.el("textarea"); e.id = `qua-campo-${c.nome}`; e.rows = 4; }
        else e = input(`qua-campo-${c.nome}`, c.tipo || "text");
        e.name = c.nome; e.value = c.valor === null || c.valor === undefined ? "" : String(c.valor);
        if (c.obrigatorio) e.required = true;
        if (c.min !== undefined) e.min = c.min; if (c.max !== undefined) e.max = c.max;
        if (c.step !== undefined) e.step = c.step; if (c.maxLength) e.maxLength = c.maxLength;
        if (c.placeholder) e.placeholder = c.placeholder;
        controles[c.nome] = e;
        const l = campo(c.rotulo, e); if (c.tipo === "textarea") l.classList.add("qua-campo-largo");
        if (c.ajuda) l.append(u.el("small", c.ajuda)); grade.append(l);
      }
      const atualizarResponsavel = () => {
        if (!controles.setor_id || !controles.responsavel_usuario_id) return;
        const selecionado = controles.responsavel_usuario_id.value;
        const pessoas = (estado.catalogo.usuarios || []).filter(p => !controles.setor_id.value || (p.setor_ids || []).includes(Number(controles.setor_id.value)));
        opcoes(controles.responsavel_usuario_id, pessoas, "Selecione", pessoas.some(p => String(p.id) === selecionado) ? selecionado : "");
      };
      controles.setor_id?.addEventListener("change", atualizarResponsavel); atualizarResponsavel();
      aoMontar?.(controles);
      const erro = u.el("p", "", "qua-erro"); erro.id = "qua-form-erro"; erro.setAttribute("role", "alert");
      const acoes = u.el("div", "", "qua-form-acoes"), ok = u.el("button", rotuloSalvar, "botao-primario"); ok.type = "submit"; ok.id = "qua-form-salvar";
      let ocupada = false, reabrirAdicionado = false;
      const fechar = (forcar = false) => {
        if (ocupada && !forcar) return;
        document.removeEventListener("keydown", teclado, true); fundo.remove(); if (estado.fecharForm === fechar) estado.fecharForm = null;
        if (gatilho?.isConnected) gatilho.focus();
      };
      const cancelar = botao("Cancelar", "qua-form-cancelar", () => fechar());
      const teclado = e => {
        if (e.key === "Escape" && !ocupada) { e.preventDefault(); fechar(); }
        if (e.key === "Tab") {
          const foco = [...form.querySelectorAll("input,select,textarea,button")].filter(e => !e.disabled && e.getClientRects().length);
          if (e.shiftKey && document.activeElement === foco[0]) { e.preventDefault(); foco.at(-1)?.focus(); }
          else if (!e.shiftKey && document.activeElement === foco.at(-1)) { e.preventDefault(); foco[0]?.focus(); }
        }
      };
      acoes.append(cancelar, ok); form.append(grade, erro, acoes); fundo.append(form); document.body.append(fundo); estado.fecharForm = fechar;
      document.addEventListener("keydown", teclado, true);
      form.addEventListener("submit", async e => {
        e.preventDefault(); if (ocupada) return;
        ocupada = true; ok.disabled = true; cancelar.disabled = true; erro.textContent = "";
        try {
          exigir(); if (Sessao.usuario !== identidadeForm) throw new Error("A sessão mudou. Reabra o formulário.");
          const valores = Object.fromEntries(campos.map(c => [c.nome, controles[c.nome].value.trim()]));
          for (const c of campos) if (c.obrigatorio && !valores[c.nome]) throw new Error(`Preencha ${c.rotulo.toLowerCase()}.`);
          await salvar(valores);
          if (!valida() || Sessao.usuario !== identidadeForm) return;
          fechar(true); if (await carregar()) informar("Registro salvo e incluído no histórico.");
        } catch (e2) {
          if (!estado.encerrada) erro.textContent = (e2.message || "Não foi possível salvar.") + (e2.status === 409 ? " Preserve sua anotação e reabra o registro atualizado antes de salvar." : "");
          if (e2.status === 409 && reabrir && !reabrirAdicionado) {
            reabrirAdicionado = true; acoes.append(botao("Reabrir registro", "qua-form-reabrir", () => { fechar(); return reabrir(); }));
          }
        } finally { ocupada = false; ok.disabled = false; cancelar.disabled = false; }
      });
      form.querySelector("input,select,textarea,button")?.focus();
    }
    const id = (valor, opcional = false) => {
      if (opcional && !valor) return null; const numero = Number(valor);
      if (!Number.isSafeInteger(numero) || numero < 1) throw new Error("Escolha um registro válido."); return numero;
    };
    const opcoesUsuarios = setorId => (estado.catalogo.usuarios || []).filter(p => !setorId || (p.setor_ids || []).includes(Number(setorId)));
    function formOcorrencia(r = null) {
      if (r) exigirAlteracao(r.pode_editar); else exigir("registrar");
      const campos = [{nome: "data", rotulo: "Data da ocorrência", tipo: "date", obrigatorio: true, valor: r?.data || u.hoje()},
        ...(!r ? [{nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: estado.catalogo.clientes, obrigatorio: true, valor: cliente.value},
          {nome: "setor_id", rotulo: "Setor responsável", tipo: "select", opcoes: estado.catalogo.setores, obrigatorio: true, valor: setor.value},
          {nome: "tarefa_id", rotulo: "ID da tarefa vinculada (opcional)", tipo: "number", min: 1}] : []),
        {nome: "responsavel_usuario_id", rotulo: "Responsável", tipo: "select", opcoes: opcoesUsuarios(r?.setor_id), obrigatorio: true, valor: r?.responsavel_usuario_id || ""},
        {nome: "tipo", rotulo: "Tipo da ocorrência", tipo: "select", opcoes: estado.catalogo.tipos, obrigatorio: true, valor: r?.tipo || ""},
        {nome: "criticidade", rotulo: "Criticidade", tipo: "select", opcoes: estado.catalogo.criticidades, obrigatorio: true, valor: r?.criticidade || ""},
        {nome: "prazo", rotulo: "Prazo de solução", tipo: "date", obrigatorio: true, valor: r?.prazo || ""},
        {nome: "descricao", rotulo: "Descrição da ocorrência", tipo: "textarea", obrigatorio: true, maxLength: 10000, valor: r?.descricao || ""}];
      formulario(r ? `Editar ocorrência #${r.id}` : "Registrar ocorrência", campos, async v => {
        if (r) exigirAlteracao(r.pode_editar); else exigir("registrar");
        const dados = {...v, responsavel_usuario_id: id(v.responsavel_usuario_id)};
        if (r) dados.revision = r.revision;
        else { dados.cliente_id = id(v.cliente_id); dados.setor_id = id(v.setor_id); dados.tarefa_id = id(v.tarefa_id, true); }
        await api(`/api/qualidade/ocorrencias${r ? "/" + r.id : ""}`, {method: r ? "PATCH" : "POST", json: dados});
      }, {rotuloSalvar: r ? "Salvar alterações" : "Registrar ocorrência", ajuda: "Descreva o fato, o responsável e a data esperada para a solução. A autoria é registrada automaticamente.", reabrir: r ? () => abrirDetalhe("ocorrencia", r.id) : null});
    }
    async function formPlano(r = null, ocorrencia = null) {
      if (r) exigirAlteracao(r.pode_editar); else exigir("registrar");
      if (ocorrencia && (!ocorrencia.pode_comentar || ["resolvida", "encerrada"].includes(ocorrencia.situacao))) throw new Error("A ocorrência não está disponível para um novo plano.");
      let ocorrencias = [], registrosOcorrencias = [];
      const consulta = estado.consulta;
      if (!r && !ocorrencia) {
        const parametros = new URLSearchParams(filtroAtual()); parametros.delete("situacao");
        const resposta = await api("/api/qualidade/ocorrencias?" + parametros); exigir("registrar");
        if (consulta !== estado.consulta) return;
        registrosOcorrencias = (resposta.itens || []).filter(o => o.pode_comentar && !["resolvida", "encerrada"].includes(o.situacao));
        ocorrencias = registrosOcorrencias.map(o => ({id: o.id, nome: `#${o.id} · ${o.descricao}`}));
        if (!ocorrencias.length) throw new Error("Registre uma ocorrência neste recorte antes de abrir um plano de ação.");
      }
      const campos = [...(!r && !ocorrencia ? [{nome: "ocorrencia_id", rotulo: "Ocorrência", tipo: "select", opcoes: ocorrencias, obrigatorio: true}] : []),
        {nome: "tipo", rotulo: "Tipo da ação", tipo: "select", obrigatorio: true, valor: r?.tipo || "corretiva", opcoes: [{valor: "corretiva", rotulo: "Corretiva"}, {valor: "preventiva", rotulo: "Preventiva"}]},
        {nome: "responsavel_usuario_id", rotulo: "Responsável pela ação", tipo: "select", obrigatorio: true, opcoes: opcoesUsuarios(r?.setor_id || ocorrencia?.setor_id), valor: r?.responsavel_usuario_id || ""},
        {nome: "prazo", rotulo: "Prazo de resolução", tipo: "date", obrigatorio: true, valor: r?.prazo || ""},
        {nome: "causa", rotulo: "Causa identificada", tipo: "textarea", obrigatorio: true, maxLength: 10000, valor: r?.causa || ""},
        {nome: "descricao", rotulo: "Ação a realizar", tipo: "textarea", obrigatorio: true, maxLength: 10000, valor: r?.descricao || ""}];
      formulario(r ? `Editar plano #${r.id}` : "Abrir plano de ação", campos, async v => {
        if (r) exigirAlteracao(r.pode_editar); else exigir("registrar");
        const dados = {...v, responsavel_usuario_id: id(v.responsavel_usuario_id)};
        if (r) dados.revision = r.revision; else dados.ocorrencia_id = ocorrencia?.id || id(v.ocorrencia_id);
        await api(`/api/qualidade/planos${r ? "/" + r.id : ""}`, {method: r ? "PATCH" : "POST", json: dados});
      }, {rotuloSalvar: r ? "Salvar alterações" : "Abrir plano de ação", ajuda: ocorrencia ? `Ocorrência #${ocorrencia.id}: ${ocorrencia.descricao}` : "O plano herda o cliente e o setor da ocorrência. A solução será submetida à validação da gestão.", reabrir: r ? () => abrirDetalhe("plano", r.id) : null,
        aoMontar: controles => {
          if (!controles.ocorrencia_id) return;
          const filtrar = () => {
            const selecionada = registrosOcorrencias.find(o => o.id === Number(controles.ocorrencia_id.value));
            const pessoas = selecionada ? opcoesUsuarios(selecionada.setor_id) : [];
            const atual = controles.responsavel_usuario_id.value;
            opcoes(controles.responsavel_usuario_id, pessoas, "Selecione", pessoas.some(p => String(p.id) === atual) ? atual : "");
          };
          controles.ocorrencia_id.addEventListener("change", filtrar); filtrar();
        }});
    }
    function transicoes(entidade, r) {
      if (!r.pode_transicionar) return [];
      return (r.transicoes_permitidas || []).filter(destino => {
        const validacao = entidade === "ocorrencia" ? destino === "encerrada"
          : destino === "validado" || r.situacao === "aguardando_validacao" && destino === "em_andamento";
        return validacao ? r.pode_validar && pode("validar") : pode("registrar") || pode("gerir");
      });
    }
    function formTransicao(entidade, r) {
      exigir(); const disponiveis = transicoes(entidade, r);
      if (!r.pode_transicionar || !disponiveis.length) throw new Error("Não há mudança de situação disponível para este registro.");
      formulario(`Atualizar ${entidade === "ocorrencia" ? "ocorrência" : "plano"} #${r.id}`, [
        {nome: "situacao", rotulo: "Nova situação", tipo: "select", obrigatorio: true, opcoes: disponiveis.map(v => ({valor: v, rotulo: rotulo(v)}))},
        {nome: "comentario", rotulo: "Descrição da solução ou motivo da mudança", tipo: "textarea", obrigatorio: true, maxLength: 10000},
      ], async v => {
        exigir(); if (!transicoes(entidade, r).includes(v.situacao)) throw new Error("Mudança de situação não autorizada.");
        await api(`/api/qualidade/${entidade === "ocorrencia" ? "ocorrencias" : "planos"}/${r.id}/transicao`, {method: "POST", json: {...v, revision: r.revision}});
      }, {rotuloSalvar: "Confirmar mudança de situação", ajuda: `Situação atual: ${rotulo(r.situacao)}. O motivo e o autor ficarão no histórico.`, reabrir: () => abrirDetalhe(entidade, r.id)});
    }
    function formComentario(entidade, r) {
      exigirAlteracao(r.pode_comentar);
      formulario("Registrar acompanhamento", [{nome: "comentario", rotulo: "Andamento ou observação", tipo: "textarea", obrigatorio: true, maxLength: 10000}], async v => {
        exigirAlteracao(r.pode_comentar); await api(`/api/qualidade/${entidade === "ocorrencia" ? "ocorrencias" : "planos"}/${r.id}/comentarios`, {method: "POST", json: {...v, revision: r.revision}});
      }, {rotuloSalvar: "Registrar acompanhamento", reabrir: () => abrirDetalhe(entidade, r.id)});
    }
    function formHoras() {
      exigir("registrar");
      const campos = [{nome: "data", rotulo: "Data da atividade", tipo: "date", obrigatorio: true, valor: u.hoje()},
        {nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: estado.catalogo.clientes, obrigatorio: true, valor: cliente.value},
        {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: estado.catalogo.setores, obrigatorio: true, valor: setor.value},
        {nome: "minutos", rotulo: "Tempo dedicado (minutos)", tipo: "number", min: 1, max: 1440, step: 1, obrigatorio: true},
        {nome: "tarefa_id", rotulo: "ID da tarefa (opcional)", tipo: "number", min: 1},
        {nome: "ocorrencia_id", rotulo: "ID da ocorrência (opcional)", tipo: "number", min: 1},
        ...(pode("custos") ? [{nome: "custo_hora", rotulo: "Custo por hora (R$, opcional)", tipo: "number", min: 0, step: "0.01", ajuda: "Deixe vazio quando desconhecido. O sistema calcula o custo do lançamento."}] : []),
        {nome: "descricao", rotulo: "Atividade realizada", tipo: "textarea", obrigatorio: true, maxLength: 10000}];
      formulario("Registrar tempo de trabalho", campos, async v => {
        exigir("registrar"); const dados = {...v, cliente_id: id(v.cliente_id), setor_id: id(v.setor_id), minutos: id(v.minutos), tarefa_id: id(v.tarefa_id, true), ocorrencia_id: id(v.ocorrencia_id, true)};
        if (dados.minutos > 1440) throw new Error("Um lançamento não pode ultrapassar 1.440 minutos.");
        if ("custo_hora" in dados) { exigir("custos"); dados.custo_hora = dados.custo_hora || null; }
        await api("/api/qualidade/horas", {method: "POST", json: dados});
      }, {rotuloSalvar: "Registrar apontamento", ajuda: "O tempo é atribuído à sua conta. Registre o esforço realizado, sem sobrepor o mesmo período de trabalho."});
    }
    function formCancelarHoras(r) {
      exigirAlteracao(r.pode_cancelar);
      formulario(`Cancelar apontamento #${r.id}`, [{nome: "motivo", rotulo: "Motivo do cancelamento", tipo: "textarea", obrigatorio: true, maxLength: 10000}], async v => {
        exigirAlteracao(r.pode_cancelar); await api(`/api/qualidade/horas/${r.id}/cancelar`, {method: "POST", json: {...v, revision: r.revision}});
      }, {rotuloSalvar: "Confirmar cancelamento", ajuda: "O lançamento deixará de compor os indicadores; o original e o motivo permanecerão no histórico."});
    }
    function desenharRelatorios() {
      const bloco = u.el("section", "", "qua-relatorios"); bloco.append(u.el("p", "ACOMPANHAMENTO COMPARTILHÁVEL", "qua-sobretitulo"),
        u.el("h3", "Da operação ao relatório"), u.el("p", "Use os filtros acima para selecionar um dia, uma semana, um mês ou um intervalo personalizado. Excel e PDF usam o mesmo conjunto autorizado."));
      const colunas = u.el("div", "", "qua-relatorio-formatos");
      for (const [formato, titulo, descricao] of [["xlsx", "Planilha Excel", "Indicadores e registros detalhados para conferir a operação, as falhas e as ações adotadas."],
        ["pdf", "Relatório PDF", "Resumo gerencial com indicadores, critérios e acompanhamento das entregas e da qualidade."]]) {
        const card = u.el("article", "", "qua-bloco"); card.append(u.el("span", formato.toUpperCase(), "qua-formato"), u.el("h4", titulo), u.el("p", descricao));
        const baixar = botao(`Exportar ${formato === "xlsx" ? "Excel" : "PDF"}`, `qua-exportar-${formato}`, async () => {
          exigir("exportar"); baixar.disabled = true;
          try { await baixarArquivo(`/api/qualidade/relatorio.${formato}?${query()}`, "exportar"); if (valida()) informar("Relatório preparado para download."); }
          finally { baixar.disabled = !pode("exportar"); }
        }, "botao-primario");
        baixar.disabled = !pode("exportar"); card.append(baixar); colunas.append(card);
      }
      bloco.append(colunas); if (!pode("exportar")) bloco.append(u.el("p", "A exportação exige uma permissão específica concedida pelo administrador.", "qua-aviso"));
      conteudo.append(bloco);
    }
    function desenharModelos() {
      conteudo.append(u.el("h3", "Rotinas de cada setor"), u.el("p", "Referências para organizar o trabalho. Escolha a agenda do setor e personalize atividades, responsáveis e prazos para cada cliente.", "qua-subtitulo"));
      const grade = u.el("div", "", "qua-modelos");
      for (const modelo of estado.catalogo.modelos || []) {
        const c = u.el("article", "", "qua-bloco"); c.append(u.el("h4", modelo.setor));
        const lista = u.el("ul"); for (const atividade of modelo.atividades || []) lista.append(u.el("li", typeof atividade === "string" ? atividade : atividade.nome)); c.append(lista);
        const setorRelacionado = (estado.catalogo.setores || []).find(s => s.nome.toLocaleLowerCase("pt-BR") === modelo.setor.toLocaleLowerCase("pt-BR"));
        if (Sessao.pode("aba.tarefas")) c.append(botao("Abrir agenda de tarefas", "", () => {
          exigir(); TarefasUI.abrirContexto({filtros: {visao: "cliente", ...(setorRelacionado ? {setor_id: setorRelacionado.id} : {})}});
        }, "qua-link"));
        grade.append(c);
      }
      conteudo.append(grade, u.el("p", "Os modelos não cadastram obrigações nem presumem vencimentos legais. A configuração da agenda continua em Tarefas e prazos.", "qua-subtitulo"));
    }
    document.addEventListener("sessao:encerrada", () => {
      estado.encerrada = true; estado.consulta++; estado.detalhe++; estado.fecharForm?.(true);
      container.textContent = ""; container.append(u.el("p", "Sessão encerrada. Entre novamente para consultar a gestão da qualidade.", "qua-status"));
    });
    async function iniciar() {
      exigir(); const versao = ++estado.consulta;
      try {
        const catalogo = await api("/api/qualidade/catalogo");
        if (!valida() || versao !== estado.consulta) return;
        if (![catalogo.clientes, catalogo.setores, catalogo.usuarios, catalogo.tipos, catalogo.criticidades].every(Array.isArray)) throw new Error("Catálogo da qualidade inválido.");
        estado.catalogo = catalogo;
        opcoes(cliente, catalogo.clientes, "Todos os clientes"); opcoes(setor, catalogo.setores, "Todos os setores"); opcoes(responsavel, catalogo.usuarios, "Todos os colaboradores");
        atualizarNav(); await carregar();
      } catch (e) { if (valida() && versao === estado.consulta) informar(e.message || "Não foi possível iniciar a gestão da qualidade.", true); }
    }
    await iniciar();
  },
};

Abas.registrar("qualidade", container => QualidadeUI.montar(container));
