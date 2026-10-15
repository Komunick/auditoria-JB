"""Benchmark reproduzivel de SC-010 da spec 006 (T038).

NAO faz parte da suite (o nome nao comeca com `test_`): mede tempo, e tempo
depende da maquina. Rode explicitamente e registre o hardware junto do
resultado, senao o numero nao quer dizer nada.

    .\\.venv\\Scripts\\python.exe tests\\benchmark_nfse.py

Meta da spec (proposta, revisar com JB-4):

- SC-010: lote de 500 linhas importado e conferido em ate 5 s no servidor.

Mede tambem, so para referencia, a aprovacao (geracao e validacao das 500
DPS no XSD), que nao tem meta na spec.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tests"))

from fixtures import nfse as fx  # noqa: E402

from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_store as ns  # noqa: E402

ATOR = {"usuario_id": 1, "usuario_login": "benchmark"}
LINHAS = 500
META_S = 5.0
HOJE = dt.date(2026, 11, 15)
AGORA = dt.datetime(2026, 11, 15, 10, 30, tzinfo=nd.FUSO_SALVADOR)


def main() -> int:
    print(f"Maquina: {platform.platform()} | {platform.processor()} | "
          f"{os.cpu_count()} nucleos | Python {platform.python_version()}")
    with tempfile.TemporaryDirectory() as pasta:
        linhas = []
        for i in range(LINHAS):
            linha = list(fx.LINHA_ANA)
            linha[5] = f"Aluno Ficticio {i:04d}"
            linha[7] = 1000 + i
            linhas.append(linha)
        planilha = fx.gerar_planilha(pasta, linhas, nome="bench.xlsx")
        store = ns.NfseStore(os.path.join(pasta, "bench.db"),
                             os.path.join(pasta, "origens"))
        pid = store.criar_perfil(fx.perfil_completo(endereco="informar"), **ATOR)["perfil_id"]

        inicio = time.perf_counter()
        lote_id = store.importar_planilha(pid, planilha, "bench.xlsx", hoje=HOJE,
                                          **ATOR)["lote_id"]
        importar = time.perf_counter() - inicio
        totais = store.lote(lote_id)["conferencia"]["totais"]

        inicio = time.perf_counter()
        store.aprovar(lote_id, revision=1, agora=AGORA, **ATOR)
        aprovar = time.perf_counter() - inicio
        store.fechar()

    print(f"SC-010 importar + conferir {LINHAS} linhas: {importar:.2f} s "
          f"(meta {META_S:.0f} s) -> {'OK' if importar <= META_S else 'ACIMA DA META'}")
    print(f"       linhas ok: {totais['ok']} | aviso: {totais['aviso']} | "
          f"bloqueio: {totais['bloqueio']}")
    print(f"Referencia: aprovar e gerar {LINHAS} DPS validadas no XSD: {aprovar:.2f} s")
    return 0 if importar <= META_S and totais["ok"] == LINHAS else 1


if __name__ == "__main__":
    raise SystemExit(main())
