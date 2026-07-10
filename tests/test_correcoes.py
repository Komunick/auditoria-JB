"""Teste das correcoes fiscais: validacao, auditoria e precedencia central."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.composicao_fiscal import compor_nota  # noqa: E402
from auditoria_fiscal.core.correcoes import (  # noqa: E402
    TIPO_AUTOMATICA, aplicar_correcoes, normalizar_valor, validar_correcao,
)
from auditoria_fiscal.core.modelos import ItemNota, NotaFiscal  # noqa: E402
from auditoria_fiscal.ferramentas.conferencia_store import (  # noqa: E402
    ConferenciaStore,
)

D = Decimal
CHAVE = "1" * 44


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    def deve_falhar(msg, *args):
        try:
            validar_correcao(*args)
            falhas.append(f"deveria rejeitar: {msg}")
        except ValueError:
            pass

    # ---- Validacoes ----
    deve_falhar("CFOP invalido (4xxx)", "cfop", "4102", "1403", "ana")
    deve_falhar("CFOP curto", "cfop", "110", "1403", "ana")
    deve_falhar("CST de 1 digito", "cst_icms", "0", "060", "ana")
    deve_falhar("aliquota > 100", "aliq_icms", "18", "150", "ana")
    deve_falhar("aliquota invalida", "aliq_icms", "18", "abc", "ana")
    deve_falhar("sem usuario", "cfop", "1102", "1403", "  ")
    deve_falhar("igual ao original", "cfop", "1102", "1.102", "ana")
    deve_falhar("campo desconhecido", "ncm", "111", "222", "ana")
    validar_correcao("cfop", "1.102", "1403", "ana")     # com ponto: valido
    validar_correcao("aliq_icms", "20,50", "27", "ana")  # virgula: valido
    checar(normalizar_valor("cfop", "1.102") == "1102", "normalizar CFOP")

    # ---- Persistencia com trilha de auditoria ----
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    store = ConferenciaStore(db)
    store.salvar(CHAVE, False, "CFOP errado")

    try:
        store.registrar_correcao(CHAVE, "cfop", "1102", "9999", "ana")
        falhas.append("store deveria validar o CFOP corrigido")
    except ValueError:
        pass

    correcao = store.registrar_correcao(
        CHAVE, "cfop", "1.102", "1403", "ana", motivo="NF de uso e consumo",
        inconsistencia="CFOP errado")
    checar(correcao.id > 0, "correcao sem id")
    checar(correcao.valor_original == "1102" and
           correcao.valor_corrigido == "1403", f"valores: {correcao}")
    checar(correcao.usuario == "ana" and correcao.data_hora != "",
           "usuario/data da auditoria")
    checar(correcao.tipo == "manual" and correcao.status == "aplicada",
           f"tipo/status: {correcao.tipo}/{correcao.status}")
    checar(correcao.inconsistencia == "CFOP errado",
           "vinculo com a inconsistencia")

    # Persistiu de verdade (reabre o banco)
    store.fechar()
    store = ConferenciaStore(db)
    lidas = store.correcoes_da_chave(CHAVE)
    checar(len(lidas) == 1 and lidas[0].motivo == "NF de uso e consumo",
           "correcao nao persistiu apos reabrir")

    # ---- Precedencia central: aplicar_correcoes ----
    nota = NotaFiscal(chave=CHAVE, valor_documento=D("500.00"),
                      valor_mercadoria=D("500.00"),
                      itens=[
                          ItemNota(cfop="1102", cst_icms="000",
                                   aliq_icms=D("20.50"),
                                   valor_item=D("200.00"),
                                   vl_bc_icms=D("200.00"),
                                   vl_icms=D("41.00")),
                          ItemNota(cfop="1403", cst_icms="060",
                                   valor_item=D("300.00")),
                      ])
    corrigida = aplicar_correcoes(nota, lidas)

    # Cenario 4: tela/PDF/SPED usam o corrigido; original preservado.
    checar(corrigida.itens[0].cfop == "1403", "correcao nao aplicada")
    checar(corrigida.itens[0].corrigido_de.get("cfop") == "1102",
           "auditoria do valor original na copia")
    checar(nota.itens[0].cfop == "1102",
           "ORIGINAL NAO PODE ser alterado")
    checar(corrigida.itens[1].corrigido_de == {},
           "item 1403 nao devia ser marcado")

    # Agrupamentos recalculados: 1102/000 virou 1403 -> ainda 2 grupos
    # (CSTs distintos), e o grupo corrigido carrega o original.
    comp = compor_nota(corrigida)
    checar(len(comp.grupos) == 2, f"grupos apos correcao: {len(comp.grupos)}")
    cfops = {g.cfop for g in comp.grupos}
    checar(cfops == {"1403"}, f"CFOPs apos correcao: {cfops}")
    checar(any(g.corrigido_de.get("cfop") == "1102" for g in comp.grupos),
           "grupo corrigido deveria apontar o original")

    # Sem correcao ativa -> valores originais (precedencia item 2)
    checar(aplicar_correcoes(nota, []) is nota,
           "sem correcoes deveria devolver a propria nota")

    # ---- Reversao preserva o registro e desativa o efeito ----
    store.reverter_correcao(correcao.id, "supervisor")
    revertidas = store.correcoes_da_chave(CHAVE)
    checar(revertidas[0].status == "revertida", "status apos reverter")
    checar(aplicar_correcoes(nota, revertidas).itens[0].cfop == "1102",
           "correcao revertida nao pode mais valer")

    # ---- Correcao automatica (em lote) registra o tipo ----
    auto = store.registrar_correcao(
        "2" * 44, "cst_icms", "000", "060", "rotina",
        tipo=TIPO_AUTOMATICA, motivo="regra ST")
    checar(auto.tipo == "automatica", f"tipo automatica: {auto.tipo}")
    checar(len(store.todas_correcoes()) == 2, "todas_correcoes por chave")

    store.fechar()
    os.unlink(db)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - correcoes (validacao, auditoria, precedencia, reversao) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
