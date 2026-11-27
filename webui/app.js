/* Nucleo do frontend: tema, autenticacao, permissoes, abas, paleta, fetch e jobs.
   Sem framework nem build (padrao da casa). Cada ferramenta registra sua aba
   com Abas.registrar(nome, montar) e recebe o container ao ser aberta.

   Permissoes: o servidor manda a lista do usuario em /api/estado e o front
   apenas DEIXA DE DESENHAR o que ele nao alcanca. Isso e conforto, nao
   seguranca — quem barra de verdade e o 403 do servidor. */

"use strict";

// ----------------------------------------------------------------------
// Tema claro/escuro (preferencia salva; padrao segue o sistema)

const Tema = {
  /* `salvar` separa a ESCOLHA da pessoa do palpite inicial. Gravando os dois
     no localStorage, o tema deduzido de prefers-color-scheme viraria uma
     escolha explicita na primeira visita e o "padrao segue o sistema" nunca
     mais valeria — quem troca o Windows para escuro continuaria no claro. */
  aplicar(tema, salvar = true) {
    document.documentElement.dataset.theme = tema;
    if (salvar && typeof localStorage !== "undefined") localStorage.setItem("tema", tema);
    const texto = tema === "escuro" ? "Modo claro" : "Modo escuro";
    for (const [btnId, rotId] of [["botao-tema", "rotulo-tema"], ["botao-tema-login", "rotulo-tema-login"]]) {
      const botao = document.getElementById(btnId);
      const rotulo = document.getElementById(rotId);
      if (rotulo) rotulo.textContent = texto;
      if (botao) botao.title = texto + " (a escolha fica salva neste navegador)";
    }
  },
  iniciar() {
    const salvo = typeof localStorage !== "undefined" ? localStorage.getItem("tema") : null;
    const escuroSys = typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
    this.aplicar(salvo || (escuroSys ? "escuro" : "claro"), !!salvo);
    const alternar = () => this.aplicar(document.documentElement.dataset.theme === "escuro" ? "claro" : "escuro");
    document.getElementById("botao-tema")?.addEventListener("click", alternar);
    document.getElementById("botao-tema-login")?.addEventListener("click", alternar);
  },
};

// ----------------------------------------------------------------------
// Menu lateral retratil (desktop) + gaveta responsiva (mobile <= 920px)

const Lateral = {
  aplicar(recolhido) {
    document.getElementById("tela-app")?.classList.toggle("menu-recolhido", recolhido);
    if (typeof localStorage !== "undefined") localStorage.setItem("menuRecolhido", recolhido ? "1" : "0");
    const botao = document.getElementById("botao-lateral");
    if (!botao) return;
    if (botao.firstChild) botao.firstChild.textContent = recolhido ? "»" : "«";
    const rotulo = recolhido ? "Expandir o menu" : "Recolher o menu";
    botao.title = rotulo;
    botao.setAttribute("aria-label", rotulo);
  },
  abrirGaveta(abrir) {
    const app = document.getElementById("tela-app");
    const jaAberto = typeof app?.classList?.contains === "function" && app.classList.contains("menu-aberto");
    const aberto = typeof abrir === "boolean" ? abrir : !jaAberto;
    app?.classList?.toggle("menu-aberto", aberto);
    const btnMenu = document.getElementById("botao-menu");
    if (btnMenu) btnMenu.setAttribute("aria-expanded", String(aberto));
  },
  fecharGaveta() { this.abrirGaveta(false); },
  iniciar() {
    document.getElementById("botao-lateral")?.addEventListener("click", () =>
      this.aplicar(!document.getElementById("tela-app")?.classList.contains("menu-recolhido")));
    const recolhido = typeof localStorage !== "undefined" && localStorage.getItem("menuRecolhido") === "1";
    this.aplicar(recolhido);
    document.getElementById("botao-menu")?.addEventListener("click", () => this.abrirGaveta());
    document.getElementById("botao-menu-fechar")?.addEventListener("click", () => this.fecharGaveta());
    document.getElementById("lateral-fundo")?.addEventListener("click", () => this.fecharGaveta());
  },
};

// ----------------------------------------------------------------------
// Alternancia de visibilidade de senha na tela de login / bootstrap

