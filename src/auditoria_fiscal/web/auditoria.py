"""Historico de acessos: quem entrou, o que abriu, o que fez e quando saiu.

Pedido do dono (2026-07-17). A trilha responde, para qualquer usuario e
periodo: quando acessou, o que acessou, o que fez ao acessar e quando saiu.
Ela e SEPARADA da trilha fiscal de `conferencia.db` (que registra a correcao
em si, para o Fisco); aqui fica a trilha de USO do sistema.

Modelo: cada rota que importa declara UMA acao do registro ACOES abaixo, via
`Depends(acesso("<slug>"))`. Essa dependency faz tres coisas de uma vez:
autentica, confere a permissao (a da acao e a da aba a que ela pertence) e
marca a requisicao para auditoria. Quem grava a linha e o middleware, DEPOIS
da resposta — assim o status real entra no historico e uma tentativa negada
(403) ou invalida (422) fica registrada igual a uma bem-sucedida, sem que
cada rota precise se lembrar de logar.

O detalhe rico ("CFOP 1102 -> 2102 em 37 nota(s)") e opcional: a rota chama
`detalhar(request, ...)` quando sabe algo que a URL nao conta. Rotas de
polling (jobs, estado) NAO estao no registro de proposito — encheriam o
historico de ruido a cada 700 ms.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import permissoes
from .auth import COOKIE_SESSAO, Usuario, agora_br, conexao, exigir_usuario

CAT_SESSAO = "sessao"
CAT_NAVEGACAO = "navegacao"
CAT_PROCESSAMENTO = "processamento"
CAT_MUTACAO = "mutacao"
CAT_DOWNLOAD = "download"
CAT_ADMIN = "admin"

ROTULO_CATEGORIA = {
    CAT_SESSAO: "Entrada e saida",
    CAT_NAVEGACAO: "Navegacao",
    CAT_PROCESSAMENTO: "Uploads e processamentos",
    CAT_MUTACAO: "Mutacoes fiscais",
    CAT_DOWNLOAD: "Downloads",
    CAT_ADMIN: "Administracao",
}

RESULTADO_OK = "ok"
RESULTADO_NEGADO = "negado"
RESULTADO_ERRO = "erro"


@dataclass(frozen=True)
class Acao:
    slug: str            # identificador da acao no historico
    descricao: str       # frase que o historico mostra ("Gerou o Livro...")
    categoria: str
    permissao: str = ""  # "" = nao exige permissao propria (so a da aba)
    aba: str = ""        # exige tambem "aba.<x>" quando preenchido


def _a(slug, descricao, categoria, permissao="", aba="") -> tuple[str, Acao]:
    return slug, Acao(slug, descricao, categoria, permissao, aba)


# Registro unico das acoes auditaveis. A chave e o slug usado nas rotas.
ACOES: dict[str, Acao] = dict((
    # ------------------------------------------------------------------
    # Sessao e navegacao
    _a("sessao.login", "Entrou no sistema", CAT_SESSAO),
    _a("sessao.login_negado", "Tentativa de login sem sucesso", CAT_SESSAO),
    _a("sessao.logout", "Saiu do sistema", CAT_SESSAO),
    _a("sessao.expirada", "Sessao expirada por tempo", CAT_SESSAO),
    _a("navegacao.aba", "Abriu uma aba", CAT_NAVEGACAO),
    _a("sessao.trabalho_nova", "Iniciou uma sessao de trabalho",
       CAT_PROCESSAMENTO),
    _a("sessao.trabalho_descartada", "Descartou a sessao de trabalho",
       CAT_PROCESSAMENTO),

    # ------------------------------------------------------------------
    # Livro de Conferencia
    _a("conferencia.upload", "Enviou arquivo para o Livro de Conferencia",
       CAT_PROCESSAMENTO, aba="conferencia"),
    _a("conferencia.carregar", "Carregou as notas do Livro de Conferencia",
       CAT_PROCESSAMENTO, aba="conferencia"),
    _a("conferencia.conferir", "Marcou a conferencia de uma nota",
       CAT_MUTACAO, "conferencia.conferir", "conferencia"),
    _a("conferencia.corrigir", "Corrigiu campo fiscal",
       CAT_MUTACAO, "conferencia.corrigir", "conferencia"),
    _a("conferencia.composicao_editar", "Editou a composicao fiscal",
       CAT_MUTACAO, "conferencia.composicao_editar", "conferencia"),
    _a("conferencia.danfe", "Abriu o DANFE de uma nota",
       CAT_DOWNLOAD, "conferencia.danfe", "conferencia"),
    _a("conferencia.livro_fiscal", "Gerou o Livro Fiscal (PDF)",
       CAT_DOWNLOAD, "conferencia.livro_fiscal", "conferencia"),
    _a("conferencia.inconsistencias",
       "Gerou o Relatorio de Inconsistencias (PDF)",
       CAT_DOWNLOAD, "conferencia.inconsistencias", "conferencia"),
    _a("conferencia.sped_corrigido", "Gerou o SPED corrigido (.txt)",
       CAT_DOWNLOAD, "conferencia.sped_corrigido", "conferencia"),

    # ------------------------------------------------------------------
    # Comparador SPED x SEFAZ
    _a("comparador.upload", "Enviou arquivo para o Comparador SEFAZ",
       CAT_PROCESSAMENTO, aba="comparador"),
    _a("comparador.comparar", "Comparou SPED com a relacao da SEFAZ",
       CAT_PROCESSAMENTO, aba="comparador"),
    _a("comparador.exportar", "Exportou o Excel do Comparador SEFAZ",
       CAT_DOWNLOAD, "comparador.exportar", "comparador"),

    # ------------------------------------------------------------------
    # Comparador SPED x SPED
    _a("diff.upload", "Enviou arquivo para o comparador de SPEDs",
       CAT_PROCESSAMENTO, aba="diff"),
    _a("diff.comparar", "Comparou duas versoes de SPED",
       CAT_PROCESSAMENTO, aba="diff"),
    _a("diff.exportar", "Exportou o Excel do comparador de SPEDs",
       CAT_DOWNLOAD, "diff.exportar", "diff"),

    # ------------------------------------------------------------------
    # Extracao de Itens
    _a("extracao.upload", "Enviou arquivo para a Extracao de Itens",
       CAT_PROCESSAMENTO, aba="extracao"),
    _a("extracao.extrair", "Extraiu os itens", CAT_PROCESSAMENTO,
       aba="extracao"),
    _a("extracao.exportar", "Exportou o Excel da Extracao de Itens",
       CAT_DOWNLOAD, "extracao.exportar", "extracao"),

    # ------------------------------------------------------------------
    # Auditoria de Produtos
    _a("produtos.upload", "Enviou o cadastro de produtos",
       CAT_PROCESSAMENTO, aba="produtos"),
    _a("produtos.auditar", "Auditou a tributacao do cadastro",
       CAT_PROCESSAMENTO, aba="produtos"),
    _a("produtos.corrigir", "Corrigiu a tributacao de produtos",
       CAT_MUTACAO, "produtos.corrigir", "produtos"),
    _a("produtos.relatorio", "Gerou o relatorio de produtos (Excel)",
       CAT_DOWNLOAD, "produtos.relatorio", "produtos"),
    _a("produtos.nova_base", "Gerou a nova base de produtos corrigida",
       CAT_DOWNLOAD, "produtos.nova_base", "produtos"),

    # ------------------------------------------------------------------
    # Administracao
    _a("admin.usuario_criado", "Criou um usuario", CAT_ADMIN,
       "admin.usuarios"),
    _a("admin.usuario_editado", "Alterou um usuario", CAT_ADMIN,
       "admin.usuarios"),
    _a("admin.permissoes", "Alterou as permissoes de um usuario", CAT_ADMIN,
       "admin.usuarios"),
    _a("admin.senha", "Trocou a senha de um usuario", CAT_ADMIN,
       "admin.usuarios"),
    _a("admin.usuarios_listados", "Consultou a lista de usuarios", CAT_ADMIN,
       "admin.usuarios"),
    _a("admin.historico", "Consultou o historico de acessos", CAT_ADMIN,
       "admin.historico"),
    _a("admin.historico_exportado", "Exportou o historico em CSV", CAT_ADMIN,
       "admin.historico"),
))


def _criar(conn: sqlite3.Connection) -> None:
    """Migracao aditiva: bancos existentes ganham a tabela sem perder nada."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS evento ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  data_iso TEXT NOT NULL,"
        "  data_hora TEXT NOT NULL,"
        "  usuario_id INTEGER NOT NULL DEFAULT 0,"
        "  usuario TEXT NOT NULL DEFAULT '',"
        "  nome TEXT NOT NULL DEFAULT '',"
        "  acao TEXT NOT NULL,"
        "  descricao TEXT NOT NULL DEFAULT '',"
        "  categoria TEXT NOT NULL DEFAULT '',"
        "  detalhe TEXT NOT NULL DEFAULT '',"
        "  ip TEXT NOT NULL DEFAULT '',"
        "  resultado TEXT NOT NULL DEFAULT 'ok',"
        "  http_status INTEGER NOT NULL DEFAULT 0"
        ")")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evento_data ON evento(data_iso)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evento_usuario ON evento(usuario)")


