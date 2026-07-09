"""Aba de Auditoria e Correcao da Tributacao do Cadastro de Produtos (Item 5)."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.base_legal import carregar_base_legal, localizar_pasta_dados
from ..core.cadastro_produtos import gerar_nova_base, ler_base_produtos
from ..ferramentas.auditoria_produtos import (
    ResultadoAuditoria, auditar_produtos, calcular_indicadores,
)
from ..ferramentas.correcao_produtos import (
    aplicar_correcoes, selecionar_alta_confianca,
)
from ..ferramentas.relatorio_produtos import exportar_relatorio_excel
from . import tema

LIMITE_PREVIA = 5000   # linhas exibidas na tabela (relatorio/nova base levam tudo)

_FILTROS = ["Todos", "Somente inconsistentes", "Somente alertas",
            "Alta confianca (auto-corrigiveis)"]

_TITULOS = ["", "Codigo", "Descricao", "NCM", "CEST", "CFOP", "CST", "Aliq",
            "Trib. atual", "Trib. sugerida", "Confianca", "Situacao",
            "Inconsistencias", "Correcao sugerida", "Status"]

_COR_INCONSISTENTE = QColor("#FDE7E9")
_COR_ALERTA = QColor("#FFF4CE")

_INDICADORES = [
    ("total", "Total"),
    ("corretos", "Corretos"),
    ("inconsistentes", "Inconsistentes"),
    ("alertas", "Alertas"),
    ("percentual_inconsistencias", "% inconsistencias"),
    ("sujeitos_st", "Sujeitos a ST"),
    ("corrigidos", "Corrigidos"),
]


def _texto_correcao(resultado: ResultadoAuditoria) -> str:
    """Monta texto legivel das correcoes sugeridas de um resultado."""
    partes: list[str] = []
    correcoes = resultado.correcoes
    if "cst" in correcoes:
        atual = resultado.produto.cst or "-"
        partes.append(f"CST {atual} -> {correcoes['cst']}")
    for de, para in resultado.cfop_map.items():
        partes.append(f"CFOP {de} -> {para}")
    if "cest" in correcoes:
        partes.append(f"CEST -> {correcoes['cest']}")
    if "aliquota" in correcoes:
        partes.append(f"Aliquota -> {correcoes['aliquota']}")
    return "; ".join(partes)


def _texto_aliquota(aliquota) -> str:
    if aliquota is None:
        return ""
    return str(aliquota).replace(".", ",")


def _texto_percentual(valor) -> str:
    return f"{valor}".replace(".", ",") + "%"


class WorkerProdutos(QObject):
    concluido = Signal(object)   # dict: base, resultados, indicadores
    erro = Signal(str)

    def __init__(self, caminho: str) -> None:
        super().__init__()
        self.caminho = caminho

    def executar(self) -> None:
        try:
            base = ler_base_produtos(self.caminho)
            base_legal = carregar_base_legal()
            resultados = auditar_produtos(base.produtos, base_legal)
            indicadores = calcular_indicadores(resultados)
            self.concluido.emit({"base": base, "resultados": resultados,
                                 "indicadores": indicadores})
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"{type(exc).__name__}: {exc}")


class ProdutosWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._base = None
        self._resultados: list[ResultadoAuditoria] = []
        self._indicadores: dict = {}
        self._filtrados: list[ResultadoAuditoria] = []
        self._alteracoes: dict[int, dict[str, object]] = {}
        self._thread: QThread | None = None
        self._worker: WorkerProdutos | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self._montar_selecao())
        layout.addWidget(self._montar_acoes())
        layout.addWidget(self._montar_indicadores())
        layout.addWidget(self._montar_tabela(), stretch=1)
        layout.addWidget(self._montar_botoes_correcao())

        self._status = QLabel("Selecione a planilha do cadastro de produtos "
                              "e clique em Importar e auditar.")
        self._status.setStyleSheet("color:#555;")
        layout.addWidget(self._status)

    # ------------------------------------------------------------------
    # Montagem da interface
    # ------------------------------------------------------------------
    def _montar_selecao(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(caixa)

        grid.addWidget(QLabel("Cadastro de produtos:"), 0, 0)
        self._edit_caminho = QLineEdit()
        self._edit_caminho.setPlaceholderText(
            "Planilha exportada do sistema do cliente (xlsx, xls, csv ou txt)")
        grid.addWidget(self._edit_caminho, 0, 1)
        btn = QPushButton("Procurar...")
        btn.clicked.connect(self._procurar)
        grid.addWidget(btn, 0, 2)

        pasta = localizar_pasta_dados()
        if pasta:
            lbl_dados = QLabel(f"Bases legais em uso: {pasta}")
            lbl_dados.setStyleSheet("color:#555;")
        else:
            lbl_dados = QLabel("Pasta dados/ nao encontrada - as validacoes "
                               "legais (Anexo I, TIPI) ficarao limitadas.")
            lbl_dados.setStyleSheet("color:#C55A11; font-weight:bold;")
        grid.addWidget(lbl_dados, 1, 0, 1, 3)

        grid.setColumnStretch(1, 1)
        return caixa

    def _montar_acoes(self) -> QWidget:
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 0, 0, 0)

        self._btn_auditar = QPushButton("Importar e auditar")
        self._btn_auditar.setMinimumHeight(34)
        self._btn_auditar.setStyleSheet(tema.QSS_BOTAO_PRIMARIO)
        self._btn_auditar.clicked.connect(self._auditar)
        h.addWidget(self._btn_auditar)

        h.addSpacing(16)
        h.addWidget(QLabel("Exibir:"))
        self._combo_filtro = QComboBox()
        self._combo_filtro.addItems(_FILTROS)
        self._combo_filtro.currentIndexChanged.connect(self._ao_filtrar)
        h.addWidget(self._combo_filtro)
        h.addStretch(1)
        return caixa

    def _montar_indicadores(self) -> QWidget:
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        h = QHBoxLayout(caixa)
        self._labels_ind: dict[str, QLabel] = {}
        for chave, titulo in _INDICADORES:
            lbl = QLabel(f"{titulo}: -")
            lbl.setStyleSheet(f"font-weight:bold; color:{tema.COR_DESTAQUE};")
            self._labels_ind[chave] = lbl
            h.addWidget(lbl)
        h.addStretch(1)
        return caixa

    def _montar_tabela(self) -> QWidget:
        self._tabela = QTableWidget(0, len(_TITULOS))
        self._tabela.setHorizontalHeaderLabels(_TITULOS)
        self._tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._tabela.setColumnWidth(0, 28)
        return self._tabela

    def _montar_botoes_correcao(self) -> QWidget:
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 0, 0, 0)

        self._btn_corrigir_sel = QPushButton("Corrigir selecionados")
        self._btn_corrigir_sel.clicked.connect(self._corrigir_selecionados)
        h.addWidget(self._btn_corrigir_sel)

        self._btn_corrigir_alta = QPushButton("Corrigir alta confianca")
        self._btn_corrigir_alta.clicked.connect(self._corrigir_alta_confianca)
        h.addWidget(self._btn_corrigir_alta)

        self._btn_relatorio = QPushButton("Exportar relatorio (.xlsx)")
        self._btn_relatorio.clicked.connect(self._exportar_relatorio)
        h.addWidget(self._btn_relatorio)

        self._btn_nova_base = QPushButton("Gerar nova base")
        self._btn_nova_base.clicked.connect(self._gerar_nova_base)
        h.addWidget(self._btn_nova_base)

        h.addStretch(1)
        for btn in (self._btn_corrigir_sel, self._btn_corrigir_alta,
                    self._btn_relatorio, self._btn_nova_base):
            btn.setMinimumHeight(30)
            btn.setEnabled(False)
        return caixa

    # ------------------------------------------------------------------
    # Auditoria
    # ------------------------------------------------------------------
    def _procurar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar cadastro de produtos", "",
            "Planilhas e texto (*.xlsx *.xlsm *.xls *.csv *.txt);;Todos (*.*)")
        if caminho:
            self._edit_caminho.setText(caminho)

    def _auditar(self) -> None:
        caminho = self._edit_caminho.text().strip()
        if not os.path.isfile(caminho):
            QMessageBox.warning(self, "Atencao",
                                "Selecione um arquivo de cadastro valido.")
            return

        self._btn_auditar.setEnabled(False)
        for btn in (self._btn_corrigir_sel, self._btn_corrigir_alta,
                    self._btn_relatorio, self._btn_nova_base):
            btn.setEnabled(False)
        self._status.setText("Importando e auditando produtos...")

        self._thread = QThread()
        self._worker = WorkerProdutos(caminho)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.concluido.connect(self._ao_concluir)
        self._worker.erro.connect(self._ao_erro)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.erro.connect(self._thread.quit)
        self._thread.start()

    def _ao_erro(self, mensagem: str) -> None:
        self._btn_auditar.setEnabled(True)
        self._status.setText("Erro na auditoria.")
        QMessageBox.critical(self, "Erro",
                             f"Falha ao auditar o cadastro:\n\n{mensagem}")

    def _ao_concluir(self, dados: dict) -> None:
        self._btn_auditar.setEnabled(True)
        self._base = dados["base"]
        self._resultados = dados["resultados"]
        self._indicadores = dados["indicadores"]
        self._alteracoes = {}

        habilitar = bool(self._resultados)
        for btn in (self._btn_corrigir_sel, self._btn_corrigir_alta,
                    self._btn_relatorio, self._btn_nova_base):
            btn.setEnabled(habilitar)

        self._atualizar_indicadores()
        self._popular_tabela()

        total = self._indicadores.get("total", len(self._resultados))
        inc = self._indicadores.get("inconsistentes", 0)
        ale = self._indicadores.get("alertas", 0)
        aviso = "" if len(self._resultados) <= LIMITE_PREVIA else \
            f" (previa: {LIMITE_PREVIA} linhas - relatorio e nova base levam tudo)"
        self._status.setText(
            f"{total} produto(s) auditado(s): {inc} inconsistente(s), "
            f"{ale} alerta(s).{aviso}")

    def _atualizar_indicadores(self) -> None:
        for chave, titulo in _INDICADORES:
            valor = self._indicadores.get(chave, "-")
            if chave == "percentual_inconsistencias" and valor != "-":
                texto = _texto_percentual(valor)
            else:
                texto = str(valor)
            self._labels_ind[chave].setText(f"{titulo}: {texto}")

    # ------------------------------------------------------------------
    # Tabela e filtro
    # ------------------------------------------------------------------
    def _ao_filtrar(self, _indice: int) -> None:
        if self._resultados:
            self._popular_tabela()

    def _resultados_filtrados(self) -> list[ResultadoAuditoria]:
        filtro = self._combo_filtro.currentText()
        if filtro == "Somente inconsistentes":
            return [r for r in self._resultados if r.situacao == "INCONSISTENTE"]
        if filtro == "Somente alertas":
            return [r for r in self._resultados if r.situacao == "ALERTA"]
        if filtro == "Alta confianca (auto-corrigiveis)":
            return list(selecionar_alta_confianca(self._resultados))
        return list(self._resultados)

    def _popular_tabela(self) -> None:
        resultados = self._resultados_filtrados()
        self._filtrados = resultados[:LIMITE_PREVIA]
        self._tabela.setRowCount(len(self._filtrados))
        for linha, resultado in enumerate(self._filtrados):
            produto = resultado.produto
            if resultado.situacao == "INCONSISTENTE":
                cor = _COR_INCONSISTENTE
            elif resultado.situacao == "ALERTA":
                cor = _COR_ALERTA
            else:
                cor = None

            marca = QTableWidgetItem()
            if resultado.tem_correcao:
                marca.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled
                               | Qt.ItemIsUserCheckable)
                marca.setCheckState(Qt.Unchecked)
            else:
                marca.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if cor is not None:
                marca.setBackground(cor)
            self._tabela.setItem(linha, 0, marca)

            valores = [
                produto.codigo,
                produto.descricao,
                produto.ncm,
                produto.cest,
                ", ".join(produto.cfops),
                produto.cst,
                _texto_aliquota(produto.aliquota),
                resultado.tributacao_atual,
                resultado.tributacao_sugerida,
                resultado.confianca,
                resultado.situacao,
                resultado.tipos,
                _texto_correcao(resultado),
                resultado.status_correcao,
            ]
            for col, texto in enumerate(valores, start=1):
                item = QTableWidgetItem(texto)
                if cor is not None:
                    item.setBackground(cor)
                self._tabela.setItem(linha, col, item)
        self._tabela.resizeColumnsToContents()
        self._tabela.setColumnWidth(0, 28)

    # ------------------------------------------------------------------
    # Correcoes
    # ------------------------------------------------------------------
    def _corrigir_selecionados(self) -> None:
        selecionados: list[ResultadoAuditoria] = []
        for linha in range(self._tabela.rowCount()):
            item = self._tabela.item(linha, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            resultado = self._filtrados[linha]
            if resultado.tem_correcao and resultado.status_correcao != "Corrigido":
                selecionados.append(resultado)
        if not selecionados:
            QMessageBox.information(
                self, "Atencao",
                "Marque na primeira coluna os produtos com correcao sugerida "
                "que deseja corrigir.")
            return
        self._executar_correcao(selecionados)

    def _corrigir_alta_confianca(self) -> None:
        candidatos = [r for r in selecionar_alta_confianca(self._resultados)
                      if r.status_correcao != "Corrigido"]
        if not candidatos:
            QMessageBox.information(
                self, "Atencao",
                "Nenhuma correcao de alta confianca pendente.")
            return
        self._executar_correcao(candidatos)

    def _executar_correcao(self, resultados: list[ResultadoAuditoria]) -> None:
        resposta = QMessageBox.question(
            self, "Confirmar correcao",
            f"Aplicar correcoes sugeridas em {len(resultados)} produto(s)?\n\n"
            "As alteracoes ficam registradas no historico e so vao para o "
            "arquivo ao usar Gerar nova base.")
        if resposta != QMessageBox.Yes:
            return
        try:
            novas = aplicar_correcoes(resultados, self._base.caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro",
                                 f"Falha ao aplicar correcoes:\n{exc}")
            return

        self._mesclar_alteracoes(novas)
        self._indicadores = calcular_indicadores(self._resultados)
        self._atualizar_indicadores()
        self._popular_tabela()
        self._status.setText(
            f"{len(novas)} produto(s) corrigido(s) agora; "
            f"{len(self._alteracoes)} produto(s) com correcao acumulada na "
            "sessao (use Gerar nova base para gravar).")

    def _mesclar_alteracoes(self, novas: dict[int, dict[str, object]]) -> None:
        for indice, campos in novas.items():
            atual = self._alteracoes.setdefault(indice, {})
            for chave, valor in campos.items():
                if chave == "cfop_map" and isinstance(atual.get(chave), dict) \
                        and isinstance(valor, dict):
                    atual[chave].update(valor)
                else:
                    atual[chave] = valor

    # ------------------------------------------------------------------
    # Saidas
    # ------------------------------------------------------------------
    def _exportar_relatorio(self) -> None:
        if not self._resultados:
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatorio de auditoria", "auditoria_produtos.xlsx",
            "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        try:
            exportar_relatorio_excel(self._resultados, caminho,
                                     self._indicadores,
                                     contexto=self._base.caminho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro",
                                 f"Nao foi possivel salvar:\n{exc}")
            return
        self._status.setText(f"Relatorio salvo em: {caminho}")
        QMessageBox.information(self, "Concluido",
                                f"Relatorio de auditoria gerado:\n{caminho}")

    def _gerar_nova_base(self) -> None:
        if self._base is None:
            return
        if not self._alteracoes:
            QMessageBox.information(
                self, "Atencao",
                "Nenhuma correcao aplicada ainda. Use Corrigir selecionados "
                "ou Corrigir alta confianca antes de gerar a nova base.")
            return
        raiz, ext = os.path.splitext(self._base.caminho)
        sugestao = f"{raiz}_corrigida{ext}"
        filtro = f"Arquivo (*{ext})" if ext else "Todos (*.*)"
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar nova base corrigida", sugestao, filtro)
        if not caminho:
            return
        try:
            saida = gerar_nova_base(self._base, caminho, self._alteracoes)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro",
                                 f"Nao foi possivel gerar a nova base:\n{exc}")
            return
        self._status.setText(f"Nova base gerada em: {saida}")
        QMessageBox.information(
            self, "Concluido",
            f"Nova base com {len(self._alteracoes)} produto(s) corrigido(s):"
            f"\n{saida}")
