"""Testes de contrato, acessibilidade (WCAG AA), ativos e shell do redesign 028."""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parents[1]
WEBUI = RAIZ / "webui"

ATIVOS_OBRIGATORIOS = (
    "favicon-64.png",
    "icon-192.png",
    "symbol-256.png",
    "logo-horizontal-light.png",
    "logo-horizontal.png",
)

ABAS_ESPERADAS = (
    "inicio",
    "tarefas",
    "qualidade",
    "clientes",
    "comparador",
    "diff",
    "conferencia",
    "extracao",
    "produtos",
    "conciliacao",
    "nfse",
    "patrimonio",
    "admin",
)


def _luminancia(hex_cor: str) -> float:
    h = hex_cor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _extrair_bloco(css: str, padrao_inicio: str) -> dict[str, str]:
    m = re.search(padrao_inicio + r"\s*\{(.*?)\n\}", css, re.S)
    assert m, f"Bloco CSS não encontrado: {padrao_inicio}"
    tokens: dict[str, str] = {}
    for nome, valor in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1), re.I):
        tokens[nome] = valor.strip()
    return tokens


def _resolver_cor(tokens: dict[str, str], chave: str) -> str:
    valor = tokens[chave]
    if valor.startswith("var("):
        ref = valor[4:-1].split(",")[0].strip()
        valor = tokens[ref]
    m = re.search(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", valor)
    assert m, f"Cor hexadecimal não encontrada para {chave}: {valor!r}"
    return "#" + m.group(1)


def testar_ativos_e_ausencia_de_cdn() -> None:
    for nome in ATIVOS_OBRIGATORIOS:
        arq = WEBUI / "img" / nome
        assert arq.is_file() and arq.stat().st_size > 1000, f"Ativo ausente: {arq}"
        assert arq.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"PNG inválido: {arq}"

    arquivos = list(WEBUI.glob("*.html")) + list(WEBUI.glob("*.css")) + list(WEBUI.glob("*.js"))
    for arq in arquivos:
        texto = arq.read_text(encoding="utf-8")
        assert not re.search(r"https?://", texto, re.I), f"URL externa proibida em {arq.name}"
        assert "logo.jpg" not in texto, f"Referência legada logo.jpg ainda presente em {arq.name}"


def testar_tokens_e_contraste_wcag() -> None:
    css = (WEBUI / "estilo.css").read_text(encoding="utf-8")
    assert "#060D28" in css.upper(), "Azul-marinho oficial #060D28 ausente em estilo.css"
    assert "#C9A227" in css.upper(), "Dourado oficial #C9A227 ausente em estilo.css"

    claro = _extrair_bloco(css, r':root,\s*:root\[data-theme="claro"\]')
    escuro = _extrair_bloco(css, r':root\[data-theme="escuro"\]')
    # Bloco de marca/cromo possui --lat-fundo
    m_cromo = re.search(r":root\s*\{([^}]*--lat-fundo[^}]*)\}", css, re.S)
    assert m_cromo, "Bloco :root de cromo lateral ausente"
    cromo = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m_cromo.group(1), re.I))
    cromo = {k: v.strip() for k, v in cromo.items()}
    assert _resolver_cor(cromo, "--lat-fundo").upper() == "#060D28"

    for nome_tema, t in (("claro", claro), ("escuro", escuro)):
        pares = [
            ("--texto", "--fundo"),
            ("--texto", "--papel"),
            ("--texto-suave", "--papel"),
            ("--texto-fraco", "--papel"),
            ("--dourado-texto", "--papel"),
            ("--menta-texto", "--papel"),
            ("--acao-texto", "--acao-fundo"),
            ("--ok", "--ok-suave"),
            ("--erro", "--erro-suave"),
            ("--alerta", "--alerta-suave"),
        ]
        for fg_k, bg_k in pares:
            fg, bg = _resolver_cor(t, fg_k), _resolver_cor(t, bg_k)
            ratio = _contraste(fg, bg)
            assert ratio >= 4.5, f"[{nome_tema}] Contraste {fg_k}({fg})/{bg_k}({bg})={ratio:.2f} < 4.5"

    # Lateral (cromo escuro permanente)
    for fg_k, bg_k in (("--lat-texto", "--lat-fundo"), ("--lat-ativo-texto", "--lat-fundo")):
        fg, bg = _resolver_cor(cromo, fg_k), _resolver_cor(cromo, bg_k)
        ratio = _contraste(fg, bg)
        assert ratio >= 4.5, f"[cromo] Contraste {fg_k}({fg})/{bg_k}({bg})={ratio:.2f} < 4.5"


