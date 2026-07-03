"""Interface desktop (PySide6) do comparador SPED x SEFAZ.

Executar:  python executar.py            (a partir da raiz do projeto)
       ou:  python -m auditoria_fiscal.ui.app
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.sped_parser import ler_sped
from ..core.sefaz_relacao import ler_relacao_sefaz
from ..ferramentas.comparador_sped_sefaz import ResultadoComparacao, comparar
from ..ferramentas.relatorio_excel import gerar_relatorio


# ----------------------------------------------------------------------
class Worker(QObject):
    """Executa a leitura e a comparacao fora da thread da interface."""

    concluido = Signal(object, object, object)  # empresa_nome, resultado, diagnostico
    erro = Signal(str)

    def __init__(self, caminho_sped: str, caminho_sefaz: str, apenas_entradas: bool):
        super().__init__()
        self.caminho_sped = caminho_sped
        self.caminho_sefaz = caminho_sefaz
        self.apenas_entradas = apenas_entradas

    def executar(self) -> None:
        try:
            doc = ler_sped(self.caminho_sped)
            registros, diag = ler_relacao_sefaz(self.caminho_sefaz)
            resultado = comparar(doc, registros, apenas_entradas=self.apenas_entradas)
            self.concluido.emit(doc.empresa.nome, resultado, diag)
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------
def _moeda(valor) -> str:
    txt = f"{float(valor or 0):,.2f}"
    # Converte 1,234.56 -> 1.234,56
    return "R$ " + txt.replace(",", "X").replace(".", ",").replace("X", ".")


def _data(dt) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


class JanelaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Auditoria Fiscal - Comparador SPED x SEFAZ")
        self.resize(1100, 720)

        self._resultado: ResultadoComparacao | None = None
        self._empresa_nome = ""
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(self._montar_titulo())
        layout.addWidget(self._montar_selecao_arquivos())
        layout.addWidget(self._montar_barra_acoes())
        layout.addWidget(self._montar_resumo())
        layout.addWidget(self._montar_abas(), stretch=1)

        self._status = QLabel("Selecione o SPED e a relacao da SEFAZ para comparar.")
        self._status.setStyleSheet("color: #555;")
        layout.addWidget(self._status)

    # ------------------------------------------------------------------
    def _montar_titulo(self) -> QWidget:
        titulo = QLabel("Comparador SPED Fiscal x Relacao da SEFAZ")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        titulo.setFont(f)
        titulo.setStyleSheet("color: #1F4E78;")
        return titulo

    def _montar_selecao_arquivos(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("Arquivo SPED Fiscal (.txt):"), 0, 0)
        self._edit_sped = QLineEdit()
        self._edit_sped.setPlaceholderText("Selecione o arquivo do SPED enviado pelo cliente")
        grid.addWidget(self._edit_sped, 0, 1)
        btn_sped = QPushButton("Procurar...")
        btn_sped.clicked.connect(self._escolher_sped)
        grid.addWidget(btn_sped, 0, 2)

        grid.addWidget(QLabel("Relacao da SEFAZ (.xlsx/.csv):"), 1, 0)
        self._edit_sefaz = QLineEdit()
        self._edit_sefaz.setPlaceholderText("Planilha/relatorio de notas emitidas contra o CNPJ")
        grid.addWidget(self._edit_sefaz, 1, 1)
        btn_sefaz = QPushButton("Procurar...")
        btn_sefaz.clicked.connect(self._escolher_sefaz)
        grid.addWidget(btn_sefaz, 1, 2)

        self._chk_entradas = QCheckBox(
            "Considerar apenas documentos de entrada no SPED (recomendado)")
        self._chk_entradas.setChecked(True)
        grid.addWidget(self._chk_entradas, 2, 1)

        self._lbl_diag = QLabel("")
        self._lbl_diag.setStyleSheet("color: #666; font-size: 11px;")
        self._lbl_diag.setWordWrap(True)
        grid.addWidget(self._lbl_diag, 3, 1, 1, 2)

        grid.setColumnStretch(1, 1)
        return caixa

    def _montar_barra_acoes(self) -> QWidget:
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 0, 0, 0)
        self._btn_comparar = QPushButton("Comparar")
        self._btn_comparar.setMinimumHeight(34)
        self._btn_comparar.setStyleSheet(
            "QPushButton { background:#1F4E78; color:white; font-weight:bold;"
            " border-radius:4px; padding:6px 18px; }"
            " QPushButton:hover { background:#2E5F91; }"
            " QPushButton:disabled { background:#9DB3C8; }")
        self._btn_comparar.clicked.connect(self._comparar)
        h.addWidget(self._btn_comparar)

        self._btn_exportar = QPushButton("Exportar relatorio (.xlsx)")
        self._btn_exportar.setMinimumHeight(34)
        self._btn_exportar.setEnabled(False)
        self._btn_exportar.clicked.connect(self._exportar)
        h.addWidget(self._btn_exportar)
        h.addStretch(1)
        return caixa

    def _montar_resumo(self) -> QWidget:
        self._caixa_resumo = QFrame()
        self._caixa_resumo.setFrameShape(QFrame.StyledPanel)
        self._grid_resumo = QGridLayout(self._caixa_resumo)
        self._cartoes: dict[str, QLabel] = {}
        definicoes = [
            ("na_sefaz", "Notas na SEFAZ", "#1F4E78"),
            ("no_sped", "Escrituradas (SPED)", "#1F4E78"),
            ("conciliadas", "Conciliadas", "#2E7D32"),
            ("faltantes", "FALTANTES no SPED", "#C00000"),
            ("canceladas", "Canceladas escrit.", "#B7791F"),
            ("diverg", "Diverg. de valor", "#B7791F"),
        ]
        for col, (chave, rotulo, cor) in enumerate(definicoes):
            mini = QVBoxLayout()
            valor = QLabel("-")
            fv = QFont()
            fv.setPointSize(18)
            fv.setBold(True)
            valor.setFont(fv)
            valor.setStyleSheet(f"color: {cor};")
            valor.setAlignment(Qt.AlignCenter)
            rot = QLabel(rotulo)
            rot.setAlignment(Qt.AlignCenter)
            rot.setStyleSheet("color:#555; font-size:11px;")
            mini.addWidget(valor)
            mini.addWidget(rot)
            cont = QWidget()
            cont.setLayout(mini)
            self._grid_resumo.addWidget(cont, 0, col)
            self._cartoes[chave] = valor
        return self._caixa_resumo

    def _montar_abas(self) -> QWidget:
        self._abas = QTabWidget()
        self._tab_faltantes = self._nova_tabela(
            ["Chave de acesso", "Numero", "Serie", "CNPJ emitente",
             "Emitente", "Data", "Valor (SEFAZ)", "Situacao"])
        self._tab_canceladas = self._nova_tabela(
            ["Chave de acesso", "Numero", "Emitente", "Situacao na SEFAZ"])
        self._tab_diverg = self._nova_tabela(
            ["Chave de acesso", "Numero", "Emitente", "Valor SEFAZ",
             "Valor SPED", "Diferenca"])
        self._tab_so_sped = self._nova_tabela(
            ["Chave de acesso", "Numero", "Serie", "Fornecedor", "Data",
             "Valor (SPED)"])
        self._abas.addTab(self._tab_faltantes, "Faltantes no SPED")
        self._abas.addTab(self._tab_canceladas, "Canceladas escrituradas")
        self._abas.addTab(self._tab_diverg, "Divergencias de valor")
        self._abas.addTab(self._tab_so_sped, "Apenas no SPED")
        return self._abas

    def _nova_tabela(self, colunas: list[str]) -> QTableWidget:
        tab = QTableWidget(0, len(colunas))
        tab.setHorizontalHeaderLabels(colunas)
        tab.setEditTriggers(QTableWidget.NoEditTriggers)
        tab.setSelectionBehavior(QTableWidget.SelectRows)
        tab.setAlternatingRowColors(True)
        tab.verticalHeader().setVisible(False)
        tab.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        tab.horizontalHeader().setStretchLastSection(True)
        return tab

    # ------------------------------------------------------------------
    def _escolher_sped(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar SPED Fiscal", "",
            "Arquivos SPED (*.txt);;Todos os arquivos (*.*)")
        if caminho:
            self._edit_sped.setText(caminho)

    def _escolher_sefaz(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar relacao da SEFAZ", "",
            "Planilhas (*.xlsx *.xlsm *.xls *.csv *.txt);;Todos os arquivos (*.*)")
        if caminho:
            self._edit_sefaz.setText(caminho)

    def _comparar(self) -> None:
        caminho_sped = self._edit_sped.text().strip()
        caminho_sefaz = self._edit_sefaz.text().strip()
        if not os.path.isfile(caminho_sped):
            QMessageBox.warning(self, "Atencao", "Selecione um arquivo SPED valido.")
            return
        if not os.path.isfile(caminho_sefaz):
            QMessageBox.warning(self, "Atencao", "Selecione a relacao da SEFAZ.")
            return

        self._btn_comparar.setEnabled(False)
        self._btn_exportar.setEnabled(False)
        self._status.setText("Processando... lendo arquivos e comparando.")

        self._thread = QThread()
        self._worker = Worker(caminho_sped, caminho_sefaz,
                              self._chk_entradas.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.concluido.connect(self._ao_concluir)
        self._worker.erro.connect(self._ao_erro)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.erro.connect(self._thread.quit)
        self._thread.start()

    def _ao_erro(self, mensagem: str) -> None:
        self._btn_comparar.setEnabled(True)
        self._status.setText("Erro ao processar.")
        QMessageBox.critical(self, "Erro", f"Falha ao comparar:\n\n{mensagem}")

    def _ao_concluir(self, empresa_nome, resultado: ResultadoComparacao, diag: dict) -> None:
        self._btn_comparar.setEnabled(True)
        self._btn_exportar.setEnabled(True)
        self._resultado = resultado
        self._empresa_nome = empresa_nome or ""

        r = resultado.resumo()
        self._cartoes["na_sefaz"].setText(str(r["notas_na_sefaz"]))
        self._cartoes["no_sped"].setText(str(r["notas_no_sped"]))
        self._cartoes["conciliadas"].setText(str(r["conciliadas"]))
        self._cartoes["faltantes"].setText(str(r["faltantes_no_sped"]))
        self._cartoes["canceladas"].setText(str(r["canceladas_escrituradas"]))
        self._cartoes["diverg"].setText(str(r["divergencias_valor"]))

        self._preencher_faltantes(resultado)
        self._preencher_canceladas(resultado)
        self._preencher_divergencias(resultado)
        self._preencher_so_sped(resultado)

        self._abas.setTabText(0, f"Faltantes no SPED ({r['faltantes_no_sped']})")
        self._abas.setTabText(1, f"Canceladas escrituradas ({r['canceladas_escrituradas']})")
        self._abas.setTabText(2, f"Divergencias de valor ({r['divergencias_valor']})")
        self._abas.setTabText(3, f"Apenas no SPED ({r['apenas_no_sped']})")

        mapa = diag.get("mapa_colunas", {})
        self._lbl_diag.setText(
            "Leitura SEFAZ - colunas detectadas: "
            + ", ".join(f"{k}='{v}'" for k, v in mapa.items())
            + f"  |  {diag.get('registros_validos', 0)} notas lidas.")

        empresa = f" - {self._empresa_nome}" if self._empresa_nome else ""
        self._status.setText(
            f"Comparacao concluida{empresa}. "
            f"{r['faltantes_no_sped']} nota(s) na SEFAZ nao escriturada(s) no SPED.")

    # ------------------------------------------------------------------
    def _preencher_faltantes(self, res: ResultadoComparacao) -> None:
        tab = self._tab_faltantes
        tab.setRowCount(len(res.faltantes_no_sped))
        for i, reg in enumerate(res.faltantes_no_sped):
            valores = [reg.chave_normalizada, reg.numero, reg.serie,
                       reg.cnpj_emitente_da_chave, reg.emitente_nome,
                       _data(reg.dt_emissao), _moeda(reg.valor),
                       reg.situacao or "Autorizada"]
            self._preencher_linha(tab, i, valores, cor_fundo="#FDECEA")

    def _preencher_canceladas(self, res: ResultadoComparacao) -> None:
        tab = self._tab_canceladas
        tab.setRowCount(len(res.canceladas_escrituradas))
        for i, c in enumerate(res.canceladas_escrituradas):
            self._preencher_linha(tab, i, [c.chave, c.numero, c.emitente, c.situacao_sefaz])

    def _preencher_divergencias(self, res: ResultadoComparacao) -> None:
        tab = self._tab_diverg
        tab.setRowCount(len(res.divergencias_valor))
        for i, d in enumerate(res.divergencias_valor):
            self._preencher_linha(tab, i, [
                d.chave, d.numero, d.emitente,
                _moeda(d.valor_sefaz), _moeda(d.valor_sped), _moeda(d.diferenca)])

    def _preencher_so_sped(self, res: ResultadoComparacao) -> None:
        tab = self._tab_so_sped
        tab.setRowCount(len(res.apenas_no_sped))
        for i, nota in enumerate(res.apenas_no_sped):
            forn = nota.participante.nome if nota.participante else ""
            self._preencher_linha(tab, i, [
                nota.chave_normalizada, nota.numero, nota.serie, forn,
                _data(nota.dt_emissao), _moeda(nota.valor_documento)])

    def _preencher_linha(self, tab: QTableWidget, linha: int, valores: list[str],
                         cor_fundo: str | None = None) -> None:
        for col, valor in enumerate(valores):
            item = QTableWidgetItem(str(valor))
            if cor_fundo:
                item.setBackground(QColor(cor_fundo))
            tab.setItem(linha, col, item)

    # ------------------------------------------------------------------
    def _exportar(self) -> None:
        if self._resultado is None:
            return
        sugestao = "conferencia_sped_sefaz.xlsx"
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatorio", sugestao, "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        try:
            gerar_relatorio(self._resultado, caminho, nome_empresa=self._empresa_nome)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", f"Nao foi possivel salvar:\n{exc}")
            return
        self._status.setText(f"Relatorio salvo em: {caminho}")
        QMessageBox.information(self, "Concluido", f"Relatorio gerado:\n{caminho}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
