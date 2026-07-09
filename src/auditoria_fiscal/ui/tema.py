"""Tema visual do aplicativo — identidade JB Fraga Contabilidade.

Paleta extraida da logomarca: azul-tinta profundo (#26263A, das letras
"JB FRAGA") como cor principal e dourado (#B8A166, do ornamento e do
"CONTABILIDADE") como cor de destaque.

Ha dois modos, CLARO e ESCURO, alternaveis pelo botao no cabecalho da
janela. A escolha fica salva em %LOCALAPPDATA%/AuditoriaFiscal/config.json;
sem escolha salva, o primeiro uso segue o modo do Windows.

Os widgets leem as cores como `tema.<NOME>` (ligacao tardia): ao trocar o
modo, os globais deste modulo sao reatribuidos e a interface e reconstruida
pela janela principal.
"""

from __future__ import annotations

import json
import os
import tempfile

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# ----- Cores da marca (logo JB Fraga) — iguais nos dois modos -----
TINTA = "#26263A"           # azul-tinta das letras "JB FRAGA"
TINTA_HOVER = "#3B3B58"     # tinta um tom acima (hover de botao)
DOURADO = "#B8A166"         # dourado do ornamento / "CONTABILIDADE"
DOURADO_ESCURO = "#9C874F"  # dourado para texto pequeno no claro

# Compatibilidade com codigo que usava o azul antigo como "cor principal".
AZUL = TINTA
AZUL_FORTE = DOURADO

_CONFIG = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                       "AuditoriaFiscal", "config.json")

# "Check" branco desenhado dentro do indicador marcado. O QSS so aceita
# imagem via arquivo, entao o SVG e gravado uma vez na pasta temporaria.
_SVG_CHECK = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="#FFFFFF" '
    'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>')


def _caminho_icone_check() -> str:
    caminho = os.path.join(tempfile.gettempdir(), "auditoria_fiscal_check.svg")
    try:
        with open(caminho, "w", encoding="utf-8") as fh:
            fh.write(_SVG_CHECK)
    except OSError:
        return ""
    return caminho.replace("\\", "/")


_ICONE_CHECK = _caminho_icone_check()
# Sem o arquivo (pasta temp indisponivel), o marcado fica so com fundo cheio.
_IMG_CHECK = f'image: url("{_ICONE_CHECK}");' if _ICONE_CHECK else ""

_ESCURO = False


def escuro_ativo() -> bool:
    return _ESCURO


