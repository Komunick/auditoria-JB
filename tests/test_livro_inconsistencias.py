"""Teste do Livro de Inconsistencias (PDF com as notas com observacao)."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.modelos import (  # noqa: E402
    ItemNota, NotaFiscal, Participante,
)
from auditoria_fiscal.ferramentas.conferencia_store import (  # noqa: E402
    EstadoConferencia,
)
from auditoria_fiscal.ferramentas.livro_inconsistencias import (  # noqa: E402
    gerar_livro_inconsistencias, notas_com_observacao,
)

CH_1, CH_2, CH_3 = "1" * 44, "2" * 44, "3" * 44


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    notas = [
        NotaFiscal(chave=CH_1, numero="101", serie="1",
                   valor_documento=Decimal("1500.00"),
                   participante=Participante(nome="FORNECEDOR ACENTUAÇÃO LTDA"),
                   itens=[ItemNota(cfop="1102"), ItemNota(cfop="1403")]),
        NotaFiscal(chave=CH_2, numero="202", serie="1",
                   valor_documento=Decimal("80.00")),
        NotaFiscal(chave=CH_3, numero="303", serie="2",
                   valor_documento=Decimal("999.99")),
    ]
    estados = {
        CH_1: EstadoConferencia(CH_1, conferida=True,
                                observacao="CFOP divergente do XML — corrigir",
                                data_conferencia="08/07/2026 10:00"),
        CH_2: EstadoConferencia(CH_2, conferida=False, observacao="   "),
        CH_3: EstadoConferencia(CH_3, conferida=False,
                                observacao="Nota sem lancamento no razao"),
    }

    # Somente as notas com observacao nao-vazia (CH_2 e so espacos)
    pares = notas_com_observacao(notas, estados)
    checar(len(pares) == 2, f"esperava 2 notas com observacao: {len(pares)}")
    checar({p[0].chave for p in pares} == {CH_1, CH_3},
           f"chaves selecionadas: {[p[0].chave for p in pares]}")

    fd, caminho = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        gerar_livro_inconsistencias(notas, estados, caminho,
                                    contexto="EMPRESA DEMO LTDA",
                                    filtro="Filtro aplicado: somente documentos "
                                           "de entrada no SPED.")
        checar(os.path.isfile(caminho), "PDF nao foi criado")
        with open(caminho, "rb") as fh:
            inicio = fh.read(5)
        checar(inicio == b"%PDF-", f"arquivo nao parece PDF: {inicio!r}")
        checar(os.path.getsize(caminho) > 1000,
               f"PDF suspeito de vazio: {os.path.getsize(caminho)} bytes")
    finally:
        os.unlink(caminho)

    # Sem observacoes -> ValueError (a UI avisa antes, mas o motor se protege)
    try:
        gerar_livro_inconsistencias(notas, {}, caminho)
        falhas.append("deveria levantar ValueError sem observacoes")
    except ValueError:
        pass

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - Livro de Inconsistencias passou (filtra por observacao e gera PDF).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
