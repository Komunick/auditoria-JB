"""Geracao e abertura do DANFE (PDF) a partir do XML da NF-e.

Usa a biblioteca brazilfiscalreport para renderizar o DANFE padrao a partir do
XML autorizado (procNFe / NFe 4.00).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile


def gerar_danfe_pdf(xml_path: str, pdf_path: str | None = None) -> str:
    """Gera o PDF do DANFE a partir de um arquivo XML. Retorna o caminho do PDF.

    Levanta excecao se o XML nao for uma NF-e valida/completa.
    """
    from brazilfiscalreport.danfe import Danfe

    with open(xml_path, "rb") as fh:
        bruto = fh.read()
    try:
        conteudo = bruto.decode("utf-8")
    except UnicodeDecodeError:
        conteudo = bruto.decode("latin-1")

    danfe = Danfe(conteudo)
    if pdf_path is None:
        base = os.path.splitext(os.path.basename(xml_path))[0]
        pdf_path = os.path.join(tempfile.gettempdir(), f"danfe_{base}.pdf")
    danfe.output(pdf_path)
    return pdf_path


def abrir_arquivo(caminho: str) -> None:
    """Abre um arquivo no aplicativo padrao do sistema."""
    if sys.platform.startswith("win"):
        os.startfile(caminho)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


def abrir_danfe(xml_path: str, pdf_path: str | None = None) -> str:
    """Gera o DANFE e abre no visualizador padrao. Retorna o caminho do PDF."""
    pdf = gerar_danfe_pdf(xml_path, pdf_path)
    abrir_arquivo(pdf)
    return pdf