def _modo_do_windows() -> bool:
    """True se o Windows estiver em modo escuro (usado so no primeiro uso)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as ch:
            return winreg.QueryValueEx(ch, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def carregar_modo() -> None:
    """Le a preferencia salva (ou o modo do Windows) e ajusta os globais."""
    escuro = _modo_do_windows()
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            tema_salvo = json.load(f).get("tema")
        if tema_salvo in ("claro", "escuro"):
            escuro = tema_salvo == "escuro"
    except (OSError, ValueError):
        pass
    definir_modo(escuro, salvar=False)


def definir_modo(escuro: bool, salvar: bool = True) -> None:
    """Troca o modo claro/escuro e reatribui os globais derivados."""
    global _ESCURO
    _ESCURO = bool(escuro)
    _derivar()
    if salvar:
        try:
            os.makedirs(os.path.dirname(_CONFIG), exist_ok=True)
            with open(_CONFIG, "w", encoding="utf-8") as f:
                json.dump({"tema": "escuro" if _ESCURO else "claro"}, f)
        except OSError:
            pass  # sem permissao de escrita: o modo vale so nesta sessao


def _derivar() -> None:
    """Recalcula as cores e folhas de estilo do modo atual."""
    global BRANCO, FUNDO, PAPEL, TEXTO, LINHA_ALT, BORDA, SELECAO
    global TINTA_DESAB, DOURADO_SUAVE, DOURADO_TEXTO, COR_DESTAQUE
    global QSS, QSS_BOTAO_PRIMARIO

    if _ESCURO:
        FUNDO = "#17171F"          # janela
        PAPEL = "#1E1E29"          # campos, tabelas, cartoes
        TEXTO = "#E8E6F0"
        LINHA_ALT = "#232330"
        BORDA = "#3A3A4C"
        SELECAO = "#4A4230"        # dourado profundo (selecao de linha/texto)
        DOURADO_SUAVE = "#33301F"
        DOURADO_TEXTO = DOURADO    # dourado puro le bem sobre o escuro
        COR_DESTAQUE = DOURADO     # titulos e rotulos de destaque
        TINTA_DESAB = "#4A4A5E"
        # No escuro o botao principal e dourado com texto de tinta.
        QSS_BOTAO_PRIMARIO = (
            f"QPushButton {{ background:{DOURADO}; color:{FUNDO}; font-weight:bold;"
            " border-radius:4px; padding:6px 18px; }"
            " QPushButton:hover { background:#CBB57A; }"
            " QPushButton:disabled { background:#55524A; color:#8B8878; }")
    else:
        FUNDO = "#FFFFFF"
        PAPEL = "#FFFFFF"
        TEXTO = "#23232F"
        LINHA_ALT = "#F7F6F2"      # zebra das tabelas (branco aquecido)
        BORDA = "#D5D2C9"
        SELECAO = "#F1EADA"
        DOURADO_SUAVE = "#F1EADA"
        DOURADO_TEXTO = DOURADO_ESCURO
        COR_DESTAQUE = TINTA
        TINTA_DESAB = "#A9A6B8"
        QSS_BOTAO_PRIMARIO = (
            f"QPushButton {{ background:{TINTA}; color:white; font-weight:bold;"
            " border-radius:4px; padding:6px 18px; }"
            f" QPushButton:hover {{ background:{TINTA_HOVER}; }}"
            f" QPushButton:disabled {{ background:{TINTA_DESAB}; }}")

    BRANCO = PAPEL  # compatibilidade com codigo antigo

    abas_fundo = "#26262F" if _ESCURO else "#F1EFE9"
    abas_texto = "#B9B6C6" if _ESCURO else "#4A4A5C"
    cab_fundo = "#2A2A3A" if _ESCURO else TINTA
    botao_fundo = "#262631" if _ESCURO else "#F5F4F0"
    botao_press = "#3A3524" if _ESCURO else "#E7DFC9"
    desab_txt = "#6A6A75" if _ESCURO else "#A0A0AA"
    grade = "#31313F" if _ESCURO else "#E7E4DC"
    rolagem = "#2A2A36" if _ESCURO else "#F2F1ED"
    rolagem_punho = "#45455A" if _ESCURO else "#CBC7BB"
    chk_borda = DOURADO if _ESCURO else TINTA
    chk_marcado = DOURADO_ESCURO if _ESCURO else TINTA
    chk_marcado_hover = DOURADO if _ESCURO else TINTA_HOVER

    QSS = f"""
QWidget {{ color: {TEXTO}; }}
QMainWindow, QDialog {{ background: {FUNDO}; }}

QToolTip {{
    background: {PAPEL}; color: {TEXTO};
    border: 1px solid {DOURADO}; padding: 4px;
}}

/* Abas */
QTabWidget::pane {{
    border: 1px solid {BORDA}; border-radius: 6px; background: {FUNDO}; top: -1px;
}}
QTabBar::tab {{
    background: {abas_fundo}; color: {abas_texto};
    padding: 9px 20px; margin-right: 2px;
    border: 1px solid {BORDA}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {FUNDO}; color: {COR_DESTAQUE}; border-bottom: 3px solid {DOURADO};
}}
QTabBar::tab:hover {{ background: {DOURADO_SUAVE}; }}

/* Tabelas */
QHeaderView::section {{
    background: {cab_fundo}; color: #FFFFFF;
    padding: 7px 9px; border: none;
    border-right: 1px solid {TINTA_HOVER}; border-bottom: 2px solid {DOURADO};
    font-weight: bold;
}}
QTableView {{
    background: {PAPEL}; alternate-background-color: {LINHA_ALT};
    gridline-color: {grade};
    selection-background-color: {SELECAO}; selection-color: {TEXTO};
    border: 1px solid {BORDA};
}}
QTableView::item {{ padding: 4px 6px; }}
QTableCornerButton::section {{ background: {cab_fundo}; border: 1px solid {TINTA_HOVER}; }}

