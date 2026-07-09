"""Smoke test da interface (headless / offscreen).

Verifica que a janela principal e as cinco abas constroem e populam sem erro.
"""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

import pandas as pd  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from auditoria_fiscal.core.cadastro_produtos import (  # noqa: E402
    BaseProdutos, LayoutBase, ProdutoCadastro,
)
from auditoria_fiscal.core.modelos import (  # noqa: E402
    DocumentoFiscalConjunto, Empresa, ItemNota, NotaFiscal, Participante,
)
from auditoria_fiscal.core.sefaz_relacao import RegistroSefaz  # noqa: E402
from auditoria_fiscal.ferramentas.auditoria_produtos import (  # noqa: E402
    CONF_ALTA, MSG_ST_COMO_TRIBUTADO, TIPO_ST_COMO_TRIBUTADO, TRIB_INTEGRAL,
    TRIB_ST, Inconsistencia, ResultadoAuditoria, calcular_indicadores,
)
from auditoria_fiscal.ferramentas.comparador_sped_sefaz import comparar  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sped import comparar_speds  # noqa: E402
from auditoria_fiscal.ferramentas.conferencia_store import ConferenciaStore  # noqa: E402
from auditoria_fiscal.ferramentas.extracao_itens import CAMPOS  # noqa: E402
from auditoria_fiscal.ui.app import JanelaPrincipal  # noqa: E402
from auditoria_fiscal.ui.comparador_widget import ComparadorWidget  # noqa: E402
from auditoria_fiscal.ui.conferencia_widget import (  # noqa: E402
    COL_CONF, COL_OBS, ConferenciaWidget,
)
from auditoria_fiscal.ui.diff_widget import DiffSpedWidget  # noqa: E402
from auditoria_fiscal.ui.extracao_widget import ExtracaoWidget  # noqa: E402
from auditoria_fiscal.ui.produtos_widget import ProdutosWidget  # noqa: E402
from auditoria_fiscal.ui.tema import aplicar_tema  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    aplicar_tema(app)   # exercita paleta/QSS do tema
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    # Janela principal com as abas
    janela = JanelaPrincipal()
    janela.show()

    # --- Aba comparador ---
    chave_a = "3" * 44
    chave_b = "4" * 44
    doc = DocumentoFiscalConjunto(
        empresa=Empresa(nome="EMPRESA DEMO LTDA"),
        notas=[NotaFiscal(chave=chave_a, ind_oper="0", situacao="00", numero="1",
                          valor_documento=Decimal("100.00"),
                          participante=Participante(nome="FORN A"))],
    )
    registros = [
        RegistroSefaz(chave=chave_a, numero="1", valor=Decimal("100.00"),
                      situacao="Autorizada"),
        RegistroSefaz(chave=chave_b, numero="2", valor=Decimal("50.00"),
                      situacao="Autorizada", emitente_nome="FORN B"),
    ]
    resultado = comparar(doc, registros)
    comp = ComparadorWidget()
    comp._ao_concluir("EMPRESA DEMO LTDA", resultado,
                      {"mapa_colunas": {"chave": "Chave de Acesso"},
                       "registros_validos": 2})
    checar(comp._tab_faltantes.rowCount() == 1,
           f"faltantes rowCount={comp._tab_faltantes.rowCount()}")
    checar(comp._cartoes["faltantes"].text() == "1",
           f"cartao faltantes={comp._cartoes['faltantes'].text()}")
    item = comp._tab_faltantes.item(0, 0)
    checar(item is not None and item.text() == chave_b,
           f"chave faltante: {item.text() if item else None}")

    # --- Aba extracao ---
    ext = ExtracaoWidget()
    linha = {chave: "" for chave, _, _ in CAMPOS}
    linha.update({"chave": chave_a, "numero": "1", "descricao": "PRODUTO X",
                  "ncm": "12345678", "cfop": "1102", "cst_icms": "000",
                  "quantidade": Decimal("10"), "valor_item": Decimal("50.00")})
    ext._ao_concluir([linha, dict(linha)], "SPED DEMO")
    checar(ext._tabela.rowCount() == 2, f"extracao rowCount={ext._tabela.rowCount()}")
    checar(ext._btn_exportar.isEnabled(), "botao exportar deveria estar habilitado")
    cel = ext._tabela.item(0, 10)  # coluna "Descricao" (indice 10 em CAMPOS)
    checar(cel is not None and cel.text() == "PRODUTO X",
           f"descricao na tabela: {cel.text() if cel else None}")

    # --- Aba comparacao de SPEDs ---
    chave_x = "5" * 44
    chave_y = "6" * 44
    doc_a = DocumentoFiscalConjunto(notas=[
        NotaFiscal(chave=chave_x, ind_oper="0", situacao="00", numero="10",
                   valor_documento=Decimal("100.00"),
                   itens=[ItemNota(num_item="1", cfop="1102", cst_icms="000")])])
    doc_b = DocumentoFiscalConjunto(notas=[
        NotaFiscal(chave=chave_x, ind_oper="0", situacao="00", numero="10",
                   valor_documento=Decimal("150.00"),
                   itens=[ItemNota(num_item="1", cfop="5102", cst_icms="000")]),
        NotaFiscal(chave=chave_y, ind_oper="0", situacao="00", numero="20",
                   valor_documento=Decimal("80.00"))])
    res_diff = comparar_speds(doc_a, doc_b, "A", "B")
    diff = DiffSpedWidget()
    diff._ao_concluir(res_diff)
    checar(diff._cartoes["divergentes"].text() == "1",
           f"diff divergentes={diff._cartoes['divergentes'].text()}")
    checar(diff._tab_diverg.rowCount() == 2,
           f"diff linhas={diff._tab_diverg.rowCount()} (esperado 2: valor + cfop)")
    checar(diff._tab_so_b.rowCount() == 1,
           f"so em B={diff._tab_so_b.rowCount()}")

    # --- Aba livro de conferencia ---
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    store = ConferenciaStore(db)
    conf = ConferenciaWidget(store=store)
    ch_c1, ch_c2 = "7" * 44, "8" * 44
    notas_conf = [
        NotaFiscal(chave=ch_c1, numero="1", situacao="00",
                   valor_documento=Decimal("100.00"),
                   participante=Participante(nome="FORN C1"),
                   itens=[ItemNota(cfop="1102", cst_icms="000",
                                   aliq_icms=Decimal("18.00"))]),
        NotaFiscal(chave=ch_c2, numero="2", situacao="00",
                   valor_documento=Decimal("200.00")),
    ]
    conf._ao_carregar(notas_conf, "XML DEMO")
    checar(conf._tabela.rowCount() == 2, f"conf rowCount={conf._tabela.rowCount()}")
    checar("0 de 2" in conf._lbl_progresso.text(),
           f"progresso inicial: {conf._lbl_progresso.text()}")
    # Marca a primeira como conferida -> persiste
    conf._tabela.item(0, COL_CONF).setCheckState(Qt.Checked)
    checar(store.obter(ch_c1).conferida, "conferida nao persistiu no store")
    checar("1 de 2" in conf._lbl_progresso.text(),
           f"progresso apos conferir: {conf._lbl_progresso.text()}")
    # Edita observacao -> persiste
    conf._tabela.item(0, COL_OBS).setText("CFOP ok")
    checar(store.obter(ch_c1).observacao == "CFOP ok", "observacao nao persistiu")
    store.fechar()
    os.unlink(db)

    # --- Aba auditoria de produtos ---
    prod_ok = ProdutoCadastro(indice=0, codigo="P1", descricao="BALA DE GOMA",
                              ncm="17041000", cest="1703100", cfops=["5405"],
                              cst="60")
    prod_err = ProdutoCadastro(indice=1, codigo="P2",
                               descricao="REFRIGERANTE COLA 2L",
                               ncm="22021000", cfops=["5102"], cst="00",
                               aliquota=Decimal("20.5"))
    res_ok = ResultadoAuditoria(produto=prod_ok, situacao="OK",
                                tributacao_atual=TRIB_ST,
                                tributacao_sugerida=TRIB_ST)
    res_err = ResultadoAuditoria(
        produto=prod_err, situacao="INCONSISTENTE",
        tributacao_atual=TRIB_INTEGRAL, tributacao_sugerida=TRIB_ST,
        confianca=CONF_ALTA,
        inconsistencias=[Inconsistencia(tipo=TIPO_ST_COMO_TRIBUTADO,
                                        mensagem=MSG_ST_COMO_TRIBUTADO)],
        correcoes={"cst": "60", "cest": "0300200"},
        cfop_map={"5102": "5405"})
    resultados_prod = [res_ok, res_err]
    base_prod = BaseProdutos(caminho="cadastro_demo.xlsx",
                             layout=LayoutBase(tipo="xlsx"),
                             df_bruto=pd.DataFrame(),
                             produtos=[prod_ok, prod_err], diagnostico={})
    prod = ProdutosWidget()
    prod._ao_concluir({"base": base_prod, "resultados": resultados_prod,
                       "indicadores": calcular_indicadores(resultados_prod)})
    checar(prod._tabela.rowCount() == 2,
           f"produtos rowCount={prod._tabela.rowCount()}")
    checar(prod._btn_relatorio.isEnabled(),
           "botao de relatorio de produtos deveria estar habilitado")
    checar(prod._btn_nova_base.isEnabled(),
           "botao de nova base deveria estar habilitado")
    marca = prod._tabela.item(1, 0)
    checar(marca is not None and bool(marca.flags() & Qt.ItemIsUserCheckable),
           "linha com correcao deveria ter checkbox marcavel")
    marca_ok = prod._tabela.item(0, 0)
    checar(marca_ok is not None
           and not bool(marca_ok.flags() & Qt.ItemIsUserCheckable),
           "linha sem correcao nao deveria ter checkbox marcavel")
    cel_sit = prod._tabela.item(1, 11)   # coluna Situacao
    checar(cel_sit is not None and cel_sit.text() == "INCONSISTENTE",
           f"situacao na tabela: {cel_sit.text() if cel_sit else None}")
    cel_corr = prod._tabela.item(1, 13)  # coluna Correcao sugerida
    checar(cel_corr is not None and "CST" in cel_corr.text()
           and "5405" in cel_corr.text(),
           f"correcao sugerida: {cel_corr.text() if cel_corr else None}")
    checar("Total: 2" in prod._labels_ind["total"].text(),
           f"indicador total: {prod._labels_ind['total'].text()}")

    janela.close()
    app.quit()

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - janela principal + 5 abas (comparador, diff, conferencia, "
          "extracao, produtos) OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
