"""Janela principal do aplicativo de auditoria fiscal (abas por ferramenta).

Executar:  python executar.py
       ou:  python -m auditoria_fiscal.ui.app
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget,
)

from .comparador_widget import ComparadorWidget
from .conferencia_widget import ConferenciaWidget
from .diff_widget import DiffSpedWidget
from .extracao_widget import ExtracaoWidget


class JanelaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Auditoria Fiscal")
        self.resize(1160, 760)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 12)

        titulo = QLabel("Ferramentas de Auditoria Fiscal")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        titulo.setFont(f)
        titulo.setStyleSheet("color:#1F4E78;")
        layout.addWidget(titulo)

        abas = QTabWidget()
        abas.addTab(ComparadorWidget(), "1. Comparador SPED x SEFAZ")
        abas.addTab(DiffSpedWidget(), "2. Comparar versoes de SPED")
        abas.addTab(ConferenciaWidget(), "3. Livro de Conferencia")
        abas.addTab(ExtracaoWidget(), "4. Extracao de Itens")
        layout.addWidget(abas)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
