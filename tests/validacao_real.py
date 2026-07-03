"""Validacao do pipeline completo usando o SPED REAL + uma relacao SEFAZ
gerada no formato exato do template do cliente (abas 'Arquivo Sefaz' e 'Sped').

Prova que, dado o SPED real, a ferramenta identifica corretamente:
  - notas faltantes no SPED (na SEFAZ e nao escrituradas);
  - divergencia de valor;
  - nota cancelada na SEFAZ porem escriturada como regular.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from openpyxl import Workbook  # noqa: E402

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.core.sefaz_relacao import ler_relacao_sefaz  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sefaz import comparar  # noqa: E402
from auditoria_fiscal.ferramentas.relatorio_excel import gerar_relatorio  # noqa: E402

SPED = r"C:\Users\brazil\Downloads\JB\052026E0001_I.txt"
AMOSTRAS = os.path.join(RAIZ, "amostras")

# Cabecalho identico ao da planilha real do cliente.
CABECALHO = ["Numero NF-e", "CNPJ/CPF Emitente", "Razao Social Emitente",
             "Data de Emissao", "Valor", "Chave de Acesso", "NAO EXCLUIR",
             "UF Emit.", "Situacao", "Tipo Operacao", "NAO EXCLUIR   Situacao"]

FAKES = [f"{'9' * 40}{i:04d}" for i in range(5)]   # 5 faltantes (autorizadas)
FAKE_CANCELADA = "8" * 40 + "0001"                 # cancelada -> nao e pendencia


def brl(valor) -> str:
    return f"{float(valor):.2f}".replace(".", ",")


def montar_sefaz(caminho, entradas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Arquivo Sefaz"
    ws.append(CABECALHO)

    reais = [n for n in entradas if n.situacao in ("00", "")][:15]

    for i, n in enumerate(reais):
        valor = n.valor_documento
        situacao = "Autorizada"
        if i == 0:
            valor = n.valor_documento - Decimal("100.00")   # divergencia
        elif i == 1:
            situacao = "Cancelada"                           # cancelada escriturada
        forn = n.participante.nome if n.participante else ""
        ws.append([n.numero, n.cnpj_emitente, forn, "05/05/2026", brl(valor),
                   n.chave, "", "BA", situacao, "Entrada", ""])

    # Faltantes: autorizadas, ausentes no SPED
    for i, ch in enumerate(FAKES):
        ws.append([f"F{i}", "11111111000191", "FORNECEDOR FAKE " + str(i),
                   "10/05/2026", "1000,00", ch, "", "BA", "Autorizada", "Entrada", ""])
    # Cancelada ausente no SPED: NAO deve virar pendencia
    ws.append(["FC", "11111111000191", "FORNECEDOR FAKE CANC", "10/05/2026",
               "500,00", FAKE_CANCELADA, "", "BA", "Cancelada", "Entrada", ""])

    wb.create_sheet("Sped")   # aba auxiliar vazia, como no template real
    wb.save(caminho)
    return reais


def main() -> int:
    os.makedirs(AMOSTRAS, exist_ok=True)
    caminho_sefaz = os.path.join(AMOSTRAS, "exemplo_sefaz_preenchida.xlsx")
    caminho_rel = os.path.join(AMOSTRAS, "exemplo_relatorio.xlsx")

    print("Lendo SPED real...")
    doc = ler_sped(SPED)
    entradas = [n for n in doc.notas
                if n.ind_oper == "0" and len(n.chave_normalizada) == 44]
    print(f"  {len(doc.notas)} notas | {len(entradas)} entradas com chave")

    reais = montar_sefaz(caminho_sefaz, entradas)
    print(f"Relacao SEFAZ de teste: {len(reais)} chaves reais + {len(FAKES)} "
          f"faltantes + 1 cancelada ausente")

    registros, diag = ler_relacao_sefaz(caminho_sefaz)
    print("Aba/colunas detectadas:", diag["mapa_colunas"])
    print("Registros lidos:", diag["registros_validos"])

    resultado = comparar(doc, registros)
    r = resultado.resumo()
    print("Resumo:", r)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    checar("chave" in diag["mapa_colunas"], "chave nao mapeada")
    checar("situacao" in diag["mapa_colunas"], "situacao nao mapeada")
    checar(diag["registros_validos"] == len(reais) + len(FAKES) + 1,
           f"registros lidos: {diag['registros_validos']}")
    checar(r["faltantes_no_sped"] == len(FAKES),
           f"faltantes esperado {len(FAKES)}, obtido {r['faltantes_no_sped']}")
    checar(r["divergencias_valor"] == 1, f"divergencias: {r['divergencias_valor']}")
    checar(r["canceladas_escrituradas"] == 1, f"canceladas: {r['canceladas_escrituradas']}")

    # As faltantes devem ser exatamente as 5 fakes autorizadas.
    chaves_faltantes = {reg.chave_normalizada for reg in resultado.faltantes_no_sped}
    checar(chaves_faltantes == set(FAKES),
           f"faltantes divergem do esperado: {chaves_faltantes ^ set(FAKES)}")
    # A cancelada ausente NAO pode estar entre as faltantes.
    checar(FAKE_CANCELADA not in chaves_faltantes,
           "cancelada ausente foi marcada como faltante (nao deveria)")

    gerar_relatorio(resultado, caminho_rel, nome_empresa=doc.empresa.nome)

    if falhas:
        print("\nFALHAS:")
        for f in falhas:
            print("  -", f)
        return 1

    print("\nOK - pipeline validado contra o SPED REAL.")
    print(f"  Empresa: {doc.empresa.nome}")
    print(f"  Faltantes detectadas corretamente: {sorted(chaves_faltantes)}")
    print(f"  Exemplo de relacao SEFAZ salvo em: {caminho_sefaz}")
    print(f"  Relatorio de conferencia salvo em: {caminho_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
