"""Aba do Livro Digital de Conferencia Fiscal (Item 3)."""

from __future__ import annotations

import getpass
import os
from decimal import Decimal

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.composicao_fiscal import GRUPO_TOTAL, chave_grupo, compor_nota
from ..core.correcoes import (
    CAMPOS_CORRIGIVEIS, TIPO_AUTOMATICA, TIPO_MANUAL, aplicar_correcoes,
    normalizar_valor, validar_correcao,
)
from ..core.filtro_sped import (
    MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS, TEXTO_OPCAO_ENTRADAS,
    filtrar_entradas,
)
from ..core.modelos import NotaFiscal
from ..core.nfe_xml import associar_xmls, ler_pasta_xml
from ..core.sped_parser import ler_sped
from ..core.utils import formatar_cfop, formatar_moeda, formatar_percentual
from ..ferramentas.conferencia_store import ConferenciaStore
from ..ferramentas.danfe import abrir_arquivo, abrir_danfe
from ..ferramentas.livro_fiscal import gerar_livro_fiscal
from ..ferramentas.livro_inconsistencias import (
    gerar_livro_inconsistencias, notas_inconsistentes,
)
from ..ferramentas.sped_corrigido import gerar_sped_corrigido
from . import tema

# Colunas da tabela
COL_CONF, COL_NUM, COL_SERIE, COL_DATA, COL_FORN, COL_CNPJ, COL_UF = \
    0, 1, 2, 3, 4, 5, 6
COL_VCONT, COL_BASE, COL_ICMS, COL_CFOP, COL_CST, COL_ALIQ = \
    7, 8, 9, 10, 11, 12
COL_OBS, COL_DATACONF = 13, 14
CABECALHO = ["Conferida", "Numero", "Serie", "Data", "Fornecedor", "CNPJ",
             "UF", "Valor contabil", "Base ICMS", "Valor ICMS", "CFOP", "CST",
             "Aliquota", "Observacao", "Data conf."]

# Colunas cuja exibicao muda quando ha correcao aplicada.
_COLS_FISCAIS = (COL_VCONT, COL_BASE, COL_ICMS, COL_CFOP, COL_CST, COL_ALIQ)

_VERDE = "#E4F3E4"


def _moeda(valor) -> str:
    return formatar_moeda(valor)


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
            txt = formatar_percentual(it.aliq_icms)
            if txt not in vistos:
                vistos.append(txt)
    return ", ".join(vistos)


class WorkerCarga(QObject):
    concluido = Signal(object, object)   # notas, contexto
    erro = Signal(str)

    def __init__(self, fonte: str, caminho: str, apenas_entradas: bool = False,
                 pasta_xml: str = ""):
        super().__init__()
        self.fonte = fonte
        self.caminho = caminho
        self.apenas_entradas = apenas_entradas
        self.pasta_xml = pasta_xml

    def executar(self) -> None:
        try:
            if self.fonte == "xml":
                # Aceita varias pastas separadas por ";" (ex.: meses de um
                # ano); cada pasta ja e lida recursivamente. Nota repetida
                # em mais de uma pasta entra uma unica vez (pela chave).
                pastas = [p.strip() for p in self.caminho.split(";")
                          if p.strip()]
                notas = []
                vistas: set[str] = set()
                for pasta in pastas:
                    for nota in ler_pasta_xml(pasta):
                        chave = nota.chave_normalizada
                        if len(chave) == 44:
                            if chave in vistas:
                                continue
                            vistas.add(chave)
                        notas.append(nota)
                extra = (f" em {len(pastas)} pastas" if len(pastas) > 1
                         else "")
                contexto = f"{len(notas)} XML(s){extra}"
            else:
                doc = ler_sped(self.caminho)
                notas = doc.notas
                if self.apenas_entradas:
                    notas = filtrar_entradas(notas)
                contexto = doc.empresa.nome or "SPED"
            # So notas com chave de 44 digitos (rastreaveis por chave)
            notas = [n for n in notas if len(n.chave_normalizada) == 44]
            # Fonte SPED com pasta de XMLs: associa pela chave p/ habilitar DANFE
            if self.fonte == "sped" and self.pasta_xml:
                associar_xmls(notas, self.pasta_xml)
            self.concluido.emit(notas, contexto)
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