/* Campos de entrada */
QLineEdit, QComboBox {{
    background: {PAPEL}; border: 1px solid {BORDA}; border-radius: 4px;
    padding: 6px 8px; min-height: 20px;
    selection-background-color: {SELECAO}; selection-color: {TEXTO};
}}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {DOURADO}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PAPEL}; color: {TEXTO};
    selection-background-color: {SELECAO}; selection-color: {TEXTO};
    border: 1px solid {BORDA};
}}

/* Botoes (os de acao principal usam QSS_BOTAO_PRIMARIO) */
QPushButton {{
    background: {botao_fundo}; color: {COR_DESTAQUE};
    border: 1px solid {BORDA}; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ background: {DOURADO_SUAVE}; border-color: {DOURADO}; }}
QPushButton:pressed {{ background: {botao_press}; }}
QPushButton:disabled {{ color: {desab_txt}; background: {LINHA_ALT}; border-color: {BORDA}; }}

/* Caixas de selecao bem visiveis: borda forte na cor da marca e fundo
   cheio com "check" branco quando marcadas (telas e tabelas). */
QCheckBox {{ spacing: 8px; font-weight: 600; }}
QCheckBox:disabled {{ color: {desab_txt}; }}
QCheckBox::indicator, QTableView::indicator {{
    width: 18px; height: 18px;
    border: 2px solid {chk_borda}; border-radius: 4px;
    background: {PAPEL};
}}
QCheckBox::indicator:hover, QTableView::indicator:hover {{
    border-color: {DOURADO}; background: {DOURADO_SUAVE};
}}
QCheckBox::indicator:checked, QTableView::indicator:checked {{
    background: {chk_marcado}; border-color: {chk_marcado};
    {_IMG_CHECK}
}}
QCheckBox::indicator:checked:hover, QTableView::indicator:checked:hover {{
    background: {chk_marcado_hover}; border-color: {DOURADO};
}}
QCheckBox::indicator:disabled {{ border-color: {desab_txt}; background: {LINHA_ALT}; }}
QCheckBox::indicator:checked:disabled {{
    background: {TINTA_DESAB}; border-color: {TINTA_DESAB};
}}

/* Barras de rolagem discretas e visiveis */
QScrollBar:vertical {{ background: {rolagem}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {rolagem_punho}; border-radius: 6px; min-height: 26px; }}
QScrollBar::handle:vertical:hover {{ background: {DOURADO}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {rolagem}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {rolagem_punho}; border-radius: 6px; min-width: 26px; }}
QScrollBar::handle:horizontal:hover {{ background: {DOURADO}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def _paleta() -> QPalette:
    p = QPalette()
    texto = QColor(TEXTO)
    Role = QPalette.ColorRole
    Grupo = QPalette.ColorGroup
    p.setColor(Role.Window, QColor(FUNDO))
    p.setColor(Role.WindowText, texto)
    p.setColor(Role.Base, QColor(PAPEL))
    p.setColor(Role.AlternateBase, QColor(LINHA_ALT))
    p.setColor(Role.Text, texto)
    p.setColor(Role.Button, QColor("#262631" if _ESCURO else "#F5F4F0"))
    p.setColor(Role.ButtonText, texto)
    p.setColor(Role.ToolTipBase, QColor(PAPEL))
    p.setColor(Role.ToolTipText, texto)
    p.setColor(Role.Highlight, QColor(DOURADO))
    p.setColor(Role.HighlightedText, QColor(FUNDO if _ESCURO else TINTA))
    p.setColor(Role.PlaceholderText, QColor("#6E6C7C" if _ESCURO else "#94919F"))
    # Estados desabilitados legiveis
    for role in (Role.Text, Role.WindowText, Role.ButtonText):
        p.setColor(Grupo.Disabled, role, QColor("#6A6A75" if _ESCURO else "#A0A0AA"))
    return p


def aplicar_tema(app: QApplication) -> None:
    """Aplica estilo Fusion + paleta do modo atual + fonte maior + QSS."""
    app.setStyle("Fusion")
    app.setPalette(_paleta())
    fonte = QFont()
    fonte.setPointSize(10)
    app.setFont(fonte)
    app.setStyleSheet(QSS)


# Estado inicial: preferencia salva (ou, sem ela, o modo do Windows).
carregar_modo()
