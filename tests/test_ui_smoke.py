"""Smoke test da interface (headless / offscreen).

Verifica que a janela constroi e popula as tabelas sem erro. Nao abre janela.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from auditoria_fiscal.core.modelos import (  # noqa: E402
    DocumentoFiscalConjunto, Empresa, NotaFiscal, Participante,
)
from auditoria_fiscal.core.sefaz_relacao import RegistroSefaz  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sefaz import comparar  # noqa: E402
from auditoria_fiscal.ui.app import JanelaPrincipal  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    chave_a = "3" * 44
    chave_b = "4" * 44
    doc = DocumentoFiscalConjunto(
        empresa=Empresa(nome="EMPRESA DEMO LTDA", cnpj="11222333000181"),
        notas=[NotaFiscal(chave=chave_a, ind_oper="0", situacao="00", numero="1",
                          valor_documento=Decimal("100.00"),
                          participante=Participante(nome="FORN A"))],
    )
    registros = [
        RegistroSefaz(chave=chave_a, numero="1", valor=Decimal("100.00"),
                      situacao="Autorizada", emitente_nome="FORN A"),
        RegistroSefaz(chave=chave_b, numero="2", valor=Decimal("50.00"),
                      situacao="Autorizada", emitente_nome="FORN B"),
    ]
    resultado = comparar(doc, registros)

    janela = JanelaPrincipal()
    janela._ao_concluir("EMPRESA DEMO LTDA", resultado,
                        {"mapa_colunas": {"chave": "Chave de Acesso"},
                         "registros_validos": 2})

    falhas = []
    if janela._tab_faltantes.rowCount() != 1:
        falhas.append(f"faltantes rowCount={janela._tab_faltantes.rowCount()} (esperado 1)")
    if janela._cartoes["faltantes"].text() != "1":
        falhas.append(f"cartao faltantes={janela._cartoes['faltantes'].text()}")
    if janela._cartoes["conciliadas"].text() != "1":
        falhas.append(f"cartao conciliadas={janela._cartoes['conciliadas'].text()}")
    # Verifica conteudo da primeira celula (chave do faltante = chave_b)
    item = janela._tab_faltantes.item(0, 0)
    if item is None or item.text() != chave_b:
        falhas.append(f"chave faltante na tabela: {item.text() if item else None}")

    janela.close()
    app.quit()

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - interface constroi e popula as tabelas corretamente (headless).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
