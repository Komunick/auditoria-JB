/* Nucleo do frontend: tema, autenticacao, permissoes, abas, fetch e jobs.
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
    if (salvar) localStorage.setItem("tema", tema);
    /* O botao virou icone (sol/lua): o CSS troca qual dos dois SVG aparece.
       Escrever no textContent apagaria os SVG, entao o rotulo mora num span
       so-para-leitor-de-tela. Ele nomeia a ACAO ("Modo escuro" = vai escurecer)
       e por isso o botao NAO leva aria-pressed: nome que muda mais estado que
       muda se anulam, e o leitor anunciaria "Modo claro, pressionado". */
    const botao = document.getElementById("botao-tema");
    const rotulo = document.getElementById("rotulo-tema");
    const texto = tema === "escuro" ? "Modo claro" : "Modo escuro";
    if (rotulo) rotulo.textContent = texto;
    if (botao) botao.title = texto + " (a escolha fica salva neste navegador)";
  },
  iniciar() {
    const salvo = localStorage.getItem("tema");
    const sistema = matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
    this.aplicar(salvo || sistema, !!salvo);
    document.getElementById("botao-tema").addEventListener("click", () => {
      this.aplicar(document.documentElement.dataset.theme === "escuro" ? "claro" : "escuro");
    });
  },
};

// ----------------------------------------------------------------------
// Menu lateral retratil (pedido do dono, 2026-07-22): o botao no rodape da
// lateral minimiza o menu para so os icones; a preferencia fica no navegador.
// Em telas estreitas a lateral ja vira barra no topo e o botao some (CSS).

const Lateral = {
  aplicar(recolhido) {
    document.getElementById("tela-app")
      .classList.toggle("menu-recolhido", recolhido);
    localStorage.setItem("menuRecolhido", recolhido ? "1" : "0");
    const botao = document.getElementById("botao-lateral");
    botao.firstChild.textContent = recolhido ? "»" : "«";
    const rotulo = recolhido ? "Expandir o menu" : "Minimizar o menu";
    botao.title = rotulo;
    /* Minimizado, o CSS esconde o <span> com o texto e sobra so a seta: sem
       aria-label o botao ficaria com o nome acessivel "»". */
    botao.setAttribute("aria-label", rotulo);
  },
  iniciar() {
    document.getElementById("botao-lateral").addEventListener("click", () =>
      this.aplicar(!document.getElementById("tela-app")
        .classList.contains("menu-recolhido")));
    this.aplicar(localStorage.getItem("menuRecolhido") === "1");
  },
};

// ----------------------------------------------------------------------
// Toasts e modais

