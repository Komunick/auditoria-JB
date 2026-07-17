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
  aplicar(tema) {
    document.documentElement.dataset.theme = tema;
    localStorage.setItem("tema", tema);
    const botao = document.getElementById("botao-tema");
    if (botao) botao.textContent = tema === "escuro" ? "Modo claro" : "Modo escuro";
  },
  iniciar() {
    const salvo = localStorage.getItem("tema");
    const sistema = matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
    this.aplicar(salvo || sistema);
    document.getElementById("botao-tema").addEventListener("click", () => {
      this.aplicar(document.documentElement.dataset.theme === "escuro" ? "claro" : "escuro");
    });
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

function confirmar(titulo, mensagem) {
  return new Promise((resolver) => {
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    fundo.innerHTML = `
      <div class="modal">
        <h3></h3><p class="mensagem"></p>
        <div class="acoes">
          <button class="cancelar">Nao</button>
          <button class="confirmar botao-primario">Sim</button>
        </div>
      </div>`;
    fundo.querySelector("h3").textContent = titulo;
    fundo.querySelector(".mensagem").textContent = mensagem;
    fundo.querySelector(".cancelar").onclick = () => { fundo.remove(); resolver(false); };
    fundo.querySelector(".confirmar").onclick = () => { fundo.remove(); resolver(true); };
    document.body.appendChild(fundo);
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
    try { detalhe = (await resposta.json()).detail || detalhe; } catch {}
    throw new Error(detalhe);
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

/* Polling de job em segundo plano (equivalente aos QThread do desktop). */
async function esperarJob(jobId) {
  for (;;) {
    const job = await api(`/api/jobs/${jobId}`);
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
  permitida(nome) {
    if (nome === "admin") {
      return Sessao.pode("admin.usuarios") || Sessao.pode("admin.historico");
    }
    return Sessao.pode(`aba.${nome}`);
  },
  abrir(nome) {
    if (!this.permitida(nome)) return;
    document.querySelectorAll(".abas button").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.aba === nome));
    document.querySelectorAll("main .aba").forEach((s) =>
      s.classList.toggle("oculto", s.id !== `aba-${nome}`));
    if (!this._montadas.has(nome) && this._registro[nome]) {
      this._montadas.add(nome);
      this._registro[nome](document.getElementById(`aba-${nome}`));
    }
    if (nome !== "admin") {
      // Registra no historico "o que acessou". Falhar aqui nao pode atrapalhar
      // quem esta trabalhando: a aba ja abriu.
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
      if (this.permitida(nome)) { primeira = primeira || nome; }
      else { botao.classList.add("oculto"); }
    });
    if (primeira) { this.abrir(primeira); return; }
    document.getElementById("sem-acesso").classList.remove("oculto");
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
    document.getElementById("usuario-logado").textContent = usuario.nome || usuario.usuario;
    document.getElementById("perfil-logado").textContent =
      usuario.admin ? "administrador" : "";
    Abas.iniciar();
  },
};

async function iniciar() {
  Tema.iniciar();
  const estado = await api("/api/estado");
  const formLogin = document.getElementById("form-login");
  const formBoot = document.getElementById("form-bootstrap");

  if (estado.logado) { Telas.mostrarApp(estado.usuario); return; }
  Telas.mostrarLogin();
  formBoot.classList.toggle("oculto", !estado.precisa_bootstrap);
  formLogin.classList.toggle("oculto", estado.precisa_bootstrap);

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
}

document.getElementById("botao-sair").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.reload();
});

iniciar().catch((erro) => toast(erro.message, "erro"));
