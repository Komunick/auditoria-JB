/* Aba 8 — Emissão de NFS-e (Fase 1: lote revisado e DPS sem envio).

   Mesma disciplina das outras abas: o que esta tela esconde é conveniência,
   nunca autorização — quem manda é o 403 do servidor. Tudo que vem do
   servidor entra por `textContent`: nomes de alunos, de responsáveis e o
   texto colado da conversa são digitados por gente de fora da JB.

   Nada aqui transmite. A DPS gerada na aprovação é uma prévia validada no
   XSD oficial, marcada como NÃO TRANSMITIDA em toda saída. */

"use strict";

Abas.registrar("nfse", (container) => {
  container.innerHTML = `
    <div class="caixa">
      <h2>Emissão de NFS-e</h2>
      <p class="dica">Recebe a lista da escola (planilha-modelo ou texto colado
         da conversa), monta cada nota pelo <b>perfil de emissão</b> do cliente,
         confere tudo e, na aprovação, gera a <b>DPS</b> do padrão nacional.
         <b>Nesta fase nada é transmitido</b>: a DPS é uma prévia validada,
         sem efeito fiscal.</p>
      <p id="nfse-status" class="status"></p>
    </div>

    <div class="caixa">
      <nav class="conc-subtelas" id="nfse-subtelas">
        <button data-sub="lotes" class="ativa" type="button">Lotes</button>
        <button data-sub="importar" type="button">Importar</button>
        <button data-sub="perfis" type="button">Perfis de emissão</button>
      </nav>

      <section id="nfse-sub-lotes" class="conc-sub">
        <div class="linha-form">
          <label>Perfil
            <select id="nfse-f-perfil"><option value="">Todos</option></select>
          </label>
          <label>Estado
            <select id="nfse-f-estado">
              <option value="">Todos</option>
              <option value="em_revisao">Em revisão</option>
              <option value="aprovado">Aprovado</option>
              <option value="descartado">Descartado</option>
            </select>
          </label>
          <button id="nfse-atualizar" type="button">Atualizar</button>
        </div>
        <div class="rolagem"><table id="nfse-lotes">
          <thead><tr>
            <th>Lote</th><th>Prestador</th><th>Origem</th><th>Estado</th>
            <th class="conc-num">Notas</th><th class="conc-num">Bloqueios</th>
            <th class="conc-num">Avisos</th><th class="conc-num">Soma</th>
            <th>Importado por</th>
          </tr></thead>
          <tbody></tbody>
        </table></div>
        <div id="nfse-lote" class="oculto"></div>
      </section>

      <section id="nfse-sub-importar" class="conc-sub oculto">
        <div id="nfse-sem-importar" class="dica oculto">Você não tem permissão
           para importar lotes. Fale com o administrador.</div>
        <div id="nfse-importar-area">
          <div class="linha-form">
            <label>Perfil do prestador
              <select id="nfse-i-perfil"></select>
            </label>
            <button id="nfse-modelo" type="button">Baixar planilha-modelo</button>
          </div>
          <p id="nfse-i-pendencias" class="dica"></p>
          <h3 class="pat-titulo">Planilha-modelo preenchida</h3>
          <div class="linha-form">
            <label>Arquivo .xlsx
              <input id="nfse-i-arquivo" type="file" accept=".xlsx">
            </label>
            <button id="nfse-i-planilha" class="botao-primario" type="button">
              Importar planilha</button>
          </div>
          <h3 class="pat-titulo">Texto colado da conversa</h3>
          <p class="dica">Cole os blocos como vieram (Competência, Responsável,
             CPF, Aluno, Turma, Valor). Linha que o sistema não entende vira
             aviso — nada some calado.</p>
          <textarea id="nfse-i-texto" class="nfse-texto" rows="12"
                    placeholder="Competência: 11/2026&#10;Responsável: ...&#10;CPF: ...&#10;ALUNO: ... - BERÇÁRIO&#10;Valor: R$ ..."></textarea>
          <div class="linha-form">
            <button id="nfse-i-colar" class="botao-primario" type="button">
              Importar texto</button>
          </div>
        </div>
      </section>

      <section id="nfse-sub-perfis" class="conc-sub oculto">
        <div class="linha-form">
          <button id="nfse-novo-perfil" type="button" class="botao-primario oculto">
            Novo perfil</button>
        </div>
        <div class="rolagem"><table id="nfse-perfis">
          <thead><tr><th>Prestador</th><th>CNPJ</th><th class="conc-num">Versão</th>
            <th>Pendências</th></tr></thead>
          <tbody></tbody>
        </table></div>
        <div id="nfse-perfil" class="oculto"></div>
      </section>
    </div>`;

  const $ = (id) => document.getElementById(id);
  const status = (t) => { $("nfse-status").textContent = t || ""; };
  const pode = {
    perfis: Sessao.pode("nfse.perfis"),
    importar: Sessao.pode("nfse.importar"),
    aprovar: Sessao.pode("nfse.aprovar_emitir"),
    exportar: Sessao.pode("nfse.exportar"),
  };
  const estado = { perfis: [], catalogo: null, loteAberto: null };

  const ESTADOS = { em_revisao: "Em revisão", aprovado: "Aprovado (DPS não transmitida)",
                    descartado: "Descartado" };
  const SITUACAO = { ok: ["OK", "conc-ok"], aviso: ["Aviso", "conc-alerta"],
                     bloqueio: ["Bloqueio", "conc-erro"], excluida: ["Excluída", ""] };
  const ROTULOS_CAMPO = {
    competencia: "Competência", responsavel_nome: "Responsável",
    responsavel_cpf: "CPF", responsavel_celular: "Celular",
    responsavel_email: "E-mail", endereco_texto: "Endereço (texto)", cep: "CEP",
    logradouro: "Logradouro", numero: "Número", complemento: "Complemento",
    bairro: "Bairro", municipio: "Município", uf: "UF",
    municipio_ibge: "Código IBGE", aluno_nome: "Aluno", turma: "Turma",
    valor: "Valor", excluida: "Excluir/reincluir linha",
  };

  // ------------------------------------------------------------------
  // Helpers

  function el(tag, texto, classe) {
    const e = document.createElement(tag);
    if (texto !== undefined && texto !== null) e.textContent = texto;
    if (classe) e.className = classe;
    return e;
  }

  function celula(texto, classe) { return el("td", texto ?? "", classe); }

  function reais(centavos) {
    if (centavos === null || centavos === undefined) return "—";
    return (centavos / 100).toLocaleString("pt-BR",
      { style: "currency", currency: "BRL" });
  }

  function competencia(c) { return c ? `${c.slice(5)}/${c.slice(0, 4)}` : "—"; }

  function cnpj(d) {
    return d && d.length === 14
      ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
      : d || "";
  }

  function cpf(d) {
    return d && d.length === 11
      ? `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}` : d || "";
  }

  function cartao(valor, rotulo, cor) {
    const c = el("div", null, cor ? `cartao ${cor}` : "cartao");
    c.append(el("div", String(valor), "valor"), el("div", rotulo, "rotulo"));
    return c;
  }

  function opcoes(select, itens, vazio) {
    select.textContent = "";
    if (vazio !== undefined) {
      const o = el("option", vazio); o.value = ""; select.appendChild(o);
    }
    for (const [valor, rotulo] of itens) {
      const o = el("option", rotulo); o.value = valor; select.appendChild(o);
    }
  }

  function erroNaTela(erro) {
    status(erro.message);
    toast(erro.message, "erro");
  }

  // ------------------------------------------------------------------
  // Subtelas

  function mostrarSub(nome) {
    $("nfse-subtelas").querySelectorAll("button[data-sub]").forEach((b) =>
      b.classList.toggle("ativa", b.dataset.sub === nome));
    ["lotes", "importar", "perfis"].forEach((s) =>
      $(`nfse-sub-${s}`).classList.toggle("oculto", s !== nome));
  }

  async function abrirSub(nome) {
    mostrarSub(nome);
    if (nome === "lotes") await carregarLotes();
    if (nome === "importar") await prepararImportar();
    if (nome === "perfis") await carregarPerfis();
  }

  $("nfse-subtelas").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-sub]");
    if (b) abrirSub(b.dataset.sub);
  });

  async function carregarListaPerfis() {
    const r = await api("/api/nfse/perfis");
    estado.perfis = r.itens;
    const itens = r.itens.map((p) => [String(p.perfil_id),
      `${p.razao_social} — ${cnpj(p.cnpj)}`]);
    const filtro = $("nfse-f-perfil").value;
    opcoes($("nfse-f-perfil"), itens, "Todos");
    $("nfse-f-perfil").value = filtro;
    opcoes($("nfse-i-perfil"), itens);
  }

  // ------------------------------------------------------------------
  // Lotes

  async function carregarLotes() {
    try {
      await carregarListaPerfis();
      const filtros = {};
      if ($("nfse-f-perfil").value) filtros.perfil_id = $("nfse-f-perfil").value;
      if ($("nfse-f-estado").value) filtros.estado = $("nfse-f-estado").value;
      const r = await api("/api/nfse/lotes?" + new URLSearchParams(filtros));
      const corpo = $("nfse-lotes").querySelector("tbody");
      corpo.textContent = "";
      for (const l of r.itens) {
        const tr = el("tr", null, "conc-clicavel");
        const origem = l.tipo === "planilha" ? `Planilha ${l.nome_arquivo || ""}` : "Texto colado";
        tr.append(celula(`#${l.id}`), celula(cnpj(l.cnpj)), celula(origem),
          celula(ESTADOS[l.estado] || l.estado,
                 l.estado === "aprovado" ? "conc-ok" : l.estado === "descartado" ? "" : ""),
          celula(String(l.totais.ativas), "conc-num"),
          celula(String(l.totais.bloqueio), l.totais.bloqueio ? "conc-num conc-erro" : "conc-num"),
          celula(String(l.totais.aviso), l.totais.aviso ? "conc-num conc-alerta" : "conc-num"),
          celula(reais(l.totais.soma_centavos), "conc-num"),
          celula(`${l.criado_por_login} — ${l.criado_em.slice(0, 16).replace("T", " ")}`));
        tr.addEventListener("click", () => abrirLote(l.id));
        corpo.appendChild(tr);
      }
      if (!r.itens.length) {
        const tr = el("tr");
        const td = celula("Nenhum lote ainda. Importe uma lista na subtela Importar.");
        td.colSpan = 9; tr.appendChild(td); corpo.appendChild(tr);
      }
      status("");
    } catch (erro) { erroNaTela(erro); }
  }

  $("nfse-atualizar").addEventListener("click", carregarLotes);
  $("nfse-f-perfil").addEventListener("change", carregarLotes);
  $("nfse-f-estado").addEventListener("change", carregarLotes);

  async function abrirLote(id) {
    try {
      const lote = await api(`/api/nfse/lotes/${id}`);
      estado.loteAberto = lote;
      desenharLote(lote);
    } catch (erro) { erroNaTela(erro); }
  }

  function desenharLote(d) {
    const alvo = $("nfse-lote");
    alvo.textContent = "";
    alvo.classList.remove("oculto");
    const l = d.lote;

    alvo.appendChild(el("hr", null, "conc-divisor"));
    alvo.appendChild(el("h3", `Lote #${l.id} — ${ESTADOS[l.estado] || l.estado}`, "pat-titulo"));
    if (l.estado === "aprovado") {
      alvo.appendChild(el("p", "DPS NÃO TRANSMITIDA — prévia validada no XSD oficial, "
        + "produção restrita, sem efeito fiscal.", "nfse-faixa"));
    }
    const origem = l.origem.tipo === "planilha"
      ? `Planilha ${l.origem.nome_arquivo || ""}` : "Texto colado";
    alvo.appendChild(el("p",
      `${d.perfil.razao_social} (${cnpj(d.perfil.cnpj)}) · ${origem} · SHA-256 `
      + `${l.origem.sha256.slice(0, 12)}… · importado por ${l.criado_por_login}`
      + (l.aprovado_por_login ? ` · aprovado por ${l.aprovado_por_login}` : "")
      + (l.descartado_por_login ? ` · descartado por ${l.descartado_por_login}: `
         + `${l.motivo_descarte}` : "")
      + (l.linhas_ignoradas ? ` · ${l.linhas_ignoradas} linha(s) vazia(s) ignorada(s)` : ""),
      "dica"));

    const t = d.conferencia.totais;
    const cartoes = el("div", null, "cartoes");
    cartoes.append(cartao(t.ativas, "Notas"), cartao(t.ok, "OK", t.ok ? "verde" : ""),
      cartao(t.aviso, "Avisos", t.aviso ? "ambar" : ""),
      cartao(t.bloqueio, "Bloqueios", t.bloqueio ? "vermelho" : ""),
      cartao(t.excluidas, "Excluídas"), cartao(reais(t.soma_centavos), "Soma"));
    alvo.appendChild(cartoes);

    for (const a of d.apontamentos_lote) {
      alvo.appendChild(el("p", a.mensagem, a.nivel === "bloqueio" ? "nfse-faixa erro" : "nfse-faixa aviso"));
    }
    alvo.appendChild(el("p",
      `Conferência #${d.conferencia.id} em ${d.conferencia.executada_em.slice(0, 16).replace("T", " ")}`
      + ` (${d.conferencia.motivo}), perfil versão ${d.perfil.versao_atual}`
      + (d.perfil.desatualizado ? " — o perfil mudou depois; use Reconferir." : "."),
      "dica"));

    alvo.appendChild(acoesDoLote(d));

    const linhas = d.linhas.map((x) => {
      const [rotulo, classe] = SITUACAO[x.situacao] || [x.situacao, ""];
      const origemLinha = x.origem.aba ? `${x.origem.aba}, linha ${x.origem.linha_planilha}`
        : `bloco ${x.origem.bloco} (linhas ${x.origem.texto_linha_ini}–${x.origem.texto_linha_fim})`;
      const tr = el("tr", null, "conc-clicavel");
      tr.append(celula(String(x.ordem)), celula(origemLinha),
        celula(x.responsavel || x.efetivos.responsavel_nome || "—"),
        celula(x.cpf ? cpf(x.cpf) : (x.efetivos.responsavel_cpf || "—")),
        celula(x.aluno || x.efetivos.aluno_nome || "—"),
        celula(x.turma || x.efetivos.turma || "—"),
        celula(competencia(x.competencia)),
        celula(reais(x.valor_centavos), "conc-num"),
        celula(rotulo, classe),
        celula(x.apontamentos.map((a) => a.mensagem).join(" · ")));
      tr.addEventListener("click", () => detalheLinha(d, x));
      return tr;
    });
    const wrap = el("div", null, "rolagem");
    const tabela = el("table");
    const thead = el("thead");
    const cab = el("tr");
    for (const c of ["#", "Origem", "Responsável", "CPF", "Aluno", "Turma",
                     "Competência", "Valor", "Situação", "Apontamentos"]) {
      cab.appendChild(el("th", c, c === "Valor" ? "conc-num" : ""));
    }
    thead.appendChild(cab);
    const tbody = el("tbody");
    linhas.forEach((tr) => tbody.appendChild(tr));
    tabela.append(thead, tbody);
    wrap.appendChild(tabela);
    alvo.appendChild(wrap);
    alvo.appendChild(el("div", null, "nfse-linha-detalhe")).id = "nfse-linha";

    if (d.dps.length) alvo.appendChild(listaDps(d));
    alvo.appendChild(botaoEventos(l.id));
  }

  function acoesDoLote(d) {
    const l = d.lote;
    const caixa = el("div", null, "linha-form");
    if (l.estado === "em_revisao" && pode.importar) {
      const b = el("button", "Reconferir"); b.type = "button";
      b.addEventListener("click", () => reconferir(l));
      caixa.appendChild(b);
    }
    if (l.estado === "em_revisao" && pode.aprovar) {
      const b = el("button", "Aprovar e gerar DPS", "botao-primario"); b.type = "button";
      b.disabled = d.conferencia.totais.bloqueio > 0 || d.apontamentos_lote.some(
        (a) => a.nivel === "bloqueio");
      b.title = b.disabled ? "Há bloqueio no lote ou pendência no perfil." : "";
      b.addEventListener("click", () => aprovar(d));
      caixa.appendChild(b);
    }
    const podeDescartar = (l.estado === "em_revisao" && pode.importar)
      || (l.estado === "aprovado" && pode.aprovar);
    if (podeDescartar) {
      const motivo = el("input"); motivo.type = "text";
      motivo.placeholder = "Motivo do descarte";
      const b = el("button", "Descartar lote"); b.type = "button";
      b.addEventListener("click", () => descartar(l, motivo.value));
      const rotulo = el("label", "Descartar"); rotulo.appendChild(motivo);
      caixa.append(rotulo, b);
    }
    if (pode.exportar) {
      const b = el("button", "Planilha-resumo (.xlsx)"); b.type = "button";
      b.addEventListener("click", () => baixar(`/api/nfse/lotes/${l.id}/resumo`));
      caixa.appendChild(b);
      if (d.dps.length) {
        const z = el("button", "Zip das DPS"); z.type = "button";
        z.addEventListener("click", () => baixar(`/api/nfse/lotes/${l.id}/dps-zip`));
        caixa.appendChild(z);
      }
    }
    return caixa;
  }

  async function baixar(caminho) {
    try {
      const nome = await apiDownload(caminho, { method: "POST" });
      toast(`Baixado: ${nome}`, "ok");
    } catch (erro) { erroNaTela(erro); }
  }

  async function reagir(promessa, sucesso) {
    try {
      await promessa;
      if (sucesso) toast(sucesso, "ok");
    } catch (erro) {
      if (erro.codigo === "REVISION_DESATUALIZADA") {
        toast("O lote mudou enquanto você revisava. Recarreguei a versão atual.", "erro");
      } else {
        erroNaTela(erro);
      }
    }
    if (estado.loteAberto) await abrirLote(estado.loteAberto.lote.id);
    await carregarLotes();
  }

  function reconferir(l) {
    return reagir(api(`/api/nfse/lotes/${l.id}/reconferir`,
      { json: { revision: l.revision } }), "Lote reconferido.");
  }

  async function aprovar(d) {
    const l = d.lote;
    const avisos = d.conferencia.totais.aviso;
    const pergunta = avisos
      ? `${avisos} linha(s) com aviso. Você conferiu os avisos e quer aprovar `
        + `${d.conferencia.totais.ativas} nota(s)? As DPS serão geradas e NÃO transmitidas.`
      : `Aprovar ${d.conferencia.totais.ativas} nota(s)? As DPS serão geradas e `
        + "NÃO transmitidas.";
    if (!(await confirmar("Aprovar o lote", pergunta))) return;
    await reagir(api(`/api/nfse/lotes/${l.id}/aprovar`,
      { json: { revision: l.revision, confirmar_avisos: avisos > 0 } }),
      "Lote aprovado. DPS geradas (não transmitidas).");
  }

  async function descartar(l, motivo) {
    if (!motivo.trim()) { toast("Informe o motivo do descarte.", "erro"); return; }
    if (!(await confirmar("Descartar o lote",
      "O descarte é definitivo. O lote continua consultável."))) return;
    await reagir(api(`/api/nfse/lotes/${l.id}/descartar`,
      { json: { revision: l.revision, motivo } }), "Lote descartado.");
  }

  function detalheLinha(d, x) {
    const alvo = $("nfse-linha");
    alvo.textContent = "";
    alvo.appendChild(el("h3", `Linha ${x.ordem}`, "pat-titulo"));
    if (x.discriminacao) {
      alvo.appendChild(el("p", "Discriminação que vai para a DPS:", "dica"));
      alvo.appendChild(el("p", x.discriminacao, "nfse-discriminacao"));
    }
    if (x.codigos) {
      alvo.appendChild(el("p", `Código de tributação nacional ${x.codigos.cTribNac || "—"}`
        + ` · NBS ${x.codigos.cNBS || "—"}`, "dica"));
    }
    if (x.endereco) {
      const e = x.endereco;
      alvo.appendChild(el("p", `Endereço na nota: ${e.xLgr}, ${e.nro}`
        + `${e.xCpl ? ", " + e.xCpl : ""}, ${e.xBairro}, CEP ${e.CEP}, IBGE ${e.cMun}`, "dica"));
    }
    for (const a of x.apontamentos) {
      alvo.appendChild(el("p", `${a.codigo}: ${a.mensagem}`,
        a.nivel === "bloqueio" ? "conc-erro" : "conc-alerta"));
    }

    const campos = Object.keys(ROTULOS_CAMPO).filter((c) => c !== "excluida");
    const tabela = el("table");
    const cab = el("tr");
    ["Campo", "Recebido", "Valor em uso"].forEach((c) => cab.appendChild(el("th", c)));
    const thead = el("thead"); thead.appendChild(cab);
    const tbody = el("tbody");
    for (const c of campos) {
      const bruto = x.brutos[c]; const efetivo = x.efetivos[c];
      if (bruto === null && efetivo === null) continue;
      const tr = el("tr");
      const corrigido = x.corrigidos.includes(c);
      tr.append(celula(ROTULOS_CAMPO[c]), celula(bruto ?? "—"),
                celula(efetivo ?? "—", corrigido ? "conc-alerta" : ""));
      tbody.appendChild(tr);
    }
    tabela.append(thead, tbody);
    const wrap = el("div", null, "rolagem"); wrap.appendChild(tabela);
    alvo.appendChild(wrap);

    if (d.lote.estado === "em_revisao" && pode.importar) {
      const form = el("div", null, "linha-form");
      const campo = el("select");
      opcoes(campo, Object.entries(ROTULOS_CAMPO));
      const valor = el("input"); valor.type = "text"; valor.placeholder = "Valor novo";
      const motivo = el("input"); motivo.type = "text"; motivo.placeholder = "Motivo (obrigatório)";
      campo.addEventListener("change", () => {
        valor.placeholder = campo.value === "excluida"
          ? "1 para excluir, 0 para reincluir" : "Valor novo";
        valor.value = campo.value === "excluida" ? (x.excluida ? "0" : "1")
          : (x.efetivos[campo.value] ?? "");
      });
      campo.dispatchEvent(new Event("change"));
      const b = el("button", "Registrar correção", "botao-primario"); b.type = "button";
      b.addEventListener("click", () => {
        if (!motivo.value.trim()) { toast("O motivo é obrigatório.", "erro"); return; }
        reagir(api(`/api/nfse/lotes/${d.lote.id}/linhas/${x.id}/correcoes`, {
          json: { campo: campo.value, valor: valor.value, motivo: motivo.value,
                  revision: d.lote.revision } }), "Correção registrada; o lote foi reconferido.");
      });
      const lc = el("label", "Campo"); lc.appendChild(campo);
      const lv = el("label", "Valor"); lv.appendChild(valor);
      const lm = el("label", "Motivo"); lm.appendChild(motivo);
      form.append(lc, lv, lm, b);
      alvo.appendChild(form);
    }

    const hist = el("button", "Ver histórico de correções"); hist.type = "button";
    hist.addEventListener("click", async () => {
      try {
        const r = await api(`/api/nfse/lotes/${d.lote.id}/linhas/${x.id}/correcoes`);
        const lista = el("ul");
        if (!r.itens.length) lista.appendChild(el("li", "Nenhuma correção nesta linha."));
        for (const c of r.itens) {
          lista.appendChild(el("li", `${c.criada_em.slice(0, 16).replace("T", " ")} · `
            + `${c.criada_por_login} · ${ROTULOS_CAMPO[c.campo] || c.campo}: `
            + `"${c.valor_anterior ?? "—"}" → "${c.valor_novo ?? "—"}" · ${c.motivo}`));
        }
        hist.replaceWith(lista);
      } catch (erro) { erroNaTela(erro); }
    });
    alvo.appendChild(hist);
    alvo.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function listaDps(d) {
    const caixa = el("div");
    caixa.appendChild(el("h3", "DPS geradas (não transmitidas)", "pat-titulo"));
    const tabela = el("table");
    const cab = el("tr");
    ["Nº", "Série", "Id da DPS", "SHA-256", ""].forEach((c) => cab.appendChild(el("th", c)));
    const thead = el("thead"); thead.appendChild(cab);
    const tbody = el("tbody");
    for (const x of d.dps) {
      const tr = el("tr");
      const acao = el("td");
      if (pode.exportar) {
        const b = el("button", "XML"); b.type = "button";
        b.addEventListener("click", () => baixar(`/api/nfse/dps/${x.id}/xml`));
        acao.appendChild(b);
      }
      tr.append(celula(String(x.numero)), celula(x.serie), celula(x.id_dps),
                celula(x.sha256.slice(0, 16) + "…"), acao);
      tbody.appendChild(tr);
    }
    tabela.append(thead, tbody);
    const wrap = el("div", null, "rolagem"); wrap.appendChild(tabela);
    caixa.appendChild(wrap);
    return caixa;
  }

  function botaoEventos(loteId) {
    const b = el("button", "Ver trilha do lote"); b.type = "button";
    b.addEventListener("click", async () => {
      try {
        const r = await api(`/api/nfse/lotes/${loteId}/eventos`);
        const lista = el("ul");
        for (const e of r.itens) {
          const extra = e.detalhe && e.detalhe.motivo ? ` · ${e.detalhe.motivo}` : "";
          lista.appendChild(el("li", `${e.criado_em.slice(0, 16).replace("T", " ")} · `
            + `${e.usuario_login} · ${e.tipo}${extra}`));
        }
        b.replaceWith(lista);
      } catch (erro) { erroNaTela(erro); }
    });
    return b;
  }

  // ------------------------------------------------------------------
  // Importar

  async function prepararImportar() {
    const area = $("nfse-importar-area");
    if (!pode.importar) {
      area.classList.add("oculto");
      $("nfse-sem-importar").classList.remove("oculto");
    }
    try {
      await carregarListaPerfis();
      atualizarPendenciasImportar();
    } catch (erro) { erroNaTela(erro); }
  }

  function atualizarPendenciasImportar() {
    const id = Number($("nfse-i-perfil").value);
    const p = estado.perfis.find((x) => x.perfil_id === id);
    $("nfse-i-pendencias").textContent = !estado.perfis.length
      ? "Cadastre um perfil de emissão antes de importar."
      : p && p.pendencias
        ? `Este perfil tem ${p.pendencias} pendência(s): dá para importar e revisar, `
          + "mas a aprovação fica bloqueada até o perfil ser completado."
        : "";
  }
  $("nfse-i-perfil").addEventListener("change", atualizarPendenciasImportar);

  $("nfse-modelo").addEventListener("click", () => baixar("/api/nfse/planilha-modelo"));

  async function depoisDeImportar(r) {
    toast(r.reaproveitado ? "Este conteúdo já tinha sido importado; abri o lote existente."
      : "Lote importado e conferido.", "ok");
    await abrirSub("lotes");
    await abrirLote(r.lote_id);
  }

  /* Sem perfil não há como montar a nota: avisa aqui, antes de mandar. */
  function perfilEscolhido() {
    if ($("nfse-i-perfil").value) return true;
    toast(estado.perfis.length ? "Escolha o perfil de emissão."
      : "Cadastre o perfil de emissão (em \"Perfis de emissão\") antes de importar.",
      "erro");
    return false;
  }

  $("nfse-i-planilha").addEventListener("click", async () => {
    const arquivo = $("nfse-i-arquivo").files[0];
    if (!perfilEscolhido()) return;
    if (!arquivo) { toast("Escolha a planilha .xlsx.", "erro"); return; }
    const corpo = new FormData();
    corpo.append("perfil_id", $("nfse-i-perfil").value);
    corpo.append("arquivo", arquivo);
    try {
      const r = await api("/api/nfse/lotes/planilha", { method: "POST", body: corpo });
      $("nfse-i-arquivo").value = "";
      await depoisDeImportar(r);
    } catch (erro) { erroNaTela(erro); }
  });

  $("nfse-i-colar").addEventListener("click", async () => {
    const texto = $("nfse-i-texto").value;
    if (!perfilEscolhido()) return;
    if (!texto.trim()) { toast("Cole o texto da conversa.", "erro"); return; }
    try {
      const r = await api("/api/nfse/lotes/texto", {
        json: { perfil_id: Number($("nfse-i-perfil").value), texto } });
      $("nfse-i-texto").value = "";
      await depoisDeImportar(r);
    } catch (erro) { erroNaTela(erro); }
  });

  // ------------------------------------------------------------------
  // Perfis

  if (pode.perfis) $("nfse-novo-perfil").classList.remove("oculto");
  $("nfse-novo-perfil").addEventListener("click", () => formularioPerfil(null));

  async function carregarPerfis() {
    try {
      await carregarListaPerfis();
      const corpo = $("nfse-perfis").querySelector("tbody");
      corpo.textContent = "";
      for (const p of estado.perfis) {
        const tr = el("tr", null, "conc-clicavel");
        tr.append(celula(p.razao_social), celula(cnpj(p.cnpj)),
          celula(String(p.versao), "conc-num"),
          celula(p.pendencias ? `${p.pendencias} pendência(s)` : "Completo",
                 p.pendencias ? "conc-alerta" : "conc-ok"));
        tr.addEventListener("click", () => abrirPerfil(p.perfil_id));
        corpo.appendChild(tr);
      }
    } catch (erro) { erroNaTela(erro); }
  }

  const SIM_NAO = (v) => (v === null || v === undefined ? "pendente" : v ? "sim" : "não");

  async function abrirPerfil(id) {
    try {
      const p = await api(`/api/nfse/perfis/${id}`);
      const alvo = $("nfse-perfil");
      alvo.textContent = "";
      alvo.classList.remove("oculto");
      const a = p.atual;
      alvo.appendChild(el("hr", null, "conc-divisor"));
      alvo.appendChild(el("h3", `${a.razao_social} — versão ${p.versao}`, "pat-titulo"));
      for (const x of p.pendencias) {
        alvo.appendChild(el("p", `Pendente (${x.origem}): ${x.descricao}`, "nfse-faixa aviso"));
      }
      const linhas = [
        ["CNPJ", cnpj(p.cnpj)], ["Inscrição municipal", a.inscricao_municipal || "—"],
        ["IM vai na DPS (registro no CNC)", SIM_NAO(a.informar_im)],
        ["Município emissor (IBGE)", a.municipio_ibge],
        ["Local da prestação (IBGE)", a.municipio_prestacao_ibge],
        ["ISS retido", a.iss_retido ? "sim" : "não"],
        ["Regime de apuração no Simples", a.reg_ap_trib_sn ?? "pendente"],
        ["Regime especial", a.reg_esp_trib ?? "pendente"],
        ["Convênio do município ativo", SIM_NAO(a.convenio_incidencia_ativo)],
        ["Alíquota cadastrada", a.aliquota_centesimos === null ? "—"
          : `${(a.aliquota_centesimos / 100).toFixed(2).replace(".", ",")}%`],
        ["Alíquota na DPS (regra oficial)", a.regra_aliquota],
        ["Tributos aproximados", a.tributos_aprox || "pendente"],
        ["Endereço do tomador", a.endereco_tomador || "pendente"],
        ["Série da DPS", a.serie_dps], ["Modelo da discriminação", a.modelo_discriminacao],
      ];
      const t = el("table"); const tb = el("tbody");
      for (const [k, v] of linhas) {
        const tr = el("tr"); tr.append(el("th", k), celula(String(v))); tb.appendChild(tr);
      }
      t.appendChild(tb);
      const w = el("div", null, "rolagem"); w.appendChild(t); alvo.appendChild(w);

      alvo.appendChild(el("h3", "Turmas", "pat-titulo"));
      const tt = el("table"); const th = el("tr");
      ["Turma", "Apelidos", "Categoria", "Cód. nacional", "NBS", "Ref. Nota Salvador", "Situação"]
        .forEach((c) => th.appendChild(el("th", c)));
      const thd = el("thead"); thd.appendChild(th);
      const tbd = el("tbody");
      for (const turma of a.turmas) {
        const tr = el("tr");
        tr.append(celula(turma.nome), celula(turma.apelidos.join(", ")),
          celula(turma.categoria || "—"), celula(turma.c_trib_nac || "—"),
          celula(turma.c_nbs || "—"),
          celula([turma.ref_cnae, turma.ref_item_lista, turma.ref_ctiss].filter(Boolean).join(" · ") || "—"),
          celula(turma.pendente ? "Pendente (JB-3)" : "Completa",
                 turma.pendente ? "conc-alerta" : "conc-ok"));
        tbd.appendChild(tr);
      }
      tt.append(thd, tbd);
      const w2 = el("div", null, "rolagem"); w2.appendChild(tt); alvo.appendChild(w2);

      alvo.appendChild(el("p", "Versões: " + p.versoes.map((v) =>
        `v${v.versao} (${v.criado_por_login}, ${v.criado_em.slice(0, 10)}`
        + `${v.motivo ? ": " + v.motivo : ""})`).join(" · "), "dica"));
      if (pode.perfis) {
        const b = el("button", "Criar nova versão", "botao-primario"); b.type = "button";
        b.addEventListener("click", () => formularioPerfil(p));
        alvo.appendChild(b);
      }
    } catch (erro) { erroNaTela(erro); }
  }

  function campoSelect(rotulo, itens, valor) {
    const s = el("select");
    opcoes(s, itens);
    s.value = valor === null || valor === undefined ? "" : String(valor);
    const l = el("label", rotulo); l.appendChild(s);
    return [l, s];
  }

  function campoTexto(rotulo, valor, dica) {
    const i = el("input"); i.type = "text"; i.value = valor ?? "";
    if (dica) i.placeholder = dica;
    const l = el("label", rotulo); l.appendChild(i);
    return [l, i];
  }

  const PENDENTE = ["", "Pendente (sem valor padrão)"];
  const percentual = (c) => (c === null || c === undefined ? ""
    : (c / 100).toFixed(2).replace(".", ","));

  function formularioPerfil(perfil) {
    const a = perfil ? perfil.atual : {};
    const alvo = $("nfse-perfil");
    alvo.textContent = "";
    alvo.classList.remove("oculto");
    alvo.appendChild(el("hr", null, "conc-divisor"));
    alvo.appendChild(el("h3", perfil ? `Nova versão de ${a.razao_social}` : "Novo perfil de emissão",
      "pat-titulo"));
    alvo.appendChild(el("p", "Campos marcados como pendentes ficam sem valor: o perfil "
      + "pode ser usado para importar e revisar, mas a DPS só é gerada quando tudo "
      + "estiver decidido. Nada aqui ganha valor padrão.", "dica"));

    const c = {};
    const grade = el("div", null, "linha-form nfse-grade");
    const add = ([l, i], nome) => { grade.appendChild(l); c[nome] = i; };
    add(campoTexto("CNPJ", perfil ? cnpj(perfil.cnpj) : ""), "cnpj");
    if (perfil) c.cnpj.disabled = true;
    add(campoTexto("Razão social", a.razao_social), "razao_social");
    add(campoTexto("Inscrição municipal", a.inscricao_municipal), "inscricao_municipal");
    add(campoSelect("IM vai na DPS (R5)", [PENDENTE, ["1", "Sim (tem registro no CNC)"],
      ["0", "Não"]], a.informar_im === undefined ? null
        : a.informar_im === null ? null : a.informar_im ? 1 : 0), "informar_im");
    add(campoTexto("Município emissor (IBGE)", a.municipio_ibge, "2927408"), "municipio_ibge");
    add(campoTexto("Local da prestação (IBGE)", a.municipio_prestacao_ibge, "2927408"),
      "municipio_prestacao_ibge");
    add(campoSelect("ISS retido pelo tomador", [["", "Escolha"], ["0", "Não"], ["1", "Sim"]],
      a.iss_retido === undefined ? null : a.iss_retido ? 1 : 0), "iss_retido");
    add(campoSelect("Regime de apuração no Simples (JB-8)", [PENDENTE,
      ["1", "1 — tributos federais e ISS pelo Simples"],
      ["2", "2 — federais pelo Simples, ISS fora"],
      ["3", "3 — federais e ISS fora do Simples"]], a.reg_ap_trib_sn), "reg_ap_trib_sn");
    add(campoSelect("Regime especial (JB-8)", [PENDENTE, ["0", "0 — Nenhum"],
      ["1", "1 — Ato cooperado"], ["2", "2 — Estimativa"], ["3", "3 — Microempresa municipal"],
      ["4", "4 — Notário ou registrador"], ["5", "5 — Profissional autônomo"],
      ["6", "6 — Sociedade de profissionais"], ["9", "9 — Outros"]], a.reg_esp_trib),
      "reg_esp_trib");
    add(campoSelect("Convênio do município ativo (R5)", [PENDENTE, ["1", "Sim"], ["0", "Não"]],
      a.convenio_incidencia_ativo === undefined || a.convenio_incidencia_ativo === null
        ? null : a.convenio_incidencia_ativo ? 1 : 0), "convenio_incidencia_ativo");
    add(campoTexto("Alíquota (%)", percentual(a.aliquota_centesimos), "5,00"), "aliquota");
    add(campoSelect("Tributos aproximados (JB-8)", [PENDENTE,
      ["pTotTribSN", "Percentual do Simples (pTotTribSN)"],
      ["pTotTrib", "Federal, estadual e municipal (pTotTrib)"]], a.tributos_aprox),
      "tributos_aprox");
    add(campoTexto("pTotTribSN (%)", percentual(a.p_tot_trib_sn)), "p_tot_trib_sn");
    add(campoTexto("Federal (%)", percentual(a.p_tot_trib_fed)), "p_tot_trib_fed");
    add(campoTexto("Estadual (%)", percentual(a.p_tot_trib_est)), "p_tot_trib_est");
    add(campoTexto("Municipal (%)", percentual(a.p_tot_trib_mun)), "p_tot_trib_mun");
    add(campoSelect("Endereço do tomador (JB-2)", [PENDENTE,
      ["informar", "Informar o que a escola mandou"], ["omitir", "Não informar"]],
      a.endereco_tomador), "endereco_tomador");
    add(campoTexto("Série da DPS (1 a 49999)", a.serie_dps), "serie_dps");
    alvo.appendChild(grade);

    const modelo = el("textarea", null, "nfse-texto"); modelo.rows = 3;
    modelo.value = a.modelo_discriminacao || "";
    modelo.placeholder = "REFERENTE AOS SERVIÇOS PRESTADOS DE {TURMA} AO MENOR: {ALUNO} NO PERÍODO DE {MES}/{ANO}.";
    const lm = el("label", "Modelo da discriminação — campos: {turma} {aluno} {responsavel} "
      + "{mes} {mes_extenso} {ano} {competencia} (em maiúsculas devolvem o valor em maiúsculas)");
    lm.appendChild(modelo);
    alvo.appendChild(lm);

    alvo.appendChild(el("h3", "Turmas", "pat-titulo"));
    const turmas = el("div");
    const linhaTurma = (t = {}) => {
      const linha = el("div", null, "linha-form");
      const campos = {};
      for (const [nome, rotulo, dica] of [
        ["nome", "Turma", "Berçário"], ["apelidos", "Apelidos (vírgula)", "Bercario I"],
        ["categoria", "Categoria", "infantil ou fundamental"],
        ["c_trib_nac", "Cód. nacional", "080101"], ["c_nbs", "NBS", "1.2201.11.00"],
        ["c_ind_op", "Ind. operação", "030101"], ["c_class_trib", "Class. trib.", "200028"],
        ["ref_cnae", "CNAE (ref.)", ""], ["ref_item_lista", "Item (ref.)", ""],
        ["ref_ctiss", "CTISS (ref.)", ""]]) {
        const valor = nome === "apelidos" ? (t.apelidos || []).join(", ") : t[nome];
        const [l, i] = campoTexto(rotulo, valor, dica);
        campos[nome] = i; linha.appendChild(l);
      }
      const tirar = el("button", "Remover"); tirar.type = "button";
      tirar.addEventListener("click", () => linha.remove());
      linha.appendChild(tirar);
      linha._campos = campos;
      turmas.appendChild(linha);
    };
    (a.turmas && a.turmas.length ? a.turmas : [{}]).forEach(linhaTurma);
    alvo.appendChild(turmas);
    const mais = el("button", "Adicionar turma"); mais.type = "button";
    mais.addEventListener("click", () => linhaTurma());
    alvo.appendChild(mais);

    const [lmot, motivo] = campoTexto("Motivo da versão", "", "Ex.: respostas da JB de 20/10");
    const salvar = el("button", perfil ? "Salvar nova versão" : "Cadastrar perfil",
      "botao-primario");
    salvar.type = "button";
    const rodape = el("div", null, "linha-form"); rodape.append(lmot, salvar);
    alvo.appendChild(rodape);

    salvar.addEventListener("click", async () => {
      const vazio = (v) => (v === "" ? null : v);
      const dados = {
        cnpj: perfil ? perfil.cnpj : c.cnpj.value,
        razao_social: c.razao_social.value,
        inscricao_municipal: vazio(c.inscricao_municipal.value),
        informar_im: vazio(c.informar_im.value),
        municipio_ibge: c.municipio_ibge.value,
        municipio_prestacao_ibge: c.municipio_prestacao_ibge.value,
        iss_retido: vazio(c.iss_retido.value),
        reg_ap_trib_sn: vazio(c.reg_ap_trib_sn.value),
        reg_esp_trib: vazio(c.reg_esp_trib.value),
        convenio_incidencia_ativo: vazio(c.convenio_incidencia_ativo.value),
        aliquota: vazio(c.aliquota.value),
        tributos_aprox: vazio(c.tributos_aprox.value),
        p_tot_trib_sn: vazio(c.p_tot_trib_sn.value),
        p_tot_trib_fed: vazio(c.p_tot_trib_fed.value),
        p_tot_trib_est: vazio(c.p_tot_trib_est.value),
        p_tot_trib_mun: vazio(c.p_tot_trib_mun.value),
        endereco_tomador: vazio(c.endereco_tomador.value),
        serie_dps: c.serie_dps.value,
        modelo_discriminacao: modelo.value,
        turmas: [...turmas.children].map((linha) => {
          const t = linha._campos;
          return {
            nome: t.nome.value,
            apelidos: t.apelidos.value.split(",").map((x) => x.trim()).filter(Boolean),
            categoria: vazio(t.categoria.value.trim()),
            c_trib_nac: vazio(t.c_trib_nac.value), c_nbs: vazio(t.c_nbs.value),
            c_ind_op: vazio(t.c_ind_op.value), c_class_trib: vazio(t.c_class_trib.value),
            ref_cnae: vazio(t.ref_cnae.value), ref_item_lista: vazio(t.ref_item_lista.value),
            ref_ctiss: vazio(t.ref_ctiss.value),
          };
        }),
      };
      try {
        const caminho = perfil ? `/api/nfse/perfis/${perfil.perfil_id}/versoes`
          : "/api/nfse/perfis";
        const r = await api(caminho, { json: { dados, motivo: motivo.value } });
        toast(perfil ? `Versão ${r.versao} salva.` : "Perfil cadastrado.", "ok");
        await carregarPerfis();
        await abrirPerfil(r.perfil_id);
      } catch (erro) {
        erroNaTela(erro);
      }
    });
  }

  abrirSub("lotes");
});