def _ip(request: Request | None) -> str:
    if request is None:
        return ""
    # Atras de proxy reverso (HTTPS futuro) o IP real vem no cabecalho.
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else ""


def registrar(acao: str, usuario: Usuario | None = None, *,
              detalhe: str = "", request: Request | None = None,
              resultado: str = RESULTADO_OK, http_status: int = 200,
              descricao: str = "", quando: tuple[str, str] | None = None) -> None:
    """Grava UMA linha do historico. Nunca levanta: auditoria que quebra a
    funcionalidade seria pior que auditoria ausente (o erro vai ao console).

    `quando` = (data_iso, data_hora) para carimbar o momento REAL do evento em
    vez de agora — usado pela sessao expirada, que so e percebida depois."""
    registro = ACOES.get(acao)
    try:
        data_iso, agora = quando or (_iso_agora(), agora_br())
        with conexao() as conn:
            _criar(conn)
            conn.execute(
                "INSERT INTO evento(data_iso, data_hora, usuario_id, usuario,"
                " nome, acao, descricao, categoria, detalhe, ip, resultado,"
                " http_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (data_iso, agora,
                 usuario.id if usuario else 0,
                 usuario.usuario if usuario else "",
                 usuario.nome if usuario else "",
                 acao,
                 descricao or (registro.descricao if registro else acao),
                 registro.categoria if registro else "",
                 detalhe, _ip(request), resultado, http_status))
    except Exception as exc:  # noqa: BLE001 — historico nunca derruba a rota
        print(f"AVISO - falha ao gravar o historico ({acao}): {exc}")


