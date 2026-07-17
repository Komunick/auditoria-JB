"""Catalogo de permissoes e o que cada usuario alcanca no site.

Ate 2026-07-16 o unico controle era a flag `admin` (tudo ou nada). O dono
pediu (decisao do dono, 2026-07-17) controle fino: o administrador define
quais ABAS e quais ACOES SENSIVEIS (correcao em lote, editar composicao
fiscal, gerar SPED corrigido, relatorios...) cada usuario alcanca.

Modelo: administrador tem TODAS as permissoes implicitamente — a tabela
`permissao_usuario` guarda apenas as concessoes dos NAO administradores, uma
linha por permissao concedida (ausencia = negado). Assim, promover alguem a
admin nunca depende de a tabela estar completa, e uma permissao nova criada
no futuro ja nasce disponivel para os admins.

O slug da aba (`aba.conferencia`, `aba.produtos`, ...) e o portao de entrada
da ferramenta: sem ele a aba nem aparece no navegador e todas as rotas dela
respondem 403. As demais permissoes recortam acoes DENTRO da aba liberada.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .auth import Usuario, conexao

GRUPO_ABAS = "Abas (ferramentas)"
GRUPO_CONFERENCIA = "Livro de Conferencia"
GRUPO_COMPARADORES = "Comparadores e Extracao"
GRUPO_PRODUTOS = "Auditoria de Produtos"
GRUPO_ADMIN = "Administracao"


@dataclass(frozen=True)
class Permissao:
    slug: str
    rotulo: str
    grupo: str
    ajuda: str = ""


# Ordem do catalogo = ordem de exibicao na tela de administracao.
CATALOGO: tuple[Permissao, ...] = (
    # ------------------------------------------------------------------
    # Abas: portao de entrada de cada ferramenta
    Permissao("aba.comparador", "1. Comparador SPED x SEFAZ", GRUPO_ABAS,
              "Abrir a aba e cruzar SPED com a relacao da SEFAZ."),
    Permissao("aba.diff", "2. Comparar versoes de SPED", GRUPO_ABAS,
              "Abrir a aba e comparar dois arquivos SPED campo a campo."),
    Permissao("aba.conferencia", "3. Livro de Conferencia", GRUPO_ABAS,
              "Abrir a aba, carregar notas e consultar a composicao fiscal."),
    Permissao("aba.extracao", "4. Extracao de Itens", GRUPO_ABAS,
              "Abrir a aba e extrair os itens para auditoria."),
    Permissao("aba.produtos", "5. Auditoria de Produtos", GRUPO_ABAS,
              "Abrir a aba e auditar a tributacao do cadastro."),

    # ------------------------------------------------------------------
    # Livro de Conferencia: acoes que gravam ou geram documento
    Permissao("conferencia.conferir", "Marcar nota como conferida",
              GRUPO_CONFERENCIA,
              "Gravar a conferencia e a observacao da nota."),
    Permissao("conferencia.corrigir", "Corrigir campo fiscal (uma nota)",
              GRUPO_CONFERENCIA,
              "Registrar correcao de CFOP, CST ou aliquota em uma nota."),
    Permissao("conferencia.corrigir_lote", "Corrigir em lote (varias notas)",
              GRUPO_CONFERENCIA,
              "Propagar a mesma correcao para todas as notas com aquele "
              "valor. Exige tambem a permissao de corrigir uma nota."),
    Permissao("conferencia.composicao_editar", "Editar a composicao fiscal",
              GRUPO_CONFERENCIA,
              "Editar celulas da composicao: correcoes nos campos fiscais e "
              "sobrescritas de texto que saem no Livro Fiscal."),
    Permissao("conferencia.danfe", "Abrir DANFE (PDF)", GRUPO_CONFERENCIA,
              "Gerar o DANFE da nota a partir do XML."),
    Permissao("conferencia.livro_fiscal", "Gerar Livro Fiscal (PDF)",
              GRUPO_CONFERENCIA, "Gerar o Livro Fiscal completo em PDF."),
    Permissao("conferencia.inconsistencias",
              "Gerar Relatorio de Inconsistencias (PDF)", GRUPO_CONFERENCIA,
              "Gerar o relatorio das notas com observacao ou correcao."),
    Permissao("conferencia.sped_corrigido", "Gerar SPED corrigido (.txt)",
              GRUPO_CONFERENCIA,
              "Gerar o arquivo SPED com as correcoes aplicadas — a saida que "
              "volta para o cliente."),

    # ------------------------------------------------------------------
    # Comparadores e Extracao
    Permissao("comparador.exportar", "Exportar Excel do Comparador SEFAZ",
              GRUPO_COMPARADORES, "Baixar a planilha de 5 abas da comparacao."),
    Permissao("diff.exportar", "Exportar Excel do comparador de SPEDs",
              GRUPO_COMPARADORES, "Baixar a planilha das divergencias."),
    Permissao("extracao.exportar", "Exportar Excel da Extracao de Itens",
              GRUPO_COMPARADORES, "Baixar a planilha com todos os itens."),

    # ------------------------------------------------------------------
    # Auditoria de Produtos
    Permissao("produtos.corrigir", "Corrigir tributacao de produtos",
              GRUPO_PRODUTOS,
              "Aplicar correcoes no cadastro (individual e alta confianca)."),
    Permissao("produtos.relatorio", "Gerar relatorio de produtos (Excel)",
              GRUPO_PRODUTOS, "Baixar o relatorio da auditoria."),
    Permissao("produtos.nova_base", "Gerar nova base corrigida",
              GRUPO_PRODUTOS,
              "Gerar a planilha do cadastro ja com as correcoes."),

    # ------------------------------------------------------------------
    # Administracao
    Permissao("admin.usuarios", "Administrar usuarios e permissoes",
              GRUPO_ADMIN,
              "Criar usuarios, definir permissoes, ativar e desativar."),
    Permissao("admin.historico", "Ver o historico de acessos",
              GRUPO_ADMIN, "Consultar a trilha de acessos e acoes de todos."),
)

SLUGS = tuple(p.slug for p in CATALOGO)
_VALIDOS = frozenset(SLUGS)

# Sugestao para um usuario novo: enxerga todas as ferramentas e trabalha
# nelas, mas as acoes que mudam numero fiscal ou geram a saida oficial ficam
# de fora ate o administrador liberar. A tela de administracao mostra estas
# caixas ja marcadas — o admin ve exatamente o que esta concedendo.
PADRAO_NOVO_USUARIO: tuple[str, ...] = (
    "aba.comparador", "aba.diff", "aba.conferencia", "aba.extracao",
    "aba.produtos", "conferencia.conferir", "conferencia.danfe",
    "comparador.exportar", "diff.exportar", "extracao.exportar",
)


def _criar(conn: sqlite3.Connection) -> None:
    """Migracao aditiva: bancos existentes ganham a tabela sem perder nada."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS permissao_usuario ("
        "  usuario_id INTEGER NOT NULL,"
        "  slug TEXT NOT NULL,"
        "  concedida_em TEXT NOT NULL DEFAULT '',"
        "  concedida_por TEXT NOT NULL DEFAULT '',"
        "  PRIMARY KEY (usuario_id, slug)"
        ")")


