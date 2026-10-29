/* Central operacional: contagens do servidor no escopo autorizado.
   Ferramentas seguem acessíveis por Abas.permitida(), sem novo papel de acesso. */

"use strict";

/* Uma linha por ferramenta, na mesma ordem da lateral. O nome e o icone NAO
   sao repetidos aqui: saem do proprio botao da lateral (clonados), para nao
   existirem dois lugares para renomear uma ferramenta. */
const RESUMO_FERRAMENTAS = {
  comparador: "Cruza o SPED com a relação da SEFAZ e aponta o que falta de "
            + "cada lado.",
  diff: "Compara dois arquivos SPED campo a campo e lista as divergências.",
  conferencia: "Carrega as notas, confere a composição fiscal e gera Livro "
             + "Fiscal, DANFE e SPED corrigido.",
  extracao: "Extrai os itens das notas para auditoria em planilha.",
  produtos: "Audita a tributação do cadastro de produtos e propõe as correções.",
  conciliacao: "Importa os relatórios da SEFAZ e concilia receita e DIMP por "
             + "competência.",
  patrimonio: "Controla bens, responsáveis, movimentações e inventário.",
  nfse: "Importa a lista do cliente, confere cada nota, gera a DPS do padrão "
      + "nacional e a transmite à produção restrita (sem valor fiscal).",
  clientes: "Cadastro dos clientes com as senhas de portais no cofre "
          + "criptografado e o aviso de vencimento dos certificados digitais.",
  tarefas: "Organiza a carteira, gera a agenda de obrigações e acompanha os prazos e as conferências.",
};

function saudacao() {
  const hora = new Date().getHours();
  if (hora < 12) return "Bom dia";
  return hora < 18 ? "Boa tarde" : "Boa noite";
}