def _iso_agora() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def detalhar(request: Request, detalhe: str) -> None:
    """Enriquece a linha do historico com o que so a rota sabe."""
    request.state.auditoria_detalhe = detalhe


def acesso(slug: str):
    """Dependency: autentica, confere permissao e marca para o historico.

    A marcacao acontece ANTES da checagem de permissao de proposito — assim o
    middleware registra tambem a tentativa NEGADA de quem nao podia."""
    registro = ACOES.get(slug)
    if registro is None:                      # erro de programacao, nao de uso
        raise KeyError(f"Acao desconhecida no registro de auditoria: {slug}")

    def _dependencia(request: Request) -> Usuario:
        usuario = exigir_usuario(request)
        request.state.auditoria_acao = slug
        request.state.auditoria_usuario = usuario
        if registro.aba:
            _exigir(usuario, f"aba.{registro.aba}",
                    "Voce nao tem acesso a esta ferramenta. Fale com o "
                    "administrador.")
        if registro.permissao:
            _exigir(usuario, registro.permissao,
                    "Voce nao tem permissao para esta acao. Fale com o "
                    "administrador.")
        return usuario

    return _dependencia


def exigir_aba(nome: str):
    """Dependency das rotas de LEITURA: exige a aba, mas nao audita.

    Consultar a tabela de notas ou a composicao de uma nota acontece o tempo
    todo (a cada correcao a tela recarrega); auditar isso afogaria o que
    importa. O acesso a ferramenta ja ficou registrado em `navegacao.aba`."""
    def _dependencia(request: Request) -> Usuario:
        usuario = exigir_usuario(request)
        _exigir(usuario, f"aba.{nome}",
                "Voce nao tem acesso a esta ferramenta. Fale com o "
                "administrador.")
        return usuario

    return _dependencia