def testar_estrutura_html() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    for aba in ABAS_ESPERADAS:
        assert f'data-aba="{aba}"' in html, f"Botão data-aba={aba} ausente"
        assert f'id="aba-{aba}"' in html, f"Section id=aba-{aba} ausente"

    for id_obrigatorio in (
        "tela-login",
        "tela-app",
        "form-login",
        "form-bootstrap",
        "botao-tema",
        "botao-tema-login",
        "toggle-login-senha",
        "toggle-boot-senha",
        "botao-menu",
        "lateral-fundo",
        "botao-busca",
        "paleta-fundo",
        "paleta-entrada",
        "paleta-lista",
        "botao-lateral",
        "botao-sair",
    ):
        assert f'id="{id_obrigatorio}"' in html, f"Elemento #{id_obrigatorio} ausente em index.html"


def testar_comportamento_shell_node() -> None:
    node = shutil.which("node")
    if not node:
        print("PULADO - Node não instalado para testar app.js")
        return

    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");

function criarElemento(tag, id = "") {
  const classes = new Set();
  const el = {
    tagName: tag.toUpperCase(),
    id,
    children: [],
    listeners: {},
    attributes: {},
    dataset: {},
    style: {},
    value: "",
    type: "text",
    disabled: false,
    hidden: false,
    _text: "",
    set textContent(v) { this._text = String(v ?? ""); this.children = []; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(""); },
    set innerHTML(v) { this.children = []; this._html = String(v ?? ""); },
    get innerHTML() { return this._html || ""; },
    append(...itens) { for (const i of itens) { i.parent = this; this.children.push(i); } },
    appendChild(i) { this.append(i); return i; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return this.attributes[k] ?? null; },
    removeAttribute(k) { delete this.attributes[k]; },
    addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); },
    removeEventListener(t, fn) { this.listeners[t] = (this.listeners[t] || []).filter(f => f !== fn); },
    async emit(t, ev = {}) {
      for (const fn of this.listeners[t] || []) {
        await fn({ preventDefault() {}, stopPropagation() {}, target: this, ...ev });
      }
    },
    focus() { doc.activeElement = this; },
    closest(sel) {
      if (sel.startsWith("[data-grupo]")) return this._grupo || null;
      if (sel.startsWith("button[data-aba]")) return this.dataset.aba ? this : null;
      return null;
    },
    querySelector(sel) {
      if (sel.startsWith(".")) return null;
      return this.querySelectorAll(sel)[0] || null;
    },
    querySelectorAll(sel) {
      const todos = [];
      const varrer = (n) => { for (const c of n.children || []) { todos.push(c); varrer(c); } };
      varrer(this);
      if (sel === "button[data-aba]" || sel === ".abas button") return todos.filter(e => e.dataset.aba);
      return [];
    },
    classList: {
      add(...v) { v.forEach(x => classes.add(x)); },
      remove(...v) { v.forEach(x => classes.delete(x)); },
      toggle(v, force) {
        const on = force === undefined ? !classes.has(v) : !!force;
        on ? classes.add(v) : classes.delete(v);
        return on;
      },
      contains(v) { return classes.has(v); },
    },
  };
  return el;
}

const porId = new Map();
const id = (nome, tag = "div") => {
  if (!porId.has(nome)) porId.set(nome, criarElemento(tag, nome));
  return porId.get(nome);
};

const nav = id("abas-nav", "nav");
const grupos = [];
for (const [grupoId, rotulo, abas] of [
  ["gestao", "Gestão", [["inicio", "Central", ""], ["tarefas", "Tarefas e prazos", ""]]],
  ["ferramentas", "Auditoria e SPED", [["comparador", "Comparador SPED x SEFAZ", "1"]]],
  ["sistema", "Organização", [["admin", "Administração", ""]]],
]) {
  const g = criarElemento("div"); g.className = "nav-grupo"; g.dataset.grupo = grupoId; g.dataset.rotulo = rotulo;
  g.querySelectorAll = (s) => s === "button[data-aba]" ? g.children : [];
  for (const [aba, texto, num] of abas) {
    const b = criarElemento("button"); b.dataset.aba = aba; if (num) b.dataset.numero = num;
    b.textContent = texto; b._grupo = g; g.append(b);
  }
  grupos.push(g); nav.append(g);
}

const secInicio = id("aba-inicio", "section");
const secComp = id("aba-comparador", "section");
const secTar = id("aba-tarefas", "section");
const secAdmin = id("aba-admin", "section");
const todasSecoes = [secInicio, secComp, secTar, secAdmin];

