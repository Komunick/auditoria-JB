"""Livro de Inconsistencias (PDF) do Livro de Conferencia Fiscal.

Relaciona exclusivamente as notas com observacao registrada na conferencia,
compondo o caderno de inconsistencias entregue ao cliente. Renderizado com
fpdf2 (a mesma base usada pelo brazilfiscalreport na geracao do DANFE).
"""

from __future__ import annotations

from datetime import datetime

from ..core.modelos import NotaFiscal

TITULO = "Livro de Inconsistencias - Conferencia Fiscal"


def _latin1(texto) -> str:
    """As fontes padrao do fpdf2 so aceitam latin-1; troca o que nao couber."""
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


def _moeda(valor) -> str:
    txt = f"{float(valor or 0):,.2f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def _data(dt) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


def _distintos(itens, attr) -> str:
    vistos: list[str] = []
    for it in itens:
        v = str(getattr(it, attr)).strip()
        if v and v not in vistos:
            vistos.append(v)
    return ", ".join(vistos)


def notas_com_observacao(notas, estados) -> list[tuple[NotaFiscal, object]]:
    """Pares (nota, estado) das notas carregadas que tem observacao registrada."""
    resultado = []
    for nota in notas:
        estado = estados.get(nota.chave_normalizada)
        if estado is not None and estado.observacao.strip():
            resultado.append((nota, estado))
    return resultado


def gerar_livro_inconsistencias(notas, estados, pdf_path: str,
                                contexto: str = "", filtro: str = "") -> str:
    """Gera o PDF com as notas que tem observacao. Retorna o caminho do PDF.

    notas: notas carregadas na conferencia (SPED ou XML).
    estados: mapa chave -> EstadoConferencia (ConferenciaStore.carregar()).
    Levanta ValueError se nenhuma nota tiver observacao.
    """
    from fpdf import FPDF

    selecionadas = notas_com_observacao(notas, estados)
    if not selecionadas:
        raise ValueError("Nenhuma nota com observacao para listar.")

    class _PDF(FPDF):
        def footer(self):
            self.set_y(-10)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 6, f"Pagina {self.page_no()}", align="C")

    pdf = _PDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    # Cabecalho
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
        f"Emitido em {emissao} - {len(selecionadas)} nota(s) com observacao "
        f"(de {len(notas)} carregadas)"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Tabela (a primeira linha e o cabecalho, repetido a cada pagina)
    pdf.set_font("Helvetica", "", 8)
    with pdf.table(
        col_widths=(14, 8, 17, 46, 26, 22, 16, 78, 24),
        text_align=("CENTER", "CENTER", "CENTER", "LEFT", "CENTER",
                    "RIGHT", "CENTER", "LEFT", "CENTER"),
        line_height=4.5,
        padding=1,
    ) as tabela:
        cab = tabela.row()
        for titulo in ("Numero", "Serie", "Data", "Fornecedor", "CNPJ",
                       "Valor contabil", "CFOP", "Observacao", "Conferida em"):
            cab.cell(_latin1(titulo))
        for nota, estado in selecionadas:
            forn = nota.participante.nome if nota.participante else ""
            conferida = (estado.data_conferencia or "Sim") if estado.conferida \
                else "Nao"
            linha = tabela.row()
            linha.cell(_latin1(nota.numero))
            linha.cell(_latin1(nota.serie))
            linha.cell(_latin1(_data(nota.dt_emissao)))
            linha.cell(_latin1(forn))
            linha.cell(_latin1(nota.cnpj_emitente))
            linha.cell(_latin1(_moeda(nota.valor_documento)))
            linha.cell(_latin1(_distintos(nota.itens, "cfop")))
            linha.cell(_latin1(estado.observacao))
            linha.cell(_latin1(conferida))

    pdf.output(pdf_path)
    return pdf_path