const SenhasLogin = {
  iniciar() {
    for (const [btnId, inputId] of [["toggle-login-senha", "login-senha"], ["toggle-boot-senha", "boot-senha"]]) {
      const btn = document.getElementById(btnId);
      const campo = document.getElementById(inputId);
      if (!btn || !campo) continue;
      btn.addEventListener("click", () => {
        const mostrar = campo.type === "password";
        campo.type = mostrar ? "text" : "password";
        btn.setAttribute("aria-pressed", String(mostrar));
        btn.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
        btn.classList.toggle("visivel", mostrar);
      });
    }
  },
};

// ----------------------------------------------------------------------
// Toasts e modais

function toast(mensagem, tipo) {
  const caixa = document.createElement("div");
  caixa.className = "toast" + (tipo === "erro" ? " erro" : "");
  caixa.textContent = mensagem;
  document.getElementById("toasts")?.appendChild(caixa);
  setTimeout(() => caixa.remove(), 6000);
}

/* Escapa texto que vira HTML por interpolacao (tr.innerHTML das tabelas). Os
   dados vem de XML de terceiros, planilha do cliente e observacao digitada por
   qualquer usuario — sem isto, uma observacao com <img onerror> rodaria script
   na sessao de quem abre a tabela (o admin, com todo o acesso). */
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* Iniciais para o avatar do topo: primeira e ultima palavra do nome. Nomes de
   uma palavra so (ou login sem nome) rendem uma letra — melhor que duas letras
   inventadas a partir do mesmo termo. */
