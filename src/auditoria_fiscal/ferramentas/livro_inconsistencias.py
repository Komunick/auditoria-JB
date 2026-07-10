"""Livro/Relatorio de Inconsistencias (PDF) do Livro de Conferencia Fiscal.

Relaciona exclusivamente as notas com inconsistencia: observacao registrada
na conferencia e/ou correcao de campo fiscal. Para cada nota apresenta a
identificacao completa (numero, serie, chave, emitente, UF), a composicao
fiscal por CFOP -> CST -> aliquota (com valor contabil, base, aliquota e
ICMS separados POR ALIQUOTA), a descricao da inconsistencia e a trilha das
correcoes (valor original -> corrigido, tipo, situacao, usuario, motivo).

Usa a MESMA composicao e a MESMA regra de precedencia da tela e do Livro
Fiscal (core/composicao_fiscal.py e core/correcoes.py), garantindo que nao
haja divergencia entre as saidas. Renderizado com fpdf2.
"""

from __future__ import annotations

from datetime import datetime

from ..core.composicao_fiscal import compor_nota
from ..core.correcoes import CAMPOS_CORRIGIVEIS, aplicar_correcoes
from ..core.modelos import NotaFiscal
from ..core.utils import formatar_cfop, formatar_moeda, formatar_percentual
from .livro_fiscal import ALTURA_LINHA, _latin1, _linha

TITULO = "Relatorio de Inconsistencias - Conferencia Fiscal"


def notas_com_observacao(notas, estados) -> list[tuple[NotaFiscal, object]]:
    """Pares (nota, estado) das notas carregadas que tem observacao."""
    resultado = []
    for nota in notas:
        estado = estados.get(nota.chave_normalizada)
        if estado is not None and estado.observacao.strip():
            resultado.append((nota, estado))
    return resultado


def notas_inconsistentes(notas, estados, correcoes_por_chave=None):
    """Notas com observacao e/ou correcao registrada (pares nota, estado)."""
    correcoes_por_chave = correcoes_por_chave or {}
    resultado = []
    for nota in notas:
        chave = nota.chave_normalizada
        estado = estados.get(chave)
        tem_obs = estado is not None and estado.observacao.strip()
        if tem_obs or correcoes_por_chave.get(chave):
            resultado.append((nota, estado))
    return resultado


def montar_blocos_inconsistencias(notas, estados,
                                  correcoes_por_chave=None) -> list[dict]:
    """Blocos do relatorio (funcao pura, testavel sem PDF)."""
    correcoes_por_chave = correcoes_por_chave or {}
    blocos = []
    for nota, estado in notas_inconsistentes(notas, estados,
                                             correcoes_por_chave):
        chave = nota.chave_normalizada
        correcoes = correcoes_por_chave.get(chave, [])
        corrigida = aplicar_correcoes(nota, correcoes)
        comp = compor_nota(corrigida)

        forn = corrigida.participante.nome if corrigida.participante else ""
        dt = corrigida.dt_emissao.strftime("%d/%m/%Y") if corrigida.dt_emissao else ""
        situacao = "Conferida" if (estado and estado.conferida) else "Pendente"

        grupos = []
        for g in comp.grupos:
            linhas = [f"CFOP {formatar_cfop(g.cfop) or '--'} - CST "
                      f"{g.cst or '--'} - Aliquota "
                      f"{formatar_percentual(g.aliquota)}",
                      f"Valor Contabil: {formatar_moeda(g.valor_contabil, True)}"
                      f"   Base de Calculo: {formatar_moeda(g.vl_bc_icms, True)}"
                      f"   Valor do ICMS: {formatar_moeda(g.vl_icms, True)}"]
            for campo, original in g.corrigido_de.items():
                nome = CAMPOS_CORRIGIVEIS.get(campo, campo)
                linhas.append(f"* {nome} corrigido (original: {original})")
            grupos.append(linhas)

        trilha = []
        for c in correcoes:
            nome = CAMPOS_CORRIGIVEIS.get(c.campo, c.campo)
            trilha.append(
                f"{nome}: {c.valor_original} -> {c.valor_corrigido}"
                f" | tipo: {c.tipo} | situacao: {c.status}"
                f" | usuario: {c.usuario} | {c.data_hora}"
                + (f" | motivo: {c.motivo}" if c.motivo else "")
                + (f" | inconsistencia: {c.inconsistencia}"
                   if c.inconsistencia else ""))

        blocos.append({
            "titulo": (f"NF {corrigida.numero}  Serie {corrigida.serie}  {dt}"
                       f"  UF {corrigida.uf_origem or '--'}"
                       f"  Situacao: {situacao}"),
            "subtitulo": f"{forn}  CNPJ {corrigida.cnpj_emitente}",
            "chave_texto": f"Chave de acesso: {chave}",
            "total": ("Valor total da nota: "
                      f"{formatar_moeda(comp.total_nota, True)}"),
            "grupos": grupos,
            "inconsistencia": (estado.observacao.strip()
                               if estado and estado.observacao.strip()
                               else ""),
            "correcoes": trilha,
            "alertas": list(comp.alertas),
        })
    return blocos