class DialogoCorrecao(QDialog):
    """Correcao manual de um campo fiscal (CFOP, CST ou aliquota).

    O valor original vem dos proprios dados da nota (ja com correcoes
    anteriores aplicadas). A gravacao e feita pelo chamador via store —
    nunca apenas na interface.
    """

    def __init__(self, parent, nota: NotaFiscal) -> None:
        super().__init__(parent)
        self._nota = nota
        self.setWindowTitle(f"Corrigir campo fiscal — NF {nota.numero}")
        self.setMinimumWidth(460)

        grid = QGridLayout(self)
        grid.addWidget(QLabel("Campo:"), 0, 0)
        self._combo_campo = QComboBox()
        for campo, rotulo in CAMPOS_CORRIGIVEIS.items():
            self._combo_campo.addItem(rotulo, campo)
        self._combo_campo.currentIndexChanged.connect(self._preencher_originais)
        grid.addWidget(self._combo_campo, 0, 1)

        grid.addWidget(QLabel("Valor original:"), 1, 0)
        self._combo_original = QComboBox()
        grid.addWidget(self._combo_original, 1, 1)

        grid.addWidget(QLabel("Valor corrigido:"), 2, 0)
        self._edit_novo = QLineEdit()
        self._edit_novo.setPlaceholderText("Ex.: 1403 (CFOP), 060 (CST), 20,50 (aliquota)")
        grid.addWidget(self._edit_novo, 2, 1)

        grid.addWidget(QLabel("Motivo:"), 3, 0)
        self._edit_motivo = QLineEdit()
        self._edit_motivo.setPlaceholderText("Justificativa da correcao (auditoria)")
        grid.addWidget(self._edit_motivo, 3, 1)

        grid.addWidget(QLabel("Usuario:"), 4, 0)
        self._edit_usuario = QLineEdit(getpass.getuser())
        grid.addWidget(self._edit_usuario, 4, 1)

        self._chk_lote = QCheckBox(
            "Aplicar a todas as notas carregadas com este valor\n"
            "(regra em lote — registrada como correcao automatica)")
        grid.addWidget(self._chk_lote, 5, 1)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        grid.addWidget(botoes, 6, 0, 1, 2)

        self._preencher_originais()

    def _preencher_originais(self) -> None:
        campo = self._combo_campo.currentData()
        self._combo_original.clear()
        vistos: list[str] = []
        for item in self._nota.itens:
            v = normalizar_valor(campo, getattr(item, campo))
            if v and v not in vistos:
                vistos.append(v)
        self._combo_original.addItems(vistos)

    def dados(self) -> dict:
        return {
            "campo": self._combo_campo.currentData(),
            "rotulo": self._combo_campo.currentText(),
            "original": self._combo_original.currentText().strip(),
            "novo": self._edit_novo.text().strip(),
            "motivo": self._edit_motivo.text().strip(),
            "usuario": self._edit_usuario.text().strip(),
            "lote": self._chk_lote.isChecked(),
        }


