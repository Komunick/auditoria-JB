/* Painel de Inicio: a porta de entrada do sistema.

   Ate aqui o site abria direto na primeira ferramenta liberada, o que dava
   uma primeira tela diferente para cada pessoa e nenhuma visao do conjunto.
   Este painel mostra o que a pessoa alcanca, com o nome e uma linha do que
   cada ferramenta faz, e leva para ela num clique.

   Nao existe rota nem permissao propria: e' so uma vitrine do que ja esta
   liberado. A regra de acesso continua uma so, em Abas.permitida(), e quem
   barra de verdade e' o 403 do servidor. */

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
    <section class="capa">
      <div class="capa-texto">
        <p class="eyebrow capa-data"></p>
        <h2 class="capa-titulo"></h2>
        <p class="capa-linha"></p>
      </div>
      <img class="capa-selo" src="logo.jpg" alt="" width="72" height="72">
    </section>

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

  container.querySelector(".capa-data").textContent = dataPorExtenso();
  container.querySelector(".capa-titulo").textContent =
    primeiroNome ? `${saudacao()}, ${primeiroNome}.` : `${saudacao()}.`;
  /* "menu de navegacao" e nao "menu a esquerda": em tela estreita a lateral
     vira uma barra no topo (ver o @media do estilo.css). */
  container.querySelector(".capa-linha").textContent = ferramentas.length
    ? "Escolha uma ferramenta abaixo ou use o menu de navegação."
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
}

Abas.registrar("inicio", montarInicio);
