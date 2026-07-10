"""Teste do Livro Fiscal em PDF (ordem dos campos, correcoes, sem data conf.)."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.correcoes import Correcao  # noqa: E402
from auditoria_fiscal.core.modelos import (  # noqa: E402
    ItemNota, NotaFiscal, Participante,
)
from auditoria_fiscal.ferramentas.conferencia_store import (  # noqa: E402
    EstadoConferencia,
)
from auditoria_fiscal.ferramentas.livro_fiscal import (  # noqa: E402
    gerar_livro_fiscal, montar_blocos,
)
from auditoria_fiscal.ferramentas.livro_inconsistencias import (  # noqa: E402
    montar_blocos_inconsistencias,
)

D = Decimal
CHAVE = "35260399888777000166550010000010011123456780"
DATA_CONF = "08/07/2026 10:00"


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    nota = NotaFiscal(
        chave=CHAVE, numero="101", serie="1",
        valor_documento=D("500.00"), valor_mercadoria=D("500.00"),
        participante=Participante(nome="FORNECEDOR ALPHA", uf="SP"),
        itens=[
            ItemNota(cfop="1102", cst_icms="000", aliq_icms=D("20.50"),
                     valor_item=D("200.00"), vl_bc_icms=D("200.00"),
                     vl_icms=D("41.00")),
            ItemNota(cfop="1403", cst_icms="060", valor_item=D("300.00")),
        ])
    estados = {CHAVE: EstadoConferencia(CHAVE, conferida=True,
                                        observacao="CFOP a revisar",
                                        data_conferencia=DATA_CONF)}
    correcoes = {CHAVE: [Correcao(id=1, chave=CHAVE, campo="cfop",
                                  valor_original="1102",
                                  valor_corrigido="1403",
                                  usuario="ana", data_hora="09/07/2026 09:00",
                                  tipo="manual", motivo="uso e consumo")]}

    # ---- Cenario 5: blocos do Livro Fiscal ----
    blocos = montar_blocos([nota], estados, correcoes)
    checar(len(blocos) == 1, f"blocos: {len(blocos)}")
    b = blocos[0]

    # UF na identificacao (da chave: 35 -> SP)
    checar("UF SP" in b["titulo"], f"titulo sem UF: {b['titulo']}")
    checar("R$ 500,00" in b["total"], f"total: {b['total']}")

    # Ordem dentro do grupo: CFOP -> Valor Contabil -> Base -> Aliq -> ICMS
    grupo_icms = next(g for g in b["grupos"] if any("Aliquota" in l for l in g))
    checar(grupo_icms[0].startswith("CFOP:"),
           f"CFOP deve vir primeiro: {grupo_icms[0]}")
    checar(grupo_icms[1].startswith("Valor Contabil:"),
           f"valor contabil apos CFOP: {grupo_icms[1]}")
    checar(grupo_icms[2].startswith("Base de Calculo:"),
           f"base apos valor contabil: {grupo_icms[2]}")
    checar(grupo_icms[3].startswith("Aliquota: 20,50%"),
           f"aliquota: {grupo_icms[3]}")
    checar(grupo_icms[4].startswith("Valor do ICMS: R$ 41,00"),
           f"icms: {grupo_icms[4]}")

    # Correcao aplicada e sinalizada; observacao presente (abaixo dos valores)
    checar("corrigido de 1102" in grupo_icms[0],
           f"correcao nao sinalizada: {grupo_icms[0]}")
    checar(b["observacao"] == "CFOP a revisar", "observacao ausente")
    checar(b["tem_correcao"], "bloco deveria indicar correcao")

    # Nao apresenta a data de conferencia em lugar nenhum
    conteudo = repr(blocos)
    checar(DATA_CONF not in conteudo,
           "data de conferencia NAO pode aparecer no Livro Fiscal")

    # ---- PDF gerado ----
    fd, caminho = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        gerar_livro_fiscal([nota], estados, caminho, contexto="EMPRESA DEMO",
                           correcoes_por_chave=correcoes)
        with open(caminho, "rb") as fh:
            inicio = fh.read(5)
        checar(inicio == b"%PDF-", f"nao parece PDF: {inicio!r}")
        checar(os.path.getsize(caminho) > 1000, "PDF suspeito de vazio")
    finally:
        os.unlink(caminho)

    # Sem notas -> ValueError
    try:
        gerar_livro_fiscal([], estados, caminho)
        falhas.append("sem notas deveria levantar ValueError")
    except ValueError:
        pass

    # ---- Cenario 6: relatorio de inconsistencias com correcoes ----
    blocos_inc = montar_blocos_inconsistencias([nota], estados, correcoes)
    checar(len(blocos_inc) == 1, "inconsistencias: 1 bloco")
    bi = blocos_inc[0]
    checar(any("1102 -> 1403" in t for t in bi["correcoes"]),
           f"trilha da correcao ausente: {bi['correcoes']}")
    checar(any("usuario: ana" in t for t in bi["correcoes"]),
           "usuario responsavel ausente")
    checar(any("tipo: manual" in t for t in bi["correcoes"]),
           "tipo de correcao ausente")
    checar(bi["inconsistencia"] == "CFOP a revisar", "descricao ausente")
    # Detalhe por aliquota: grupos com BC/aliquota/ICMS separados
    checar(any("Aliquota 20,50%" in g[0] for g in bi["grupos"]),
           f"detalhe por aliquota ausente: {[g[0] for g in bi['grupos']]}")
    checar(any("Base de Calculo" in g[1] for g in bi["grupos"]),
           "base de calculo ausente no detalhe")

    # Nota so com correcao (sem observacao) tambem entra no relatorio
    blocos_so_corr = montar_blocos_inconsistencias([nota], {}, correcoes)
    checar(len(blocos_so_corr) == 1,
           "nota com correcao sem observacao deveria entrar no relatorio")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - Livro Fiscal e relatorio de inconsistencias passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