class ConferenciaWidget(QWidget):
    def __init__(self, store: ConferenciaStore | None = None) -> None:
        super().__init__()
        self._store = store or ConferenciaStore()
        self._notas: list[NotaFiscal] = []
        self._chaves: list[str] = []
        self._nota_por_chave: dict[str, NotaFiscal] = {}
        # Copias com correcoes aplicadas (precedencia central): a tela sempre
        # exibe estas; os originais ficam em _notas para historico.
        self._corrigidas: dict[str, NotaFiscal] = {}
        self._carregando = False
        self._comp_carregando = False   # guarda do itemChanged da composicao
        self._grupos_comp: list[str] = []   # chave de grupo por linha da comp.
        self._filtro_entradas = False   # filtro usado na ultima carga
        self._contexto = ""             # origem da ultima carga (p/ relatorios)
        self._fonte_atual = ""          # "xml" ou "sped" da ultima carga
        self._caminho_fonte = ""        # arquivo SPED da ultima carga
        self._thread: QThread | None = None
        self._worker: WorkerCarga | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self._montar_selecao())
        layout.addWidget(self._montar_acoes())
        layout.addWidget(self._montar_tabela(), stretch=3)
        layout.addWidget(self._montar_composicao(), stretch=1)

        self._status = QLabel(
            "Importe um SPED (com a pasta de XMLs para abrir o DANFE) "
            "ou uma pasta de XMLs de NF-e.")
        self._status.setStyleSheet("color:#555;")
        layout.addWidget(self._status)

    def _montar_selecao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("Fonte:"), 0, 0)
        self._combo_fonte = QComboBox()
        self._combo_fonte.addItems(["Pasta de XMLs de NF-e", "SPED Fiscal (.txt)"])
        self._combo_fonte.currentIndexChanged.connect(self._ao_trocar_fonte)
        grid.addWidget(self._combo_fonte, 0, 1)

        grid.addWidget(QLabel("Caminho:"), 1, 0)
        self._edit_caminho = QLineEdit()
        self._edit_caminho.setPlaceholderText(
            "Pasta com XMLs (aceita varias, separadas por ;) ou arquivo SPED")
        self._edit_caminho.setToolTip(
            "Fonte XML: as subpastas sao lidas automaticamente (ex.: a pasta\n"
            "do ano inteiro com os meses dentro). Para juntar pastas avulsas,\n"
            "separe os caminhos com ; ou use Procurar mais de uma vez.")
        grid.addWidget(self._edit_caminho, 1, 1)
        btn = QPushButton("Procurar...")
        btn.clicked.connect(self._procurar)
        grid.addWidget(btn, 1, 2)

        # Fonte SPED: pasta opcional com os XMLs das NF-e. Cada nota do SPED e
        # vinculada ao seu XML pela chave de acesso, o que habilita o DANFE.
        self._lbl_pasta_xml = QLabel("XMLs p/ DANFE:")
        grid.addWidget(self._lbl_pasta_xml, 2, 0)
        self._edit_pasta_xml = QLineEdit()
        self._edit_pasta_xml.setPlaceholderText(
            "Opcional: pasta com os XMLs das notas do SPED (vincula pela chave de acesso)")
        grid.addWidget(self._edit_pasta_xml, 2, 1)
        self._btn_pasta_xml = QPushButton("Procurar...")
        self._btn_pasta_xml.clicked.connect(self._procurar_pasta_xml)
        grid.addWidget(self._btn_pasta_xml, 2, 2)

        # So faz sentido para a fonte SPED; fica desabilitada para XMLs.
        self._chk_entradas = QCheckBox(TEXTO_OPCAO_ENTRADAS)
        self._chk_entradas.setChecked(True)   # padrao: notas de entrada do SPED
        self._chk_entradas.setToolTip(
            "Marcado: somente as notas de entrada do SPED sao carregadas\n"
            "(IND_OPER = 0; sem IND_OPER, decide pelo CFOP dos itens).\n"
            "Desmarcado: todas as notas do arquivo.")
        grid.addWidget(self._chk_entradas, 3, 1)

        grid.setColumnStretch(1, 1)
        self._ao_trocar_fonte(self._combo_fonte.currentIndex())
        return caixa

    def _ao_trocar_fonte(self, indice: int) -> None:
        self._edit_caminho.clear()
        eh_sped = indice == 1
        self._chk_entradas.setEnabled(eh_sped)
        self._lbl_pasta_xml.setEnabled(eh_sped)
        self._edit_pasta_xml.setEnabled(eh_sped)
        self._btn_pasta_xml.setEnabled(eh_sped)

    def _montar_acoes(self) -> QWidget:
        caixa = QWidget()
        v = QVBoxLayout(caixa)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        linha1 = QHBoxLayout()
        self._btn_carregar = QPushButton("Carregar notas")
        self._btn_carregar.setMinimumHeight(32)
        self._btn_carregar.setStyleSheet(tema.QSS_BOTAO_PRIMARIO)
        self._btn_carregar.clicked.connect(self._carregar)
        linha1.addWidget(self._btn_carregar)

        self._btn_danfe = QPushButton("Abrir DANFE")
        self._btn_danfe.setMinimumHeight(32)
        self._btn_danfe.clicked.connect(self._abrir_danfe)
        linha1.addWidget(self._btn_danfe)

        self._btn_corrigir = QPushButton("Corrigir campo fiscal...")
        self._btn_corrigir.setMinimumHeight(32)
        self._btn_corrigir.setToolTip(
            "Corrige CFOP, CST ou aliquota da nota selecionada.\n"
            "O valor original e preservado no historico de auditoria e a\n"
            "correcao vale para a tela, o Livro Fiscal, o relatorio de\n"
            "inconsistencias e o SPED corrigido.")
        self._btn_corrigir.clicked.connect(self._corrigir_nota)
        linha1.addWidget(self._btn_corrigir)

        linha1.addWidget(QLabel("Filtro:"))
        self._combo_filtro = QComboBox()
        self._combo_filtro.addItems(["Todas", "Pendentes", "Conferidas"])
        self._combo_filtro.currentIndexChanged.connect(lambda _: self._aplicar_filtro())
        linha1.addWidget(self._combo_filtro)

        linha1.addStretch(1)
        self._lbl_progresso = QLabel("")
        self._lbl_progresso.setStyleSheet(
            f"font-weight:bold; color:{tema.COR_DESTAQUE};")
        linha1.addWidget(self._lbl_progresso)
        v.addLayout(linha1)

        linha2 = QHBoxLayout()
        linha2.addWidget(QLabel("Documentos:"))

        self._btn_livro_fiscal = QPushButton("Livro Fiscal (PDF)")
        self._btn_livro_fiscal.setMinimumHeight(30)
        self._btn_livro_fiscal.setToolTip(
            "Livro com TODAS as notas carregadas, ja com as correcoes,\n"
            "agrupadas por CFOP -> CST -> aliquota.")
        self._btn_livro_fiscal.clicked.connect(self._gerar_livro_fiscal)
        linha2.addWidget(self._btn_livro_fiscal)

        self._btn_livro = QPushButton("Inconsistencias (PDF)")
        self._btn_livro.setMinimumHeight(30)
        self._btn_livro.setToolTip(
            "PDF somente com as notas com observacao e/ou correcao,\n"
            "incluindo a trilha de auditoria das correcoes.")
        self._btn_livro.clicked.connect(self._gerar_livro)
        linha2.addWidget(self._btn_livro)

        self._btn_sped = QPushButton("Gerar SPED corrigido")
        self._btn_sped.setMinimumHeight(30)
        self._btn_sped.setToolTip(
            "Reescreve o arquivo SPED importado aplicando as correcoes de\n"
            "CFOP/CST (C170 + C190 reagrupados + contadores recalculados).")
        self._btn_sped.clicked.connect(self._gerar_sped)
        linha2.addWidget(self._btn_sped)

        linha2.addStretch(1)
        v.addLayout(linha2)
        return caixa

    def _montar_composicao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(caixa)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)

        titulo = QLabel("Composicao fiscal da nota selecionada "
                        "(CFOP -> CST -> Aliquota) — duplo clique em "
                        "CFOP/CST/Aliquota corrige a nota")
        titulo.setStyleSheet(f"font-weight:bold; color:{tema.COR_DESTAQUE};")
        v.addWidget(titulo)

        self._tab_comp = QTableWidget(0, 8)
        self._tab_comp.setHorizontalHeaderLabels(
            ["CFOP", "CST", "Aliquota", "Valor contabil", "Base ICMS",
             "Valor ICMS", "ICMS-ST", "Itens"])
        # Celulas selecionaveis (com Ctrl+C). CFOP/CST/Aliquota dos grupos
        # sao editaveis: a edicao registra uma CORRECAO real (mesma
        # precedencia da tela, do Livro Fiscal e do SPED corrigido).
        self._tab_comp.setSelectionMode(QTableWidget.ExtendedSelection)
        self._tab_comp.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked
            | QTableWidget.EditKeyPressed)
        self._tab_comp.itemChanged.connect(self._ao_editar_composicao)
        atalho_copiar = QShortcut(QKeySequence.Copy, self._tab_comp)
        atalho_copiar.setContext(Qt.WidgetWithChildrenShortcut)
        atalho_copiar.activated.connect(self._copiar_composicao)
        self._tab_comp.verticalHeader().setVisible(False)
        self._tab_comp.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._tab_comp.setMinimumHeight(110)
        v.addWidget(self._tab_comp)

        self._lbl_alertas = QLabel("")
        self._lbl_alertas.setWordWrap(True)
        self._lbl_alertas.setStyleSheet(
            f"color:{tema.DOURADO_TEXTO}; font-style:italic;")
        v.addWidget(self._lbl_alertas)
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
        self._tabela.itemSelectionChanged.connect(self._atualizar_composicao)
        return self._tabela

    # ------------------------------------------------------------------
    def _procurar(self) -> None:
        if self._combo_fonte.currentIndex() == 0:
            caminho = QFileDialog.getExistingDirectory(self, "Pasta com XMLs de NF-e")
            atual = self._edit_caminho.text().strip()
            if caminho and atual and caminho not in atual.split(";"):
                resp = QMessageBox.question(
                    self, "Pastas de XML",
                    "Ja existe pasta selecionada.\n\n"
                    "Adicionar esta pasta a selecao atual (Sim) ou "
                    "substituir (Nao)?",
                    QMessageBox.Yes | QMessageBox.No)
                if resp == QMessageBox.Yes:
                    caminho = f"{atual};{caminho}"
        else:
            caminho, _ = QFileDialog.getOpenFileName(
                self, "Selecionar SPED", "", "Arquivos SPED (*.txt);;Todos (*.*)")
        if caminho:
            self._edit_caminho.setText(caminho)

    def _procurar_pasta_xml(self) -> None:
        pasta = QFileDialog.getExistingDirectory(
            self, "Pasta com os XMLs das notas do SPED (para DANFE)")
        if pasta:
            self._edit_pasta_xml.setText(pasta)

    def _carregar(self) -> None:
        caminho = self._edit_caminho.text().strip()
        fonte = "xml" if self._combo_fonte.currentIndex() == 0 else "sped"
        if fonte == "xml":
            pastas = [p.strip() for p in caminho.split(";") if p.strip()]
            invalidas = [p for p in pastas if not os.path.isdir(p)]
            if not pastas or invalidas:
                detalhe = ("\n\nNao encontrada(s):\n" + "\n".join(invalidas)
                           if invalidas else "")
                QMessageBox.warning(
                    self, "Atencao",
                    f"Selecione pasta(s) de XMLs valida(s).{detalhe}")
                return
        if fonte == "sped" and not os.path.isfile(caminho):
            QMessageBox.warning(self, "Atencao", "Selecione um arquivo SPED valido.")
            return
        pasta_xml = self._edit_pasta_xml.text().strip() if fonte == "sped" else ""
        if pasta_xml and not os.path.isdir(pasta_xml):
            QMessageBox.warning(self, "Atencao",
                                "A pasta de XMLs (para DANFE) nao existe.")
            return

        self._btn_carregar.setEnabled(False)
        self._status.setText("Carregando notas...")
        self._filtro_entradas = fonte == "sped" and self._chk_entradas.isChecked()
        self._fonte_atual = fonte
        self._caminho_fonte = caminho
        self._thread = QThread()
        self._worker = WorkerCarga(fonte, caminho, self._filtro_entradas, pasta_xml)
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
        self._contexto = contexto
        self._nota_por_chave = {n.chave_normalizada: n for n in notas}
        self._chaves = [n.chave_normalizada for n in notas]
        self._reaplicar_correcoes()
        estados = self._store.carregar()

        self._carregando = True
        self._tabela.setRowCount(len(notas))
        for i, nota in enumerate(notas):
            chave = nota.chave_normalizada
            estado = estados.get(chave)
            conferida = estado.conferida if estado else False
            obs = estado.observacao if estado else ""
            data_conf = estado.data_conferencia if estado else ""
            forn = nota.participante.nome if nota.participante else ""

            self._por_texto(i, COL_NUM, nota.numero)
            self._por_texto(i, COL_SERIE, nota.serie)
            self._por_texto(i, COL_DATA, _data(nota.dt_emissao))
            self._por_texto(i, COL_FORN, forn)
            self._por_texto(i, COL_CNPJ, nota.cnpj_emitente)
            self._por_texto(i, COL_UF, nota.uf_origem)
            self._preencher_fiscal(i, self._corrigidas.get(chave, nota))
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
        self._atualizar_composicao()

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

    def _reaplicar_correcoes(self) -> None:
        """Reconstroi as copias corrigidas (precedencia central)."""
        mapa = self._store.todas_correcoes()
        self._corrigidas = {}
        for nota in self._notas:
            chave = nota.chave_normalizada
            corrigida = aplicar_correcoes(nota, mapa.get(chave, []))
            corrigida.xml_path = nota.xml_path   # vinculo do DANFE acompanha
            self._corrigidas[chave] = corrigida

    def _preencher_fiscal(self, i: int, nota: NotaFiscal) -> None:
        """Preenche as colunas fiscais com os valores vigentes (corrigidos)."""
        self._por_texto(i, COL_VCONT, _moeda(nota.valor_documento))
        self._por_texto(i, COL_BASE, _moeda(nota.vl_bc_icms))
        self._por_texto(i, COL_ICMS, _moeda(nota.vl_icms))
        self._por_texto(i, COL_CFOP, _distintos_texto(nota.itens, "cfop"))
        self._por_texto(i, COL_CST, _distintos_texto(nota.itens, "cst_icms"))
        self._por_texto(i, COL_ALIQ, _aliquotas(nota.itens))

        # Valores corrigidos: destaque dourado + tooltip com o original.
        originais: dict[str, str] = {}
        for item in nota.itens:
            for campo, original in item.corrigido_de.items():
                originais.setdefault(campo, original)
        col_por_campo = {"cfop": COL_CFOP, "cst_icms": COL_CST,
                         "aliq_icms": COL_ALIQ}
        for campo, original in originais.items():
            celula = self._tabela.item(i, col_por_campo[campo])
            if celula is None:
                continue
            celula.setForeground(QColor(tema.DOURADO_TEXTO))
            fonte = celula.font()
            fonte.setBold(True)
            celula.setFont(fonte)
            rotulo = CAMPOS_CORRIGIVEIS.get(campo, campo)
            celula.setToolTip(f"{rotulo} corrigido — valor original: {original}")

    def _atualizar_composicao(self) -> None:
        """Composicao CFOP -> CST -> aliquota da nota selecionada."""
        self._comp_carregando = True
        try:
            self._tab_comp.setRowCount(0)
            self._lbl_alertas.setText("")
            linha = self._tabela.currentRow()
            if linha < 0 or linha >= len(self._chaves):
                return
            nota = self._corrigidas.get(self._chaves[linha])
            if nota is None:
                return
            comp = compor_nota(nota)

            chave_nota = self._chaves[linha]
            overrides = self._store.overrides_da_chave(chave_nota)
            # Chave de grupo por linha da tabela (linha 0 = TOTAL) — usada
            # para casar cada celula com a sua sobrescrita e para gravar
            # novas edicoes de valores em _ao_editar_composicao.
            self._grupos_comp = [GRUPO_TOTAL] + [chave_grupo(g)
                                                 for g in comp.grupos]

            def _celula(r, c, texto, negrito=False, corrigido_de=None,
                        original_bruto=None, editavel=True):
                item = QTableWidgetItem(str(texto))
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if r >= 1 and c in self._CAMPO_POR_COLUNA_COMP:
                    # CFOP/CST/Aliquota: edicao registra CORRECAO real;
                    # exige valor original para corrigir a partir dele.
                    if original_bruto is not None and str(original_bruto).strip():
                        flags |= Qt.ItemIsEditable
                        item.setData(Qt.UserRole, str(original_bruto))
                elif editavel:
                    # Demais celulas: edicao vira SOBRESCRITA de texto
                    # persistida (tela + Livro Fiscal). O texto calculado
                    # fica no UserRole para auditoria/retorno.
                    flags |= Qt.ItemIsEditable
                    item.setData(Qt.UserRole, str(texto))
                    ov = overrides.get((self._grupos_comp[r], c))
                    if ov is not None:
                        item.setText(ov.valor)
                        fonte = item.font()
                        fonte.setItalic(True)
                        item.setFont(fonte)
                        item.setForeground(QColor(tema.DOURADO_TEXTO))
                        item.setToolTip(
                            "Editado manualmente — valor calculado: "
                            f"{ov.valor_original or '(vazio)'} "
                            f"(por {ov.usuario} em {ov.data_hora}).\n"
                            "Apague o texto para voltar ao calculado.")
                item.setFlags(flags)
                if negrito or corrigido_de:
                    fonte = item.font()
                    fonte.setBold(True)
                    item.setFont(fonte)
                if corrigido_de:
                    item.setForeground(QColor(tema.DOURADO_TEXTO))
                    item.setToolTip(
                        f"Corrigido — valor original: {corrigido_de}")
                self._tab_comp.setItem(r, c, item)

            self._tab_comp.setRowCount(len(comp.grupos) + 1)
            _celula(0, 0, "TOTAL DA NOTA", negrito=True, editavel=False)
            _celula(0, 1, "")
            _celula(0, 2, "")
            _celula(0, 3, formatar_moeda(comp.total_nota, True), negrito=True)
            _celula(0, 4, "")
            _celula(0, 5, "")
            _celula(0, 6, "")
            soma = comp.soma_valor_contabil
            _celula(0, 7, f"soma itens: {formatar_moeda(soma, True)}")

            for r, g in enumerate(comp.grupos, start=1):
                _celula(r, 0, formatar_cfop(g.cfop) or "--",
                        corrigido_de=g.corrigido_de.get("cfop"),
                        original_bruto=g.cfop)
                _celula(r, 1, g.cst or "--",
                        corrigido_de=g.corrigido_de.get("cst_icms"),
                        original_bruto=g.cst)
                _celula(r, 2, formatar_percentual(g.aliquota),
                        corrigido_de=g.corrigido_de.get("aliq_icms"),
                        original_bruto=(None if g.aliquota is None
                                        else g.aliquota))
                _celula(r, 3, formatar_moeda(g.valor_contabil, True))
                _celula(r, 4, formatar_moeda(g.vl_bc_icms, True))
                _celula(r, 5, formatar_moeda(g.vl_icms, True))
                st = (f"{formatar_moeda(g.vl_icms_st, True)}"
                      if (g.vl_icms_st or g.vl_bc_icms_st) else "")
                _celula(r, 6, st)
                _celula(r, 7, g.qtd_itens or "")

            if comp.alertas:
                self._lbl_alertas.setText(
                    "Alertas: " + " | ".join(comp.alertas))
        finally:
            self._comp_carregando = False

    _CAMPO_POR_COLUNA_COMP = {0: "cfop", 1: "cst_icms", 2: "aliq_icms"}

    def _ao_editar_composicao(self, item: QTableWidgetItem) -> None:
        """Edicao inline de CFOP/CST/Aliquota vira correcao registrada.

        Mesma precedencia central do botao "Corrigir campo fiscal": vale
        para a tela, o Livro Fiscal (PDF), o relatorio de inconsistencias
        e o SPED corrigido.
        """
        if self._comp_carregando:
            return
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._chaves):
            self._atualizar_composicao()
            return
        chave = self._chaves[linha]
        usuario = getpass.getuser()

        # Colunas fora de CFOP/CST/Aliquota (e a linha TOTAL): sobrescrita
        # de texto persistida — vale na tela e no Livro Fiscal (PDF).
        eh_correcao = (item.row() >= 1
                       and item.column() in self._CAMPO_POR_COLUNA_COMP)
        if not eh_correcao:
            if item.row() >= len(self._grupos_comp):
                self._atualizar_composicao()
                return
            grupo = self._grupos_comp[item.row()]
            calculado = str(item.data(Qt.UserRole) or "")
            novo_texto = item.text().strip()
            if novo_texto == calculado:
                novo_texto = ""   # voltou ao calculado: remove a sobrescrita
            self._store.salvar_override(
                chave, grupo, item.column(), novo_texto, calculado, usuario)
            self._atualizar_composicao()
            if novo_texto:
                self._status.setText(
                    f"Texto da composicao editado (coluna "
                    f"{self._tab_comp.horizontalHeaderItem(item.column()).text()}) "
                    "— vale para a tela e para o Livro Fiscal.")
            else:
                self._status.setText(
                    "Texto da composicao restaurado ao valor calculado.")
            return

        campo = self._CAMPO_POR_COLUNA_COMP.get(item.column())
        original = item.data(Qt.UserRole)
        if campo is None or not original:
            self._atualizar_composicao()
            return
        novo = item.text().strip().replace("%", "").strip()
        if normalizar_valor(campo, original) == normalizar_valor(campo, novo):
            self._atualizar_composicao()   # nada mudou: refaz a formatacao
            return
        try:
            validar_correcao(campo, original, novo, usuario)
        except ValueError as exc:
            QMessageBox.warning(self, "Correcao invalida", str(exc))
            self._atualizar_composicao()
            return

        rotulo = CAMPOS_CORRIGIVEIS[campo]
        nota = self._corrigidas.get(chave)
        numero = nota.numero if nota else ""
        resp = QMessageBox.question(
            self, "Confirmar correcao",
            f"Alterar {rotulo} de {original} para {novo} na NF {numero}?\n\n"
            "O valor original sera preservado no historico de auditoria e a "
            "correcao valera para a tela, o Livro Fiscal, o relatorio de "
            "inconsistencias e o SPED corrigido.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            self._atualizar_composicao()
            return

        self._store.registrar_correcao(
            chave, campo, str(original), novo, usuario, tipo=TIPO_MANUAL,
            motivo="Edicao direta na composicao fiscal",
            inconsistencia=self._store.obter(chave).observacao)
        self._reaplicar_correcoes()
        self._carregando = True
        for i, ch in enumerate(self._chaves):
            nota_c = self._corrigidas.get(ch)
            if nota_c is not None:
                self._preencher_fiscal(i, nota_c)
        self._carregando = False
        self._atualizar_composicao()
        self._status.setText(
            f"Correcao registrada: {rotulo} {original} -> {novo} "
            f"(por {usuario}).")

    def _copiar_composicao(self) -> None:
        """Copia as celulas selecionadas da composicao como texto tabulado."""
        indices = self._tab_comp.selectedIndexes()
        if not indices:
            return
        indices = sorted(indices, key=lambda i: (i.row(), i.column()))
        linhas: dict[int, list[str]] = {}
        for indice in indices:
            item = self._tab_comp.item(indice.row(), indice.column())
            linhas.setdefault(indice.row(), []).append(
                item.text() if item else "")
        texto = "\n".join("\t".join(cols) for _, cols in sorted(linhas.items()))
        QApplication.clipboard().setText(texto)

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
        if nota is None:
            return
        if not nota.xml_path or not os.path.isfile(nota.xml_path):
            # Nota veio do SPED sem XML: oferece vincular os XMLs agora.
            if not self._associar_xmls_interativo(nota):
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

    def _associar_xmls_interativo(self, nota: NotaFiscal) -> bool:
        """Pede a pasta de XMLs e vincula pela chave. True se a nota ganhou XML."""
        resp = QMessageBox.question(
            self, "DANFE precisa do XML",
            "O DANFE e gerado a partir do XML da NF-e, e esta nota (carregada "
            "do SPED) ainda nao tem XML vinculado.\n\n"
            "Deseja indicar agora a pasta com os XMLs? Todas as notas serao "
            "vinculadas pela chave de acesso.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return False
        pasta = QFileDialog.getExistingDirectory(self, "Pasta com XMLs de NF-e")
        if not pasta:
            return False
        self._status.setText("Vinculando XMLs pela chave de acesso...")
        associadas = associar_xmls(self._notas, pasta)
        self._reaplicar_correcoes()   # copias corrigidas herdam o xml_path
        self._edit_pasta_xml.setText(pasta)
        sem_xml = sum(1 for n in self._notas if not n.xml_path)
        extra = f" ({sem_xml} ainda sem XML)" if sem_xml else ""
        self._status.setText(f"{associadas} nota(s) vinculadas ao XML{extra}.")
        if not nota.xml_path or not os.path.isfile(nota.xml_path):
            QMessageBox.information(
                self, "XML nao encontrado",
                "O XML desta nota nao foi encontrado na pasta informada.\n\n"
                f"Chave de acesso: {nota.chave_normalizada}")
            return False
        return True

    # ------------------------------------------------------------------
    # Correcao de campos fiscais

    def _corrigir_nota(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._chaves):
            QMessageBox.information(self, "Correcao",
                                    "Selecione uma nota na tabela.")
            return
        chave = self._chaves[linha]
        nota = self._corrigidas.get(chave)
        if nota is None:
            return
        if not nota.itens:
            QMessageBox.information(
                self, "Correcao",
                "Esta nota nao tem itens detalhados (sem C170/det) — nao ha "
                "CFOP/CST/aliquota por item para corrigir.")
            return

        dlg = DialogoCorrecao(self, nota)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.dados()
        try:
            validar_correcao(d["campo"], d["original"], d["novo"], d["usuario"])
        except ValueError as exc:
            QMessageBox.warning(self, "Correcao invalida", str(exc))
            return

        alvo = ("TODAS as notas carregadas com este valor" if d["lote"]
                else f"a NF {nota.numero}")
        resp = QMessageBox.question(
            self, "Confirmar correcao",
            f"Alterar {d['rotulo']} de {d['original']} para {d['novo']} "
            f"em {alvo}?\n\nO valor original sera preservado no historico "
            "de auditoria e a correcao valera para a tela, o Livro Fiscal, "
            "o relatorio de inconsistencias e o SPED corrigido.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        aplicadas = 0
        try:
            if d["lote"]:
                alvo_norm = normalizar_valor(d["campo"], d["original"])
                for ch, nota_c in self._corrigidas.items():
                    tem_valor = any(
                        normalizar_valor(d["campo"], getattr(it, d["campo"]))
                        == alvo_norm for it in nota_c.itens)
                    if not tem_valor:
                        continue
                    tipo = TIPO_MANUAL if ch == chave else TIPO_AUTOMATICA
                    self._store.registrar_correcao(
                        ch, d["campo"], d["original"], d["novo"],
                        d["usuario"], tipo=tipo, motivo=d["motivo"],
                        inconsistencia=self._store.obter(ch).observacao)
                    aplicadas += 1
            else:
                self._store.registrar_correcao(
                    chave, d["campo"], d["original"], d["novo"], d["usuario"],
                    tipo=TIPO_MANUAL, motivo=d["motivo"],
                    inconsistencia=self._store.obter(chave).observacao)
                aplicadas = 1
        except ValueError as exc:
            QMessageBox.warning(self, "Correcao invalida", str(exc))
            return

        # Recalcula e atualiza a tela sem retrabalho do usuario.
        self._reaplicar_correcoes()
        self._carregando = True
        for i, ch in enumerate(self._chaves):
            nota_c = self._corrigidas.get(ch)
            if nota_c is not None:
                self._preencher_fiscal(i, nota_c)
        self._carregando = False
        self._atualizar_composicao()
        self._status.setText(
            f"Correcao registrada em {aplicadas} nota(s): {d['rotulo']} "
            f"{d['original']} -> {d['novo']} (por {d['usuario']}).")

    # ------------------------------------------------------------------
    # Documentos (Livro Fiscal, Inconsistencias, SPED corrigido)

    def _gerar_livro_fiscal(self) -> None:
        if not self._notas:
            QMessageBox.information(self, "Livro Fiscal",
                                    "Carregue as notas antes de gerar o livro.")
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar Livro Fiscal", "livro_fiscal.pdf", "PDF (*.pdf)")
        if not caminho:
            return
        self._status.setText("Gerando Livro Fiscal...")
        filtro = f"{ROTULO_FILTRO_ENTRADAS}." if self._filtro_entradas else ""
        try:
            gerar_livro_fiscal(
                self._notas, self._store.carregar(), caminho,
                contexto=self._contexto, filtro=filtro,
                correcoes_por_chave=self._store.todas_correcoes(),
                overrides_por_chave=self._store.todas_overrides())
            abrir_arquivo(caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Erro",
                f"Nao foi possivel gerar o Livro Fiscal:\n\n{exc}")
            self._status.setText("Erro ao gerar o Livro Fiscal.")
            return
        self._status.setText(
            f"Livro Fiscal gerado com {len(self._notas)} nota(s).")

    def _gerar_livro(self) -> None:
        if not self._notas:
            QMessageBox.information(
                self, "Relatorio de Inconsistencias",
                "Carregue as notas antes de gerar o relatorio.")
            return
        estados = self._store.carregar()
        correcoes = self._store.todas_correcoes()
        inconsistentes = notas_inconsistentes(self._notas, estados, correcoes)
        if not inconsistentes:
            QMessageBox.information(
                self, "Relatorio de Inconsistencias",
                "Nenhuma nota carregada tem observacao ou correcao.\n\n"
                "Registre as inconsistencias na coluna Observacao (ou aplique "
                "correcoes) e gere novamente.")
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar Relatorio de Inconsistencias",
            "relatorio_inconsistencias.pdf", "PDF (*.pdf)")
        if not caminho:
            return
        self._status.setText("Gerando Relatorio de Inconsistencias...")
        filtro = f"{ROTULO_FILTRO_ENTRADAS}." if self._filtro_entradas else ""
        try:
            gerar_livro_inconsistencias(self._notas, estados, caminho,
                                        contexto=self._contexto, filtro=filtro,
                                        correcoes_por_chave=correcoes)
            abrir_arquivo(caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Erro",
                f"Nao foi possivel gerar o Relatorio de Inconsistencias:"
                f"\n\n{exc}")
            self._status.setText("Erro ao gerar o Relatorio de Inconsistencias.")
            return
        self._status.setText(
            f"Relatorio de Inconsistencias gerado com "
            f"{len(inconsistentes)} nota(s).")

    def _gerar_sped(self) -> None:
        if self._fonte_atual != "sped" or not os.path.isfile(self._caminho_fonte):
            QMessageBox.information(
                self, "SPED corrigido",
                "Carregue um arquivo SPED Fiscal (fonte SPED) para gerar a "
                "versao corrigida.")
            return
        correcoes = self._store.todas_correcoes()
        ativas = [c for lista in correcoes.values() for c in lista if c.ativa]
        if not ativas:
            QMessageBox.information(
                self, "SPED corrigido",
                "Nenhuma correcao registrada — o arquivo gerado seria "
                "identico ao original.")
            return
        base, ext = os.path.splitext(os.path.basename(self._caminho_fonte))
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar SPED corrigido", f"{base}_corrigido{ext or '.txt'}",
            "Arquivos SPED (*.txt);;Todos (*.*)")
        if not caminho:
            return
        if os.path.abspath(caminho) == os.path.abspath(self._caminho_fonte):
            QMessageBox.warning(
                self, "SPED corrigido",
                "Escolha um nome diferente do arquivo original — o SPED "
                "importado nunca e sobrescrito.")
            return
        self._status.setText("Gerando SPED corrigido...")
        try:
            resumo = gerar_sped_corrigido(self._caminho_fonte, caminho,
                                          correcoes)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Erro", f"Nao foi possivel gerar o SPED:\n\n{exc}")
            self._status.setText("Erro ao gerar o SPED corrigido.")
            return
        detalhes = [
            f"Arquivo: {caminho}",
            f"Itens C170 alterados: {resumo.itens_c170_alterados}",
            f"Registros C190 mesclados: {resumo.c190_mesclados}",
            f"Notas alteradas: {resumo.notas_alteradas}",
        ]
        if resumo.ignoradas:
            detalhes.append("\nCorrecoes NAO levadas ao SPED:")
            detalhes.extend(f"- {msg}" for msg in resumo.ignoradas)
        if resumo.avisos:
            detalhes.append("\nAvisos:")
            detalhes.extend(f"- {msg}" for msg in resumo.avisos)
        QMessageBox.information(self, "SPED corrigido gerado",
                                "\n".join(detalhes))
        self._status.setText(
            f"SPED corrigido gerado ({resumo.notas_alteradas} nota(s) "
            "alteradas).")
