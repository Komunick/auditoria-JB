"""Tema visual do aplicativo — identidade JB Fraga Contabilidade.

Paleta extraida da logomarca: azul-tinta profundo (#26263A, das letras
"JB FRAGA") como cor principal e dourado (#B8A166, do ornamento e do
"CONTABILIDADE") como cor de destaque, sobre fundo branco de alto contraste.

Aplica uma paleta clara (forcando fundo branco mesmo em Windows no modo
escuro), uma fonte um pouco maior e uma folha de estilo (QSS) que destaca
cabecalhos de tabela, abas, campos e botoes. Centralizado aqui para valer
em todas as abas.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# ----- Cores da marca (logo JB Fraga) -----
TINTA = "#26263A"           # azul-tinta das letras "JB FRAGA"
TINTA_HOVER = "#3B3B58"     # tinta um tom acima (hover de botao)
TINTA_DESAB = "#A9A6B8"     # tinta lavada (botao desabilitado)
DOURADO = "#B8A166"         # dourado do ornamento / "CONTABILIDADE"
DOURADO_ESCURO = "#9C874F"  # dourado para texto pequeno (mais contraste)
DOURADO_SUAVE = "#F1EADA"   # fundo dourado bem claro (selecoes)

# ----- Cores base do tema -----
BRANCO = "#FFFFFF"
TEXTO = "#23232F"
LINHA_ALT = "#F7F6F2"       # zebra das tabelas (branco levemente aquecido)
BORDA = "#D5D2C9"
SELECAO = DOURADO_SUAVE

# Compatibilidade com codigo que usava o azul antigo como "cor principal".
AZUL = TINTA
AZUL_FORTE = DOURADO

# Botao de acao principal (mesmo visual nas 5 abas).
QSS_BOTAO_PRIMARIO = (
    f"QPushButton {{ background:{TINTA}; color:white; font-weight:bold;"
    " border-radius:4px; padding:6px 18px; }"
    f" QPushButton:hover {{ background:{TINTA_HOVER}; }}"
    f" QPushButton:disabled {{ background:{TINTA_DESAB}; }}")


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
    p.setColor(Role.Button, QColor("#F5F4F0"))
    p.setColor(Role.ButtonText, texto)
    p.setColor(Role.ToolTipBase, QColor(BRANCO))
    p.setColor(Role.ToolTipText, texto)
    p.setColor(Role.Highlight, QColor(DOURADO))
    p.setColor(Role.HighlightedText, QColor(TINTA))
    p.setColor(Role.PlaceholderText, QColor("#94919F"))
    # Estados desabilitados legiveis
    for role in (Role.Text, Role.WindowText, Role.ButtonText):
        p.setColor(Grupo.Disabled, role, QColor("#A0A0AA"))
    return p


QSS = f"""
QWidget {{ color: {TEXTO}; }}
QMainWindow, QDialog {{ background: {BRANCO}; }}

QToolTip {{
    background: {BRANCO}; color: {TEXTO};
    border: 1px solid {DOURADO}; padding: 4px;
}}

/* Abas */
QTabWidget::pane {{
    border: 1px solid {BORDA}; border-radius: 6px; background: {BRANCO}; top: -1px;
}}
QTabBar::tab {{
    background: #F1EFE9; color: #4A4A5C;
    padding: 9px 20px; margin-right: 2px;
    border: 1px solid {BORDA}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {BRANCO}; color: {TINTA}; border-bottom: 3px solid {DOURADO};
}}
QTabBar::tab:hover {{ background: {DOURADO_SUAVE}; }}

/* Tabelas */
QHeaderView::section {{
    background: {TINTA}; color: #FFFFFF;
    padding: 7px 9px; border: none;
    border-right: 1px solid #3B3B58; border-bottom: 2px solid {DOURADO};
    font-weight: bold;
}}
QTableView {{
    background: {BRANCO}; alternate-background-color: {LINHA_ALT};
    gridline-color: #E7E4DC;
    selection-background-color: {SELECAO}; selection-color: {TINTA};
    border: 1px solid {BORDA};
}}
QTableView::item {{ padding: 4px 6px; }}
QTableCornerButton::section {{ background: {TINTA}; border: 1px solid #3B3B58; }}

/* Campos de entrada */
QLineEdit, QComboBox {{
    background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 4px;
    padding: 6px 8px; min-height: 20px;
    selection-background-color: {SELECAO}; selection-color: {TINTA};
}}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {DOURADO}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BRANCO}; color: {TEXTO};
    selection-background-color: {SELECAO}; selection-color: {TINTA};
    border: 1px solid {BORDA};
}}

/* Botoes (os botoes de acao principal tem estilo proprio, mais forte) */
QPushButton {{
    background: #F5F4F0; color: {TINTA};
    border: 1px solid {BORDA}; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ background: {DOURADO_SUAVE}; border-color: {DOURADO}; }}
QPushButton:pressed {{ background: #E7DFC9; }}
QPushButton:disabled {{ color: #A0A0AA; background: #F2F1EE; border-color: #E2E0D9; }}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; }}

/* Barras de rolagem discretas e visiveis */
QScrollBar:vertical {{ background: #F2F1ED; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #CBC7BB; border-radius: 6px; min-height: 26px; }}
QScrollBar::handle:vertical:hover {{ background: {DOURADO}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: #F2F1ED; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #CBC7BB; border-radius: 6px; min-width: 26px; }}
QScrollBar::handle:horizontal:hover {{ background: {DOURADO}; }}
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
