"""Tema visual do aplicativo: branco, alto contraste e maior visibilidade.

Aplica uma paleta clara (forcando fundo branco mesmo em Windows no modo escuro),
uma fonte um pouco maior e uma folha de estilo (QSS) que destaca cabecalhos de
tabela, abas, campos e botoes. Centralizado aqui para valer nas 4 abas.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# Cores base do tema
BRANCO = "#FFFFFF"
TEXTO = "#1A2230"
LINHA_ALT = "#F1F5FB"
BORDA = "#C8D2E0"
AZUL = "#1F4E78"
AZUL_FORTE = "#1F6FEB"
SELECAO = "#CFE3FF"


def _paleta_clara() -> QPalette:
    p = QPalette()
    texto = QColor(TEXTO)
    Role = QPalette.ColorRole
    Grupo = QPalette.ColorGroup
    p.setColor(Role.Window, QColor(BRANCO))
    p.setColor(Role.WindowText, texto)
    p.setColor(Role.Base, QColor(BRANCO))
    p.setColor(Role.AlternateBase, QColor(LINHA_ALT))
    p.setColor(Role.Text, texto)
    p.setColor(Role.Button, QColor("#F2F5FA"))
    p.setColor(Role.ButtonText, texto)
    p.setColor(Role.ToolTipBase, QColor(BRANCO))
    p.setColor(Role.ToolTipText, texto)
    p.setColor(Role.Highlight, QColor(AZUL_FORTE))
    p.setColor(Role.HighlightedText, QColor(BRANCO))
    p.setColor(Role.PlaceholderText, QColor("#8A93A3"))
    # Estados desabilitados legiveis
    for role in (Role.Text, Role.WindowText, Role.ButtonText):
        p.setColor(Grupo.Disabled, role, QColor("#9AA3B2"))
    return p


QSS = f"""
QWidget {{ color: {TEXTO}; }}
QMainWindow, QDialog {{ background: {BRANCO}; }}

QToolTip {{
    background: {BRANCO}; color: {TEXTO};
    border: 1px solid {BORDA}; padding: 4px;
}}

/* Abas */
QTabWidget::pane {{
    border: 1px solid {BORDA}; border-radius: 6px; background: {BRANCO}; top: -1px;
}}
QTabBar::tab {{
    background: #EEF2F8; color: #33415C;
    padding: 9px 20px; margin-right: 2px;
    border: 1px solid {BORDA}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {BRANCO}; color: {AZUL}; border-bottom: 3px solid {AZUL_FORTE};
}}
QTabBar::tab:hover {{ background: #E3EAF4; }}

/* Tabelas */
QHeaderView::section {{
    background: #E7EEF7; color: #17263C;
    padding: 7px 9px; border: none;
    border-right: 1px solid {BORDA}; border-bottom: 1px solid #B9C5D6;
    font-weight: bold;
}}
QTableView {{
    background: {BRANCO}; alternate-background-color: {LINHA_ALT};
    gridline-color: #E1E7F0;
    selection-background-color: {SELECAO}; selection-color: #10233D;
    border: 1px solid {BORDA};
}}
QTableView::item {{ padding: 4px 6px; }}
QTableCornerButton::section {{ background: #E7EEF7; border: 1px solid {BORDA}; }}

/* Campos de entrada */
QLineEdit, QComboBox {{
    background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 4px;
    padding: 6px 8px; min-height: 20px;
    selection-background-color: {SELECAO}; selection-color: #10233D;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {AZUL_FORTE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BRANCO}; color: {TEXTO};
    selection-background-color: {SELECAO}; selection-color: #10233D;
    border: 1px solid {BORDA};
}}

/* Botoes (os botoes de acao principal tem estilo proprio, mais forte) */
QPushButton {{
    background: #F4F7FB; color: #1F2A3D;
    border: 1px solid {BORDA}; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ background: #E9EFF7; border-color: #9DB3C8; }}
QPushButton:pressed {{ background: #DCE6F2; }}
QPushButton:disabled {{ color: #9AA3B2; background: #F0F2F5; border-color: #DDE3EC; }}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; }}

/* Barras de rolagem discretas e visiveis */
QScrollBar:vertical {{ background: #F0F3F8; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #C0CBDA; border-radius: 6px; min-height: 26px; }}
QScrollBar::handle:vertical:hover {{ background: #A5B4C8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: #F0F3F8; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #C0CBDA; border-radius: 6px; min-width: 26px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def aplicar_tema(app: QApplication) -> None:
    """Aplica estilo Fusion + paleta clara + fonte maior + QSS."""
    app.setStyle("Fusion")
    app.setPalette(_paleta_clara())
    fonte = QFont()
    fonte.setPointSize(10)
    app.setFont(fonte)
    app.setStyleSheet(QSS)
