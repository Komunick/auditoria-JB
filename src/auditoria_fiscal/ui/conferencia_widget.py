"""Aba do Livro Digital de Conferencia Fiscal (Item 3)."""

from __future__ import annotations

import os
from decimal import Decimal

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.filtro_sped import (
    MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS, TEXTO_OPCAO_ENTRADAS,
    filtrar_entradas,
)
from ..core.modelos import NotaFiscal
from ..core.nfe_xml import ler_pasta_xml
from ..core.sped_parser import ler_sped
from ..ferramentas.conferencia_store import ConferenciaStore
from ..ferramentas.danfe import abrir_danfe

# Colunas da tabela
COL_CONF, COL_NUM, COL_SERIE, COL_DATA, COL_FORN, COL_CNPJ = 0, 1, 2, 3, 4, 5
COL_VCONT, COL_BASE, COL_ICMS, COL_CFOP, COL_CST, COL_ALIQ = 6, 7, 8, 9, 10, 11
COL_OBS, COL_DATACONF = 12, 13
CABECALHO = ["Conferida", "Numero", "Serie", "Data", "Fornecedor", "CNPJ",
             "Valor contabil", "Base ICMS", "Valor ICMS", "CFOP", "CST",
             "Aliquota", "Observacao", "Data conf."]

_VERDE = "#E4F3E4"


def _moeda(valor) -> str:
    txt = f"{float(valor or 0):,.2f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def _data(dt) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


def _distintos_texto(itens, attr) -> str:
    vistos: list[str] = []
    for it in itens:
        v = str(getattr(it, attr)).strip()
        if v and v not in vistos:
            vistos.append(v)
    return ", ".join(vistos)


def _aliquotas(itens) -> str:
    vistos: list[str] = []
    for it in itens:
        if it.aliq_icms and it.aliq_icms != Decimal("0"):
            txt = _moeda(it.aliq_icms)
            if txt not in vistos:
                vistos.append(txt)
    return ", ".join(vistos)


class WorkerCarga(QObject):
    concluido = Signal(object, object)   # notas, contexto
    erro = Signal(str)

    def __init__(self, fonte: str, caminho: str, apenas_entradas: bool = False):
        super().__init__()
        self.fonte = fonte
        self.caminho = caminho
        self.apenas_entradas = apenas_entradas

    def executar(self) -> None:
        try:
            if self.fonte == "xml":
                notas = ler_pasta_xml(self.caminho)
                contexto = f"{len(notas)} XML(s)"
            else:
                doc = ler_sped(self.caminho)
                notas = doc.notas
                if self.apenas_entradas:
                    notas = filtrar_entradas(notas)
                contexto = doc.empresa.nome or "SPED"
            # So notas com chave de 44 digitos (rastreaveis por chave)
            notas = [n for n in notas if len(n.chave_normalizada) == 44]
            self.concluido.emit(notas, contexto)
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


