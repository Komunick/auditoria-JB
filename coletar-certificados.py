"""Coletor da pasta de certificados digitais (spec 012, US8).

Rodar num computador do escritorio que enxerga a pasta da rede:

    .venv\\Scripts\\python.exe coletar-certificados.py "X:\\CERTIFICADOS DIGITAIS ATUALIZADOS"

Grava `coleta-certificados-AAAAMMDD-HHMM.json` na pasta atual (ou no caminho
passado como segundo argumento). Esse arquivo vai na aba "9. Clientes" >
Importar. Ele NAO leva senha, chave privada nem o certificado — mas leva nomes
e CNPJs de clientes: trate-o como documento interno e apague depois de
importar.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from auditoria_fiscal.core import coletor_certificados as cc  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help") or len(argv) > 2:
        print(__doc__)
        return 2
    pasta = argv[0]
    saida = argv[1] if len(argv) == 2 else cc.nome_padrao()
    try:
        coleta = cc.coletar(pasta)
    except FileNotFoundError as exc:
        print(f"ERRO - {exc}", file=sys.stderr)
        return 1
    parcial = saida + ".parcial"
    with open(parcial, "w", encoding="utf-8") as arquivo:
        json.dump(coleta, arquivo, ensure_ascii=False, indent=1)
    os.replace(parcial, saida)
    print(cc.resumo_texto(coleta))
    print(f"\nArquivo gravado: {os.path.abspath(saida)}")
    print("Envie-o na aba 9. Clientes > Importar e apague-o depois.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