def _exigir(usuario: Usuario, slug: str, mensagem: str) -> None:
    if not permissoes.tem_permissao(usuario, slug):
        raise HTTPException(status_code=403, detail=mensagem)


def exigir_permissao(usuario: Usuario, slug: str, mensagem: str) -> None:
    """Checagem pontual dentro da rota (ex.: correcao em LOTE, que so o corpo
    da requisicao revela)."""
    _exigir(usuario, slug, mensagem)


async def middleware_historico(request: Request, chamar_proxima):
    """Grava a linha do historico DEPOIS da resposta, com o status real.

    Uma excecao inesperada na rota (um 500) tambem PRECISA deixar rastro: e o
    momento em que o dono mais quer saber o que a pessoa tentou. Por isso o
    `await` fica num try/except que grava a linha como erro e re-levanta — sem
    isso, um lote de correcao que estoura no meio (mutacao fiscal parcial ja
    gravada) sumiria da trilha de uso."""
    request.state.auditoria_acao = ""
    request.state.auditoria_detalhe = ""
    try:
        resposta = await chamar_proxima(request)
    except Exception:
        acao = getattr(request.state, "auditoria_acao", "")
        if acao:
            registrar(acao, getattr(request.state, "auditoria_usuario", None),
                      detalhe=getattr(request.state, "auditoria_detalhe", ""),
                      request=request, resultado=RESULTADO_ERRO,
                      http_status=500)
        raise

    acao = getattr(request.state, "auditoria_acao", "")
    if not acao:
        return resposta                     # rota sem auditoria (polling etc.)

    codigo = resposta.status_code
    if codigo == 403:
        resultado = RESULTADO_NEGADO
    elif codigo >= 400:
        resultado = RESULTADO_ERRO
    else:
        resultado = RESULTADO_OK
    registrar(acao, getattr(request.state, "auditoria_usuario", None),
              detalhe=getattr(request.state, "auditoria_detalhe", ""),
              request=request, resultado=resultado, http_status=codigo)
    return resposta


def varrer_sessoes_expiradas() -> None:
    """Fecha as sessoes vencidas e grava a saida com a hora REAL do vencimento.

    Sem isto, quem fecha o navegador e nunca volta some da resposta 'quando
    saiu' (a sessao vencida so era percebida quando aquela pessoa voltava). A
    varredura roda a cada login: barata e garante que a saida por tempo apareca
    mesmo para quem nao retorna, carimbada no minuto certo, nao no da varredura."""
    from datetime import datetime

    from .auth import conexao as _conexao

    try:
        agora = datetime.now().isoformat()
        with _conexao() as conn:
            vencidas = conn.execute(
                "SELECT s.token, s.expira_em, u.id, u.nome, u.usuario, u.admin"
                " FROM sessao_login s JOIN usuario u ON u.id = s.usuario_id"
                " WHERE s.expira_em < ?", (agora,)).fetchall()
            for linha in vencidas:
                conn.execute("DELETE FROM sessao_login WHERE token=?",
                             (linha["token"],))
    except Exception as exc:  # noqa: BLE001 — varredura nunca derruba o login
        print(f"AVISO - falha ao varrer sessoes expiradas: {exc}")
        return

    for linha in vencidas:
        vencimento = datetime.fromisoformat(linha["expira_em"])
        registrar(
            "sessao.expirada",
            Usuario(id=linha["id"], nome=linha["nome"],
                    usuario=linha["usuario"], admin=bool(linha["admin"])),
            quando=(vencimento.isoformat(timespec="seconds"),
                    vencimento.strftime("%d/%m/%Y %H:%M")))


def registrar_login(request: Request, usuario: Usuario | None,
                    tentado: str = "") -> None:
    """Login/logout ficam fora da dependency: no login ainda nao ha usuario e
    no logout ele esta sendo destruido."""
    if usuario is None:
        registrar("sessao.login_negado", None,
                  detalhe=f"usuario informado: {tentado}", request=request,
                  resultado=RESULTADO_NEGADO, http_status=401)
    else:
        registrar("sessao.login", usuario, request=request)