function iniciais(nome) {
  const partes = String(nome || "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  const primeira = partes[0][0];
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return (primeira + ultima).toUpperCase();
}

/* Pergunta de sim/nao. As perguntas daqui sao caras (gerar SPED corrigido, dar
   baixa em bem, aprovar competencia), entao o dialogo precisa se comportar
   como dialogo: anunciar-se, receber o foco, aceitar Escape como "nao" e
   devolver o foco a quem o abriu. */
function confirmar(titulo, mensagem) {
  return new Promise((resolver) => {
    const gatilho = document.activeElement;
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    fundo.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <h3></h3><p class="mensagem"></p>
        <div class="acoes">
          <button class="cancelar" type="button">Não</button>
          <button class="confirmar botao-primario" type="button">Sim</button>
        </div>
      </div>`;
    /* aria-label em vez de aria-labelledby: dois dialogos abertos ao mesmo
       tempo dividiriam o mesmo id de titulo. */
    fundo.querySelector(".modal").setAttribute("aria-label", titulo);
    fundo.querySelector("h3").textContent = titulo;
    fundo.querySelector(".mensagem").textContent = mensagem;

    const fechar = (resposta) => {
      document.removeEventListener("keydown", aoTeclar, true);
      fundo.remove();
      if (gatilho && gatilho.isConnected) gatilho.focus();
      resolver(resposta);
    };
    const aoTeclar = (evento) => {
      if (evento.key !== "Escape") return;
      evento.preventDefault();
      fechar(false);
    };
    document.addEventListener("keydown", aoTeclar, true);
    fundo.querySelector(".cancelar").onclick = () => fechar(false);
    fundo.querySelector(".confirmar").onclick = () => fechar(true);
    document.body.appendChild(fundo);
    // O foco comeca no "Nao": a resposta segura e a que fica a um Enter.
    fundo.querySelector(".cancelar").focus();
  });
}

// ----------------------------------------------------------------------
// API (fetch com tratamento de erro/401 padronizado)

async function api(caminho, opcoes = {}) {
  const config = { headers: {}, ...opcoes };
  if (config.json !== undefined) {
    config.method = config.method || "POST";
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(config.json);
    delete config.json;
  }
  const resposta = await fetch(caminho, config);
  if (resposta.status === 401) {
    Telas.mostrarLogin();
    throw new Error("Faça login para continuar.");
  }
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    let extras = null;
    try { extras = (await resposta.json()).detail; } catch {}
    if (Array.isArray(extras)) {
      const motivos = extras.map((e) => {
        const campo = (e && Array.isArray(e.loc) ? e.loc : [])
          .filter((p) => p !== "body" && p !== "query").join(".");
        const texto = e && e.type === "missing" ? "não foi enviado" : (e && e.msg) || "";
        return campo ? `${campo} ${texto}` : texto;
      }).filter(Boolean);
      detalhe = motivos.length
        ? `Dados incompletos ou inválidos: ${motivos.join("; ")}.` : detalhe;
    } else if (extras && typeof extras === "object") {
      detalhe = extras.detail || detalhe;
    } else if (extras) {
      detalhe = extras;
    }
    const erro = new Error(detalhe);
    erro.status = resposta.status;
    if (extras && typeof extras === "object") {
      erro.codigo = extras.code || "";
      if (extras.current_revision !== undefined) {
        erro.revisionAtual = extras.current_revision;
      }
    }
    throw erro;
  }
  const tipo = resposta.headers.get("content-type") || "";
  return tipo.includes("application/json") ? resposta.json() : resposta;
}

async function apiUpload(caminho, arquivo) {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);
  return api(caminho, { method: "POST", body: corpo });
}

async function apiDownload(caminho, opcoes = {}) {
  const resposta = await api(caminho, opcoes);
  const blob = await resposta.blob();
  const nome = (resposta.headers.get("content-disposition") || "")
    .match(/filename="?([^";]+)"?/)?.[1] || "arquivo";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nome; a.click();
  URL.revokeObjectURL(url);
  return nome;
}

/* Polling de job em segundo plano (equivalente aos QThread do desktop).

   `ferramenta` e a aba que iniciou o processamento e vai obrigatoriamente na
   consulta: a rota /api/jobs/ e compartilhada pelas seis ferramentas e, alem
   de conferir o dono, confere a aba esperada. Sem ela o servidor responde
   422. Falhar aqui, no cliente, deixa o erro obvio na primeira execucao em
   vez de virar um 422 confuso no meio de um processamento. */
async function esperarJob(jobId, ferramenta) {
  if (!ferramenta) throw new Error("esperarJob exige a ferramenta da aba.");
  const consulta = `/api/jobs/${jobId}?ferramenta=${encodeURIComponent(ferramenta)}`;
  for (;;) {
    const job = await api(consulta);
    if (job.status === "concluido") return job.resultado;
    if (job.status === "erro") throw new Error(job.erro);
    await new Promise((r) => setTimeout(r, 700));
  }
}

// ----------------------------------------------------------------------
// Sessao e permissoes do usuario logado

const Sessao = {
  usuario: null,
  _permissoes: new Set(),
  definir(usuario) {
    this.usuario = usuario;
    this._permissoes = new Set((usuario && usuario.permissoes) || []);
  },
  pode(slug) { return this._permissoes.has(slug); },
  ehAdmin() { return !!(this.usuario && this.usuario.admin); },
};

/* Esconde o elemento quando falta a permissao. Devolve se pode (o chamador
   costuma pular a montagem do resto do controle). */
function seNaoPuder(elemento, slug) {
  const pode = Sessao.pode(slug);
  if (!pode && elemento) elemento.classList.add("oculto");
  return pode;
}

// ----------------------------------------------------------------------
// Abas (cada ferramenta registra a sua; montagem sob demanda)

function _dadosBotaoAba(botao) {
  const rotuloEl = typeof botao.querySelector === "function" ? botao.querySelector(".nav-rotulo") : null;
  const textoBase = (rotuloEl ? rotuloEl.textContent : botao.textContent || "").trim();
  const numerada = textoBase.match(/^(\d+)\.\s*(.+)$/);
  const numero = (botao.dataset && botao.dataset.numero) || (numerada ? numerada[1] : "");
  const nomeLimpo = numerada ? numerada[2] : textoBase;
  const grupoEl = typeof botao.closest === "function" ? botao.closest("[data-grupo]") : null;
  const grupo = grupoEl?.dataset?.grupo || "";
  const rotuloGrupo = grupoEl?.dataset?.rotulo || "";
  return { numero, nomeLimpo, grupo, rotuloGrupo };
}

const Abas = {
  _registro: {},
  _montadas: new Set(),
  registrar(nome, montar) { this._registro[nome] = montar; },
  /* O Inicio e um painel do proprio front (atalhos para o que a pessoa
     alcanca) — nao existe no catalogo de permissoes do servidor e por isso
     esta sempre liberado. */
  permitida(nome) {
    if (nome === "inicio") return true;
    if (nome === "admin") {
      return Sessao.pode("admin.usuarios") || Sessao.pode("admin.historico");
    }
    return Sessao.pode(`aba.${nome}`);
  },
  abrir(nome) {
    if (!this.permitida(nome)) return;
    const focado = document.activeElement;
    document.querySelectorAll(".abas button").forEach((b) => {
      const ativa = b.dataset.aba === nome;
      b.classList.toggle("ativa", ativa);
      if (ativa) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    document.querySelectorAll("main .aba").forEach((s) =>
      s.classList.toggle("oculto", s.id !== `aba-${nome}`));
    const botao = document.querySelector(`.abas button[data-aba="${nome}"]`);
    const titulo = document.getElementById("titulo-tela");
    const chapeu = document.getElementById("eyebrow-tela");
    if (botao && titulo) {
      const info = _dadosBotaoAba(botao);
      titulo.textContent = info.nomeLimpo;
      if (chapeu) {
        chapeu.textContent = info.numero
          ? `Ferramenta ${info.numero}`
          : info.rotuloGrupo || (info.grupo === "gestao" ? "Gestão" : info.grupo === "sistema" ? "Sistema" : "Ferramentas");
      }
    }
    const jaMontada = this._montadas.has(nome);
    if (!this._montadas.has(nome) && this._registro[nome]) {
      this._montadas.add(nome);
      this._registro[nome](document.getElementById(`aba-${nome}`));
    }
    if (nome === "inicio" && jaMontada) document.dispatchEvent(new CustomEvent("inicio:abrir"));
    Lateral.fecharGaveta();
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      window.scrollTo(0, 0);
    }
    if (focado && focado.closest && focado.closest("main .aba.oculto")) {
      botao?.focus();
    }
    if (nome !== "admin" && nome !== "inicio") {
      api("/api/eventos/aba", { json: { aba: nome } }).catch(() => {});
    }
  },
  iniciar() {
    const nav = document.getElementById("abas-nav");
    nav.addEventListener("click", (e) => {
      const botao = e.target.closest("button[data-aba]");
      if (botao) this.abrir(botao.dataset.aba);
    });
    let primeira = "";
    nav.querySelectorAll("button[data-aba]").forEach((botao) => {
      const nome = botao.dataset.aba;
      const info = _dadosBotaoAba(botao);
      botao.title = info.numero ? `${info.numero}. ${info.nomeLimpo}` : info.nomeLimpo;
      if (this.permitida(nome)) {
        if (nome !== "inicio") primeira = primeira || nome;
      }
      botao.classList.toggle("oculto", !this.permitida(nome));
    });
    this.atualizarGrupos();
    if (primeira) { this.abrir("inicio"); return; }
    document.querySelector('.abas button[data-aba="inicio"]')
      ?.classList.add("oculto");
    this.atualizarGrupos();
    document.querySelectorAll("main .aba").forEach((s) => s.classList.add("oculto"));
    document.getElementById("sem-acesso").classList.remove("oculto");
    document.getElementById("titulo-tela").textContent = "Sem acesso";
    document.getElementById("eyebrow-tela").textContent = "Painel";
  },
  atualizarGrupos() {
    document.querySelectorAll(".nav-grupo").forEach((grupo) => {
      const temAcesso = [...grupo.querySelectorAll("button[data-aba]")].some((b) => !b.classList.contains("oculto"));
      grupo.classList.toggle("oculto", !temAcesso);
    });
  },
  /* Lista das ferramentas que a pessoa alcanca, na ordem da lateral, para o
     painel de Inicio montar os atalhos sem duplicar a regra de permissao. */
  disponiveis() {
    return [...document.querySelectorAll('.abas button[data-aba]')]
      .map((b) => b.dataset.aba)
      .filter((nome) => nome !== "inicio" && nome !== "admin"
                        && this.permitida(nome));
  },
};

// ----------------------------------------------------------------------
// Paleta rapida (Ctrl+K) — lista apenas abas permitidas ao usuario

const PALAVRAS_ABAS = {
  inicio: "central painel prioridades fila atalhos resumo",
  tarefas: "tarefas prazos agenda carteira obrigacoes vencimentos",
  qualidade: "qualidade ocorrencias planos acao indicadores horas custo",
  clientes: "clientes cofre senhas certificados vencimentos base fiscal",
  comparador: "comparador sped sefaz faltantes canceladas",
  diff: "comparar versoes sped diff divergencias",
  conferencia: "livro conferencia fiscal danfe xml sped corrigido",
  extracao: "extracao itens planilha auditoria",
  produtos: "auditoria produtos tributacao ncm cest cst fdb firebird",
  conciliacao: "conciliacao fiscal sefaz receita dimp quadro 50",
  nfse: "emissao nfse dps sefin nacional recibo",
  antecipacao: "antecipacao parcial difal icms bahia ba xml nfe cfop aliquota interestadual",
  patrimonio: "patrimonio bens etiqueta inventario termo responsabilidade",
  admin: "administracao usuarios permissoes historico acessos trilha",
};

const _norm = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const Paleta = {
  _indice: 0,
  _itens: [],
  _gatilho: null,
  _permitidas() {
    const botoes = [...document.querySelectorAll(".abas button[data-aba]")];
    const saida = [];
    for (const botao of botoes) {
      const aba = botao.dataset.aba;
      if (!Abas.permitida(aba)) continue;
      const info = _dadosBotaoAba(botao);
      saida.push({
        aba,
        nome: info.nomeLimpo,
        numero: info.numero,
        grupo: info.rotuloGrupo || info.grupo || "Geral",
        busca: _norm(`${aba} ${info.numero} ${info.nomeLimpo} ${info.rotuloGrupo} ${PALAVRAS_ABAS[aba] || ""}`),
      });
    }
    return saida;
  },
  renderizar() {
    const entrada = document.getElementById("paleta-entrada");
    const lista = document.getElementById("paleta-lista");
    const vazio = document.getElementById("paleta-vazio");
    if (!lista) return;
    const termo = _norm((entrada?.value || "").trim());
    const todos = this._permitidas();
    this._itens = termo ? todos.filter((i) => i.busca.includes(termo)) : todos;
    this._indice = this._itens.length ? Math.min(this._indice, this._itens.length - 1) : 0;
    lista.textContent = "";
    vazio?.classList.toggle("oculto", this._itens.length > 0);
    this._itens.forEach((item, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "paleta-item" + (idx === this._indice ? " ativa" : "");
      b.setAttribute("role", "option");
      b.setAttribute("aria-selected", String(idx === this._indice));
      const esq = document.createElement("span");
      esq.className = "paleta-item-nome";
      esq.textContent = item.numero ? `${item.numero.padStart(2, "0")} · ${item.nome}` : item.nome;
      const dir = document.createElement("span");
      dir.className = "paleta-item-grupo";
      dir.textContent = item.grupo;
      b.append(esq, dir);
      b.addEventListener("click", () => { this.fechar(false); Abas.abrir(item.aba); });
      lista.appendChild(b);
    });
  },
  abrir() {
    if (!Sessao.usuario) return;
    const fundo = document.getElementById("paleta-fundo");
    const entrada = document.getElementById("paleta-entrada");
    if (!fundo) return;
    this._gatilho = document.activeElement;
    this._indice = 0;
    if (entrada) entrada.value = "";
    fundo.classList.remove("oculto");
    this.renderizar();
    entrada?.focus();
  },
  fechar(restaurar = true) {
    const fundo = document.getElementById("paleta-fundo");
    if (!fundo) return;
    if (typeof fundo.classList?.contains === "function" && fundo.classList.contains("oculto")) return;
    fundo.classList?.add("oculto");
    if (restaurar && this._gatilho?.isConnected) this._gatilho.focus();
  },
  iniciar() {
    const fundo = document.getElementById("paleta-fundo");
    const entrada = document.getElementById("paleta-entrada");
    document.getElementById("botao-busca")?.addEventListener("click", () => this.abrir());
    document.getElementById("paleta-fechar")?.addEventListener("click", () => this.fechar());
    fundo?.addEventListener("click", (e) => { if (e.target === fundo) this.fechar(); });
    entrada?.addEventListener("input", () => { this._indice = 0; this.renderizar(); });
    entrada?.addEventListener("keydown", (e) => {
      if (!this._itens.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault(); this._indice = (this._indice + 1) % this._itens.length; this.renderizar();
      } else if (e.key === "ArrowUp") {
        e.preventDefault(); this._indice = (this._indice - 1 + this._itens.length) % this._itens.length; this.renderizar();
      } else if (e.key === "Enter") {
        e.preventDefault(); const alvo = this._itens[this._indice];
        if (alvo) { this.fechar(false); Abas.abrir(alvo.aba); }
      }
    });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        if (!Sessao.usuario) return;
        e.preventDefault();
        fundo?.classList.contains("oculto") ? this.abrir() : this.fechar();
      } else if (e.key === "Escape") {
        if (fundo && !fundo.classList.contains("oculto")) { e.preventDefault(); this.fechar(); return; }
        Lateral.fecharGaveta();
      }
    });
  },
};

// ----------------------------------------------------------------------
// Telas (login/bootstrap/app)

const Telas = {
  mostrarLogin() {
    Sessao.definir(null);
    document.dispatchEvent(new CustomEvent("sessao:encerrada"));
    // Fecha qualquer modal aberto: um editor/confirmacao por cima do cartao de
    // login (sessao que caiu com o modal aberto) deixaria o login inalcancavel.
    document.querySelectorAll(".modal-fundo").forEach((m) => m.remove());
    Paleta.fechar(false);
    Lateral.fecharGaveta();
    document.getElementById("tela-app").classList.add("oculto");
    document.getElementById("tela-login").classList.remove("oculto");
  },
  mostrarApp(usuario) {
    Sessao.definir(usuario);
    document.getElementById("tela-login").classList.add("oculto");
    document.getElementById("tela-app").classList.remove("oculto");
    const nome = usuario.nome || usuario.usuario || "";
    document.getElementById("usuario-logado").textContent = nome;
    document.getElementById("perfil-logado").textContent =
      usuario.admin ? "administrador" : "";
    document.getElementById("avatar-usuario").textContent = iniciais(nome);
    Abas.iniciar();
    /* Certificados vencidos ou vencendo: aviso no topo para quem alcanca a
       aba 9 (spec 012). Falhar aqui nao atrapalha a entrada no sistema. */
    if (typeof AvisoVencimentos !== "undefined") {
      AvisoVencimentos.mostrar().catch(() => {});
    }
    if (typeof AvisoTarefas !== "undefined") {
      AvisoTarefas.mostrar().catch(() => {});
    }
  },
};

/* Cada ferramenta se registra no seu proprio <script>, todos depois deste.
   Se /api/estado responder antes de o navegador terminar de ler esses
   arquivos (resposta em cache, servidor na mesma maquina), Abas.iniciar()
   abriria uma aba cujo modulo ainda nao existe e a area de trabalho ficaria
   em branco, sem erro nenhum na tela. Esperar o documento fechar custa nada
   e tira a corrida do caminho. */
function documentoPronto() {
  if (document.readyState !== "loading") return Promise.resolve();
  return new Promise((resolver) =>
    document.addEventListener("DOMContentLoaded", resolver, { once: true }));
}

async function iniciar() {
  Tema.iniciar();
  Lateral.iniciar();
  SenhasLogin.iniciar();
  Paleta.iniciar();
  const estado = await api("/api/estado");
  await documentoPronto();
  const formLogin = document.getElementById("form-login");
  const formBoot = document.getElementById("form-bootstrap");

  /* Os dois formularios sao preparados SEMPRE, inclusive quando ja entramos
     logados. Eles nascem com .oculto no HTML e, antes disto, so eram revelados
     e ligados no caminho "nao logado" — entao a sessao que caia no meio do
     trabalho levava a um cartao de login sem campo, sem botao e sem saida a
     nao ser recarregar a pagina na mao. */
  formBoot.classList.toggle("oculto", !estado.precisa_bootstrap);
  formLogin.classList.toggle("oculto", !!estado.precisa_bootstrap);

  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    document.getElementById("login-erro").textContent = "";
    try {
      await api("/api/login", { json: {
        usuario: document.getElementById("login-usuario").value,
        senha: document.getElementById("login-senha").value } });
      const novo = await api("/api/estado");
      // Recomeçar o documento impede reaproveitar DOM/consultas de outro usuário.
      if (!novo.logado) throw new Error("Não foi possível confirmar a sessão.");
      location.reload();
    } catch (erro) {
      document.getElementById("login-erro").textContent = erro.message;
    }
  });

  formBoot.addEventListener("submit", async (e) => {
    e.preventDefault();
    document.getElementById("boot-erro").textContent = "";
    try {
      await api("/api/bootstrap", { json: {
        usuario: document.getElementById("boot-usuario").value,
        nome: document.getElementById("boot-nome").value,
        senha: document.getElementById("boot-senha").value } });
      const novo = await api("/api/estado");
      if (!novo.logado) throw new Error("Não foi possível confirmar a sessão.");
      location.reload();
    } catch (erro) {
      document.getElementById("boot-erro").textContent = erro.message;
    }
  });

  if (estado.logado) { Telas.mostrarApp(estado.usuario); return; }
  Telas.mostrarLogin();
}

document.getElementById("botao-sair").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.reload();
});

iniciar().catch((erro) => {
  /* Sem o estado nao da para decidir qual tela abrir, e as duas nascem
     ocultas: um toast que some em seis segundos deixaria a pessoa diante de
     uma pagina totalmente em branco. Cai no login, com o motivo escrito onde
     ele nao desaparece. */
  document.getElementById("form-login").classList.remove("oculto");
  Telas.mostrarLogin();
  document.getElementById("login-erro").textContent = erro.message;
  toast(erro.message, "erro");
});
