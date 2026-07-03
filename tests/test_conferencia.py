"""Teste da persistencia de conferencia (SQLite)."""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.ferramentas.conferencia_store import ConferenciaStore  # noqa: E402


def main() -> int:
    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(caminho)  # deixa o sqlite criar do zero

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    chave = "3" * 44
    store = ConferenciaStore(caminho)

    # Estado inicial: nao conferida
    e0 = store.obter(chave)
    checar(not e0.conferida and e0.observacao == "", "estado inicial deveria ser vazio")

    # Marca conferida com observacao
    e1 = store.salvar(chave, True, "CFOP conferido, ok")
    checar(e1.conferida and e1.observacao == "CFOP conferido, ok", "salvar conferida")
    checar(e1.data_conferencia != "", "data deveria ser preenchida ao conferir")
    data_original = e1.data_conferencia

    # Reabre o banco (persistencia entre sessoes)
    store.fechar()
    store = ConferenciaStore(caminho)
    e2 = store.obter(chave)
    checar(e2.conferida and e2.observacao == "CFOP conferido, ok",
           "estado nao persistiu apos reabrir")
    checar(e2.data_conferencia == data_original, "data mudou indevidamente")

    # Atualiza observacao mantendo conferida -> data preservada
    e3 = store.salvar(chave, True, "revisado")
    checar(e3.data_conferencia == data_original, "data deveria ser preservada")
    checar(e3.observacao == "revisado", "observacao nao atualizou")

    # Desmarca conferida -> data limpa
    e4 = store.salvar(chave, False, "revisado")
    checar(not e4.conferida and e4.data_conferencia == "", "desmarcar deveria limpar data")

    # carregar() retorna o mapa
    store.salvar("4" * 44, True, "outra")
    mapa = store.carregar()
    checar(len(mapa) == 2, f"carregar deveria ter 2 registros: {len(mapa)}")

    store.fechar()
    os.unlink(caminho)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - persistencia de conferencia passou (inclui reabrir o banco).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
