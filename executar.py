"""Lancador do aplicativo desktop de auditoria fiscal.

Uso:  python executar.py
"""

import os
import sys

# Garante que o pacote em src/ seja encontrado sem instalacao.
RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.ui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