const doc = {
  readyState: "complete",
  activeElement: null,
  listeners: {},
  documentElement: { dataset: {} },
  body: criarElemento("body"),
  createElement: (tag) => criarElemento(tag),
  getElementById: (nome) => id(nome),
  querySelector(sel) {
    const m = sel.match(/button\[data-aba="([^"]+)"\]/);
    if (m) return [...nav.querySelectorAll("button[data-aba]")].find(b => b.dataset.aba === m[1]) || null;
    return null;
  },
  querySelectorAll(sel) {
    if (sel === ".abas button" || sel === ".abas button[data-aba]") return nav.querySelectorAll("button[data-aba]");
    if (sel === "main .aba") return todasSecoes;
    if (sel === ".nav-grupo") return grupos;
    if (sel === ".modal-fundo") return [];
    return [];
  },
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); },
  removeEventListener(t, fn) { this.listeners[t] = (this.listeners[t] || []).filter(f => f !== fn); },
  dispatchEvent(e) { for (const fn of this.listeners[e.type] || []) fn(e); },
};

id("botao-lateral").append({ textContent: "«" });
id("login-senha", "input").type = "password";
id("boot-senha", "input").type = "password";

const storage = new Map();
const ctx = {
  document: doc,
  console,
  localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v)) },
  matchMedia: () => ({ matches: false }),
  CustomEvent: class { constructor(type, opt = {}) { this.type = type; this.detail = opt.detail; } },
  location: { reload() {} },
  fetch: async () => ({
    status: 200, ok: true, headers: { get: () => "application/json" },
    json: async () => ({ logado: true, precisa_bootstrap: false, usuario: { id: 1, nome: "Teste Sintetico", usuario: "teste", admin: false, permissoes: ["aba.comparador"] } }),
  }),
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("webui/app.js", "utf8"), ctx);

(async () => {
  await new Promise(r => setTimeout(r, 20));
  // Tema no login tambem alterna o tema
  assert.strictEqual(doc.documentElement.dataset.theme, "claro");
  await id("botao-tema-login").emit("click");
  assert.strictEqual(doc.documentElement.dataset.theme, "escuro");

  // Toggle de visibilidade de senha
  await id("toggle-login-senha").emit("click");
  assert.strictEqual(id("login-senha").type, "text");
  await id("toggle-login-senha").emit("click");
  assert.strictEqual(id("login-senha").type, "password");

  // Gaveta mobile abre e fecha
  await id("botao-menu").emit("click");
  assert.strictEqual(id("tela-app").classList.contains("menu-aberto"), true);
  await id("lateral-fundo").emit("click");
  assert.strictEqual(id("tela-app").classList.contains("menu-aberto"), false);

  // Paleta de comando lista apenas permissoes do usuario (inicio + comparador, nunca tarefas/admin)
  vm.runInContext("Paleta.abrir()", ctx);
  assert.strictEqual(id("paleta-fundo").classList.contains("oculto"), false);
  const rotulos = id("paleta-lista").children.map(c => c.textContent);
  assert(rotulos.some(r => r.includes("Comparador")), "Permissao aba.comparador deve aparecer na paleta");
  assert(!rotulos.some(r => r.includes("Tarefas")), "Aba nao permitida nao pode aparecer na paleta");
  assert(!rotulos.some(r => r.includes("Administração")), "Admin nao permitido nao pode aparecer na paleta");

  // Filtragem e acionamento na paleta
  id("paleta-entrada").value = "sped";
  await id("paleta-entrada").emit("input");
  assert.strictEqual(id("paleta-lista").children.length, 1);
  await id("paleta-lista").children[0].emit("click");
  assert.strictEqual(id("paleta-fundo").classList.contains("oculto"), true);
  assert.strictEqual(id("titulo-tela").textContent, "Comparador SPED x SEFAZ");
  assert.strictEqual(id("eyebrow-tela").textContent, "Ferramenta 1");

  console.log("OK - Redesign 028 shell, paleta, gaveta, senha e tema");
})().catch(e => { console.error(e); process.exitCode = 1; });
'''
    res = subprocess.run([node, "-e", script], cwd=RAIZ, text=True,
                         capture_output=True, encoding="utf-8")
    print(res.stdout, end="")
    if res.returncode:
        print(res.stderr)
    assert res.returncode == 0, "Falha no teste Node do shell"


def main() -> int:
    testar_ativos_e_ausencia_de_cdn()
    testar_tokens_e_contraste_wcag()
    testar_estrutura_html()
    testar_comportamento_shell_node()
    print("OK - redesign 028: ativos locais, WCAG AA, estrutura HTML e shell validados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