class ConferenciaWidget(QWidget):
    def __init__(self, store: ConferenciaStore | None = None) -> None:
        super().__init__()
        self._store = store or ConferenciaStore()
        self._notas: list[NotaFiscal] = []
        self._chaves: list[str] = []
        self._nota_por_chave: dict[str, NotaFiscal] = {}
        self._carregando = False
        self._filtro_entradas = False   # filtro usado na ultima carga
        self._thread: QThread | None = None
        self._worker: WorkerCarga | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self._montar_selecao())
        layout.addWidget(self._montar_acoes())
        layout.addWidget(self._montar_tabela(), stretch=1)

        self._status = QLabel("Importe uma pasta de XMLs (habilita o DANFE) ou um SPED.")
        self._status.setStyleSheet("color:#555;")
        layout.addWidget(self._status)

    def _montar_selecao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("Fonte:"), 0, 0)
        self._combo_fonte = QComboBox()
        self._combo_fonte.addItems(["Pasta de XMLs de NF-e", "SPED Fiscal (.txt)"])
        self._combo_fonte.currentIndexChanged.connect(lambda _: self._edit_caminho.clear())
        grid.addWidget(self._combo_fonte, 0, 1)

        grid.addWidget(QLabel("Caminho:"), 1, 0)
        self._edit_caminho = QLineEdit()
        self._edit_caminho.setPlaceholderText("Pasta com XMLs ou arquivo SPED")
        grid.addWidget(self._edit_caminho, 1, 1)
        btn = QPushButton("Procurar...")
        btn.clicked.connect(self._procurar)
        grid.addWidget(btn, 1, 2)

        # So faz sentido para a fonte SPED; fica desabilitada para XMLs.
        self._chk_entradas = QCheckBox(TEXTO_OPCAO_ENTRADAS)
        self._chk_entradas.setChecked(False)  # padrao: todas as operacoes
        self._chk_entradas.setEnabled(False)  # fonte inicial e a pasta de XMLs
        self._chk_entradas.setToolTip(
            "Marcado: somente as notas de entrada do SPED sao carregadas\n"
            "(IND_OPER = 0; sem IND_OPER, decide pelo CFOP dos itens).\n"
            "Desmarcado: comportamento padrao, todas as notas do arquivo.")
        self._combo_fonte.currentIndexChanged.connect(
            lambda i: self._chk_entradas.setEnabled(i == 1))
        grid.addWidget(self._chk_entradas, 2, 1)

        grid.setColumnStretch(1, 1)
        return caixa

    def _montar_acoes(self) -> QWidget:
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 0, 0, 0)

        self._btn_carregar = QPushButton("Carregar notas")
        self._btn_carregar.setMinimumHeight(32)
        self._btn_carregar.setStyleSheet(
            "QPushButton { background:#1F4E78; color:white; font-weight:bold;"
            " border-radius:4px; padding:6px 16px; }"
            " QPushButton:hover { background:#2E5F91; }"
            " QPushButton:disabled { background:#9DB3C8; }")
        self._btn_carregar.clicked.connect(self._carregar)
        h.addWidget(self._btn_carregar)

        self._btn_danfe = QPushButton("Abrir DANFE da nota selecionada")
        self._btn_danfe.setMinimumHeight(32)
        self._btn_danfe.clicked.connect(self._abrir_danfe)
        h.addWidget(self._btn_danfe)

        h.addWidget(QLabel("Filtro:"))
        self._combo_filtro = QComboBox()
        self._combo_filtro.addItems(["Todas", "Pendentes", "Conferidas"])
        self._combo_filtro.currentIndexChanged.connect(lambda _: self._aplicar_filtro())
        h.addWidget(self._combo_filtro)

        h.addStretch(1)
        self._lbl_progresso = QLabel("")
        self._lbl_progresso.setStyleSheet("font-weight:bold; color:#1F4E78;")
        h.addWidget(self._lbl_progresso)
        return caixa

    def _montar_tabela(self) -> QWidget:
        self._tabela = QTableWidget(0, len(CABECALHO))
        self._tabela.setHorizontalHeaderLabels(CABECALHO)
        self._tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SingleSelection)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._tabela.itemChanged.connect(self._ao_editar)
        self._tabela.itemDoubleClicked.connect(lambda _: self._abrir_danfe())
        return self._tabela

    # ------------------------------------------------------------------
    def _procurar(self) -> None:
        if self._combo_fonte.currentIndex() == 0:
            caminho = QFileDialog.getExistingDirectory(self, "Pasta com XMLs de NF-e")
        else:
            caminho, _ = QFileDialog.getOpenFileName(
                self, "Selecionar SPED", "", "Arquivos SPED (*.txt);;Todos (*.*)")
        if caminho:
            self._edit_caminho.setText(caminho)

    def _carregar(self) -> None:
        caminho = self._edit_caminho.text().strip()
        fonte = "xml" if self._combo_fonte.currentIndex() == 0 else "sped"
        if fonte == "xml" and not os.path.isdir(caminho):
            QMessageBox.warning(self, "Atencao", "Selecione uma pasta de XMLs valida.")
            return
        if fonte == "sped" and not os.path.isfile(caminho):
            QMessageBox.warning(self, "Atencao", "Selecione um arquivo SPED valido.")
            return

        self._btn_carregar.setEnabled(False)
        self._status.setText("Carregando notas...")
        self._filtro_entradas = fonte == "sped" and self._chk_entradas.isChecked()
        self._thread = QThread()
        self._worker = WorkerCarga(fonte, caminho, self._filtro_entradas)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.concluido.connect(self._ao_carregar)
        self._worker.erro.connect(self._ao_erro)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.erro.connect(self._thread.quit)
        self._thread.start()

    def _ao_erro(self, mensagem: str) -> None:
        self._btn_carregar.setEnabled(True)
        self._status.setText("Erro ao carregar.")
        QMessageBox.critical(self, "Erro", f"Falha ao carregar:\n\n{mensagem}")

    def _ao_carregar(self, notas, contexto) -> None:
        self._btn_carregar.setEnabled(True)
        self._notas = notas
        self._nota_por_chave = {n.chave_normalizada: n for n in notas}
        self._chaves = [n.chave_normalizada for n in notas]
        estados = self._store.carregar()

        self._carregando = True
        self._tabela.setRowCount(len(notas))
        for i, nota in enumerate(notas):
            estado = estados.get(nota.chave_normalizada)
            conferida = estado.conferida if estado else False
            obs = estado.observacao if estado else ""
            data_conf = estado.data_conferencia if estado else ""
            forn = nota.participante.nome if nota.participante else ""

            self._por_texto(i, COL_NUM, nota.numero)
            self._por_texto(i, COL_SERIE, nota.serie)
            self._por_texto(i, COL_DATA, _data(nota.dt_emissao))
            self._por_texto(i, COL_FORN, forn)
            self._por_texto(i, COL_CNPJ, nota.cnpj_emitente)
            self._por_texto(i, COL_VCONT, _moeda(nota.valor_documento))
            self._por_texto(i, COL_BASE, _moeda(nota.vl_bc_icms))
            self._por_texto(i, COL_ICMS, _moeda(nota.vl_icms))
            self._por_texto(i, COL_CFOP, _distintos_texto(nota.itens, "cfop"))
            self._por_texto(i, COL_CST, _distintos_texto(nota.itens, "cst_icms"))
            self._por_texto(i, COL_ALIQ, _aliquotas(nota.itens))
            self._por_texto(i, COL_DATACONF, data_conf)

            # Conferida (checkbox)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if conferida else Qt.Unchecked)
            self._tabela.setItem(i, COL_CONF, chk)

            # Observacao (editavel)
            obs_item = QTableWidgetItem(obs)
            obs_item.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self._tabela.setItem(i, COL_OBS, obs_item)

            self._estilo_linha(i, conferida)
        self._carregando = False

        self._tabela.resizeColumnsToContents()
        self._tabela.setColumnWidth(COL_OBS, 220)
        self._atualizar_progresso()
        self._aplicar_filtro()
        sem_xml = sum(1 for n in notas if not n.xml_path)
        aviso = "" if sem_xml == 0 else f" ({sem_xml} sem XML — DANFE indisponivel nessas)"
        filtro = f" {ROTULO_FILTRO_ENTRADAS}." if self._filtro_entradas else ""
        self._status.setText(f"{len(notas)} nota(s) de {contexto}.{aviso}" + filtro)

        # O filtro de entradas nao achou nenhum documento: avisa em vez de
        # deixar a tabela vazia sem explicacao.
        if self._filtro_entradas and not notas:
            QMessageBox.information(self, "Sem documentos de entrada",
                                    MSG_SEM_ENTRADAS)

    def _por_texto(self, linha, col, texto) -> None:
        item = QTableWidgetItem(str(texto))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # somente leitura
        self._tabela.setItem(linha, col, item)

    def _estilo_linha(self, linha, conferida) -> None:
        cor = QColor(_VERDE) if conferida else QColor(Qt.white)
        for col in range(len(CABECALHO)):
            item = self._tabela.item(linha, col)
            if item is not None and col != COL_CONF:
                item.setBackground(cor)

    # ------------------------------------------------------------------
    def _ao_editar(self, item: QTableWidgetItem) -> None:
        if self._carregando:
            return
        col = item.column()
        if col not in (COL_CONF, COL_OBS):
            return
        linha = item.row()
        if linha >= len(self._chaves):
            return
        chave = self._chaves[linha]
        conf_item = self._tabela.item(linha, COL_CONF)
        obs_item = self._tabela.item(linha, COL_OBS)
        conferida = conf_item is not None and conf_item.checkState() == Qt.Checked
        obs = obs_item.text() if obs_item else ""

        estado = self._store.salvar(chave, conferida, obs)

        self._carregando = True
        data_item = self._tabela.item(linha, COL_DATACONF)
        if data_item is not None:
            data_item.setText(estado.data_conferencia)
        self._estilo_linha(linha, conferida)
        self._carregando = False

        self._atualizar_progresso()
        if col == COL_CONF:
            self._aplicar_filtro()

    def _atualizar_progresso(self) -> None:
        total = len(self._chaves)
        conferidas = sum(
            1 for i in range(total)
            if self._tabela.item(i, COL_CONF)
            and self._tabela.item(i, COL_CONF).checkState() == Qt.Checked)
        self._lbl_progresso.setText(f"{conferidas} de {total} conferidas")

    def _aplicar_filtro(self) -> None:
        filtro = self._combo_filtro.currentText()
        for i in range(len(self._chaves)):
            conf_item = self._tabela.item(i, COL_CONF)
            conferida = conf_item is not None and conf_item.checkState() == Qt.Checked
            if filtro == "Pendentes":
                mostrar = not conferida
            elif filtro == "Conferidas":
                mostrar = conferida
            else:
                mostrar = True
            self._tabela.setRowHidden(i, not mostrar)

    def _abrir_danfe(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._chaves):
            QMessageBox.information(self, "DANFE", "Selecione uma nota na tabela.")
            return
        nota = self._nota_por_chave.get(self._chaves[linha])
        if nota is None or not nota.xml_path or not os.path.isfile(nota.xml_path):
            QMessageBox.information(
                self, "DANFE indisponivel",
                "Esta nota nao tem XML associado.\n\nPara gerar o DANFE, carregue "
                "as notas a partir de uma pasta de XMLs de NF-e.")
            return
        self._status.setText("Gerando DANFE...")
        try:
            abrir_danfe(nota.xml_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro",
                                 f"Nao foi possivel gerar o DANFE:\n\n{exc}")
            self._status.setText("Erro ao gerar DANFE.")
            return
        self._status.setText(f"DANFE aberto (NF {nota.numero}).")
