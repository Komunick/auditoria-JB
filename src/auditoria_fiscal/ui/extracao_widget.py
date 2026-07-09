"""Aba de Extracao de Itens para auditoria tributaria (Item 4)."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.filtro_sped import MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS
from ..core.sped_parser import ler_sped
from ..core.nfe_xml import ler_pasta_xml
from ..ferramentas.extracao_itens import (
    CAMPOS, TITULOS, exportar_itens_excel, extrair_itens, valor_para_texto,
)

LIMITE_PREVIA = 2000   # linhas exibidas na previa (a exportacao leva tudo)

_OPERACOES = {"Todas": None, "Apenas entradas": "0", "Apenas saidas": "1"}


class WorkerExtracao(QObject):
    concluido = Signal(object, object)   # linhas, contexto
    erro = Signal(str)

    def __init__(self, fonte: str, caminho: str, operacao):
        super().__init__()
        self.fonte = fonte
        self.caminho = caminho
        self.operacao = operacao

    def executar(self) -> None:
        try:
            if self.fonte == "sped":
                doc = ler_sped(self.caminho)
                notas = doc.notas
                contexto = doc.empresa.nome or "SPED"
            else:
                notas = ler_pasta_xml(self.caminho)
                contexto = f"{len(notas)} XML(s)"
            linhas = extrair_itens(notas, somente_operacao=self.operacao)
            self.concluido.emit(linhas, contexto)
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


class ExtracaoWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._linhas: list[dict] = []
        self._contexto = ""
        self._filtro_entradas_sped = False   # filtro usado na ultima extracao
        self._thread: QThread | None = None
        self._worker: WorkerExtracao | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self._montar_selecao())
        layout.addWidget(self._montar_acoes())
        layout.addWidget(self._montar_tabela(), stretch=1)

        self._status = QLabel("Escolha a fonte (SPED ou pasta de XMLs) e extraia os itens.")
        self._status.setStyleSheet("color:#555;")
        layout.addWidget(self._status)

    def _montar_selecao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("Fonte:"), 0, 0)
        self._combo_fonte = QComboBox()
        self._combo_fonte.addItems(["SPED Fiscal (.txt)", "Pasta de XMLs de NF-e"])
        self._combo_fonte.currentIndexChanged.connect(lambda _: self._edit_caminho.clear())
        grid.addWidget(self._combo_fonte, 0, 1)

        grid.addWidget(QLabel("Caminho:"), 1, 0)
        self._edit_caminho = QLineEdit()
        self._edit_caminho.setPlaceholderText("Arquivo SPED ou pasta contendo os XMLs")
        grid.addWidget(self._edit_caminho, 1, 1)
        btn = QPushButton("Procurar...")
        btn.clicked.connect(self._procurar)
        grid.addWidget(btn, 1, 2)

        grid.addWidget(QLabel("Operacao:"), 2, 0)
        self._combo_oper = QComboBox()
        self._combo_oper.addItems(list(_OPERACOES.keys()))
        self._combo_oper.setToolTip(
            '"Apenas entradas" com a fonte SPED = considerar apenas documentos\n'
            "de entrada no SPED (IND_OPER = 0). Saidas e demais operacoes\n"
            'ficam de fora. "Todas" mantem o comportamento padrao.')
        grid.addWidget(self._combo_oper, 2, 1)

        grid.setColumnStretch(1, 1)
        return caixa

    def _montar_acoes(self) -> QWidget:
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 0, 0, 0)
        self._btn_extrair = QPushButton("Extrair itens")
        self._btn_extrair.setMinimumHeight(34)
        self._btn_extrair.setStyleSheet(
            "QPushButton { background:#1F4E78; color:white; font-weight:bold;"
            " border-radius:4px; padding:6px 18px; }"
            " QPushButton:hover { background:#2E5F91; }"
            " QPushButton:disabled { background:#9DB3C8; }")
        self._btn_extrair.clicked.connect(self._extrair)
        h.addWidget(self._btn_extrair)

        self._btn_exportar = QPushButton("Exportar planilha (.xlsx)")
        self._btn_exportar.setMinimumHeight(34)
        self._btn_exportar.setEnabled(False)
        self._btn_exportar.clicked.connect(self._exportar)
        h.addWidget(self._btn_exportar)
        h.addStretch(1)
        return caixa

    def _montar_tabela(self) -> QWidget:
        self._tabela = QTableWidget(0, len(TITULOS))
        self._tabela.setHorizontalHeaderLabels(TITULOS)
        self._tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        return self._tabela

    # ------------------------------------------------------------------
    def _procurar(self) -> None:
        if self._combo_fonte.currentIndex() == 0:
            caminho, _ = QFileDialog.getOpenFileName(
                self, "Selecionar SPED Fiscal", "",
                "Arquivos SPED (*.txt);;Todos os arquivos (*.*)")
        else:
            caminho = QFileDialog.getExistingDirectory(
                self, "Selecionar pasta com XMLs de NF-e")
        if caminho:
            self._edit_caminho.setText(caminho)

    def _extrair(self) -> None:
        caminho = self._edit_caminho.text().strip()
        fonte = "sped" if self._combo_fonte.currentIndex() == 0 else "xml"
        if fonte == "sped" and not os.path.isfile(caminho):
            QMessageBox.warning(self, "Atencao", "Selecione um arquivo SPED valido.")
            return
        if fonte == "xml" and not os.path.isdir(caminho):
            QMessageBox.warning(self, "Atencao", "Selecione uma pasta de XMLs valida.")
            return

        operacao = _OPERACOES[self._combo_oper.currentText()]
        # Registra se esta extracao usa o filtro de entradas do SPED, para o
        # status, a validacao de vazio e a indicacao na planilha exportada.
        self._filtro_entradas_sped = fonte == "sped" and operacao == "0"
        self._btn_extrair.setEnabled(False)
        self._btn_exportar.setEnabled(False)
        self._status.setText("Extraindo itens...")

        self._thread = QThread()
        self._worker = WorkerExtracao(fonte, caminho, operacao)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.concluido.connect(self._ao_concluir)
        self._worker.erro.connect(self._ao_erro)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.erro.connect(self._thread.quit)
        self._thread.start()

    def _ao_erro(self, mensagem: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._status.setText("Erro ao extrair.")
        QMessageBox.critical(self, "Erro", f"Falha ao extrair itens:\n\n{mensagem}")

    def _ao_concluir(self, linhas: list[dict], contexto: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._linhas = linhas
        self._contexto = contexto
        self._btn_exportar.setEnabled(bool(linhas))

        total = len(linhas)
        mostradas = min(total, LIMITE_PREVIA)
        self._tabela.setRowCount(mostradas)
        for i in range(mostradas):
            linha = linhas[i]
            for col, (chave, _, tipo) in enumerate(CAMPOS):
                texto = valor_para_texto(chave, tipo, linha.get(chave))
                self._tabela.setItem(i, col, QTableWidgetItem(texto))
        self._tabela.resizeColumnsToContents()

        aviso = "" if total <= LIMITE_PREVIA else \
            f" (previa: {LIMITE_PREVIA} de {total} — exportacao inclui tudo)"
        filtro = f" {ROTULO_FILTRO_ENTRADAS}." if self._filtro_entradas_sped else ""
        self._status.setText(f"{total} item(ns) extraido(s) de {contexto}.{aviso}"
                             + filtro)

        # O filtro de entradas nao achou nenhum documento: avisa em vez de
        # deixar a previa vazia sem explicacao.
        if self._filtro_entradas_sped and total == 0:
            QMessageBox.information(self, "Sem documentos de entrada",
                                    MSG_SEM_ENTRADAS)

    def _exportar(self) -> None:
        if not self._linhas:
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar planilha de itens", "itens_auditoria.xlsx",
            "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        filtro = ROTULO_FILTRO_ENTRADAS if self._filtro_entradas_sped else ""
        try:
            exportar_itens_excel(self._linhas, caminho, filtro_aplicado=filtro)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", f"Nao foi possivel salvar:\n{exc}")
            return
        self._status.setText(f"Planilha salva em: {caminho}")
        QMessageBox.information(self, "Concluido",
                               f"Planilha de {len(self._linhas)} itens gerada:\n{caminho}")