def gerar_livro_inconsistencias(notas, estados, pdf_path: str,
                                contexto: str = "", filtro: str = "",
                                correcoes_por_chave=None) -> str:
    """Gera o PDF de inconsistencias. Retorna o caminho do PDF.

    Levanta ValueError se nenhuma nota tiver observacao nem correcao.
    """
    from fpdf import FPDF

    blocos = montar_blocos_inconsistencias(notas, estados, correcoes_por_chave)
    if not blocos:
        raise ValueError("Nenhuma nota com observacao para listar.")

    class _PDF(FPDF):
        def footer(self):
            self.set_y(-10)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 6, f"Pagina {self.page_no()}", align="C")

    pdf = _PDF(orientation="P", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(TITULO), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if contexto:
        pdf.cell(0, 5, _latin1(f"Origem: {contexto}"),
                 new_x="LMARGIN", new_y="NEXT")
    if filtro:
        pdf.cell(0, 5, _latin1(filtro), new_x="LMARGIN", new_y="NEXT")
    emissao = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, _latin1(
        f"Emitido em {emissao} - {len(blocos)} nota(s) com inconsistencia "
        f"(de {len(notas)} carregadas)"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    limite = pdf.h - 16
    for bloco in blocos:
        linhas = (4 + sum(len(g) + 0.5 for g in bloco["grupos"])
                  + len(bloco["correcoes"]) + len(bloco["alertas"]) + 3)
        altura = linhas * ALTURA_LINHA + 6
        if pdf.get_y() + altura > limite and altura <= limite - pdf.t_margin:
            pdf.add_page()

        _linha(pdf, bloco["titulo"], estilo="B", tamanho=10)
        _linha(pdf, bloco["subtitulo"])
        _linha(pdf, bloco["chave_texto"], tamanho=8)
        _linha(pdf, bloco["total"], estilo="B")
        for grupo in bloco["grupos"]:
            if pdf.get_y() + (len(grupo) + 1) * ALTURA_LINHA > limite:
                pdf.add_page()
            pdf.ln(1)
            _linha(pdf, grupo[0], estilo="B", recuo=4)
            for linha in grupo[1:]:
                _linha(pdf, linha, recuo=8)
        if bloco["inconsistencia"]:
            pdf.ln(1)
            _linha(pdf, f"Inconsistencia: {bloco['inconsistencia']}",
                   estilo="B", recuo=4)
        if bloco["correcoes"]:
            _linha(pdf, "Correcoes:", estilo="B", recuo=4)
            for linha in bloco["correcoes"]:
                _linha(pdf, linha, tamanho=8, recuo=8)
        for alerta in bloco["alertas"]:
            _linha(pdf, f"Alerta: {alerta}", estilo="I", tamanho=8, recuo=4)

        pdf.ln(2)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(3)

    pdf.output(pdf_path)
    return pdf_path
