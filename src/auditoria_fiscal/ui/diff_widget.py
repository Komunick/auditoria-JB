"""Aba de comparacao entre duas versoes de SPED (Item 2)."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.filtro_sped import (
    MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS, TEXTO_OPCAO_ENTRADAS,
)
from ..core.sped_parser import ler_sped
from ..ferramentas.comparador_sped_sped import ResultadoDiffSped, comparar_speds
from ..ferramentas.relatorio_diff_excel import gerar_relatorio_diff

LIMITE_PREVIA = 5000
ROTULO_A = "A (contabilidade)"
ROTULO_B = "B (cliente)"


def _moeda(valor) -> str:
    txt = f"{float(valor or 0):,.2f}"
    return "R$ " + txt.replace(",", "X").replace(".", ",").replace("X", ".")


class WorkerDiff(QObject):
    concluido = Signal(object)
    erro = Signal(str)

    def __init__(self, caminho_a, caminho_b, apenas_entradas=False):
        super().__init__()
        self.caminho_a = caminho_a
        self.caminho_b = caminho_b
        self.apenas_entradas = apenas_entradas

    def executar(self) -> None:
        try:
            doc_a = ler_sped(self.caminho_a)
            doc_b = ler_sped(self.caminho_b)
            res = comparar_speds(doc_a, doc_b, ROTULO_A, ROTULO_B,
                                 apenas_entradas=self.apenas_entradas)
            self.concluido.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


class DiffSpedWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._resultado: ResultadoDiffSped | None = None
        self._thread: QThread | None = None
        self._worker: WorkerDiff | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self._montar_selecao())
        layout.addWidget(self._montar_acoes())
        layout.addWidget(self._montar_resumo())
        layout.addWidget(self._montar_abas(), stretch=1)

        self._status = QLabel("Selecione os dois SPEDs (ex.: contabilidade x cliente).")
        self._status.setStyleSheet("color:#555;")
        layout.addWidget(self._status)

    def _montar_selecao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("SPED A - contabilidade (corrigido):"), 0, 0)
        self._edit_a = QLineEdit()
        self._edit_a.setPlaceholderText("Arquivo de referencia")
        grid.addWidget(self._edit_a, 0, 1)
        ba = QPushButton("Procurar...")
        ba.clicked.connect(lambda: self._escolher(self._edit_a))
        grid.addWidget(ba, 0, 2)

        grid.addWidget(QLabel("SPED B - cliente (sistema):"), 1, 0)
        self._edit_b = QLineEdit()
        self._edit_b.setPlaceholderText("Arquivo gerado pelo cliente")
        grid.addWidget(self._edit_b, 1, 1)
        bb = QPushButton("Procurar...")
        bb.clicked.connect(lambda: self._escolher(self._edit_b))
        grid.addWidget(bb, 1, 2)

        self._chk_entradas = QCheckBox(TEXTO_OPCAO_ENTRADAS)
        self._chk_entradas.setChecked(False)  # padrao: todas as operacoes
        self._chk_entradas.setToolTip(
            "Marcado: somente as notas de entrada dos dois SPEDs entram na\n"
            "comparacao (IND_OPER = 0; sem IND_OPER, decide pelo CFOP dos itens).\n"
            "Desmarcado: comportamento padrao, todas as operacoes.")
        grid.addWidget(self._chk_entradas, 2, 1)

        grid.setColumnStretch(1, 1)
        return caixa

    def _montar_acoes(self) -> QWidget:
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
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)
        self._cartoes: dict[str, QLabel] = {}
        definicoes = [
            ("total_a", "Notas em A", "#1F4E78"),
            ("total_b", "Notas em B", "#1F4E78"),
            ("iguais", "Identicas", "#2E7D32"),
            ("divergentes", "DIVERGENTES", "#C00000"),
            ("apenas_em_a", "So em A", "#B7791F"),
            ("apenas_em_b", "So em B", "#B7791F"),
        ]
        for col, (chave, rotulo, cor) in enumerate(definicoes):
            mini = QVBoxLayout()
            valor = QLabel("-")
            fv = QFont()
            fv.setPointSize(18)
            fv.setBold(True)
            valor.setFont(fv)
            valor.setStyleSheet(f"color:{cor};")
            valor.setAlignment(Qt.AlignCenter)
            rot = QLabel(rotulo)
            rot.setAlignment(Qt.AlignCenter)
            rot.setStyleSheet("color:#555; font-size:11px;")
            mini.addWidget(valor)
            mini.addWidget(rot)
            cont = QWidget()
            cont.setLayout(mini)
            grid.addWidget(cont, 0, col)
            self._cartoes[chave] = valor
        return caixa

    def _montar_abas(self) -> QWidget:
        self._abas = QTabWidget()
        self._tab_diverg = QTableWidget(0, 8)
        self._tab_diverg.setHorizontalHeaderLabels(
            ["Chave de acesso", "Numero", "Fornecedor", "Nivel", "Item",
             "Campo", "Valor A", "Valor B"])
        self._preparar_tabela(self._tab_diverg)
        self._tab_so_a = self._nova_tabela_notas()
        self._tab_so_b = self._nova_tabela_notas()
        self._abas.addTab(self._tab_diverg, "Divergencias (campo a campo)")
        self._abas.addTab(self._tab_so_a, "So em A")
        self._abas.addTab(self._tab_so_b, "So em B")
        return self._abas

    def _nova_tabela_notas(self) -> QTableWidget:
        tab = QTableWidget(0, 5)
        tab.setHorizontalHeaderLabels(
            ["Chave de acesso", "Numero", "Serie", "Fornecedor", "Valor"])
        self._preparar_tabela(tab)
        return tab

    def _preparar_tabela(self, tab: QTableWidget) -> None:
        tab.setEditTriggers(QTableWidget.NoEditTriggers)
        tab.setSelectionBehavior(QTableWidget.SelectRows)
        tab.setAlternatingRowColors(True)
        tab.verticalHeader().setVisible(False)
        tab.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        tab.horizontalHeader().setStretchLastSection(True)

    # ------------------------------------------------------------------
    def _escolher(self, edit: QLineEdit) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar SPED", "",
            "Arquivos SPED (*.txt);;Todos os arquivos (*.*)")
        if caminho:
            edit.setText(caminho)

    def _comparar(self) -> None:
        ca, cb = self._edit_a.text().strip(), self._edit_b.text().strip()
        if not os.path.isfile(ca) or not os.path.isfile(cb):
            QMessageBox.warning(self, "Atencao", "Selecione os dois arquivos SPED.")
            return
        if os.path.abspath(ca) == os.path.abspath(cb):
            QMessageBox.warning(self, "Atencao", "Os dois arquivos sao o mesmo.")
            return

        self._btn_comparar.setEnabled(False)
        self._btn_exportar.setEnabled(False)
        self._status.setText("Processando... lendo e comparando os dois SPEDs.")

        self._thread = QThread()
        self._worker = WorkerDiff(ca, cb, self._chk_entradas.isChecked())
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

    def _ao_concluir(self, resultado: ResultadoDiffSped) -> None:
        self._btn_comparar.setEnabled(True)
        self._btn_exportar.setEnabled(True)
        self._resultado = resultado
        r = resultado.resumo()
        for chave in ("total_a", "total_b", "iguais", "divergentes",
                      "apenas_em_a", "apenas_em_b"):
            self._cartoes[chave].setText(str(r[chave]))

        self._preencher_divergencias(resultado)
        self._preencher_notas(self._tab_so_a, resultado.apenas_em_a)
        self._preencher_notas(self._tab_so_b, resultado.apenas_em_b)

        self._abas.setTabText(0, f"Divergencias ({r['total_diferencas']} campos)")
        self._abas.setTabText(1, f"So em A ({r['apenas_em_a']})")
        self._abas.setTabText(2, f"So em B ({r['apenas_em_b']})")

        filtro = f" {ROTULO_FILTRO_ENTRADAS}." if resultado.apenas_entradas else ""
        self._status.setText(
            f"Comparacao concluida: {r['divergentes']} nota(s) divergente(s), "
            f"{r['total_diferencas']} campo(s) com diferenca." + filtro)

        # O filtro de entradas nao achou nenhum documento nos dois arquivos:
        # avisa em vez de deixar o resultado vazio sem explicacao.
        if resultado.apenas_entradas and r["total_a"] == 0 and r["total_b"] == 0:
            QMessageBox.information(self, "Sem documentos de entrada",
                                    MSG_SEM_ENTRADAS)

    def _preencher_divergencias(self, res: ResultadoDiffSped) -> None:
        tab = self._tab_diverg
        linhas = [(nota, d) for nota in res.divergentes for d in nota.diferencas]
        mostradas = min(len(linhas), LIMITE_PREVIA)
        tab.setRowCount(mostradas)
        for i in range(mostradas):
            nota, d = linhas[i]
            valores = [nota.chave, nota.numero, nota.fornecedor,
                       "Nota" if d.nivel == "nota" else "Item",
                       d.num_item, d.campo, d.valor_a, d.valor_b]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor))
                if col >= 5:
                    item.setBackground(QColor("#FDECEA"))
                tab.setItem(i, col, item)
        if len(linhas) > LIMITE_PREVIA:
            self._status.setText(
                f"Exibindo {LIMITE_PREVIA} de {len(linhas)} diferencas "
                f"(exportacao inclui tudo).")

    def _preencher_notas(self, tab: QTableWidget, notas) -> None:
        tab.setRowCount(len(notas))
        for i, nota in enumerate(notas):
            forn = nota.participante.nome if nota.participante else ""
            valores = [nota.chave_normalizada, nota.numero, nota.serie, forn,
                       _moeda(nota.valor_documento)]
            for col, valor in enumerate(valores):
                tab.setItem(i, col, QTableWidgetItem(str(valor)))

    def _exportar(self) -> None:
        if self._resultado is None:
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatorio", "comparacao_speds.xlsx",
            "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        try:
            gerar_relatorio_diff(self._resultado, caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", f"Nao foi possivel salvar:\n{exc}")
            return
        self._status.setText(f"Relatorio salvo em: {caminho}")
        QMessageBox.information(self, "Concluido", f"Relatorio gerado:\n{caminho}")
