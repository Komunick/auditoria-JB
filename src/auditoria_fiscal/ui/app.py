"""Janela principal do aplicativo de auditoria fiscal (abas por ferramenta).

Executar:  python executar.py
       ou:  python -m auditoria_fiscal.ui.app
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QTabWidget, QVBoxLayout,
    QWidget,
)

from .comparador_widget import ComparadorWidget
from .conferencia_widget import ConferenciaWidget
from .diff_widget import DiffSpedWidget
from .extracao_widget import ExtracaoWidget
from .logo import icone, pixmap
from .produtos_widget import ProdutosWidget
from .tema import DOURADO_ESCURO, TINTA, aplicar_tema


class JanelaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Auditoria Fiscal — JB Fraga Contabilidade")
        self.setWindowIcon(icone())
        self.resize(1160, 760)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 12)

        # Cabecalho com a logomarca e o titulo nas cores da marca.
        cab = QHBoxLayout()
        cab.setSpacing(10)
        marca = QLabel()
        marca.setPixmap(pixmap(largura=52))
        cab.addWidget(marca)

        textos = QVBoxLayout()
        textos.setSpacing(0)
        titulo = QLabel("Ferramentas de Auditoria Fiscal")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        titulo.setFont(f)
        titulo.setStyleSheet(f"color:{TINTA};")
        subtitulo = QLabel("JB FRAGA CONTABILIDADE")
        fs = QFont()
        fs.setPointSize(9)
        fs.setBold(True)
        fs.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        subtitulo.setFont(fs)
        subtitulo.setStyleSheet(f"color:{DOURADO_ESCURO};")
        textos.addWidget(titulo)
        textos.addWidget(subtitulo)
        cab.addLayout(textos)
        cab.addStretch(1)
        layout.addLayout(cab)

        abas = QTabWidget()
        abas.addTab(ComparadorWidget(), "1. Comparador SPED x SEFAZ")
        abas.addTab(DiffSpedWidget(), "2. Comparar versoes de SPED")
        abas.addTab(ConferenciaWidget(), "3. Livro de Conferencia")
        abas.addTab(ExtracaoWidget(), "4. Extracao de Itens")
        abas.addTab(ProdutosWidget(), "5. Auditoria de Produtos")
        layout.addWidget(abas)


def main() -> int:
    app = QApplication(sys.argv)
    aplicar_tema(app)
    app.setWindowIcon(icone())   # barra de tarefas e dialogos
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