function dataPorExtenso() {
  const texto = new Date().toLocaleDateString("pt-BR",
    { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/* Monta o cartao de uma ferramenta. O icone e o rotulo vem clonados do botao
   da lateral; se por algum motivo o botao nao existir, o cartao e' pulado —
   um atalho sem destino seria pior que atalho nenhum. */
function cartaoDaFerramenta(nome) {
  const botaoLateral =
    document.querySelector(`.abas button[data-aba="${nome}"]`);
  if (!botaoLateral) return null;

  const rotulo = botaoLateral.textContent.trim();
  const numerada = rotulo.match(/^(\d+)\.\s*(.+)$/);

  const cartao = document.createElement("button");
  cartao.type = "button";
  cartao.className = "atalho";
  cartao.innerHTML = `
    <span class="atalho-icone" aria-hidden="true"></span>
    <span class="atalho-corpo">
      <span class="atalho-nome"></span>
      <span class="atalho-texto"></span>
    </span>
    <span class="atalho-numero" aria-hidden="true"></span>
    <svg class="atalho-seta" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
         aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>`;

  const icone = botaoLateral.querySelector("svg");
  if (icone) {
    const copia = icone.cloneNode(true);
    copia.setAttribute("width", "20");
    copia.setAttribute("height", "20");
    cartao.querySelector(".atalho-icone").appendChild(copia);
  }
  cartao.querySelector(".atalho-nome").textContent =
    numerada ? numerada[2] : rotulo;
  cartao.querySelector(".atalho-texto").textContent =
    RESUMO_FERRAMENTAS[nome] || "";
  cartao.querySelector(".atalho-numero").textContent =
    numerada ? numerada[1] : "";

  cartao.addEventListener("click", () => Abas.abrir(nome));
  return cartao;
}

function montarInicio(container) {
  const nome = (Sessao.usuario && (Sessao.usuario.nome || Sessao.usuario.usuario))
             || "";
  const primeiroNome = nome.trim().split(/\s+/)[0] || "";
  const ferramentas = Abas.disponiveis();

  const temAdmin = Abas.permitida("admin");

  container.innerHTML = `
    <section class="capa${Sessao.pode("aba.tarefas") ? " capa-operacional" : ""}">
      <div class="capa-texto">
        <p class="eyebrow capa-data"></p>
        <h2 class="capa-titulo"></h2>
        <p class="capa-linha"></p>
      </div>
      <img class="capa-selo" src="logo.jpg" alt="" width="72" height="72">
    </section>

    <div id="inicio-central"></div>
    ${ferramentas.length ? `
      <div class="secao-titulo">
        <h3>Suas ferramentas</h3>
        <span class="cracha" id="inicio-contagem"></span>
      </div>
      <div class="atalhos" id="inicio-atalhos"></div>` : `
      <div class="caixa vazio">
        <h2>Nenhuma ferramenta liberada</h2>
        <p class="dica" id="inicio-vazio"></p>
      </div>`}
    <div id="inicio-admin"></div>`;

  const atualizarSaudacao = () => {
    container.querySelector(".capa-data").textContent = dataPorExtenso();
    container.querySelector(".capa-titulo").textContent = primeiroNome ? `${saudacao()}, ${primeiroNome}.` : `${saudacao()}.`;
  };
  atualizarSaudacao(); document.addEventListener("inicio:abrir", atualizarSaudacao);
  /* "menu de navegacao" e nao "menu a esquerda": em tela estreita a lateral
     vira uma barra no topo (ver o @media do estilo.css). */
  container.querySelector(".capa-linha").textContent = ferramentas.length
    ? (Sessao.pode("aba.tarefas") ? "Acompanhe as prioridades e continue o trabalho da sua equipe." : "Escolha uma ferramenta abaixo ou use o menu de navegação.")
    : "Nenhuma ferramenta de auditoria liberada para o seu usuário.";
  if (ferramentas.length) {
    container.querySelector("#inicio-contagem").textContent =
      ferramentas.length === 1 ? "1 liberada" : `${ferramentas.length} liberadas`;
    const grade = container.querySelector("#inicio-atalhos");
    ferramentas.forEach((ferramenta) => {
      const cartao = cartaoDaFerramenta(ferramenta);
      if (cartao) grade.appendChild(cartao);
    });
  } else {
    /* Quem tem SO administracao chega aqui. Mandar essa pessoa "pedir ao
       administrador" seria mandar ela falar consigo mesma — o texto muda
       conforme o que ela alcanca. */
    container.querySelector("#inicio-vazio").textContent = temAdmin
      ? "Seu acesso é só de administração. Libere ferramentas para o seu "
        + "usuário na aba Administração."
      : "Peça ao administrador para liberar o seu acesso.";
  }

  if (temAdmin) {
    const area = container.querySelector("#inicio-admin");
    area.innerHTML = `<div class="secao-titulo"><h3>Sistema</h3></div>
                      <div class="atalhos"></div>`;
    const cartao = cartaoDaFerramenta("admin");
    if (cartao) {
      cartao.classList.add("atalho-sistema");
      cartao.querySelector(".atalho-texto").textContent =
        "Usuários, permissões e histórico de acessos.";
      area.querySelector(".atalhos").appendChild(cartao);
    }
  }
  CentralUI.montar(container.querySelector("#inicio-central"));
}

const CentralUI = {
  consulta(filtros = {}, fila = "pendentes", pagina = 1) {
    return {...TarefasUI.contexto({filtros}).filtros, fila, pagina, limite: 10};
  },
  async consultar(estado, obter) {
    const numero = estado.consulta = (estado.consulta || 0) + 1;
    const vigente = () => numero === estado.consulta && (!("usuarioId" in estado) || Sessao.usuario?.id === estado.usuarioId);
    try { const dados = await obter(); return {atual: vigente(), dados}; }
    catch (erro) { if (!vigente()) return {atual: false}; throw erro; }
  },
  montar(container) {
    if (!Sessao.pode("aba.tarefas")) return false;
    const u = TarefasUI, s = {fila: "pendentes", pagina: 1, consulta: 0, catalogo: null, filtros: {visao: "cliente"}, usuarioId: Sessao.usuario?.id};
    const sessaoValida = () => Sessao.usuario?.id === s.usuarioId && Sessao.pode("aba.tarefas");
    container.innerHTML = `
      <section class="caixa central" aria-label="Central operacional">
        <div class="tar-cabecalho"><div><p class="eyebrow">Gestão do escritório</p><h2>Sua operação, por prioridade</h2>
          <p class="dica">As contagens consideram todas as ocorrências no seu acesso e nos filtros abaixo.</p></div>
          <button type="button" id="central-atualizar">Atualizar</button></div>
        <details class="central-filtros-bloco"><summary>Filtros <span id="central-filtros-resumo">Todo o meu acesso · Todas as competências</span></summary>
        <form id="central-filtros" class="central-filtros">
          <label>Escopo<select name="visao"><option value="cliente">Todo o meu acesso</option><option value="minhas">Minhas tarefas</option></select></label>
          <label>Competência<input name="competencia" type="month"><small class="dica">Vazio inclui todas as competências.</small></label>
          <label>Cliente<select name="cliente_id"><option value="">Todos os clientes</option></select></label>
          <label>Setor<select name="setor_id"><option value="">Todos os setores</option></select></label>
          <label>Responsável<select name="responsavel_usuario_id"><option value="">Todos</option></select></label>
          <label>Buscar tarefa ou cliente<input name="texto" type="search" maxlength="200" placeholder="Digite um nome ou tarefa"></label>
          <div class="acoes"><button class="botao-primario" type="submit">Aplicar filtros</button><button type="button" id="central-limpar">Limpar</button></div>
        </form></details>
        <p id="central-status" role="status" aria-live="polite"></p>
        <div id="central-resultados" class="oculto">
          <p id="central-referencia" class="dica"></p><div id="central-indicadores" class="central-indicadores"></div>
          <p class="dica">Uma tarefa pode aparecer em mais de um indicador. Os indicadores permanecem iguais ao trocar a fila.</p>
          <div class="central-colunas"><section class="central-fila" aria-label="Fila de tarefas">
            <div class="tar-cabecalho"><h3>Fila de trabalho</h3><button type="button" id="central-lista">Abrir lista completa</button></div>
            <label class="central-seletor">Mostrar<select id="central-fila"></select></label>
            <div id="central-itens"></div>
            <div class="conc-paginacao"><button id="central-anterior" type="button">‹ Anterior</button><span id="central-pagina"></span><button id="central-proxima" type="button">Próxima ›</button></div>
          </section><section class="central-distribuicao" aria-label="Pendências por responsável">
            <h3>Pendências por responsável</h3><p class="dica">Carga atual, incluindo conferências. Responsáveis efetivos na data da consulta.</p>
            <div id="central-responsaveis"></div>
          </section></div>
        </div>
      </section>`;
    const $ = id => container.querySelector(`#${id}`), form = $("central-filtros");
    const controle = nome => form.elements.namedItem(nome);
    const mensagem = (texto, erro = false) => { $("central-status").textContent = texto; $("central-status").classList.toggle("erro", erro); };
    const filtros = () => {
      const valores = Object.fromEntries(["visao", "competencia", "cliente_id", "setor_id", "responsavel_usuario_id", "texto"].map(k => [k, controle(k).value.trim()]));
      if (valores.visao === "minhas") valores.responsavel_usuario_id = "";
      return u.contexto({filtros: valores}).filtros;
    };
    const refletirEscopo = () => {
      controle("responsavel_usuario_id").disabled = controle("visao").value === "minhas";
      if (controle("responsavel_usuario_id").disabled) controle("responsavel_usuario_id").value = "";
    };
    const refletirFiltros = () => {
      const f = s.filtros, c = s.catalogo || {}, partes = [({cliente: "Todo o meu acesso", minhas: "Minhas tarefas", setor: "Visão dos setores"})[f.visao], f.competencia ? `Competência ${f.competencia}` : "Todas as competências"];
      for (const [campo, itens, nome] of [["cliente_id", c.clientes, "Cliente"], ["setor_id", c.setores, "Setor"], ["responsavel_usuario_id", c.usuarios, "Responsável"]]) {
        if (f[campo]) { const item = (itens || []).find(i => String(i.id) === String(f[campo])); partes.push(`${nome}: ${item?.nome || item?.usuario || "selecionado"}`); }
      }
      if (f.texto) partes.push(`Busca: ${f.texto}`);
      $("central-filtros-resumo").textContent = partes.join(" · ");
    };
    u.opcoes($("central-fila"), Object.entries(u.filas).map(([valor, rotulo]) => ({valor, rotulo})), undefined, s.fila);
    const desenhar = dados => {
      $("central-resultados").classList.remove("oculto");
      $("central-referencia").textContent = `${dados.resumo.total} tarefa(s) no conjunto filtrado · ${dados.resumo.pendentes} pendente(s) · Referência: ${u.data(dados.hoje)}, Salvador.`;
      const cards = $("central-indicadores"); cards.textContent = "";
      for (const [fila, chave, titulo, ajuda, cor] of [
        ["atrasadas", "atrasadas", "Atrasadas", "Abertas com prazo vencido", "vermelho"],
        ["hoje", "vencendo_hoje", "Vencem hoje", "Abertas para a data de hoje", "amarelo"],
        ["proximas", "proximas", "Próximos prazos", `Nos próximos ${dados.alerta_dias} dias`, ""],
        ["conferencia", "pendentes_conferencia", "Para conferir", "Concluídas aguardando conferência", ""],
        ["aguardando_cliente", "aguardando_cliente", "Aguardando cliente", "Inclui tarefas sem prazo", ""],
        ["sem_responsavel", "sem_responsavel", "Sem responsável", "Pendentes para atribuir", ""],
        ["sem_vencimento", "sem_vencimento", "Sem vencimento", "Pendentes sem data limite", ""]]) {
        const card = u.botao("", () => { s.focoIndicador = fila; s.fila = fila; s.pagina = 1; $("central-fila").value = fila; return carregar(); }, `central-indicador ${cor}`);
        card.dataset.fila = fila;
        card.setAttribute("aria-pressed", String(s.fila === fila));
        card.append(u.el("span", titulo), u.el("strong", String(dados.resumo[chave])), u.el("small", ajuda)); cards.append(card);
      }
      const itens = $("central-itens"); itens.textContent = "";
      for (const t of dados.fila.itens) {
        const linha = u.el("article", undefined, "central-tarefa"), info = u.el("div");
        info.append(u.el("strong", t.titulo), u.el("p", t.cliente_nome || "Cliente"),
          u.el("small", `${t.responsavel_efetivo_nome || t.responsavel_nome || "Sem responsável"} · ${t.competencia || "Avulsa"}`));
        if (u.ocorrencia(t)) info.append(u.el("small", u.ocorrencia(t)));
        const estado = u.el("div", undefined, "central-tarefa-estado");
        estado.append(u.el("span", u.vencimento(t.vencimento)), u.el("span", u.rotuloSituacao(t.situacao), `tar-cor ${["verde","amarelo","vermelho"].includes(t.cor) ? t.cor : "neutro"}`),
          u.botao("Abrir tarefa", () => u.abrirContexto({filtros: s.filtros, fila: s.fila, tarefa_id: t.id})));
        linha.append(info, estado); itens.append(linha);
      }
      if (!dados.fila.itens.length) itens.append(u.el("p", dados.resumo.total ? "Nenhuma tarefa nesta fila com os filtros aplicados." : "Nenhuma tarefa no seu acesso com os filtros aplicados.", "central-vazio"));
      s.pagina = dados.fila.pagina;
      $("central-pagina").textContent = `${dados.fila.total} tarefa(s) · Página ${s.pagina} de ${Math.max(1, dados.fila.paginas)}`;
      $("central-anterior").disabled = s.pagina <= 1; $("central-proxima").disabled = s.pagina >= dados.fila.paginas;
      const pessoas = $("central-responsaveis"); pessoas.textContent = "";
      const pendentes = dados.por_responsavel.filter(p => p.pendentes > 0).sort((a,b) => b.pendentes - a.pendentes);
      for (const p of pendentes) {
        const linha = u.el("div", undefined, "central-pessoa"); linha.append(u.el("strong", p.nome || "Sem responsável"),
          u.el("span", `${p.pendentes} pendente(s)`), u.el("small", `${p.atrasadas} atrasada(s) · ${p.pendentes_conferencia} para conferir`)); pessoas.append(linha);
      }
      if (!pendentes.length) pessoas.append(u.el("p", "Nenhuma pendência no conjunto filtrado.", "dica"));
      if (s.focoIndicador) { cards.querySelector(`[data-fila="${s.focoIndicador}"]`)?.focus(); s.focoIndicador = ""; }
    };
    const carregar = async () => {
      if (!sessaoValida() || s.catalogoPendente) return;
      refletirFiltros();
      mensagem("Carregando a operação…"); $("central-resultados").classList.add("oculto"); container.setAttribute("aria-busy", "true");
      try {
        const consulta = this.consulta(s.filtros, s.fila, s.pagina);
        const r = await this.consultar(s, () => api("/api/tarefas/painel?" + new URLSearchParams(consulta)));
        if (!r.atual || !container.isConnected) return;
        desenhar(r.dados); mensagem(""); container.setAttribute("aria-busy", "false");
      } catch (erro) { if (container.isConnected && sessaoValida()) { mensagem(erro.message + " Use Atualizar para tentar novamente.", true); container.setAttribute("aria-busy", "false"); } }
    };
    const aplicar = () => { s.filtros = filtros(); s.pagina = 1; return carregar(); };
    form.addEventListener("submit", e => { e.preventDefault(); aplicar(); });
    controle("visao").addEventListener("change", refletirEscopo);
    $("central-limpar").addEventListener("click", () => { form.reset(); refletirEscopo(); s.fila = "pendentes"; $("central-fila").value = s.fila; aplicar(); });
    $("central-fila").addEventListener("change", () => { s.fila = $("central-fila").value; s.pagina = 1; carregar(); });
    $("central-anterior").addEventListener("click", () => { s.pagina -= 1; carregar(); });
    $("central-proxima").addEventListener("click", () => { s.pagina += 1; carregar(); });
    $("central-lista").addEventListener("click", () => u.abrirContexto({filtros: s.filtros, fila: s.fila}));
    const iniciarCatalogo = async () => {
      if (!sessaoValida()) return;
      const numero = s.consultaCatalogo = (s.consultaCatalogo || 0) + 1;
      const vigente = () => numero === s.consultaCatalogo && container.isConnected && sessaoValida();
      ++s.consulta; s.catalogoPendente = true;
      $("central-atualizar").disabled = true;
      $("central-resultados").classList.add("oculto"); container.setAttribute("aria-busy", "true");
      mensagem("Carregando os filtros…"); form.querySelectorAll("input,select,button").forEach(e => { e.disabled = true; });
      try {
        const c = await api("/api/tarefas/catalogo"); if (!vigente()) return; s.catalogo = c;
        for (const [campo, itens, vazio] of [["cliente_id", c.clientes, "Todos os clientes"], ["setor_id", c.setores, "Todos os setores"],
          ["responsavel_usuario_id", c.usuarios.filter(p => p.ativo !== false && p.ativo !== 0), "Todos"]]) {
          const valido = valor => itens.some(i => String(i.id) === String(valor));
          const anterior = controle(campo).value;
          u.opcoes(controle(campo), itens, vazio, valido(anterior) ? anterior : "");
          if (s.filtros[campo] && !valido(s.filtros[campo])) { delete s.filtros[campo]; s.pagina = 1; }
        }
        const visoes = [{valor: "cliente", rotulo: "Todo o meu acesso"}, {valor: "minhas", rotulo: "Minhas tarefas"}];
        if ((c.setores_geridos || []).length || Sessao.pode("tarefas.todas")) {
          visoes.push({valor: "setor", rotulo: "Visão dos setores"});
        }
        const visaoValida = valor => visoes.some(i => i.valor === valor);
        u.opcoes(controle("visao"), visoes, undefined, visaoValida(controle("visao").value) ? controle("visao").value : "cliente");
        if (!visaoValida(s.filtros.visao)) { s.filtros.visao = "cliente"; s.pagina = 1; }
        form.querySelectorAll("input,select,button").forEach(e => { e.disabled = false; }); refletirEscopo();
        s.catalogoPendente = false; await carregar();
      } catch (erro) { if (vigente()) { mensagem(erro.message + " Use Atualizar para tentar novamente.", true); container.setAttribute("aria-busy", "false"); } }
      finally { if (vigente()) { s.catalogoPendente = false; $("central-atualizar").disabled = false; } }
    };
    $("central-atualizar").addEventListener("click", iniciarCatalogo);
    document.addEventListener("inicio:abrir", iniciarCatalogo);
    document.addEventListener("sessao:encerrada", () => { ++s.consulta; ++s.consultaCatalogo; $("central-resultados").classList.add("oculto"); });
    iniciarCatalogo(); return true;
  },
};

Abas.registrar("inicio", montarInicio);