def validar(slugs) -> list[str]:
    """Filtra e ordena pelo catalogo. Slug desconhecido levanta ValueError."""
    pedidos = {str(s).strip() for s in slugs or ()} - {""}
    invalidos = pedidos - _VALIDOS
    if invalidos:
        raise ValueError(
            f"Permissao desconhecida: {', '.join(sorted(invalidos))}.")
    return [s for s in SLUGS if s in pedidos]


def permissoes_do_usuario(usuario_id: int, admin: bool = False) -> list[str]:
    """Admin recebe o catalogo inteiro; os demais, o que esta concedido."""
    if admin:
        return list(SLUGS)
    with conexao() as conn:
        _criar(conn)
        linhas = conn.execute(
            "SELECT slug FROM permissao_usuario WHERE usuario_id=?",
            (usuario_id,)).fetchall()
    concedidas = {linha["slug"] for linha in linhas}
    return [s for s in SLUGS if s in concedidas]


def tem_permissao(usuario: Usuario, slug: str) -> bool:
    if usuario.admin:
        return True
    return slug in permissoes_do_usuario(usuario.id, False)


def definir(usuario_id: int, slugs, por: str = "") -> list[str]:
    """Substitui o conjunto de permissoes do usuario (o que nao vier, sai)."""
    from .auth import agora_br

    novas = validar(slugs)
    with conexao() as conn:
        _criar(conn)
        atuais = {linha["slug"] for linha in conn.execute(
            "SELECT slug FROM permissao_usuario WHERE usuario_id=?",
            (usuario_id,)).fetchall()}
        for slug in atuais - set(novas):
            conn.execute(
                "DELETE FROM permissao_usuario WHERE usuario_id=? AND slug=?",
                (usuario_id, slug))
        for slug in set(novas) - atuais:
            conn.execute(
                "INSERT INTO permissao_usuario(usuario_id, slug,"
                " concedida_em, concedida_por) VALUES(?,?,?,?)",
                (usuario_id, slug, agora_br(), por))
    return novas


def remover_do_usuario(usuario_id: int) -> None:
    with conexao() as conn:
        _criar(conn)
        conn.execute("DELETE FROM permissao_usuario WHERE usuario_id=?",
                     (usuario_id,))


def catalogo_json() -> list[dict]:
    """Catalogo para a tela de administracao, ja agrupado na ordem de exibicao."""
    grupos: list[dict] = []
    for permissao in CATALOGO:
        if not grupos or grupos[-1]["grupo"] != permissao.grupo:
            grupos.append({"grupo": permissao.grupo, "itens": []})
        grupos[-1]["itens"].append({
            "slug": permissao.slug, "rotulo": permissao.rotulo,
            "ajuda": permissao.ajuda,
        })
    return grupos
