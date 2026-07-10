"""Livro Fiscal (PDF) do Livro de Conferencia.

Relaciona TODAS as notas carregadas, ja com as correcoes aplicadas (regra de
precedencia central de core/correcoes.py), agrupadas por CFOP -> CST ->
aliquota (core/composicao_fiscal.py — a mesma composicao da tela, para nao
haver divergencia entre as saidas).

Ordem visual de cada grupo (requisito):

    CFOP: 1.102 - CST 000
    Valor Contabil: R$ 200,00
    Base de Calculo: R$ 200,00
    Aliquota: 20,50%
    Valor do ICMS: R$ 41,00
    Observacao/Inconsistencia: [abaixo dos valores]

O livro NAO apresenta a data de conferencia. O bloco de uma nota nao e
dividido entre paginas: se nao couber no espaco restante, comeca em nova
pagina (blocos maiores que uma pagina inteira — raros — quebram apos grupos
completos).
"""

from __future__ import annotations

from datetime import datetime

from ..core.composicao_fiscal import compor_nota
from ..core.correcoes import CAMPOS_CORRIGIVEIS, aplicar_correcoes
from ..core.utils import formatar_cfop, formatar_moeda, formatar_percentual

TITULO_LIVRO = "Livro Fiscal - Conferencia de Notas"

# Altura de linha (mm) usada no calculo de quebra de pagina.
ALTURA_LINHA = 4.6


def _latin1(texto) -> str:
    """As fontes padrao do fpdf2 so aceitam latin-1; troca o que nao couber."""
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


def _rotulo_grupo(grupo) -> str:
    cfop = formatar_cfop(grupo.cfop) if grupo.cfop else "(sem CFOP)"
    cst = grupo.cst or "(sem CST)"
    rotulo = f"CFOP: {cfop} - CST {cst}"
    correcoes = []
    for campo, original in grupo.corrigido_de.items():
        nome = CAMPOS_CORRIGIVEIS.get(campo, campo)
        correcoes.append(f"{nome} corrigido de {original}")
    if correcoes:
        rotulo += f"  [{'; '.join(correcoes)}]"
    return rotulo


def _linhas_grupo(grupo) -> list[str]:
    """Linhas do grupo na ordem exigida: CFOP, valor contabil, BC, aliq, ICMS."""
    linhas = [_rotulo_grupo(grupo),
              f"Valor Contabil: {formatar_moeda(grupo.valor_contabil, True)}"]
    if grupo.tem_icms:
        linhas.append(
            f"Base de Calculo: {formatar_moeda(grupo.vl_bc_icms, True)}")
        linhas.append(f"Aliquota: {formatar_percentual(grupo.aliquota)}")
        linhas.append(f"Valor do ICMS: {formatar_moeda(grupo.vl_icms, True)}")
    if grupo.vl_icms_st or grupo.vl_bc_icms_st:
        linhas.append(
            f"ICMS-ST: base {formatar_moeda(grupo.vl_bc_icms_st, True)}"
            f" / valor {formatar_moeda(grupo.vl_icms_st, True)}")
    return linhas


def montar_blocos(notas, estados, correcoes_por_chave=None) -> list[dict]:
    """Blocos do livro (um por nota), ja com correcoes e composicao.

    Funcao pura (sem PDF) para permitir teste do conteudo e da ordem.
    Nao inclui data de conferencia em nenhum campo.
    """
    correcoes_por_chave = correcoes_por_chave or {}
    blocos = []
    for nota in notas:
        chave = nota.chave_normalizada
        corrigida = aplicar_correcoes(nota, correcoes_por_chave.get(chave, []))
        comp = compor_nota(corrigida)
        estado = estados.get(chave)
        observacao = estado.observacao.strip() if estado else ""

        forn = corrigida.participante.nome if corrigida.participante else ""
        dt = corrigida.dt_emissao.strftime("%d/%m/%Y") if corrigida.dt_emissao else ""
        blocos.append({
            "chave": chave,
            "titulo": (f"NF {corrigida.numero}  Serie {corrigida.serie}  "
                       f"{dt}  UF {corrigida.uf_origem or '--'}"),
            "subtitulo": f"{forn}  CNPJ {corrigida.cnpj_emitente}",
            "chave_texto": f"Chave de acesso: {chave}",
            "total": ("Valor total da nota: "
                      f"{formatar_moeda(comp.total_nota, True)}"),
            "grupos": [_linhas_grupo(g) for g in comp.grupos],
            "observacao": observacao,
            "alertas": list(comp.alertas),
            "tem_correcao": corrigida.tem_correcao,
        })
    return blocos


