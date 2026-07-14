"""Sobe a Auditoria Fiscal Web (site interno).

Uso: .venv\\Scripts\\python servidor.py  (ou servidor.ps1)
Variaveis: AUDITORIA_WEB_PORTA (padrao 8600), AUDITORIA_WEB_DADOS.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "src"))


def main() -> None:
    import uvicorn

    from auditoria_fiscal.web.servidor import criar_app

    porta = int(os.environ.get("AUDITORIA_WEB_PORTA", "8600"))
    uvicorn.run(criar_app(), host="0.0.0.0", port=porta)


if __name__ == "__main__":
    main()
