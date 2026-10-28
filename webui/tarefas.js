/* Aba 10 — tarefas e prazos. As cores e permissões vêm do servidor.
   Dados de clientes entram no DOM como texto; nenhuma credencial é guardada. */
"use strict";

const TarefasUI = {
  situacoes: {a_fazer: "A fazer", em_andamento: "Em andamento",
    aguardando_cliente: "Aguardando cliente", concluida: "Concluída",
    conferida: "Conferida", devolvida: "Devolvida", dispensada: "Dispensada"},
  data(valor) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(valor || "");
    return m ? `${m[3]}/${m[2]}/${m[1]}` : "—";
  },
  vencimento(valor) { return valor ? this.data(valor) : "Sem vencimento"; },
  resultadoPrazo(t) { return !t.vencimento ? "Sem vencimento" : t.fora_do_prazo ? "Fora do prazo" : "Dentro do prazo"; },
  ocorrencia(t) {
    if (!t.obrigacao_id) return "";
    const intervalo = t.origem?.intervalo;
    return `Ocorrência ${t.ocorrencia || 1}${intervalo ? " · período " + intervalo : ""}`;
  },
  rotuloSituacao(valor) { return this.situacoes[valor] || "Situação desconhecida"; },
  meses(valor) {
    const meses = String(valor || "").split(",").map(s => s.trim()).filter(Boolean).map(Number);
    if (meses.some(m => !Number.isInteger(m) || m < 1 || m > 12) || new Set(meses).size !== meses.length)
      throw new Error("Escolha competências entre janeiro e dezembro, sem repetir.");
    return meses;
  },
  periodos(valor) {
    const entradas = String(valor || "").split(/[;\n]/).map(p => p.trim()).filter(Boolean);
    if (!entradas.length) throw new Error("Informe ao menos um período, como 01-15; 16-30.");
    const periodos = entradas.map(texto => {
      const m = /^(\d{1,2})\s*-\s*(\d{1,2})$/.exec(texto);
      if (!m) throw new Error("Escreva cada período como 01-15, separado por ponto e vírgula ou nova linha.");
      const inicio = Number(m[1]), fim = Number(m[2]);
      if (inicio < 1 || fim > 31 || inicio > fim)
        throw new Error("Use dias de 1 a 31, com início anterior ou igual ao fim.");
      return {inicio, fim};
    });
    if (periodos.some((p, i) => i > 0 && p.inicio <= periodos[i - 1].fim))
      throw new Error("Informe os períodos em ordem, sem dias repetidos entre eles.");
    return periodos;
  },
  regra(v) {
    if (v.tipo === "sem_vencimento") return {tipo: v.tipo};
    const r = {tipo: v.tipo, sem_expediente: v.sem_expediente};
    if (v.tipo === "periodos_mes_seguinte") { r.periodos = this.periodos(v.periodos); return r; }
    if (["dia_mes_seguinte", "dia_mes_fixo"].includes(v.tipo)) r.dia = Number(v.dia);
    if (v.tipo === "dia_mes_fixo") r.mes = Number(v.mes);
    if (v.tipo === "dia_mes_seguinte" && v.inicio_dia !== undefined && v.inicio_dia !== null && v.inicio_dia !== "") {
      r.inicio_dia = Number(v.inicio_dia);
      if (!Number.isInteger(r.inicio_dia) || r.inicio_dia < 1 || r.inicio_dia > 31 || r.inicio_dia > r.dia)
        throw new Error("O dia de início deve ficar entre 1 e o dia de vencimento.");
    }
    return r;
  },
  antecedencia(v) {
    if (["periodos_mes_seguinte", "sem_vencimento"].includes(v.tipo)) return null;
    const preenchida = v.inicio_antecedencia_dias !== undefined && v.inicio_antecedencia_dias !== null && v.inicio_antecedencia_dias !== "";
    if (v.tipo === "dia_mes_seguinte" && v.inicio_dia !== undefined && v.inicio_dia !== null && v.inicio_dia !== "" && preenchida)
      throw new Error("Escolha dia fixo de início ou antecedência em dias. Deixe o outro campo vazio.");
    return preenchida ? Number(v.inicio_antecedencia_dias) : null;
  },
  validarPeriodicidade(tipo, periodicidade) {
    if (tipo === "periodos_mes_seguinte" && periodicidade !== "mensal")
      throw new Error("Períodos no mês seguinte exigem periodicidade mensal.");
    return true;
  },
  selecao(itens, ids) { return itens.filter(t => ids.has(t.id)).map(t => ({id: t.id, revision: t.revision})); },
  podeLote(t) { return !!t.pode_gerir && ["a_fazer", "em_andamento", "aguardando_cliente", "devolvida"].includes(t.situacao); },
  visaoConsulta(visao) { return ["minhas", "setor", "cliente"].includes(visao) ? visao : "cliente"; },
  ajuste(v, revision) {
    const dados = {cliente_id: Number(v.cliente_id), obrigacao_id: Number(v.obrigacao_id), tipo: v.ajuste_tipo,
      regra_vencimento: v.ajuste_tipo === "vencimento" ? this.regra(v) : null,
      valido_de: v.valido_de, valido_ate: v.valido_ate, motivo: v.motivo};
    if (revision !== undefined) dados.revision = revision;
    return dados;
  },
  descreverRegra(r = {}) {
    if (r.tipo === "sem_vencimento") return "Sem vencimento";
    if (r.tipo === "ultimo_dia_util_mes_seguinte") return "Último dia útil do mês seguinte à competência";
    const intervalos = (r.periodos || []).map(p => `${String(p.inicio).padStart(2, "0")}–${String(p.fim).padStart(2, "0")}`);
    const texto = r.tipo === "dia_mes_seguinte" ? `${r.inicio_dia ? "Início no dia " + r.inicio_dia + "; vencimento no dia " : "Dia "}${r.dia} do mês seguinte à competência`
      : r.tipo === "dia_mes_fixo" ? `Dia ${r.dia} do mês ${r.mes}`
      : r.tipo === "periodos_mes_seguinte" ? `Períodos ${intervalos.join(" e ")} do mês seguinte à competência` : "Regra não disponível";
    const ajuste = {antecipar: "antecipar para dia útil", adiar: "adiar para dia útil", manter: "manter a data"}[r.sem_expediente || "manter"];
    return `${texto}; ${ajuste}`;
  },
  setoresGeridos(c) { return (c.setores || []).filter(s => (c.setores_geridos || []).includes(s.id)); },
  usuariosSetor(c, setorId) {
    const setor = (c.setores || []).find(s => s.id === Number(setorId));
    const membros = (setor?.membros || []).map(m => typeof m === "object" ? m.usuario_id : m);
    return (c.usuarios || []).filter(p => p.ativo !== false && p.ativo !== 0 && membros.includes(p.id));
  },
  el(tag, texto, classe) {
    const e = document.createElement(tag);
    if (texto !== undefined) e.textContent = texto;
    if (classe) e.className = classe;
    return e;
  },
  botao(texto, acao, classe) {
    const b = this.el("button", texto, classe); b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await acao(); } catch (e) { toast(e.message, "erro"); }
      finally { if (b.isConnected) b.disabled = false; }
    });
    return b;
  },
  opcoes(select, itens, vazio, selecionado) {
    select.textContent = "";
    if (vazio !== undefined) { const o = this.el("option", vazio); o.value = ""; select.append(o); }
    for (const i of itens) {
      const o = this.el("option", i.rotulo ?? i.nome ?? i.usuario ?? String(i.id));
      o.value = i.valor ?? i.id; select.append(o);
    }
    if (selecionado !== undefined) select.value = selecionado ?? "";
  },
  form(titulo, campos, salvar, ajuda = "") {
    const u = this, gatilho = document.activeElement, fundo = u.el("div", undefined, "modal-fundo");
    const form = u.el("form", undefined, "modal largo tar-modal");
    form.setAttribute("role", "dialog"); form.setAttribute("aria-modal", "true");
    form.setAttribute("aria-label", titulo); form.append(u.el("h3", titulo));
    if (ajuda) form.append(u.el("p", ajuda, "dica"));
    const grade = u.el("div", undefined, "tar-grade"), controles = {}, grupos = {};
    for (const c of campos) {
      let entrada;
      const label = u.el(c.tipo === "multi" ? "fieldset" : "label", undefined,
        c.tipo === "multi" ? "tar-opcoes" : "");
      grupos[c.nome] = label;
      if (c.tipo === "multi") {
        label.append(u.el("legend", c.rotulo)); entrada = label;
        for (const o of c.opcoes || []) {
          const l = u.el("label", undefined, "permissao"), box = u.el("input"); box.type = "checkbox";
          box.value = o.valor ?? o.id;
          box.checked = (c.valor || []).map(String).includes(String(box.value));
          l.append(box, u.el("span", o.rotulo ?? o.nome)); label.append(l);
        }
        if (!c.opcoes?.length) label.append(u.el("p", "Nenhuma opção cadastrada.", "dica"));
      } else {
        label.append(u.el("span", c.rotulo));
        if (c.tipo === "select") { entrada = u.el("select"); u.opcoes(entrada, c.opcoes || [], c.vazio, c.valor); }
        else if (c.tipo === "textarea") { entrada = u.el("textarea"); entrada.rows = 3; }
        else { entrada = u.el("input"); entrada.type = c.tipo || "text"; }
        entrada.name = c.nome;
        if (c.tipo === "checkbox") { entrada.checked = !!c.valor; label.classList.add("permissao"); }
        else if (c.valor !== undefined && c.tipo !== "file") entrada.value = c.valor ?? "";
        if (c.obrigatorio) entrada.required = true;
        if (c.desabilitado) entrada.disabled = true;
        if (c.min !== undefined) entrada.min = c.min;
        if (c.max !== undefined) entrada.max = c.max;
        if (c.placeholder) entrada.placeholder = c.placeholder;
        label.append(entrada);
      }
      if (c.ajuda) label.append(u.el("small", c.ajuda, "dica"));
      controles[c.nome] = entrada; grade.append(label);
    }
    const valores = () => Object.fromEntries(campos.map(c => [c.nome,
      c.tipo === "multi" ? [...controles[c.nome].querySelectorAll("input:checked")].map(e => Number(e.value))
        : c.tipo === "checkbox" ? controles[c.nome].checked : controles[c.nome].value]));
    const atualizar = () => { const v = valores(); campos.forEach(c => {
      if (c.opcoesDinamicas) {
        const entrada = controles[c.nome], anterior = entrada.value;
        u.opcoes(entrada, c.opcoesDinamicas(v), c.vazio, anterior);
      }
      if (c.quando) { const visivel = c.quando(v); grupos[c.nome].classList.toggle("oculto", !visivel);
        if (c.tipo !== "multi") controles[c.nome].disabled = !visivel; }
    }); };
    form.addEventListener("change", atualizar); atualizar();
    const erro = u.el("p", "", "erro"); erro.setAttribute("role", "alert");
    const acoes = u.el("div", undefined, "acoes"), ok = u.el("button", "Salvar", "botao-primario"); ok.type = "submit";
    const fechar = () => { document.removeEventListener("keydown", teclado, true); fundo.remove();
      if (gatilho?.isConnected) gatilho.focus(); };
    const teclado = e => {
      if (e.key === "Escape" && !ok.disabled) { e.preventDefault(); fechar(); }
      if (e.key === "Tab") {
        const foco = [...form.querySelectorAll('button,input,select,textarea')].filter(e => !e.disabled && e.getClientRects().length);
        const primeiro = foco[0], ultimo = foco.at(-1);
        if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo?.focus(); }
        else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro?.focus(); }
      }
    };
    document.addEventListener("keydown", teclado, true);
    acoes.append(u.botao("Cancelar", fechar), ok); form.append(grade, erro, acoes); fundo.append(form);
    form.addEventListener("submit", async e => { e.preventDefault(); ok.disabled = true; erro.textContent = "";
      try { if (await salvar(valores()) !== false) fechar(); } catch (e2) { erro.textContent = e2.message; }
      finally { ok.disabled = false; } });
    document.body.append(fundo);
    form.querySelector("input:not(:disabled),select:not(:disabled),textarea:not(:disabled),button:not(:disabled)")?.focus();
  },
  confirmarGeracao(previa, competencia) {
    const u = this;
    return new Promise(resolve => {
      const gatilho = document.activeElement, fundo = u.el("div", undefined, "modal-fundo");
      const modal = u.el("div", undefined, "modal largo tar-modal");
      modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true");
      modal.setAttribute("aria-label", "Prévia de geração");
      modal.append(u.el("h3", "Prévia de geração"),
        u.el("p", `${previa.total} tarefa(s) para a competência ${competencia}. Confira os períodos e as datas antes de gerar.`));
      const rolagem = u.el("div", undefined, "rolagem"), tabela = u.el("table", undefined, "tar-previa-geracao");
      const cabecalho = u.el("thead"), linha = u.el("tr"), corpo = u.el("tbody");
      for (const titulo of ["Cliente", "Tarefa", "Ocorrência", "Início", "Vencimento"]) {
        const th = u.el("th", titulo); th.setAttribute("scope", "col"); linha.append(th);
      }
      cabecalho.append(linha);
      for (const t of previa.itens || previa.tarefas || []) {
        const tr = u.el("tr");
        for (const texto of [t.cliente_nome, t.titulo, u.ocorrencia(t), u.data(t.inicio), u.vencimento(t.vencimento)])
          tr.append(u.el("td", texto));
        corpo.append(tr);
      }
      tabela.append(cabecalho, corpo); rolagem.append(tabela); modal.append(rolagem,
        u.el("p", "As tarefas já existentes serão preservadas. Cada período listado gera uma ocorrência independente.", "dica"));
      const fechar = resposta => {
        document.removeEventListener("keydown", teclado, true); fundo.remove();
        if (gatilho?.isConnected) {
          const foco = gatilho.disabled ? gatilho.closest("form")?.querySelector("input:not(:disabled),select:not(:disabled),button:not(:disabled)") : gatilho;
          foco?.focus();
        }
        resolve(resposta);
      };
      const cancelar = u.botao("Voltar", () => fechar(false));
      const confirmar = u.botao("Confirmar geração", () => fechar(true), "botao-primario");
      const teclado = e => {
        if (e.key === "Escape") { e.preventDefault(); fechar(false); }
        if (e.key === "Tab" && e.shiftKey && document.activeElement === cancelar) { e.preventDefault(); confirmar.focus(); }
        else if (e.key === "Tab" && !e.shiftKey && document.activeElement === confirmar) { e.preventDefault(); cancelar.focus(); }
      };
      const acoes = u.el("div", undefined, "acoes"); acoes.append(cancelar, confirmar); modal.append(acoes); fundo.append(modal);
      document.addEventListener("keydown", teclado, true); document.body.append(fundo); cancelar.focus();
    });
  },
  camposRegra(regra = {}) {
    return [
      {nome: "tipo", rotulo: "Vencimento", tipo: "select", valor: regra.tipo || "dia_mes_seguinte", opcoes: [
        {valor: "dia_mes_seguinte", rotulo: "Dia do mês seguinte à competência"},
        {valor: "ultimo_dia_util_mes_seguinte", rotulo: "Último dia útil do mês seguinte"},
        {valor: "dia_mes_fixo", rotulo: "Dia e mês fixos (anual)"},
        {valor: "periodos_mes_seguinte", rotulo: "Períodos no mês seguinte (mensal)"},
        {valor: "sem_vencimento", rotulo: "Sem vencimento"}],
        ajuda: "Sem vencimento: a tarefa começa no primeiro dia do mês seguinte e não recebe alertas de prazo."},
      {nome: "dia", rotulo: "Dia", tipo: "number", min: 1, max: 31, valor: regra.dia || 20,
        quando: v => ["dia_mes_seguinte", "dia_mes_fixo"].includes(v.tipo), obrigatorio: true},
      {nome: "inicio_dia", rotulo: "Dia fixo de início (opcional)", tipo: "number", min: 1, max: 31, valor: regra.inicio_dia,
        quando: v => v.tipo === "dia_mes_seguinte", ajuda: "No mês seguinte à competência, até o dia do vencimento. Use este campo ou a antecedência em dias."},
      {nome: "periodos", rotulo: "Períodos do mês seguinte", tipo: "textarea", obrigatorio: true,
        valor: (regra.periodos || []).map(p => `${String(p.inicio).padStart(2, "0")}-${String(p.fim).padStart(2, "0")}`).join("; "),
        placeholder: "01-10; 11-20; 21-30", quando: v => v.tipo === "periodos_mes_seguinte",
        ajuda: "Uma tarefa por período, em ordem e sem sobreposição. O dia 30 continua sendo 30 em meses com 31 dias. Em fevereiro, dias inexistentes passam para o último dia do mês."},
      {nome: "mes", rotulo: "Mês do vencimento", tipo: "select", valor: regra.mes || 1,
        opcoes: this.opcoesMeses(), quando: v => v.tipo === "dia_mes_fixo"},
      {nome: "sem_expediente", rotulo: "Se não houver expediente", tipo: "select", valor: regra.sem_expediente || "manter",
        quando: v => v.tipo !== "sem_vencimento",
        opcoes: [{valor: "manter", rotulo: "Manter a data"}, {valor: "antecipar", rotulo: "Antecipar para dia útil"},
          {valor: "adiar", rotulo: "Adiar para dia útil"}]}];
  },
  opcoesMeses() { return ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
    "Setembro", "Outubro", "Novembro", "Dezembro"].map((rotulo, i) => ({valor: i + 1, rotulo})); },
};