def _altura_bloco(bloco) -> float:
    """Altura estimada (mm) do bloco para decidir a quebra de pagina."""
    linhas = 3 + 1                                   # cabecalho + total
    for grupo in bloco["grupos"]:
        linhas += len(grupo) + 0.5                   # respiro entre grupos
    if bloco["observacao"]:
        linhas += 1 + bloco["observacao"].count("\n")
    linhas += len(bloco["alertas"])
    return linhas * ALTURA_LINHA + 6                 # separador/margem


def gerar_livro_fiscal(notas, estados, pdf_path: str, contexto: str = "",
                       filtro: str = "", correcoes_por_chave=None) -> str:
    """Gera o PDF do Livro Fiscal. Retorna o caminho do PDF."""
    from fpdf import FPDF

    if not notas:
        raise ValueError("Nenhuma nota carregada para compor o Livro Fiscal.")
    blocos = montar_blocos(notas, estados, correcoes_por_chave)

    class _PDF(FPDF):
        def footer(self):
            self.set_y(-10)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 6, f"Pagina {self.page_no()}", align="C")

    pdf = _PDF(orientation="P", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    # Cabecalho do livro
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(TITULO_LIVRO), align="C", new_x="LMARGIN",
             new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if contexto:
        pdf.cell(0, 5, _latin1(f"Origem: {contexto}"),
                 new_x="LMARGIN", new_y="NEXT")
    if filtro:
        pdf.cell(0, 5, _latin1(filtro), new_x="LMARGIN", new_y="NEXT")
    emissao = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, _latin1(f"Emitido em {emissao} - {len(blocos)} nota(s)"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    limite = pdf.h - 16   # inicio do rodape
    for bloco in blocos:
        altura = _altura_bloco(bloco)
        pagina_util = limite - pdf.t_margin
        # Nao separa o cabecalho da nota dos seus valores: se o bloco nao
        # cabe no restante da pagina (mas cabe em uma pagina), quebra antes.
        if pdf.get_y() + altura > limite and altura <= pagina_util:
            pdf.add_page()
        _render_bloco(pdf, bloco, limite)

    pdf.output(pdf_path)
    return pdf_path


def _linha(pdf, texto, estilo="", tamanho=9, recuo=0.0) -> None:
    pdf.set_font("Helvetica", estilo, tamanho)
    if recuo:
        pdf.set_x(pdf.l_margin + recuo)
    pdf.multi_cell(0, ALTURA_LINHA, _latin1(texto), new_x="LMARGIN",
                   new_y="NEXT")


def _render_bloco(pdf, bloco, limite) -> None:
    _linha(pdf, bloco["titulo"], estilo="B", tamanho=10)
    _linha(pdf, bloco["subtitulo"])
    _linha(pdf, bloco["chave_texto"], tamanho=8)
    total = bloco["total"]
    if bloco["tem_correcao"]:
        total += "   (contem correcoes aplicadas)"
    _linha(pdf, total, estilo="B")

    for grupo in bloco["grupos"]:
        # Grupo tambem indivisivel (para blocos maiores que uma pagina).
        altura_grupo = (len(grupo) + 1) * ALTURA_LINHA
        if pdf.get_y() + altura_grupo > limite:
            pdf.add_page()
        pdf.ln(1)
        _linha(pdf, grupo[0], estilo="B", recuo=4)
        for linha in grupo[1:]:
            _linha(pdf, linha, recuo=8)

    if bloco["observacao"]:
        pdf.ln(1)
        _linha(pdf, f"Observacao/Inconsistencia: {bloco['observacao']}",
               estilo="B", recuo=4)
    for alerta in bloco["alertas"]:
        _linha(pdf, f"Alerta: {alerta}", estilo="I", tamanho=8, recuo=4)

    # Separador entre notas
    pdf.ln(2)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
