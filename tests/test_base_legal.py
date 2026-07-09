"""Teste das bases legais (pasta dados/ temporaria sintetica, autocontido)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.base_legal import (  # noqa: E402
    BaseLegal, carregar_base_legal, localizar_pasta_dados,
    normalizar_descricao, similaridade,
)

ANEXO1 = "\n".join([
    "# AMOSTRA sintetica de teste - nao usar em producao",
    "cest;ncm;descricao;segmento;fundamentacao",
    "03.002.00;2202.10.00;Refrigerante em embalagem pet;"
    "Cervejas e refrigerantes;Anexo I RICMS/BA seg. 03",
    "03.007.00;2202;Outras bebidas nao alcoolicas;"
    "Cervejas e refrigerantes;Anexo I RICMS/BA seg. 03",
    "",
    "# comentario no meio do arquivo",
    "17.031.00;1704;Balas e caramelos;Produtos alimenticios;"
    "Anexo I RICMS/BA seg. 17",
    "17.032.00;1704;Chicletes e gomas de mascar;Produtos alimenticios;"
    "Anexo I RICMS/BA seg. 17",
    "20.015.00;3305.10.00;Xampus para o cabelo;Perfumaria e higiene;"
    "Anexo I RICMS/BA seg. 20",
])

NCM_TIPI = "\n".join([
    "# Amostra pequena: validacao TIPI so ativa com >= 1000 linhas",
    "ncm;descricao",
    "2202.10.00;Refrigerantes",
    "1704.10.00;Gomas de mascar",
    "7318.15.00;Parafusos",
])

MONOFASICO = "\n".join([
    "# Combustiveis - ICMS monofasico",
    "ncm;descricao;fundamentacao;detalhe",
    "2710.12.5;Gasolina;LC 192/2022 - Conv. ICMS 199/22;",
    "2710;Oleos de petroleo;LC 192/2022;generico",
    "2207.10;Etanol;LC 192/2022 - Conv. ICMS 15/23;",
])

ISENCAO = "\n".join([
    "ncm;descricao;fundamentacao;detalhe",
    "0702;Tomate;Conv. ICM 44/75;in natura",
    "0701;Batata;Conv. ICM 44/75;in natura",
])

REDUCAO = "\n".join([
    "ncm;descricao;fundamentacao;detalhe",
    "1006;Arroz;Cesta basica BA;carga efetiva 7%",
])

PARAMETROS = {"uf": "BA", "aliquota_interna_padrao": 20.5,
              "vigencia_confirmada_em": "2026-07-01"}


def montar_pasta_dados(pasta: str) -> None:
    """Grava os CSVs sinteticos (diferimento_ba.csv fica ausente de proposito)."""
    arquivos = {
        "anexo1_ba.csv": ANEXO1,
        "ncm_tipi.csv": NCM_TIPI,
        "monofasico.csv": MONOFASICO,
        "isencao_ba.csv": ISENCAO,
        "reducao_base_ba.csv": REDUCAO,
    }
    for nome, conteudo in arquivos.items():
        with open(os.path.join(pasta, nome), "w",
                  encoding="utf-8-sig", newline="\n") as fh:
            fh.write(conteudo + "\n")
    with open(os.path.join(pasta, "parametros.json"), "w",
              encoding="utf-8") as fh:
        json.dump(PARAMETROS, fh)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="dados_teste_")
    pasta = os.path.join(tmp, "dados")
    os.makedirs(pasta)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    try:
        montar_pasta_dados(pasta)
        base = carregar_base_legal(pasta)

        # ---------------- carga geral ----------------
        checar(base.pasta == pasta, f"pasta: {base.pasta}")
        checar(len(base.anexo1) == 5, f"anexo1: {len(base.anexo1)} (esperado 5)")
        checar(base.anexo1[0].cest == "0300200",
               f"cest item 1: {base.anexo1[0].cest}")
        checar(base.anexo1[0].ncm == "22021000",
               f"ncm item 1: {base.anexo1[0].ncm}")
        checar(base.anexo1[0].segmento == "Cervejas e refrigerantes",
               f"segmento item 1: {base.anexo1[0].segmento}")
        checar(base.tipi == {"22021000", "17041000", "73181500"},
               f"tipi: {sorted(base.tipi)}")
        checar(base.tipi_ativa is False, "tipi_ativa devia ser False")
        checar(len(base.monofasico) == 3,
               f"monofasico: {len(base.monofasico)}")
        checar(base.monofasico[0].ncm == "2710125",
               f"ncm monofasico 1: {base.monofasico[0].ncm}")
        checar(len(base.isencao) == 2, f"isencao: {len(base.isencao)}")
        checar(len(base.reducao) == 1, f"reducao: {len(base.reducao)}")
        checar(base.diferimento == [], "diferimento devia ser vazio")
        checar(base.parametros.get("uf") == "BA",
               f"parametros uf: {base.parametros.get('uf')}")

        # ---------------- avisos p/ arquivo ausente ----------------
        checar(len(base.avisos) == 1, f"avisos: {base.avisos}")
        checar(base.avisos and "diferimento" in base.avisos[0].lower(),
               f"aviso sem diferimento: {base.avisos}")

        # ---------------- aliquota padrao ----------------
        checar(base.aliquota_padrao == Decimal("20.5"),
               f"aliquota_padrao: {base.aliquota_padrao}")
        checar(BaseLegal().aliquota_padrao == Decimal("20.5"),
               "fallback aliquota_padrao sem parametros")

        # ---------------- buscar_anexo1: criterio cest ----------------
        m = base.buscar_anexo1("17041000", "1703100", "Bala de goma")
        checar(m is not None and m.criterio == "cest",
               f"criterio cest: {m and m.criterio}")
        checar(m is not None and m.item.cest == "1703100",
               f"item cest: {m and m.item.cest}")
        checar(m is not None and m.tamanho_prefixo == 4,
               f"tamanho_prefixo cest: {m and m.tamanho_prefixo}")

        # prioridade cest > ncm8 (ncm casa item refrigerante em 8 digitos,
        # mas o cest do produto aponta para as balas)
        m = base.buscar_anexo1("22021000", "1703100", "Bala refrescante")
        checar(m is not None and m.criterio == "cest"
               and m.item.cest == "1703100",
               f"prioridade cest>ncm8: {m and (m.criterio, m.item.cest)}")

        # ---------------- buscar_anexo1: criterio ncm8 ----------------
        # (tambem cobre prioridade ncm8 > prefixo: o item ncm 2202 casa junto)
        m = base.buscar_anexo1("22021000", "", "Refrigerante de cola 2l")
        checar(m is not None and m.criterio == "ncm8",
               f"criterio ncm8: {m and m.criterio}")
        checar(m is not None and m.item.cest == "0300200",
               f"prioridade ncm8>prefixo: {m and m.item.cest}")
        checar(m is not None and m.tamanho_prefixo == 8,
               f"tamanho_prefixo ncm8: {m and m.tamanho_prefixo}")
        checar(m is not None and 0.0 <= m.similaridade <= 1.0,
               f"similaridade fora de 0..1: {m and m.similaridade}")

        # ---------------- buscar_anexo1: prefixo + desempate ----------------
        # dois itens com prefixo 1704: o desempate e pela similaridade.
        m = base.buscar_anexo1("17049020", "", "Goma de mascar sabor hortela")
        checar(m is not None and m.criterio == "ncm_prefixo",
               f"criterio prefixo: {m and m.criterio}")
        checar(m is not None and m.tamanho_prefixo == 4,
               f"tamanho_prefixo: {m and m.tamanho_prefixo}")
        checar(m is not None and m.item.cest == "1703200",
               f"desempate por similaridade: {m and m.item.cest}")

        # sem match
        checar(base.buscar_anexo1("84713012", "", "Notebook 15 pol") is None,
               "buscar_anexo1 devia retornar None")

        # ---------------- buscar_regra: prefixo mais longo ----------------
        r = base.buscar_regra(base.monofasico, "27101259")
        checar(r is not None and r.ncm == "2710125",
               f"regra prefixo longo: {r and r.ncm}")
        r = base.buscar_regra(base.monofasico, "27101921")
        checar(r is not None and r.ncm == "2710",
               f"regra prefixo curto: {r and r.ncm}")
        checar(base.buscar_regra(base.monofasico, "73181500") is None,
               "buscar_regra devia retornar None")
        checar(base.buscar_regra(base.monofasico, "") is None,
               "buscar_regra com ncm vazio devia retornar None")
        r = base.buscar_regra(base.isencao, "07020000")
        checar(r is not None and r.fundamentacao == "Conv. ICM 44/75",
               f"fundamentacao isencao: {r and r.fundamentacao}")
        r = base.buscar_regra(base.reducao, "10063021")
        checar(r is not None and r.detalhe == "carga efetiva 7%",
               f"detalhe reducao: {r and r.detalhe}")

        # ---------------- normalizacao e similaridade ----------------
        checar(normalizar_descricao("  Refrigerante, PET - 2L!!  ")
               == "refrigerante pet 2l",
               "normalizar_descricao com pontuacao")
        checar(normalizar_descricao("") == "", "normalizar_descricao vazia")
        sim = similaridade("Bala de goma sortida", "Balas de goma")
        checar(sim > 0.5, f"similaridade parecidas: {sim:.3f} (esperado > 0.5)")
        sim = similaridade("CAFE TORRADO E MOIDO", "cafe torrado e moido")
        checar(abs(sim - 1.0) < 1e-9, f"similaridade identicas: {sim:.3f}")
        sim = similaridade("Parafuso sextavado", "Refrigerante em embalagem pet")
        checar(sim < 0.5, f"similaridade distintas: {sim:.3f} (esperado < 0.5)")
        checar(similaridade("", "qualquer") == 0.0, "similaridade com vazio")

        # ---------------- pasta inexistente (tolerancia) ----------------
        base_vazia = carregar_base_legal(os.path.join(tmp, "nao_existe"))
        checar(base_vazia.anexo1 == [] and not base_vazia.tipi_ativa,
               "base de pasta inexistente devia ser vazia")
        checar(len(base_vazia.avisos) == 7,
               f"avisos pasta inexistente: {len(base_vazia.avisos)}")

        # ---------------- localizar_pasta_dados ----------------
        achada = localizar_pasta_dados()
        checar(achada is None or os.path.isdir(achada),
               f"localizar_pasta_dados invalida: {achada}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - base legal passou.")
    print(f"  {len(base.anexo1)} itens anexo1 | {len(base.tipi)} ncm tipi | "
          f"{len(base.monofasico)} monofasico | aliquota "
          f"{base.aliquota_padrao}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
