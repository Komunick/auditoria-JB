"""Teste do motor de auditoria/correcao de produtos (dados sinteticos)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.base_legal import carregar_base_legal  # noqa: E402
from auditoria_fiscal.core.cadastro_produtos import ProdutoCadastro  # noqa: E402
from auditoria_fiscal.ferramentas.auditoria_produtos import (  # noqa: E402
    CONF_ALTA, CONF_MEDIA, MSG_ST_COMO_TRIBUTADO, MSG_TRIBUTADO_COMO_ST,
    TIPO_CEST_INCOMPATIVEL, TIPO_DIVERGENCIA_DESCRICAO, TIPO_NCM_AUSENTE,
    TIPO_NCM_INVALIDO, TIPO_ST_COMO_TRIBUTADO, TIPO_TRIBUTACAO_DIVERGENTE,
    TIPO_TRIBUTADO_COMO_ST, TRIB_INTEGRAL, TRIB_ISENTO, TRIB_MONOFASICO,
    TRIB_ST, auditar_produtos, calcular_indicadores,
    formatar_cst_como_original, normalizar_cst,
)
from auditoria_fiscal.ferramentas.correcao_produtos import (  # noqa: E402
    CABECALHO_HISTORICO, aplicar_correcoes, selecionar_alta_confianca,
)

ANEXO1 = """# AMOSTRA sintetica para teste (nao usar em producao)
cest;ncm;descricao;segmento;fundamentacao
03.002.00;2202.10.00;Refrigerante;Refrigerantes;Anexo I RICMS/BA, Conv. ICMS 142/18, seg. 03
17.031.00;1704;Balas e gomas de mascar;Produtos alimenticios;Anexo I RICMS/BA, Conv. ICMS 142/18, seg. 17
20.015.00;3305.10.00;Shampoo para o cabelo;Perfumaria e higiene;Anexo I RICMS/BA, Conv. ICMS 142/18, seg. 20
"""

MONOFASICO = """# combustiveis com ICMS monofasico
ncm;descricao;fundamentacao;detalhe
2710125;Gasolina;LC 192/2022, Conv. ICMS 199/22;
"""

ISENCAO = """ncm;descricao;fundamentacao;detalhe
0702;Tomate in natura;Conv. ICM 44/75;
"""

PARAMETROS = '{"uf": "BA", "aliquota_interna_padrao": 20.5}'


def montar_dados(pasta: str) -> None:
    conteudos = {
        "anexo1_ba.csv": ANEXO1,
        "monofasico.csv": MONOFASICO,
        "isencao_ba.csv": ISENCAO,
        "parametros.json": PARAMETROS,
    }
    for nome, texto in conteudos.items():
        with open(os.path.join(pasta, nome), "w", encoding="utf-8-sig") as fh:
            fh.write(texto)


def montar_produtos() -> list[ProdutoCadastro]:
    return [
        ProdutoCadastro(indice=0, codigo="P1", descricao="REFRIGERANTE COLA 2L",
                        ncm="22021000", cest="", cfops=["5102"], cst="00",
                        aliquota=Decimal("20.5")),
        ProdutoCadastro(indice=1, codigo="P2", descricao="PARAFUSO SEXTAVADO M8",
                        ncm="73181500", cest="", cfops=["5405"], cst="060",
                        aliquota=None),
        ProdutoCadastro(indice=2, codigo="P3", descricao="BALA DE GOMA SORTIDA",
                        ncm="17041000", cest="1703100", cfops=["5405"],
                        cst="60", aliquota=None),
        ProdutoCadastro(indice=3, codigo="P4", descricao="PRODUTO GENERICO XYZ",
                        ncm="123", cest="", cfops=["5102"], cst="",
                        aliquota=None),
        ProdutoCadastro(indice=4, codigo="P5", descricao="SHAMPOO ANTICASPA 200ML",
                        ncm="33051000", cest="", cfops=["5102"], cst="102",
                        aliquota=None),
        ProdutoCadastro(indice=5, codigo="P6", descricao="GASOLINA COMUM",
                        ncm="27101259", cest="", cfops=["5102"], cst="00",
                        aliquota=Decimal("20.5")),
        ProdutoCadastro(indice=6, codigo="P7", descricao="TOMATE IN NATURA",
                        ncm="07020000", cest="", cfops=["5102"], cst="40",
                        aliquota=None),
        ProdutoCadastro(indice=7, codigo="P8", descricao="REFRIGERANTE GUARANA 350ML",
                        ncm="", cest="", cfops=[], cst="", aliquota=None),
        ProdutoCadastro(indice=8, codigo="P9", descricao="BALAS E GOMAS DIVERSAS",
                        ncm="17041000", cest="1703101", cfops=["5405"],
                        cst="60", aliquota=None),
    ]


def main() -> int:
    falhas: list[str] = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    # normalizar_cst / formatar_cst_como_original
    checar(normalizar_cst("060") == ("0", "60", "normal"), "normalizar 060")
    checar(normalizar_cst("60") == ("", "60", "normal"), "normalizar 60")
    checar(normalizar_cst("102") == ("", "102", "simples"), "normalizar 102")
    checar(normalizar_cst("0102") == ("0", "102", "simples"), "normalizar 0102")
    checar(normalizar_cst("160") == ("1", "60", "normal"), "normalizar 160")
    checar(normalizar_cst("900") == ("", "900", "simples"), "normalizar 900")
    checar(formatar_cst_como_original("060", "00") == "000", "formatar 060->000")
    checar(formatar_cst_como_original("60", "00") == "00", "formatar 60->00")
    checar(formatar_cst_como_original("0500", "102") == "0102",
           "formatar 0500->0102")
    checar(formatar_cst_como_original("", "60") == "60", "formatar vazio->60")

    pasta_tmp = tempfile.mkdtemp(prefix="aud_prod_")
    try:
        pasta_dados = os.path.join(pasta_tmp, "dados")
        os.makedirs(pasta_dados)
        montar_dados(pasta_dados)
        base = carregar_base_legal(pasta_dados)
        checar(len(base.anexo1) == 3, f"anexo1: {len(base.anexo1)}")
        checar(base.aliquota_padrao == Decimal("20.5"),
               f"aliquota padrao: {base.aliquota_padrao}")

        produtos = montar_produtos()
        resultados = auditar_produtos(produtos, base)
        checar(len(resultados) == 9, f"resultados: {len(resultados)}")
        r1, r2, r3, r4, r5, r6, r7, r8, r9 = resultados

        # 1. refrigerante: ST vendido como tributado (ncm8, conf alta).
        checar(r1.situacao == "INCONSISTENTE", f"r1 situacao: {r1.situacao}")
        checar(TIPO_ST_COMO_TRIBUTADO in r1.tipos, f"r1 tipos: {r1.tipos}")
        checar(MSG_ST_COMO_TRIBUTADO in [i.mensagem for i in r1.inconsistencias],
               "r1 mensagem exata ausente")
        checar(r1.tributacao_atual == TRIB_INTEGRAL, f"r1 atual: {r1.tributacao_atual}")
        checar(r1.tributacao_sugerida == TRIB_ST, f"r1 sugerida: {r1.tributacao_sugerida}")
        checar(r1.correcoes.get("cst") == "60", f"r1 cst: {r1.correcoes}")
        checar(r1.correcoes.get("cest") == "0300200", f"r1 cest: {r1.correcoes}")
        checar(r1.cfop_map == {"5102": "5405"}, f"r1 cfop_map: {r1.cfop_map}")
        checar(r1.confianca == CONF_ALTA, f"r1 confianca: {r1.confianca}")
        checar(r1.match_anexo1 is not None and r1.match_anexo1.criterio == "ncm8",
               "r1 criterio do match")

        # 2. parafuso: tributado vendido como ST (conf alta, sem match).
        checar(r2.situacao == "INCONSISTENTE", f"r2 situacao: {r2.situacao}")
        checar(TIPO_TRIBUTADO_COMO_ST in r2.tipos, f"r2 tipos: {r2.tipos}")
        checar(MSG_TRIBUTADO_COMO_ST in [i.mensagem for i in r2.inconsistencias],
               "r2 mensagem exata ausente")
        checar(r2.correcoes.get("cst") == "000", f"r2 cst: {r2.correcoes}")
        checar(r2.correcoes.get("aliquota") == "20,5", f"r2 aliq: {r2.correcoes}")
        checar(r2.cfop_map == {"5405": "5102"}, f"r2 cfop_map: {r2.cfop_map}")
        checar(r2.confianca == CONF_ALTA, f"r2 confianca: {r2.confianca}")

        # 3. bala: ST correto (cest + prefixo 1704) -> OK.
        checar(r3.situacao == "OK", f"r3 situacao: {r3.situacao} ({r3.tipos})")
        checar(r3.tributacao_atual == TRIB_ST and r3.tributacao_sugerida == TRIB_ST,
               f"r3 trib: {r3.tributacao_atual} x {r3.tributacao_sugerida}")
        checar(not r3.tem_correcao, f"r3 correcoes: {r3.correcoes}")
        checar(r3.confianca == "", f"r3 confianca: {r3.confianca}")

        # 4. NCM invalido.
        checar(r4.situacao == "INCONSISTENTE", f"r4 situacao: {r4.situacao}")
        checar(r4.tipos == TIPO_NCM_INVALIDO, f"r4 tipos: {r4.tipos}")
        checar(not r4.tem_correcao, f"r4 correcoes: {r4.correcoes}")

        # 5. shampoo Simples Nacional: correcao CSOSN 500.
        checar(TIPO_ST_COMO_TRIBUTADO in r5.tipos, f"r5 tipos: {r5.tipos}")
        checar(r5.correcoes.get("cst") == "500", f"r5 cst: {r5.correcoes}")
        checar(r5.correcoes.get("cest") == "2001500", f"r5 cest: {r5.correcoes}")
        checar(r5.cfop_map == {"5102": "5405"}, f"r5 cfop_map: {r5.cfop_map}")
        checar(r5.confianca == CONF_ALTA, f"r5 confianca: {r5.confianca}")

        # 6. gasolina: sugerida monofasico, divergencia sem auto-correcao.
        checar(r6.tributacao_sugerida == TRIB_MONOFASICO,
               f"r6 sugerida: {r6.tributacao_sugerida}")
        checar(TIPO_TRIBUTACAO_DIVERGENTE in r6.tipos, f"r6 tipos: {r6.tipos}")
        msg_div = (f"Tributacao atual ({TRIB_INTEGRAL}) diverge da sugerida "
                   f"({TRIB_MONOFASICO}).")
        checar(msg_div in [i.mensagem for i in r6.inconsistencias],
               "r6 mensagem de divergencia")
        checar(not r6.tem_correcao, f"r6 correcoes: {r6.correcoes}")
        checar(r6.confianca == CONF_MEDIA, f"r6 confianca: {r6.confianca}")

        # 7. tomate isento: OK, sem erro de CST x aliquota.
        checar(r7.situacao == "OK", f"r7 situacao: {r7.situacao} ({r7.tipos})")
        checar(r7.tributacao_atual == TRIB_ISENTO and
               r7.tributacao_sugerida == TRIB_ISENTO,
               f"r7 trib: {r7.tributacao_atual} x {r7.tributacao_sugerida}")

        # 8. sem NCM, descricao de item de ST -> alerta de divergencia.
        checar(TIPO_NCM_AUSENTE in r8.tipos, f"r8 tipos: {r8.tipos}")
        checar(TIPO_DIVERGENCIA_DESCRICAO in r8.tipos, f"r8 tipos: {r8.tipos}")
        checar(r8.situacao == "INCONSISTENTE", f"r8 situacao: {r8.situacao}")

        # 9. bala com CEST divergente do Anexo I -> so alerta (conf media).
        checar(r9.situacao == "ALERTA", f"r9 situacao: {r9.situacao} ({r9.tipos})")
        checar(r9.tipos == TIPO_CEST_INCOMPATIVEL, f"r9 tipos: {r9.tipos}")
        checar(not r9.tem_correcao, f"r9 correcoes: {r9.correcoes}")

        # Indicadores.
        ind = calcular_indicadores(resultados)
        checar(ind["total"] == 9, f"total: {ind['total']}")
        checar(ind["corretos"] == 2, f"corretos: {ind['corretos']}")
        checar(ind["inconsistentes"] == 6, f"inconsistentes: {ind['inconsistentes']}")
        checar(ind["alertas"] == 1, f"alertas: {ind['alertas']}")
        checar(ind["percentual_inconsistencias"] == 66.7,
               f"percentual: {ind['percentual_inconsistencias']}")
        checar(ind["sujeitos_st"] == 4, f"sujeitos_st: {ind['sujeitos_st']}")
        checar(ind["st_incorretos"] == 3, f"st_incorretos: {ind['st_incorretos']}")
        checar(ind["corrigidos"] == 0, f"corrigidos: {ind['corrigidos']}")
        checar(ind["por_tipo"].get(TIPO_ST_COMO_TRIBUTADO) == 2,
               f"por_tipo ST: {ind['por_tipo']}")
        checar(ind["por_tipo"].get(TIPO_TRIBUTADO_COMO_ST) == 1,
               f"por_tipo trib: {ind['por_tipo']}")
        checar(ind["por_tipo"].get(TIPO_NCM_INVALIDO) == 1,
               f"por_tipo ncm: {ind['por_tipo']}")

        # Selecao de alta confianca.
        alta = selecionar_alta_confianca(resultados)
        codigos_alta = sorted(r.produto.codigo for r in alta)
        checar(codigos_alta == ["P1", "P2", "P5"], f"alta confianca: {codigos_alta}")

        # Aplicacao das correcoes + historico (em pasta temporaria).
        historico = os.path.join(pasta_tmp, "historico_produtos.csv")
        alteracoes = aplicar_correcoes(resultados, "cadastro_teste.xlsx",
                                       caminho_historico=historico)
        checar(sorted(alteracoes) == [0, 1, 4], f"indices: {sorted(alteracoes)}")
        checar(alteracoes[0] == {"cst": "60", "cest": "0300200",
                                 "cfop_map": {"5102": "5405"}},
               f"alteracoes[0]: {alteracoes[0]}")
        checar(alteracoes[1] == {"cst": "000", "aliquota": "20,5",
                                 "cfop_map": {"5405": "5102"}},
               f"alteracoes[1]: {alteracoes[1]}")
        checar(alteracoes[4] == {"cst": "500", "cest": "2001500",
                                 "cfop_map": {"5102": "5405"}},
               f"alteracoes[4]: {alteracoes[4]}")
        checar(r1.status_correcao == "Corrigido", f"r1 status: {r1.status_correcao}")
        checar(r3.status_correcao == "Nao corrigido", f"r3 status: {r3.status_correcao}")

        with open(historico, encoding="utf-8-sig") as fh:
            linhas_hist = [ln for ln in fh.read().splitlines() if ln]
        checar(linhas_hist[0] == ";".join(CABECALHO_HISTORICO),
               f"cabecalho historico: {linhas_hist[0]}")
        checar(len(linhas_hist) == 10, f"linhas historico: {len(linhas_hist)}")
        checar(any(";cfop 5405->5102;5405;5102;" in ln for ln in linhas_hist),
               "linha de cfop no historico")
        checar(any(";cst;060;000;" in ln for ln in linhas_hist),
               "linha de cst no historico")
        checar(any(";aliquota;;20,5;" in ln for ln in linhas_hist),
               "linha de aliquota no historico")

        ind2 = calcular_indicadores(resultados)
        checar(ind2["corrigidos"] == 3, f"corrigidos apos: {ind2['corrigidos']}")

        # Segunda aplicacao anexa sem duplicar o cabecalho.
        aplicar_correcoes([r1], "cadastro_teste.xlsx",
                          caminho_historico=historico)
        with open(historico, encoding="utf-8-sig") as fh:
            linhas_hist2 = [ln for ln in fh.read().splitlines() if ln]
        checar(len(linhas_hist2) == 13, f"linhas apos 2a: {len(linhas_hist2)}")
        checar(linhas_hist2.count(";".join(CABECALHO_HISTORICO)) == 1,
               "cabecalho duplicado no historico")
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - auditoria de produtos passou.")
    print(f"  {len(resultados)} produtos | {ind['inconsistentes']} inconsistentes "
          f"| {ind['sujeitos_st']} sujeitos a ST | {ind2['corrigidos']} corrigidos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