function toast(mensagem, tipo) {
  const caixa = document.createElement("div");
  caixa.className = "toast" + (tipo === "erro" ? " erro" : "");
  caixa.textContent = mensagem;
  document.getElementById("toasts").appendChild(caixa);
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
          <button class="cancelar">Nao</button>
          <button class="confirmar botao-primario">Sim</button>
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
    throw new Error("Faca login para continuar.");
  }
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    let extras = null;
    try { extras = (await resposta.json()).detail; } catch {}
    /* O erro pode vir como texto simples (rotas antigas) ou como o objeto
       {detail, code, ...} do contrato da conciliacao. Sem tratar o objeto,
       `new Error(obj)` viraria a mensagem inutil "[object Object]" na cara do
       usuario. O `code` fica no erro para quem precisa reagir a um caso
       especifico sem depender do texto, que muda. */
    if (extras && typeof extras === "object") {
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
    /* A classe "ativa" so pinta. aria-current e o que faz o leitor de tela
       anunciar QUAL das nove abas esta aberta — sem ele, a cor e a barrinha
       da lateral nao chegam a ninguem que navegue por audio. */
    document.querySelectorAll(".abas button").forEach((b) => {
      const ativa = b.dataset.aba === nome;
      b.classList.toggle("ativa", ativa);
      if (ativa) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    document.querySelectorAll("main .aba").forEach((s) =>
      s.classList.toggle("oculto", s.id !== `aba-${nome}`));
    // O topo mostra a ferramenta ativa (o nome vem do proprio botao da lateral).
    const botao = document.querySelector(`.abas button[data-aba="${nome}"]`);
    const titulo = document.getElementById("titulo-tela");
    const chapeu = document.getElementById("eyebrow-tela");
    if (botao && titulo) {
      /* O rotulo da lateral traz o numero da ferramenta ("3. Livro de
         Conferencia"). No topo o numero sai do titulo e vira o chapeu, que
         fica menor e em caixa alta — o titulo respira e a numeracao nao some. */
      const rotulo = botao.textContent.trim();
      const numerada = rotulo.match(/^(\d+)\.\s*(.+)$/);
      titulo.textContent = numerada ? numerada[2] : rotulo;
      if (chapeu) {
        chapeu.textContent = numerada ? `Ferramenta ${numerada[1]}`
          : nome === "admin" ? "Sistema" : "Painel";
      }
    }
    /* O Inicio remonta sempre: ele mostra a saudacao e a data do dia, e num
       escritorio o navegador fica aberto da manha a noite — montado uma vez
       so, ele diria "Bom dia" as sete da noite. Remontar e barato (ele so le
       o que ja esta na lateral); as ferramentas seguem montando uma vez, que
       e o que preserva o trabalho em andamento nelas. */
    if (nome === "inicio") this._montadas.delete("inicio");
    if (!this._montadas.has(nome) && this._registro[nome]) {
      this._montadas.add(nome);
      this._registro[nome](document.getElementById(`aba-${nome}`));
    }
    /* Se o clique veio de dentro da secao que acabou de sumir (os atalhos do
       Inicio), o foco cairia no <body> em silencio. Ele vai para a aba que
       abriu — que e' onde a pessoa esta agora. */
    if (focado && focado.closest && focado.closest("main .aba.oculto")) {
      botao?.focus();
    }
    if (nome !== "admin" && nome !== "inicio") {
      /* Registra no historico "o que acessou". Falhar aqui nao pode atrapalhar
         quem esta trabalhando: a aba ja abriu. O Inicio fica de fora porque
         /api/eventos/aba so aceita slug do catalogo (responde 422 no resto). */
      api("/api/eventos/aba", { json: { aba: nome } }).catch(() => {});
    }
  },
  iniciar() {
    const nav = document.getElementById("abas-nav");
    nav.addEventListener("click", (e) => {
      const botao = e.target.closest("button[data-aba]");
      if (botao) this.abrir(botao.dataset.aba);
    });
    /* `primeira` conta so ferramenta de verdade: o Inicio esta sempre
       liberado e, se contasse, quem nao tem nenhuma ferramenta cairia num
       painel vazio em vez do aviso "sem acesso liberado". */
    let primeira = "";
    nav.querySelectorAll("button[data-aba]").forEach((botao) => {
      const nome = botao.dataset.aba;
      // Tooltip com o nome da ferramenta: e o unico rotulo visivel quando o
      // menu esta minimizado (so icones).
      botao.title = botao.textContent.trim();
      if (this.permitida(nome)) {
        if (nome !== "inicio") primeira = primeira || nome;
      } else {
        botao.classList.add("oculto");
      }
    });
    /* O rotulo "Ferramentas" encabeca so as sete. Sem nenhuma visivel — nao
       so no caso de zero permissoes, mas tambem para quem so administra — ele
       ficaria pairando sobre uma lista vazia. */
    if (!this.disponiveis().length) {
      document.querySelector(".abas-grupo")?.classList.add("oculto");
    }
    if (primeira) { this.abrir("inicio"); return; }
    /* Nada liberado, nem administracao: nao ha painel para mostrar, entao some
       tambem o Inicio e a tela inteira vira o aviso de "sem acesso liberado". */
    document.querySelector('.abas button[data-aba="inicio"]')
      ?.classList.add("oculto");
    document.querySelectorAll("main .aba").forEach((s) => s.classList.add("oculto"));
    document.getElementById("sem-acesso").classList.remove("oculto");
    document.getElementById("titulo-tela").textContent = "Sem acesso";
    document.getElementById("eyebrow-tela").textContent = "Painel";
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
// Telas (login/bootstrap/app)

const Telas = {
  mostrarLogin() {
    // Fecha qualquer modal aberto: um editor/confirmacao por cima do cartao de
    // login (sessao que caiu com o modal aberto) deixaria o login inalcancavel.
    document.querySelectorAll(".modal-fundo").forEach((m) => m.remove());
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
      Telas.mostrarApp(novo.usuario);
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
      Telas.mostrarApp(novo.usuario);
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