const AvisoTarefas = {
  async mostrar() {
    const alvo = document.getElementById("aviso-tarefas");
    if (!alvo) return;
    alvo.classList.add("oculto");
    if (!Sessao.pode("aba.tarefas")) return;
    const r = await api("/api/tarefas/avisos");
    alvo.textContent = "";
    if (!r.vencendo && !r.atrasadas) return;
    alvo.append(TarefasUI.el("span", `${r.vencendo || 0} tarefa(s) vencendo nos próximos ${r.alerta_dias || 3} dias e ${r.atrasadas || 0} atrasada(s).`),
      TarefasUI.botao("Ver tarefas", () => Abas.abrir("tarefas")));
    alvo.classList.remove("oculto");
  },
};

/* A ficha da aba 9 usa as mesmas escolhas e APIs da aba 10. */
const TarefasCliente = {
  async montar(alvo, cliente, recarregar) {
    if (!Sessao.pode("aba.tarefas")) return;
    const u = TarefasUI, bloco = u.el("div", undefined, "conc-bloco tar-cliente");
    bloco.append(u.el("h3", "Características e carteira")); alvo.append(bloco);
    try {
      const [c, d] = await Promise.all([api("/api/tarefas/catalogo"), api(`/api/tarefas/clientes/${cliente.id}`)]);
      const nomes = (d.caracteristicas || []).map(x => typeof x === "object" ? x.nome : c.caracteristicas.find(k => k.id === x)?.nome).filter(Boolean);
      bloco.append(u.el("p", nomes.join(" · ") || "Nenhuma característica marcada."));
      for (const item of d.carteira || []) {
        const setor = c.setores.find(s => s.id === item.setor_id);
        const pessoa = c.usuarios.find(p => p.id === item.responsavel_usuario_id);
        bloco.append(u.el("p", `${setor?.nome || item.setor_nome || "Setor"}: ${pessoa?.nome || pessoa?.usuario || "Sem responsável"}`));
      }
      for (const ajuste of d.ajustes || []) {
        const obrigacao = c.obrigacoes.find(o => o.id === ajuste.obrigacao_id);
        const tipo = {incluir: "Inclusão", excluir: "Exclusão", vencimento: "Vencimento personalizado"}[ajuste.tipo] || "Ajuste";
        bloco.append(u.el("p", `${tipo} · ${obrigacao?.nome || "Obrigação"}: ${ajuste.motivo}${ajuste.valido_ate ? " (até " + u.data(ajuste.valido_ate) + ")" : ""}`, "dica"));
      }
      const acoes = u.el("div", undefined, "acoes");
      acoes.append(u.botao("Ver agenda", () => { Abas.abrir("tarefas");
        document.dispatchEvent(new CustomEvent("tarefas:cliente", {detail: cliente.id})); }));
      if (Sessao.pode("tarefas.configurar") && u.setoresGeridos(c).length) {
        acoes.append(u.botao("Marcar características", () => u.form("Características do cliente", [
          {nome: "caracteristica_ids", rotulo: "Características", tipo: "multi",
            opcoes: c.caracteristicas.map(k => ({id: k.id, nome: `${k.grupo} · ${k.nome}`})),
            valor: (d.caracteristicas || []).map(k => typeof k === "object" ? k.id : k)}], async v => {
          await api(`/api/tarefas/clientes/${cliente.id}/caracteristicas`, {method: "PUT", json: v});
          if (recarregar) await recarregar();
          else { bloco.remove(); await this.montar(alvo, cliente); }
        }, "Em um grupo exclusivo, escolha apenas uma característica.")));
        acoes.append(u.botao("Definir carteira", () => u.form("Responsável pela carteira", [
          {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: u.setoresGeridos(c), obrigatorio: true},
          {nome: "responsavel_usuario_id", rotulo: "Responsável", tipo: "select", opcoes: c.usuarios,
            opcoesDinamicas: v => u.usuariosSetor(c, v.setor_id), vazio: "Sem responsável"}], async v => {
          await api(`/api/tarefas/clientes/${cliente.id}/carteira`, {method: "PUT", json: {
            setor_id: Number(v.setor_id), responsavel_usuario_id: v.responsavel_usuario_id ? Number(v.responsavel_usuario_id) : null}});
          if (recarregar) await recarregar();
          else { bloco.remove(); await this.montar(alvo, cliente); }
        }, "A troca atualiza as tarefas abertas deste setor. As concluídas preservam o responsável anterior.")));
      }
      bloco.append(acoes);
    } catch (e) { bloco.append(u.el("p", e.message, "dica")); }
  },
};

