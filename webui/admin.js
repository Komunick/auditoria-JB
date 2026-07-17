/* Aba de Administracao — usuarios, permissoes e historico de acessos.

   Duas telas dentro da mesma aba, cada uma com a sua permissao: "Usuarios"
   (admin.usuarios) e "Historico" (admin.historico). Quem so tem uma delas ve
   so uma. Dados vindos do servidor entram por textContent, nunca innerHTML:
   nome de usuario e detalhe de evento sao texto digitado por gente. */

"use strict";

Abas.registrar("admin", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <div class="sub-abas" id="adm-nav">
        <button data-sub="usuarios" class="ativa">Usuarios e permissoes</button>
        <button data-sub="historico">Historico de acessos</button>
      </div>
    </div>

    <div id="adm-usuarios">
      <div class="caixa">
        <div class="linha-form">
          <h2>Usuarios</h2>
          <button id="adm-novo" class="botao-primario">Novo usuario</button>
        </div>
        <div class="rolagem"><table id="adm-tabela">
          <thead><tr>
            <th>Usuario</th><th>Nome</th><th>Perfil</th><th>Situacao</th>
            <th>Ultimo acesso</th><th>Criado em</th><th></th>
          </tr></thead><tbody></tbody>
        </table></div>
        <p id="adm-status" class="status"></p>
      </div>
    </div>

    <div id="adm-historico" class="oculto">
      <div class="caixa">
        <h2>Historico de acessos</h2>
        <div class="linha-form">
          <label>Usuario <select id="hist-usuario"></select></label>
          <label>Categoria <select id="hist-categoria"></select></label>
          <label>Acao <select id="hist-acao"></select></label>
          <label>De <input id="hist-de" type="date"></label>
          <label>Ate <input id="hist-ate" type="date"></label>
          <label>Busca <input id="hist-texto" placeholder="texto do evento"></label>
          <button id="hist-filtrar" class="botao-primario">Filtrar</button>
          <button id="hist-limpar">Limpar</button>
          <button id="hist-csv">Exportar CSV</button>
        </div>
        <p id="hist-status" class="status"></p>
        <div class="rolagem"><table id="hist-tabela">
          <thead><tr>
            <th>Data e hora</th><th>Usuario</th><th>Categoria</th>
            <th>O que fez</th><th>Detalhe</th><th>Resultado</th><th>IP</th>
          </tr></thead><tbody></tbody>
        </table></div>
        <div class="linha-form">
          <button id="hist-anterior">&lt; Anteriores</button>
          <span id="hist-pagina" class="status"></span>
          <button id="hist-proxima">Proximos &gt;</button>
        </div>
      </div>
    </div>`;

  const $ = (id) => document.getElementById(id);
  const estado = { catalogo: [], padrao: [], usuarios: [], pagina: 1,
                   total: 0, limite: 200 };

  // --------------------------------------------------------------------
  // Sub-abas (cada uma com a sua permissao)

  const podeUsuarios = Sessao.pode("admin.usuarios");
  const podeHistorico = Sessao.pode("admin.historico");
  if (!podeUsuarios) {
    $("adm-nav").querySelector('[data-sub="usuarios"]').classList.add("oculto");
    $("adm-usuarios").classList.add("oculto");
  }
  if (!podeHistorico) {
    $("adm-nav").querySelector('[data-sub="historico"]').classList.add("oculto");
  }

  function abrirSub(nome) {
    $("adm-nav").querySelectorAll("button").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    $("adm-usuarios").classList.toggle("oculto", nome !== "usuarios");
    $("adm-historico").classList.toggle("oculto", nome !== "historico");
    if (nome === "historico") carregarHistorico(1);
  }

  $("adm-nav").addEventListener("click", (e) => {
    const botao = e.target.closest("button[data-sub]");
    if (botao) abrirSub(botao.dataset.sub);
  });

  // --------------------------------------------------------------------
  // Usuarios

  function celula(linha, texto, classe) {
    const td = document.createElement("td");
    td.textContent = texto;
    if (classe) td.className = classe;
    linha.appendChild(td);
    return td;
  }

  function renderUsuarios() {
    const corpo = $("adm-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    for (const u of estado.usuarios) {
      const linha = document.createElement("tr");
      celula(linha, u.usuario);
      celula(linha, u.nome);
      celula(linha, u.admin ? "Administrador"
                            : `${u.permissoes.length} permissao(oes)`);
      celula(linha, u.ativo ? "Ativo" : "Desativado", u.ativo ? "" : "erro");
      celula(linha, u.resumo.ultimo_acesso || "nunca acessou");
      celula(linha, u.criado_em);
      const acoes = document.createElement("td");
      const botao = document.createElement("button");
      botao.textContent = "Editar";
      botao.onclick = () => editor(u);
      acoes.appendChild(botao);
      linha.appendChild(acoes);
      if (!u.ativo) linha.classList.add("desativado");
      corpo.appendChild(linha);
    }
    $("adm-status").textContent =
      `${estado.usuarios.length} usuario(s) cadastrado(s).`;
  }

  async function carregarUsuarios() {
    const dados = await api("/api/admin/usuarios");
    estado.catalogo = dados.catalogo;
    estado.padrao = dados.padrao_novo;
    estado.usuarios = dados.usuarios;
    renderUsuarios();
    preencherFiltroUsuarios();
  }

  /* Caixas de permissao agrupadas. `marcadas` = slugs ja concedidos. */
  function montarPermissoes(marcadas) {
    const caixa = document.createElement("div");
    caixa.className = "permissoes";
    for (const grupo of estado.catalogo) {
      const bloco = document.createElement("fieldset");
      const titulo = document.createElement("legend");
      titulo.textContent = grupo.grupo;
      bloco.appendChild(titulo);
      for (const item of grupo.itens) {
        const rotulo = document.createElement("label");
        rotulo.className = "permissao";
        rotulo.title = item.ajuda;
        const caixinha = document.createElement("input");
        caixinha.type = "checkbox";
        caixinha.value = item.slug;
        caixinha.checked = marcadas.includes(item.slug);
        rotulo.appendChild(caixinha);
        const texto = document.createElement("span");
        texto.textContent = item.rotulo;
        rotulo.appendChild(texto);
        bloco.appendChild(rotulo);
      }
      caixa.appendChild(bloco);
    }
    return caixa;
  }

  function slugsMarcados(raiz) {
    return [...raiz.querySelectorAll(".permissoes input:checked")]
      .map((c) => c.value);
  }

  /* Painel unico para criar e editar: `usuario` null = criacao. */
  function editor(usuario) {
    const novo = !usuario;
    const fundo = document.createElement("div");
    fundo.className = "modal-fundo";
    fundo.innerHTML = `
      <div class="modal largo">
        <h3></h3>
        <div class="linha-form">
          <label>Usuario (login) <input id="ed-usuario"></label>
          <label>Nome <input id="ed-nome"></label>
          <label class="oculto" id="ed-senha-campo">Senha (min. 6)
            <input id="ed-senha" type="password" autocomplete="new-password">
          </label>
        </div>
        <div class="linha-form">
          <label class="permissao"><input id="ed-admin" type="checkbox">
            <span>Administrador (tem todas as permissoes e administra os
                  demais usuarios)</span></label>
          <label class="permissao" id="ed-ativo-campo">
            <input id="ed-ativo" type="checkbox">
            <span>Ativo (desmarcar impede o login e encerra as sessoes)</span>
          </label>
        </div>
        <div id="ed-permissoes"></div>
        <p id="ed-erro" class="erro"></p>
        <div class="acoes">
          <button id="ed-senha-trocar" class="oculto">Trocar senha</button>
          <button class="cancelar">Cancelar</button>
          <button id="ed-salvar" class="botao-primario">Salvar</button>
        </div>
      </div>`;
    document.body.appendChild(fundo);

    const q = (id) => fundo.querySelector(`#${id}`);
    fundo.querySelector("h3").textContent =
      novo ? "Novo usuario" : `Editar ${usuario.usuario}`;
    q("ed-usuario").value = novo ? "" : usuario.usuario;
    q("ed-usuario").disabled = !novo;          // login e a identidade: nao muda
    q("ed-nome").value = novo ? "" : usuario.nome;
    q("ed-admin").checked = novo ? false : usuario.admin;
    q("ed-ativo").checked = novo ? true : usuario.ativo;
    q("ed-senha-campo").classList.toggle("oculto", !novo);
    q("ed-ativo-campo").classList.toggle("oculto", novo);
    q("ed-senha-trocar").classList.toggle("oculto", novo);

    const marcadas = novo ? estado.padrao
                          : (usuario.admin ? [] : usuario.permissoes);
    const painel = q("ed-permissoes");
    painel.appendChild(montarPermissoes(marcadas));

    /* Administrador tem tudo por definicao: as caixas somem para nao dar a
       impressao de que recortam alguma coisa. */
    const refletirAdmin = () => {
      painel.classList.toggle("oculto", q("ed-admin").checked);
    };
    q("ed-admin").addEventListener("change", refletirAdmin);
    refletirAdmin();

    const fechar = () => fundo.remove();
    fundo.querySelector(".cancelar").onclick = fechar;

    q("ed-senha-trocar").onclick = async () => {
      const senha = await pedirSenha(usuario.usuario);
      if (!senha) return;
      try {
        await api(`/api/admin/usuarios/${usuario.id}/senha`,
                  { method: "PUT", json: { senha } });
        toast(`Senha de ${usuario.usuario} trocada. As sessoes abertas dele ` +
              `foram encerradas.`);
      } catch (erro) { q("ed-erro").textContent = erro.message; }
    };

    q("ed-salvar").onclick = async () => {
      q("ed-erro").textContent = "";
      const admin = q("ed-admin").checked;
      const permissoes = slugsMarcados(painel);
      try {
        if (novo) {
          await api("/api/admin/usuarios", { json: {
            usuario: q("ed-usuario").value, nome: q("ed-nome").value,
            senha: q("ed-senha").value, admin, permissoes } });
          toast(`Usuario ${q("ed-usuario").value.trim().toLowerCase()} criado.`);
        } else {
          await api(`/api/admin/usuarios/${usuario.id}`, {
            method: "PUT",
            json: { nome: q("ed-nome").value, admin,
                    ativo: q("ed-ativo").checked } });
          if (!admin) {
            await api(`/api/admin/usuarios/${usuario.id}/permissoes`,
                      { method: "PUT", json: { permissoes } });
          }
          toast(`Usuario ${usuario.usuario} atualizado.`);
        }
        fechar();
        await carregarUsuarios();
      } catch (erro) { q("ed-erro").textContent = erro.message; }
    };
  }

  /* Senha nova: o admin digita, o servidor guarda o hash. */
  function pedirSenha(usuario) {
    return new Promise((resolver) => {
      const fundo = document.createElement("div");
      fundo.className = "modal-fundo";
      fundo.innerHTML = `
        <div class="modal">
          <h3></h3>
          <label>Nova senha (min. 6)
            <input id="ps-senha" type="password" autocomplete="new-password">
          </label>
          <div class="acoes">
            <button class="cancelar">Cancelar</button>
            <button class="confirmar botao-primario">Trocar senha</button>
          </div>
        </div>`;
      fundo.querySelector("h3").textContent = `Trocar a senha de ${usuario}`;
      document.body.appendChild(fundo);
      fundo.querySelector(".cancelar").onclick =
        () => { fundo.remove(); resolver(""); };
      fundo.querySelector(".confirmar").onclick = () => {
        const senha = fundo.querySelector("#ps-senha").value;
        fundo.remove();
        resolver(senha);
      };
    });
  }

  $("adm-novo").onclick = () => editor(null);

  // --------------------------------------------------------------------
  // Historico

  function opcoes(select, itens, vazio) {
    select.innerHTML = "";
    const nenhum = document.createElement("option");
    nenhum.value = "";
    nenhum.textContent = vazio;
    select.appendChild(nenhum);
    for (const item of itens) {
      const opcao = document.createElement("option");
      opcao.value = item.valor;
      opcao.textContent = item.rotulo;
      select.appendChild(opcao);
    }
  }

  function preencherFiltroUsuarios() {
    if (!podeHistorico) return;
    const atual = $("hist-usuario").value;
    opcoes($("hist-usuario"), estado.usuarios.map(
      (u) => ({ valor: u.usuario, rotulo: `${u.usuario} (${u.nome})` })),
      "Todos os usuarios");
    $("hist-usuario").value = atual;
  }

  function filtros() {
    return {
      usuario_filtro: $("hist-usuario").value,
      categoria: $("hist-categoria").value,
      acao: $("hist-acao").value,
      de: $("hist-de").value, ate: $("hist-ate").value,
      texto: $("hist-texto").value.trim(),
    };
  }

  function consulta(extra) {
    const parametros = new URLSearchParams({ ...filtros(), ...extra });
    return parametros.toString();
  }

  async function carregarHistorico(pagina) {
    estado.pagina = pagina;
    $("hist-status").textContent = "Consultando...";
    let dados;
    try {
      dados = await api(
        `/api/admin/historico?${consulta({ pagina, limite: estado.limite })}`);
    } catch (erro) {
      $("hist-status").textContent = "";
      toast(erro.message, "erro");
      return;
    }
    estado.total = dados.total;

    if (!$("hist-categoria").options.length) {
      opcoes($("hist-categoria"), dados.categorias, "Todas as categorias");
      opcoes($("hist-acao"), dados.acoes, "Todas as acoes");
    }
    // O proprio historico traz os usuarios distintos; quem so tem
    // admin.historico (nao alcanca a lista de usuarios) filtra por pessoa
    // mesmo assim. So preenche se ainda nao veio da lista de usuarios.
    if (!$("hist-usuario").options.length && dados.usuarios) {
      const atual = $("hist-usuario").value;
      opcoes($("hist-usuario"), dados.usuarios, "Todos os usuarios");
      $("hist-usuario").value = atual;
    }

    const corpo = $("hist-tabela").querySelector("tbody");
    corpo.innerHTML = "";
    for (const item of dados.itens) {
      const linha = document.createElement("tr");
      celula(linha, item.data_hora);
      celula(linha, item.nome ? `${item.usuario} (${item.nome})`
                              : (item.usuario || "-"));
      celula(linha, item.categoria_rotulo);
      celula(linha, item.descricao);
      celula(linha, item.detalhe);
      celula(linha, item.resultado,
             item.resultado === "negado" ? "erro"
               : (item.resultado === "erro" ? "aviso" : ""));
      celula(linha, item.ip);
      corpo.appendChild(linha);
    }

    const primeiro = dados.total ? (pagina - 1) * estado.limite + 1 : 0;
    const ultimo = (pagina - 1) * estado.limite + dados.itens.length;
    $("hist-status").textContent = dados.total
      ? `${dados.total} evento(s) — mostrando ${primeiro} a ${ultimo}.`
      : "Nenhum evento para este filtro.";
    $("hist-pagina").textContent = `Pagina ${pagina}`;
    $("hist-anterior").disabled = pagina <= 1;
    $("hist-proxima").disabled = ultimo >= dados.total;
  }

  $("hist-filtrar").onclick = () => carregarHistorico(1).catch(
    (erro) => toast(erro.message, "erro"));
  $("hist-limpar").onclick = () => {
    ["hist-usuario", "hist-categoria", "hist-acao", "hist-de", "hist-ate",
     "hist-texto"].forEach((id) => { $(id).value = ""; });
    carregarHistorico(1).catch((erro) => toast(erro.message, "erro"));
  };
  $("hist-anterior").onclick = () => carregarHistorico(estado.pagina - 1);
  $("hist-proxima").onclick = () => carregarHistorico(estado.pagina + 1);
  $("hist-csv").onclick = async () => {
    try {
      const nome = await apiDownload(
        `/api/admin/historico/exportar?${consulta({})}`);
      toast(`Historico exportado: ${nome}`);
    } catch (erro) { toast(erro.message, "erro"); }
  };

  // --------------------------------------------------------------------

  if (podeUsuarios) {
    carregarUsuarios().catch((erro) => toast(erro.message, "erro"));
  } else {
    abrirSub("historico");
  }
});
