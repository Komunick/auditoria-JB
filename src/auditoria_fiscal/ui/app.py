"""Janela principal do aplicativo de auditoria fiscal (abas por ferramenta).

Executar:  python executar.py
       ou:  python -m auditoria_fiscal.ui.app
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from . import tema
from .logo import icone, pixmap


class JanelaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Auditoria Fiscal — JB Fraga Contabilidade")
        self.setWindowIcon(icone())
        self.resize(1160, 760)
        self._montar()

    # ------------------------------------------------------------------
    def _montar(self) -> None:
        """(Re)constroi todo o conteudo — chamado tambem ao trocar o tema."""
        central = QWidget()
        self.setCentralWidget(central)   # descarta o conteudo anterior
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
        titulo.setStyleSheet(f"color:{tema.COR_DESTAQUE};")
        subtitulo = QLabel("JB FRAGA CONTABILIDADE")
        fs = QFont()
        fs.setPointSize(9)
        fs.setBold(True)
        fs.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        subtitulo.setFont(fs)
        subtitulo.setStyleSheet(f"color:{tema.DOURADO_TEXTO};")
        textos.addWidget(titulo)
        textos.addWidget(subtitulo)
        cab.addLayout(textos)
        cab.addStretch(1)

        btn_tema = QPushButton("☀  Modo claro" if tema.escuro_ativo() else "🌙  Modo escuro")
        btn_tema.setToolTip("Alternar entre modo claro e modo escuro.\n"
                            "A escolha fica salva para as proximas aberturas.")
        btn_tema.clicked.connect(self._alternar_tema)
        cab.addWidget(btn_tema)
        layout.addLayout(cab)

        # Import tardio: os widgets leem as cores do tema ao serem construidos.
        from .comparador_widget import ComparadorWidget
        from .conferencia_widget import ConferenciaWidget
        from .diff_widget import DiffSpedWidget
        from .extracao_widget import ExtracaoWidget
        from .produtos_widget import ProdutosWidget

        abas = QTabWidget()
        abas.addTab(ComparadorWidget(), "1. Comparador SPED x SEFAZ")
        abas.addTab(DiffSpedWidget(), "2. Comparar versoes de SPED")
        abas.addTab(ConferenciaWidget(), "3. Livro de Conferencia")
        abas.addTab(ExtracaoWidget(), "4. Extracao de Itens")
        abas.addTab(ProdutosWidget(), "5. Auditoria de Produtos")
        layout.addWidget(abas)

    # ------------------------------------------------------------------
    def _alternar_tema(self) -> None:
        """Troca claro/escuro; as abas sao recarregadas com o novo visual."""
        resposta = QMessageBox.question(
            self, "Trocar o tema",
            "Trocar o tema recarrega as abas — arquivos ja processados na "
            "tela precisarao ser carregados de novo.\n\nContinuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resposta != QMessageBox.Yes:
            return
        tema.definir_modo(not tema.escuro_ativo())
        tema.aplicar_tema(QApplication.instance())
        self._montar()


def main() -> int:
    app = QApplication(sys.argv)
    tema.aplicar_tema(app)
    app.setWindowIcon(icone())   # barra de tarefas e dialogos
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