Abas.registrar("tarefas", container => {
  const u = TarefasUI;
  container.innerHTML = `
    <div class="caixa tar-cabecalho"><div><h2>Tarefas e prazos</h2>
      <p class="dica">Acompanhe as entregas da sua carteira, as conferências e a agenda de cada cliente.</p></div>
      <div class="acoes" id="tar-acoes"><button type="button" id="tar-atualizar">Atualizar</button></div>
      <p id="tar-email" class="dica tar-linha-inteira"></p>
      <p id="tar-status" class="status tar-linha-inteira" role="status" aria-live="polite"></p></div>
    <div class="caixa">
      <nav class="conc-subtelas" id="tar-nav" aria-label="Visões de tarefas">
        <button type="button" data-visao="minhas" class="ativa">Minhas tarefas</button>
        <button type="button" data-visao="setor">Setor</button>
        <button type="button" data-visao="cliente">Agenda do cliente</button>
        <button type="button" data-visao="configuracao">Configuração</button>
        <button type="button" data-visao="importar">Importar carteira</button>
      </nav>
      <section id="tar-listagem">
        <form id="tar-filtros" class="linha-form">
          <label>Cliente<select id="tar-cliente"></select></label>
          <label>Setor<select id="tar-setor"></select></label>
          <label>Responsável<select id="tar-responsavel"></select></label>
          <label>Competência<input id="tar-competencia" type="month"></label>
          <label>Situação<select id="tar-situacao"></select></label>
          <label>Vence de<input id="tar-de" type="date"></label>
          <label>Vence até<input id="tar-ate" type="date"></label>
          <label class="permissao"><input type="checkbox" id="tar-sem-responsavel">Sem responsável</label>
          <button type="submit" class="botao-primario">Filtrar</button>
          <button type="button" id="tar-limpar">Limpar</button>
        </form>
        <p class="dica tar-legenda"><span class="tar-cor verde">No prazo</span><span class="tar-cor amarelo">Em atenção</span>
          <span class="tar-cor vermelho">Atrasada ou devolvida</span>As datas e situações também aparecem por escrito.</p>
        <div id="tar-lote" class="linha-form oculto"><span id="tar-selecao">Nenhuma selecionada</span></div>
        <div class="rolagem"><table id="tar-tabela"><thead><tr><th><input id="tar-todas" type="checkbox" aria-label="Selecionar tarefas desta página"></th>
          <th>Tarefa / cliente</th><th>Setor</th><th>Responsável</th><th>Competência</th><th>Vencimento</th><th>Situação</th><th></th>
        </tr></thead><tbody></tbody></table></div>
        <div class="conc-paginacao"><button type="button" id="tar-anterior">‹ Anterior</button><span id="tar-pagina"></span>
          <button type="button" id="tar-proxima">Próxima ›</button></div>
        <div id="tar-detalhe" class="conc-bloco oculto"></div>
      </section>
      <section id="tar-configuracao" class="oculto"></section>
      <section id="tar-importar" class="oculto">
        <h3>Importar a carteira de um colaborador</h3>
        <p class="dica">Confira o cliente de cada linha e escolha as características sugeridas. Contato e e-mail serão atualizados apenas nas linhas confirmadas. As marcas de checklist não são importadas.</p>
        <form id="tar-importar-form" class="linha-form">
          <label>Setor<select id="tar-imp-setor" required></select></label>
          <label>Responsável<select id="tar-imp-responsavel" required></select></label>
          <label>Planilha<input id="tar-imp-arquivo" type="file" accept=".xls,.xlsx" required></label>
          <button class="botao-primario" type="submit">Ver prévia</button>
        </form><div id="tar-imp-previa"></div>
      </section>
    </div>`;
  const $ = id => container.querySelector(`#${id}`);
  const s = {visao: "minhas", pagina: 1, catalogo: null, itens: [], selecionadas: new Set(), consulta: 0};
  const pode = slug => Sessao.pode(slug), gerencia = pode("tarefas.setor") || Sessao.ehAdmin();
  const status = (texto, erro = false) => { $("tar-status").textContent = texto; $("tar-status").classList.toggle("erro", erro); };
  const pessoas = () => (s.catalogo.usuarios || []).filter(x => x.ativo !== false && x.ativo !== 0);
  const setoresGeridos = () => u.setoresGeridos(s.catalogo);
  const obrigacoesGeridas = () => s.catalogo.obrigacoes.filter(o => (s.catalogo.setores_geridos || []).includes(o.setor_id));
  const nomePessoa = id => { const p = s.catalogo.usuarios.find(x => x.id === id); return p?.nome || p?.usuario || (id ? `Usuário ${id}` : "Sem responsável"); };
  const caracteristicas = () => s.catalogo.caracteristicas.map(k => ({id: k.id, nome: `${k.grupo} · ${k.nome}`}));
  const salvar = async (rota, valor, id) => {
    await api(`/api/tarefas/${rota}${id ? "/" + id : ""}`, {method: id ? "PUT" : "POST", json: valor});
    toast("Alteração salva."); await catalogo(); configurar();
  };
  function filtros() {
    const p = {visao: u.visaoConsulta(s.visao)};
    for (const [id, chave] of [["cliente", "cliente_id"], ["setor", "setor_id"], ["responsavel", "responsavel_usuario_id"],
      ["competencia", "competencia"], ["situacao", "situacao"], ["de", "vencimento_de"], ["ate", "vencimento_ate"]]) {
      if ($(`tar-${id}`).value) p[chave] = $(`tar-${id}`).value;
    }
    if ($("tar-sem-responsavel").checked) p.sem_responsavel = "true";
    return p;
  }
  async function catalogo() {
    s.catalogo = await api("/api/tarefas/catalogo");
    for (const [id, itens, vazio] of [["tar-cliente", s.catalogo.clientes, "Todos os clientes"],
      ["tar-setor", s.catalogo.setores, "Todos os setores"], ["tar-responsavel", pessoas(), "Todos"],
      ["tar-imp-setor", setoresGeridos(), "Escolha o setor"], ["tar-imp-responsavel", u.usuariosSetor(s.catalogo, $("tar-imp-setor").value), "Escolha o responsável"]]) {
      const atual = $(id).value; u.opcoes($(id), itens || [], vazio, atual);
    }
    u.opcoes($("tar-situacao"), Object.entries(u.situacoes).map(([valor, rotulo]) => ({valor, rotulo})), "Todas", $("tar-situacao").value);
    $("tar-email").textContent = s.catalogo.email_ativo ? "Resumo diário por e-mail ativado."
      : "E-mail desligado. Os avisos continuam disponíveis aqui; o administrador pode configurar o envio no servidor.";
  }
  function atualizarSelecao() {
    $("tar-selecao").textContent = `${s.selecionadas.size} tarefa(s) selecionada(s)`;
    const disponiveis = s.itens.filter(t => u.podeLote(t));
    $("tar-todas").checked = disponiveis.length > 0 && disponiveis.every(t => s.selecionadas.has(t.id));
    $("tar-todas").disabled = !disponiveis.length;
    $("tar-todas").indeterminate = s.selecionadas.size > 0 && !$("tar-todas").checked;
  }
  async function carregar() {
    const chamada = ++s.consulta;
    status("Carregando tarefas…");
    try {
      const r = await api("/api/tarefas?" + new URLSearchParams({...filtros(), pagina: s.pagina}));
      if (chamada !== s.consulta) return;
      s.itens = r.itens; s.pagina = r.pagina; s.selecionadas.clear();
      const tbody = $("tar-tabela").querySelector("tbody"); tbody.textContent = "";
      for (const t of r.itens) {
        const tr = u.el("tr"), escolher = u.el("input"); escolher.type = "checkbox";
        escolher.setAttribute("aria-label", `Selecionar ${t.titulo}`); escolher.disabled = !u.podeLote(t);
        escolher.addEventListener("change", () => { if (escolher.checked) s.selecionadas.add(t.id); else s.selecionadas.delete(t.id); atualizarSelecao(); });
        const tdEscolher = u.el("td"); tdEscolher.append(escolher); tr.append(tdEscolher);
        const titulo = u.el("td"); titulo.append(u.el("strong", t.titulo), u.el("small", t.cliente_nome || "", "tar-secundario"));
        if (u.ocorrencia(t)) titulo.append(u.el("small", u.ocorrencia(t), "tar-secundario")); tr.append(titulo);
        for (const texto of [t.setor_nome || "—", t.responsavel_efetivo_nome || t.responsavel_nome || nomePessoa(t.responsavel_efetivo_id ?? t.responsavel_usuario_id),
          t.competencia || "Avulsa", u.vencimento(t.vencimento)]) tr.append(u.el("td", texto));
        const estado = u.el("td"); const cor = ["verde", "amarelo", "vermelho"].includes(t.cor) ? t.cor : "neutro";
        estado.append(u.el("span", u.rotuloSituacao(t.situacao), `tar-cor ${cor}`));
        if (t.atrasada) estado.append(u.el("small", "Prazo vencido", "tar-secundario"));
        if (t.fora_do_prazo) estado.append(u.el("small", "Concluída fora do prazo", "tar-secundario"));
        if (t.nao_se_aplica_mais) estado.append(u.el("small", "Não se aplica mais — avaliar dispensa", "tar-secundario"));
        tr.append(estado); const acoes = u.el("td"); acoes.append(u.botao("Abrir", () => detalhe(t.id))); tr.append(acoes); tbody.append(tr);
      }
      if (!r.itens.length) { const tr = u.el("tr"), td = u.el("td", "Nenhuma tarefa encontrada com estes filtros.", "tar-vazio"); td.colSpan = 8; tr.append(td); tbody.append(tr); }
      $("tar-pagina").textContent = `${r.total} tarefa(s) · Página ${r.pagina} de ${Math.max(1, r.paginas)}`;
      $("tar-anterior").disabled = r.pagina <= 1; $("tar-proxima").disabled = r.pagina >= r.paginas;
      atualizarSelecao(); status(""); await AvisoTarefas.mostrar();
    } catch (e) { if (chamada === s.consulta) status(e.message, true); }
  }
  async function detalhe(id) {
    const t = await api(`/api/tarefas/${id}`), alvo = $("tar-detalhe"); alvo.textContent = ""; alvo.classList.remove("oculto");
    const topo = u.el("div", undefined, "tar-cabecalho"); topo.append(u.el("h3", t.titulo), u.botao("Fechar detalhe", () => alvo.classList.add("oculto"))); alvo.append(topo);
    alvo.append(u.el("p", `${t.cliente_nome || "Cliente"} · ${t.setor_nome || "Setor"} · ${u.rotuloSituacao(t.situacao)}`),
      u.el("p", `Vencimento: ${u.vencimento(t.vencimento)} · Responsável: ${t.responsavel_efetivo_nome || nomePessoa(t.responsavel_efetivo_id ?? t.responsavel_usuario_id)}`));
    if (u.ocorrencia(t)) alvo.append(u.el("p", u.ocorrencia(t), "dica"));
    if (t.inicio) alvo.append(u.el("p", `Início previsto: ${u.data(t.inicio)}`, "dica"));
    if (t.concluida_em) alvo.append(u.el("p", `Concluída por ${nomePessoa(t.concluida_por)} em ${new Date(t.concluida_em).toLocaleString("pt-BR")} · ${u.resultadoPrazo(t)}`));
    if (t.conferida_em) alvo.append(u.el("p", `Conferida por ${nomePessoa(t.conferida_por)} em ${new Date(t.conferida_em).toLocaleString("pt-BR")}${t.conferida_substituindo ? ", substituindo " + nomePessoa(t.conferida_substituindo) : ""}`));
    if (t.obrigacao_id) {
      alvo.append(u.el("p", `Origem: obrigação cadastrada · ${u.descreverRegra(t.origem?.regra)}`, "dica"));
      for (const ajuste of t.origem?.ajustes || []) alvo.append(u.el("p", `Ajuste do cliente: ${ajuste.motivo}`, "dica"));
    } else alvo.append(u.el("p", "Origem: tarefa avulsa.", "dica"));
    if (t.nao_se_aplica_mais) alvo.append(u.el("p", "A obrigação não se aplica mais às características atuais. A tarefa foi preservada; o responsável pode dispensá-la com motivo.", "aviso"));
    const acoes = u.el("div", undefined, "acoes");
    const destinos = t.transicoes || ({a_fazer: ["em_andamento", "aguardando_cliente"], em_andamento: ["concluida", "aguardando_cliente"],
      aguardando_cliente: ["em_andamento", "concluida"], devolvida: ["em_andamento", "aguardando_cliente", "concluida"], concluida: t.exige_conferencia ? ["conferida", "devolvida"] : []}[t.situacao] || []);
    for (const situacao of destinos) {
      const supervisao = ["conferida", "devolvida", "dispensada"].includes(situacao);
      if (!(supervisao ? t.pode_gerir : t.pode_executar)) continue;
      acoes.append(u.botao(u.rotuloSituacao(situacao), () => u.form(u.rotuloSituacao(situacao), [
        {nome: "comentario", rotulo: supervisao ? "Motivo" : "Comentário (opcional)", tipo: "textarea", obrigatorio: situacao === "devolvida"}], async v => {
          await api(`/api/tarefas/${id}/situacao`, {json: {situacao, revision: t.revision, comentario: v.comentario}});
          await carregar(); await detalhe(id);
        })));
    }
    if (t.pode_gerir && ["a_fazer", "em_andamento", "aguardando_cliente", "devolvida"].includes(t.situacao)) acoes.append(u.botao("Dispensar", () => u.form("Dispensar tarefa", [
      {nome: "comentario", rotulo: "Motivo da dispensa", tipo: "textarea", obrigatorio: true}], async v => {
        await api(`/api/tarefas/${id}/situacao`, {json: {situacao: "dispensada", revision: t.revision, comentario: v.comentario}}); await carregar(); await detalhe(id);
      })));
    if (t.pode_executar || t.pode_gerir) acoes.append(u.botao("Comentar", () => u.form("Novo comentário", [
      {nome: "comentario", rotulo: "Comentário", tipo: "textarea", obrigatorio: true}], async v => {
        await api(`/api/tarefas/${id}/comentarios`, {json: {comentario: v.comentario, revision: t.revision}}); await carregar(); await detalhe(id);
      })));
    alvo.append(acoes, u.el("h4", "Histórico"));
    const lista = u.el("ol", undefined, "tar-historico");
    for (const e of t.eventos || []) {
      const li = u.el("li"); li.append(u.el("strong", `${e.usuario_login || "Sistema"} · ${new Date(e.criado_em).toLocaleString("pt-BR")}`));
      const dePara = e.tipo === "situacao" ? `${u.rotuloSituacao(e.de)} → ${u.rotuloSituacao(e.para)}` : ({criada: "Tarefa criada", comentario: "Comentário", responsavel: "Responsável alterado", vencimento: "Vencimento alterado"}[e.tipo] || e.tipo);
      li.append(u.el("p", dePara)); if (e.comentario) li.append(u.el("p", e.comentario));
      if (e.substituindo_usuario_id) li.append(u.el("small", `Substituindo ${nomePessoa(e.substituindo_usuario_id)}`)); lista.append(li);
    }
    alvo.append(lista); alvo.scrollIntoView({behavior: "smooth", block: "start"});
  }
  function avulsa() {
    u.form("Nova tarefa avulsa", [
      {nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: s.catalogo.clientes, obrigatorio: true},
      {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: setoresGeridos(), obrigatorio: true},
      {nome: "titulo", rotulo: "O que precisa ser feito", obrigatorio: true},
      {nome: "responsavel_usuario_id", rotulo: "Responsável", tipo: "select", opcoes: pessoas(),
        opcoesDinamicas: v => u.usuariosSetor(s.catalogo, v.setor_id), vazio: "Sem responsável"},
      {nome: "competencia", rotulo: "Competência (opcional)", tipo: "month"},
      {nome: "inicio", rotulo: "Início (opcional)", tipo: "date"}, {nome: "vencimento", rotulo: "Vencimento", tipo: "date", obrigatorio: true},
      {nome: "exige_conferencia", rotulo: "Exigir conferência do responsável do setor", tipo: "checkbox"}], async v => {
        const r = await api("/api/tarefas/avulsas", {json: {...v, cliente_id: Number(v.cliente_id), setor_id: Number(v.setor_id), responsavel_usuario_id: v.responsavel_usuario_id ? Number(v.responsavel_usuario_id) : null}});
        abrirVisao("setor"); if (r.id) await detalhe(r.id);
      });
  }
  function lote(acao) {
    const tarefas = u.selecao(s.itens, s.selecionadas);
    if (!tarefas.length) { toast("Selecione ao menos uma tarefa desta página.", "erro"); return; }
    const campos = [{nome: "motivo", rotulo: "Motivo", tipo: "textarea", obrigatorio: true}];
    const setores = [...new Set(s.itens.filter(t => s.selecionadas.has(t.id)).map(t => t.setor_id))];
    const membrosComuns = pessoas().filter(p => setores.every(id => u.usuariosSetor(s.catalogo, id).some(m => m.id === p.id)));
    if (acao === "redistribuir") campos.unshift({nome: "responsavel_usuario_id", rotulo: "Novo responsável", tipo: "select", opcoes: membrosComuns, vazio: "Sem responsável"});
    u.form(acao === "redistribuir" ? "Redistribuir tarefas" : "Dispensar tarefas", campos, async v => {
      await api("/api/tarefas/lote", {json: {acao, tarefas, motivo: v.motivo, responsavel_usuario_id: v.responsavel_usuario_id ? Number(v.responsavel_usuario_id) : null}});
      $("tar-detalhe").classList.add("oculto"); await carregar();
    }, `${tarefas.length} tarefa(s) selecionada(s). A operação exige que todas ainda estejam na versão exibida.`);
  }
  async function gerar() {
    u.form("Gerar tarefas da competência", [
      {nome: "competencia", rotulo: "Competência", tipo: "month", obrigatorio: true, valor: $("tar-competencia").value},
      {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: setoresGeridos(), obrigatorio: true},
      {nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: s.catalogo.clientes, vazio: "Todos do setor"}], async v => {
        const previa = await api("/api/tarefas/geracao/previa", {json: {competencia: v.competencia, setor_id: Number(v.setor_id), cliente_id: v.cliente_id ? Number(v.cliente_id) : null}});
        if (!previa.total) { toast("Nenhuma tarefa nova a gerar. Confira o catálogo, a carteira e os filtros."); return; }
        if (!await u.confirmarGeracao(previa, v.competencia)) return false;
        await api("/api/tarefas/geracao/confirmar", {json: {token: previa.token}});
        $("tar-competencia").value = v.competencia; $("tar-setor").value = v.setor_id; $("tar-cliente").value = v.cliente_id;
        abrirVisao("setor"); toast("Geração concluída.");
      }, "Você verá as ocorrências e suas datas antes de confirmar. Nenhuma obrigação é criada automaticamente no catálogo.");
  }
  function secao(titulo, ajuda, novo, itens, texto, editar) {
    const bloco = u.el("div", undefined, "conc-bloco tar-config-bloco"), topo = u.el("div", undefined, "tar-cabecalho");
    topo.append(u.el("h3", titulo)); if (novo) topo.append(u.botao("Adicionar", novo)); bloco.append(topo);
    if (ajuda) bloco.append(u.el("p", ajuda, "dica"));
    if (!itens.length) bloco.append(u.el("p", "Nenhum registro cadastrado.", "dica"));
    for (const i of itens) { const linha = u.el("div", undefined, "tar-config-linha"); linha.append(u.el("span", texto(i)));
      if (editar) linha.append(u.botao("Editar", () => editar(i))); bloco.append(linha); }
    $("tar-configuracao").append(bloco);
  }
  function editarSetor(d = {}) {
    u.form(d.id ? "Editar setor" : "Novo setor", [
      {nome: "nome", rotulo: "Nome", valor: d.nome, obrigatorio: true},
      {nome: "responsavel_usuario_id", rotulo: "Responsável do setor", tipo: "select", opcoes: pessoas(), vazio: "Sem responsável", valor: d.responsavel_usuario_id},
      {nome: "membros", rotulo: "Membros do setor", tipo: "multi", opcoes: pessoas(), valor: (d.membros || []).map(x => typeof x === "object" ? x.usuario_id : x)},
      {nome: "ativo", rotulo: "Setor ativo", tipo: "checkbox", valor: d.ativo ?? true}], v => salvar("setores", {...v, responsavel_usuario_id: v.responsavel_usuario_id ? Number(v.responsavel_usuario_id) : null}, d.id));
  }
  function novaSubstituicao() {
    u.form("Substituição por período", [
      {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: s.catalogo.setores, vazio: "Todos os setores"},
      {nome: "titular_usuario_id", rotulo: "Titular", tipo: "select", opcoes: pessoas(), obrigatorio: true},
      {nome: "substituto_usuario_id", rotulo: "Substituto", tipo: "select", opcoes: pessoas(), obrigatorio: true},
      {nome: "inicio", rotulo: "De", tipo: "date", obrigatorio: true}, {nome: "fim", rotulo: "Até (inclusive)", tipo: "date", obrigatorio: true},
      {nome: "motivo", rotulo: "Motivo", tipo: "textarea", obrigatorio: true}], v => salvar("substituicoes", {...v,
        setor_id: v.setor_id ? Number(v.setor_id) : null, titular_usuario_id: Number(v.titular_usuario_id), substituto_usuario_id: Number(v.substituto_usuario_id)}));
  }
  function editarCaracteristica(d = {}) {
    u.form(d.id ? "Editar característica" : "Nova característica", [
      {nome: "grupo", rotulo: "Grupo", valor: d.grupo, placeholder: "Regime, Tributos, Folha…", obrigatorio: true},
      {nome: "nome", rotulo: "Característica", valor: d.nome, obrigatorio: true},
      {nome: "exclusiva_no_grupo", rotulo: "Permitir apenas uma característica deste grupo por cliente", tipo: "checkbox", valor: d.exclusiva_no_grupo},
      {nome: "ativa", rotulo: "Ativa", tipo: "checkbox", valor: d.ativa ?? true}], v => salvar("caracteristicas", v, d.id));
  }
  function editarObrigacao(d = {}) {
    const regra = d.regra_vencimento || {}, condicao = d.condicao || {};
    u.form(d.id ? "Editar obrigação" : "Nova obrigação", [
      {nome: "nome", rotulo: "Nome da obrigação", valor: d.nome, obrigatorio: true},
      {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: setoresGeridos(), valor: d.setor_id, obrigatorio: true},
      {nome: "periodicidade", rotulo: "Periodicidade", tipo: "select", valor: d.periodicidade || "mensal", opcoes: [
        {valor: "mensal", rotulo: "Mensal"}, {valor: "trimestral", rotulo: "Trimestral"}, {valor: "anual", rotulo: "Anual"}, {valor: "demanda", rotulo: "Por demanda"}]},
      {nome: "competencias", rotulo: "Meses de competência", tipo: "multi", opcoes: u.opcoesMeses(), valor: d.competencias || [3, 6, 9, 12],
        quando: v => ["trimestral", "anual"].includes(v.periodicidade), ajuda: "Anual: escolha um mês. Trimestral: escolha os meses de fechamento."},
      ...u.camposRegra(regra),
      {nome: "inicio_antecedencia_dias", rotulo: "Iniciar quantos dias antes do prazo (opcional)", tipo: "number", min: 0, max: 365, valor: d.inicio_antecedencia_dias,
        quando: v => !["periodos_mes_seguinte", "sem_vencimento"].includes(v.tipo),
        ajuda: "Deixe vazio se informar um dia fixo de início. Os períodos já definem seus próprios dias de início."},
      {nome: "todas", rotulo: "O cliente deve ter todas estas características", tipo: "multi", opcoes: caracteristicas(), valor: condicao.todas || []},
      {nome: "alguma", rotulo: "Deve ter pelo menos uma destas", tipo: "multi", opcoes: caracteristicas(), valor: condicao.alguma || []},
      {nome: "nenhuma", rotulo: "Não pode ter nenhuma destas", tipo: "multi", opcoes: caracteristicas(), valor: condicao.nenhuma || []},
      {nome: "exige_conferencia", rotulo: "Exigir conferência do responsável do setor", tipo: "checkbox", valor: d.exige_conferencia},
      {nome: "ativa", rotulo: "Obrigação ativa", tipo: "checkbox", valor: d.ativa ?? true}], async v => {
        const competencias = ["anual", "trimestral"].includes(v.periodicidade) ? v.competencias : [];
        if (v.periodicidade === "anual" && competencias.length !== 1) throw new Error("Escolha uma competência para a obrigação anual.");
        if (v.periodicidade === "trimestral" && !competencias.length) throw new Error("Escolha as competências trimestrais.");
        u.validarPeriodicidade(v.tipo, v.periodicidade);
        await salvar("obrigacoes", {nome: v.nome, setor_id: Number(v.setor_id), periodicidade: v.periodicidade, competencias,
          regra_vencimento: u.regra(v), condicao: {todas: v.todas, alguma: v.alguma, nenhuma: v.nenhuma},
          inicio_antecedencia_dias: u.antecedencia(v),
          exige_conferencia: v.exige_conferencia, ativa: v.ativa, revision: d.revision}, d.id);
      }, "A alteração valerá para as próximas gerações. Tarefas já geradas preservam o prazo e a regra de origem.");
  }
  function novoAjuste(d = {}) {
    u.form(d.id ? "Editar ajuste do cliente" : "Ajuste de uma obrigação para um cliente", [
      {nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: s.catalogo.clientes, obrigatorio: true, valor: d.cliente_id, desabilitado: !!d.id},
      {nome: "obrigacao_id", rotulo: "Obrigação", tipo: "select", opcoes: obrigacoesGeridas(), obrigatorio: true, valor: d.obrigacao_id, desabilitado: !!d.id},
      {nome: "ajuste_tipo", rotulo: "Ajuste", tipo: "select", valor: d.tipo || "incluir", opcoes: [
        {valor: "incluir", rotulo: "Incluir mesmo sem atender às condições"}, {valor: "excluir", rotulo: "Não gerar esta obrigação"}, {valor: "vencimento", rotulo: "Usar outro vencimento"}]},
      ...u.camposRegra(d.regra_vencimento || {}).map(c => ({...c, quando: v => v.ajuste_tipo === "vencimento" && (!c.quando || c.quando(v))})),
      {nome: "valido_de", rotulo: "Válido a partir de (opcional)", tipo: "date", valor: d.valido_de},
      {nome: "valido_ate", rotulo: "Válido até (opcional)", tipo: "date", valor: d.valido_ate},
      {nome: "motivo", rotulo: "Motivo", tipo: "textarea", obrigatorio: true, valor: d.motivo}],
      v => {
        if (v.ajuste_tipo === "vencimento") u.validarPeriodicidade(v.tipo,
          s.catalogo.obrigacoes.find(o => o.id === Number(v.obrigacao_id))?.periodicidade);
        return salvar("ajustes", u.ajuste(v, d.revision), d.id);
      },
      `${d.id ? "A alteração preserva o histórico e vale para as próximas gerações. Para encerrar o ajuste, informe o último dia de validade. " : ""}Para usar início fixo, períodos ou uma rotina sem vencimento, deixe vazia a antecedência em dias no cadastro da obrigação.`);
  }
  function editarFeriado(d = {}) {
    u.form("Feriado e expediente", [
      {nome: "data", rotulo: "Data", tipo: "date", valor: d.data, obrigatorio: true},
      {nome: "descricao", rotulo: "Descrição", valor: d.descricao, obrigatorio: true},
      {nome: "abrangencia", rotulo: "Abrangência", tipo: "select", valor: d.abrangencia || "municipal", opcoes: [
        {valor: "nacional", rotulo: "Nacional"}, {valor: "estadual", rotulo: "Estadual"}, {valor: "municipal", rotulo: "Municipal"}]},
      {nome: "sem_expediente", rotulo: "Sem expediente nesta data", tipo: "checkbox", valor: d.sem_expediente ?? true}], v => salvar("feriados", v),
      "Desmarque a opção para manter expediente em pontos facultativos. As tarefas existentes não serão recalculadas.");
  }
  function configurar() {
    if (!s.catalogo) return;
    $("tar-configuracao").textContent = "";
    if (pode("setores.administrar")) {
      secao("Setores e membros", "Comece pelos setores, seus responsáveis e membros.", () => editarSetor(), s.catalogo.setores,
        d => `${d.nome} · ${nomePessoa(d.responsavel_usuario_id)}${d.ativo ? "" : " · Inativo"}`, editarSetor);
      secao("Substituições", "O substituto assume no período informado; o titular volta automaticamente ao final.", novaSubstituicao,
        s.catalogo.substituicoes || [], d => `${nomePessoa(d.titular_usuario_id)} → ${nomePessoa(d.substituto_usuario_id)} · ${u.data(d.inicio)} a ${u.data(d.fim)} · ${d.motivo}`);
    }
    if (pode("tarefas.configurar")) {
      secao("Características", "As características determinam quais obrigações se aplicam ao cliente.", () => editarCaracteristica(), s.catalogo.caracteristicas,
        d => `${d.grupo} · ${d.nome}${d.exclusiva_no_grupo ? " · Grupo exclusivo" : ""}${d.ativa ? "" : " · Inativa"}`, editarCaracteristica);
      const acoes = u.el("div", undefined, "acoes");
      acoes.append(u.botao("Substituir características em lote", () => u.form("Substituir características em lote", [
        {nome: "cliente_ids", rotulo: "Clientes", tipo: "multi", opcoes: s.catalogo.clientes},
        {nome: "caracteristica_ids", rotulo: "Características", tipo: "multi", opcoes: caracteristicas()}], async v => {
          if (!v.cliente_ids.length) throw new Error("Selecione os clientes.");
          await api("/api/tarefas/caracteristicas/lote", {json: v}); toast("Características atualizadas.");
        }, "A lista de características de cada cliente selecionado será substituída por esta seleção. Escolha todas as características que devem permanecer.")));
      acoes.append(u.botao("Definir carteira de um cliente", () => u.form("Carteira do cliente", [
        {nome: "cliente_id", rotulo: "Cliente", tipo: "select", opcoes: s.catalogo.clientes, obrigatorio: true},
        {nome: "setor_id", rotulo: "Setor", tipo: "select", opcoes: setoresGeridos(), obrigatorio: true},
        {nome: "responsavel_usuario_id", rotulo: "Responsável", tipo: "select", opcoes: pessoas(),
          opcoesDinamicas: v => u.usuariosSetor(s.catalogo, v.setor_id), vazio: "Sem responsável"}], async v => {
          await api(`/api/tarefas/clientes/${v.cliente_id}/carteira`, {method: "PUT", json: {setor_id: Number(v.setor_id), responsavel_usuario_id: v.responsavel_usuario_id ? Number(v.responsavel_usuario_id) : null}});
          toast("Carteira atualizada.");
        }, "As tarefas abertas do setor acompanham a troca; as concluídas preservam o histórico.")));
      $("tar-configuracao").append(acoes);
      secao("Obrigações", "O catálogo começa vazio. Cadastre os prazos confirmados pelo escritório.", () => editarObrigacao(), obrigacoesGeridas(),
        d => `${d.nome} · ${d.periodicidade}${d.exige_conferencia ? " · Exige conferência" : ""}${d.ativa ? "" : " · Inativa"}`, editarObrigacao);
      secao("Ajustes por cliente", "Exceções com motivo e validade, preservadas no histórico.", () => novoAjuste(), s.catalogo.ajustes || [],
        d => `${d.cliente_nome || s.catalogo.clientes.find(c => c.id === d.cliente_id)?.nome || "Cliente"} · ${d.obrigacao_nome || s.catalogo.obrigacoes.find(o => o.id === d.obrigacao_id)?.nome || "Obrigação"} · ${d.tipo} · ${d.motivo}`, novoAjuste);
      secao("Feriados e expediente", "Os nacionais vêm calculados; confirme os estaduais e municipais. Carnaval e Corpus Christi podem ter expediente.", () => editarFeriado(), s.catalogo.feriados || [],
        d => `${u.data(d.data)} · ${d.descricao} · ${d.abrangencia} · ${d.sem_expediente ? "Sem expediente" : "Com expediente"}`, editarFeriado);
    }
    if (pode("setores.administrar") && pode("tarefas.configurar")) {
      const cfg = s.catalogo.configuracao || {}, bloco = u.el("div", undefined, "conc-bloco"); bloco.append(u.el("h3", "Alertas"));
      bloco.append(u.botao("Configurar antecedência e horário", () => u.form("Alertas de tarefas", [
        {nome: "tarefas_alerta_dias", rotulo: "Avisar quantos dias antes", tipo: "number", min: 0, max: 365, valor: cfg.tarefas_alerta_dias ?? 3},
        {nome: "tarefas_resumo_hora", rotulo: "Horário do resumo (Salvador)", tipo: "time", valor: cfg.tarefas_resumo_hora || "07:00", obrigatorio: true},
        {nome: "tarefas_aguardando_cliente_dias", rotulo: "Alertar após quantos dias aguardando cliente", tipo: "number", min: 0, max: 365, valor: cfg.tarefas_aguardando_cliente_dias ?? 5}], async v => {
          await api("/api/tarefas/configuracao", {method: "PUT", json: {...v, tarefas_alerta_dias: Number(v.tarefas_alerta_dias), tarefas_aguardando_cliente_dias: Number(v.tarefas_aguardando_cliente_dias)}}); await catalogo(); toast("Alertas configurados.");
        }))); $("tar-configuracao").append(bloco);
    }
  }
  async function importar(e) {
    e.preventDefault(); const botao = $("tar-importar-form").querySelector("button"); botao.disabled = true;
    const alvo = $("tar-imp-previa"); alvo.textContent = "";
    try {
      const fd = new FormData(); fd.append("arquivo", $("tar-imp-arquivo").files[0]);
      fd.append("setor_id", $("tar-imp-setor").value); fd.append("responsavel_usuario_id", $("tar-imp-responsavel").value);
      const r = await api("/api/tarefas/importacao/previa", {method: "POST", body: fd});
      alvo.append(u.el("h3", "Confira antes de importar"), u.el("p", "Linhas sem cliente escolhido serão ignoradas. As sugestões de características precisam ser marcadas por você.", "dica"));
      const form = u.el("form"), linhas = [];
      for (const l of r.linhas) {
        const box = u.el("div", undefined, "conc-bloco"), select = u.el("select");
        const idsSugeridos = new Set((l.sugestoes || []).map(x => x.id));
        const opcoesClientes = [...(l.sugestoes || []).map(x => ({id: x.id, nome: `Sugestão · ${x.nome}`})),
          ...s.catalogo.clientes.filter(x => !idsSugeridos.has(x.id))];
        const rotulo = u.el("label", "Ligar ao cliente"); u.opcoes(select, opcoesClientes, "Ignorar esta linha", l.cliente_id || ""); rotulo.append(select);
        box.append(u.el("h4", `Linha ${l.linha}: ${l.nome || l.empresa || "Sem nome"}`), rotulo);
        if (l.sugestoes?.length) box.append(u.el("p", "Sugestões: " + l.sugestoes.map(x => x.nome).join(" · "), "dica"));
        if (l.pendencias?.length) box.append(u.el("p", l.pendencias.join(" · "), "aviso"));
        const contato = u.el("input"), email = u.el("input"); contato.value = l.contato_nome || ""; email.type = "email"; email.value = l.contato_email_informado || l.contato_email || "";
        const labelContato = u.el("label", "Contato"), labelEmail = u.el("label", "E-mail (corrija ou deixe vazio)"); labelContato.append(contato); labelEmail.append(email);
        const grade = u.el("div", undefined, "tar-grade"); grade.append(labelContato, labelEmail); box.append(grade);
        if (l.observacao) box.append(u.el("p", `Observação: ${l.observacao}`));
        const campos = u.el("fieldset", undefined, "tar-opcoes"); campos.append(u.el("legend", "Confirmar características"));
        const sugeridas = (l.caracteristicas_sugeridas || []).map(x => typeof x === "object" ? x.id : x);
        for (const k of s.catalogo.caracteristicas) {
          const label = u.el("label", undefined, "permissao"), cb = u.el("input"); cb.type = "checkbox"; cb.value = k.id;
          label.append(cb, u.el("span", `${k.grupo} · ${k.nome}${sugeridas.includes(k.id) ? " (sugerida)" : ""}`)); campos.append(label);
        }
        const refletirLinha = () => {
          contato.disabled = !select.value; email.disabled = !select.value;
          campos.querySelectorAll("input").forEach(cb => { cb.disabled = !select.value; });
        };
        select.addEventListener("change", refletirLinha); refletirLinha();
        box.append(campos); form.append(box); linhas.push({l, select, contato, email, campos});
      }
      const erro = u.el("p", "", "erro"), confirmar = u.el("button", "Confirmar importação", "botao-primario"); confirmar.type = "submit";
      form.append(erro, confirmar); alvo.append(form);
      form.addEventListener("submit", async evento => {
        evento.preventDefault(); confirmar.disabled = true; erro.textContent = "";
        let enviada = false;
        try {
          const decisoes = linhas.filter(x => x.select.value).map(x => ({linha: x.l.linha, cliente_id: Number(x.select.value),
            contato_nome: x.contato.value, contato_email: x.email.value,
            caracteristica_ids: [...x.campos.querySelectorAll("input:checked")].map(c => Number(c.value))}));
          if (!decisoes.length) throw new Error("Escolha ao menos um cliente para importar.");
          if (new Set(decisoes.map(x => x.cliente_id)).size !== decisoes.length) throw new Error("Escolha apenas uma linha para cada cliente.");
          enviada = true;
          await api("/api/tarefas/importacao/confirmar", {json: {token: r.token, decisoes}});
          alvo.textContent = ""; alvo.append(u.el("p", "Carteira importada. Contatos, características e responsáveis confirmados foram gravados juntos.", "status"));
          $("tar-imp-arquivo").value = ""; await catalogo();
        } catch (e2) {
          erro.textContent = e2.message + (enviada ? " Gere uma nova prévia para tentar novamente." : "");
          if (enviada) confirmar.textContent = "Gere uma nova prévia acima";
          else confirmar.disabled = false;
        }
      });
    } catch (e2) { alvo.append(u.el("p", e2.message, "erro")); }
    finally { botao.disabled = false; }
  }
  function abrirVisao(visao) {
    s.visao = visao; s.pagina = 1; s.selecionadas.clear();
    $("tar-nav").querySelectorAll("button").forEach(b => { b.classList.toggle("ativa", b.dataset.visao === visao); b.setAttribute("aria-pressed", b.dataset.visao === visao ? "true" : "false"); });
    $("tar-listagem").classList.toggle("oculto", ["configuracao", "importar"].includes(visao));
    $("tar-configuracao").classList.toggle("oculto", visao !== "configuracao"); $("tar-importar").classList.toggle("oculto", visao !== "importar");
    $("tar-responsavel").disabled = visao === "minhas";
    $("tar-sem-responsavel").disabled = visao === "minhas";
    if (visao === "minhas") { $("tar-responsavel").value = ""; $("tar-sem-responsavel").checked = false; }
    $("tar-detalhe").classList.add("oculto");
    if (visao === "configuracao") configurar(); else if (visao !== "importar") carregar();
  }
  $("tar-nav").addEventListener("click", e => { const b = e.target.closest("button[data-visao]"); if (b) abrirVisao(b.dataset.visao); });
  if (!(gerencia || pode("tarefas.todas"))) $("tar-nav").querySelector('[data-visao="setor"]').classList.add("oculto");
  if (!(pode("tarefas.configurar") || pode("setores.administrar"))) $("tar-nav").querySelector('[data-visao="configuracao"]').classList.add("oculto");
  if (!pode("tarefas.configurar")) $("tar-nav").querySelector('[data-visao="importar"]').classList.add("oculto");
  if (pode("tarefas.configurar")) $("tar-acoes").append(u.botao("Gerar competência", gerar), u.botao("Nova tarefa avulsa", avulsa, "botao-primario"));
  if (pode("tarefas.exportar")) $("tar-acoes").append(u.botao("Exportar Excel", () => apiDownload("/api/tarefas/exportar?" + new URLSearchParams(filtros()))));
  if (gerencia) { $("tar-lote").classList.remove("oculto"); $("tar-lote").append(u.botao("Redistribuir", () => lote("redistribuir")), u.botao("Dispensar", () => lote("dispensar"))); }
  $("tar-todas").addEventListener("change", e => { s.selecionadas.clear(); if (e.target.checked) s.itens.filter(t => u.podeLote(t)).forEach(t => s.selecionadas.add(t.id));
    $("tar-tabela").querySelectorAll("tbody input").forEach((cb, i) => { cb.checked = s.selecionadas.has(s.itens[i].id); }); atualizarSelecao(); });
  $("tar-filtros").addEventListener("submit", e => { e.preventDefault(); s.pagina = 1; carregar(); });
  $("tar-limpar").addEventListener("click", () => { $("tar-filtros").reset(); s.pagina = 1; carregar(); });
  $("tar-anterior").addEventListener("click", () => { s.pagina = Math.max(1, s.pagina - 1); carregar(); });
  $("tar-proxima").addEventListener("click", () => { s.pagina += 1; carregar(); });
  $("tar-atualizar").addEventListener("click", async () => { try { await catalogo(); abrirVisao(s.visao); } catch (e) { status(e.message, true); } });
  $("tar-importar-form").addEventListener("submit", importar);
  $("tar-imp-setor").addEventListener("change", () => u.opcoes($("tar-imp-responsavel"), u.usuariosSetor(s.catalogo, $("tar-imp-setor").value), "Escolha o responsável"));
  const pronto = catalogo();
  pronto.then(() => abrirVisao("minhas")).catch(e => status(e.message, true));
  document.addEventListener("tarefas:cliente", async e => {
    try { await pronto; $("tar-filtros").reset(); $("tar-cliente").value = e.detail; abrirVisao("cliente"); }
    catch (erro) { status(erro.message, true); }
  });
});