# ----------------------------------------------------------------------
# Consulta (tela de historico)


def consultar(*, usuario: str = "", categoria: str = "", acao: str = "",
              de: str = "", ate: str = "", texto: str = "",
              limite: int = 200, pagina: int = 1) -> dict:
    """Historico filtrado, do mais recente para o mais antigo.

    `de`/`ate` sao datas ISO (aaaa-mm-dd); `ate` cobre o dia inteiro."""
    condicoes: list[str] = []
    valores: list[object] = []
    if usuario:
        condicoes.append("usuario=?")
        valores.append(usuario.strip().lower())
    if categoria:
        condicoes.append("categoria=?")
        valores.append(categoria)
    if acao:
        condicoes.append("acao=?")
        valores.append(acao)
    if de:
        condicoes.append("data_iso >= ?")
        valores.append(f"{de}T00:00:00")
    if ate:
        condicoes.append("data_iso <= ?")
        valores.append(f"{ate}T23:59:59")
    if texto:
        condicoes.append("(descricao LIKE ? OR detalhe LIKE ? OR nome LIKE ?)")
        valores.extend([f"%{texto}%"] * 3)
    onde = f" WHERE {' AND '.join(condicoes)}" if condicoes else ""

    limite = max(1, min(int(limite or 200), 1000))
    pagina = max(1, int(pagina or 1))
    with conexao() as conn:
        _criar(conn)
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM evento{onde}", valores).fetchone()["n"]
        # Prende a pagina ao numero real de paginas: alem de devolver a ultima
        # em vez de nada, impede que um OFFSET gigante (pagina=2^63) estoure o
        # inteiro do SQLite e vire 500.
        paginas = max(1, -(-total // limite))
        pagina = min(pagina, paginas)
        linhas = conn.execute(
            f"SELECT * FROM evento{onde} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()
    return {
        "total": total, "pagina": pagina, "limite": limite,
        "itens": [_linha_json(linha) for linha in linhas],
    }


def usuarios_no_historico() -> list[dict]:
    """Usuarios distintos que tem evento — popula o filtro do historico mesmo
    para quem so tem admin.historico (nao alcanca a lista de usuarios)."""
    with conexao() as conn:
        _criar(conn)
        linhas = conn.execute(
            "SELECT usuario, nome FROM evento WHERE usuario<>''"
            " GROUP BY usuario ORDER BY usuario").fetchall()
    return [{"valor": linha["usuario"],
             "rotulo": f"{linha['usuario']} ({linha['nome']})"
                       if linha["nome"] else linha["usuario"]}
            for linha in linhas]


def _linha_json(linha: sqlite3.Row) -> dict:
    return {
        "id": linha["id"], "data_hora": linha["data_hora"],
        "usuario": linha["usuario"], "nome": linha["nome"],
        "acao": linha["acao"], "descricao": linha["descricao"],
        "categoria": linha["categoria"],
        "categoria_rotulo": ROTULO_CATEGORIA.get(linha["categoria"], ""),
        "detalhe": linha["detalhe"], "ip": linha["ip"],
        "resultado": linha["resultado"], "http_status": linha["http_status"],
    }


def resumo_por_usuario(usuario: str) -> dict:
    """Ultimo acesso e contagem por categoria — cabecalho da tela de usuario."""
    with conexao() as conn:
        _criar(conn)
        ultimo = conn.execute(
            "SELECT data_hora FROM evento WHERE usuario=? AND acao='sessao.login'"
            " ORDER BY id DESC LIMIT 1", (usuario,)).fetchone()
        contagens = conn.execute(
            "SELECT categoria, COUNT(*) AS n FROM evento WHERE usuario=?"
            " GROUP BY categoria", (usuario,)).fetchall()
    return {
        "ultimo_acesso": ultimo["data_hora"] if ultimo else "",
        "por_categoria": {linha["categoria"]: linha["n"]
                          for linha in contagens},
    }


def texto_json(valor: dict) -> str:
    """Detalhe estruturado -> texto curto para a coluna Detalhe."""
    return json.dumps(valor, ensure_ascii=True, sort_keys=True)
