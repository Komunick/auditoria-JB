"""Nucleo da Antecipacao/DIFAL do ICMS-BA (spec 027).

Os numeros esperados vem dos dois documentos de origem: a tabela da secao 5
da especificacao do Fiscal (metodo por dentro) e o exemplo didatico do
prototipo (diferenca simples). Uma conferencia independente com fracoes exatas
garante que a precisao intermediaria nao e' arredondada no meio da conta.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import antecipacao_ba as ab  # noqa: E402
from auditoria_fiscal.core.antecipacao_nfe import NFeInvalida, ler_nfe  # noqa: E402

import nfe_sintetica as fab  # noqa: E402

D = Decimal


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def levanta(funcao, codigo: str, msg: str):
    try:
        funcao()
    except ab.ErroAntecipacao as exc:
        checar(exc.codigo == codigo, f"{msg}: veio {exc.codigo}")
        return
    checar(False, f"{msg}: deveria recusar")


TABELA = ab.TabelaAliquotas(ab.aliquotas_iniciais())
POR_DENTRO = ab.validar_parametros(ab.METODO_POR_DENTRO, presuncao=True)
SEM_PRESUNCAO = ab.validar_parametros(ab.METODO_POR_DENTRO)
SIMPLES = ab.validar_parametros(ab.METODO_DIFERENCA, presuncao=True)


def avaliar(xml: bytes, parametros=POR_DENTRO, finalidade="revenda",
            tabela=TABELA, indice=0) -> dict:
    nota = ler_nfe(xml)
    return ab.avaliar_item(nota.itens[indice], nota, parametros, tabela,
                           finalidade)


def codigos(resultado: dict, tipo: str | None = None) -> set[str]:
    return {p["codigo"] for p in resultado["pendencias"]
            if tipo is None or p["tipo"] == tipo}


def exato(valor: str, credito: str, aliquota: str, metodo: str) -> Decimal:
    """A mesma conta com fracoes exatas, arredondada so no fim."""
    v, c, a = Fraction(valor), Fraction(credito), Fraction(aliquota) / 100
    if metodo == ab.METODO_POR_DENTRO:
        resultado = (v - c) / (1 - a) * a - c
    else:
        resultado = v * a - c
    return D(resultado.numerator) .__truediv__(D(resultado.denominator)) \
        .quantize(D("0.01"), rounding=ROUND_HALF_UP)


def main() -> int:
    # ------------------------------------------------------------------
    # Secao 5 da especificacao: os tres exemplos, linha por linha

    exemplos = [
        ("SP com destaque", "70.00", "930.00", "1169.81", "239.81", "169.81"),
        ("GO sem destaque", "120.00", "880.00", "1106.92", "226.92", "106.92"),
        ("Importado", "40.00", "960.00", "1207.55", "247.55", "207.55"),
    ]
    for nome, credito, sem, base, interno, difal in exemplos:
        c = ab.calcular(D("1000.00"), D(credito), D("20.5"), ab.METODO_POR_DENTRO)
        checar(c.divisor == D("0.795"), f"{nome}: divisor {c.divisor}")
        checar((c.valor_sem_icms, c.base_calculo, c.icms_interno, c.a_recolher)
               == (D(sem), D(base), D(interno), D(difal)),
               f"{nome}: {c}")

    # Os mesmos exemplos saindo do XML, com a tabela de aliquotas inicial.
    r = avaliar(fab.nota_sp_com_destaque())
    checar(r["memoria"]["tipo_credito"] == ab.CREDITO_DESTACADO, r["memoria"])
    checar(r["a_recolher"] == D("169.81"), r["a_recolher"])
    checar(r["memoria"]["aliquota_interestadual"] == "7", r["memoria"])
    checar(ab.decisao_automatica(r["pendencias"], r["a_recolher"])
           == ab.DECISAO_CALCULAR, f"nota limpa deveria ser proposta: {r['pendencias']}")

    r = avaliar(fab.nota_go_sem_destaque())
    checar(r["memoria"]["tipo_credito"] == ab.CREDITO_CALCULADO, r["memoria"])
    checar(r["memoria"]["credito"] == "120.00", r["memoria"]["credito"])
    checar(r["a_recolher"] == D("106.92"), r["a_recolher"])
    checar(ab.P_CREDITO_CALCULADO in codigos(r, ab.AVISO), r["pendencias"])
    checar(ab.P_FORNECEDOR_SIMPLES in codigos(r, ab.AVISO), r["pendencias"])

    r = avaliar(fab.nota_importado_sem_destaque())
    checar(r["memoria"]["aliquota_interestadual"] == "4", r["memoria"])
    checar(r["memoria"]["credito"] == "40.00", r["memoria"]["credito"])
    checar(r["a_recolher"] == D("207.55"), r["a_recolher"])

    # Origens 6 e 7 (importado sem similar) NAO usam os 4%.
    xml = fab.xml_nfe([fab.item(grupo="ICMSSN102", cst="102", orig="6")],
                      uf="SP", crt="1")
    checar(avaliar(xml)["memoria"]["aliquota_interestadual"] == "7",
           "origem 6 deveria usar a aliquota da UF")

    # ------------------------------------------------------------------
    # Prototipo: diferenca simples e reducao de 20%

    for aliquota, esperado in (("4", "1650.00"), ("7", "1350.00"),
                               ("12", "850.00")):
        credito = D("10000") * D(aliquota) / 100
        c = ab.calcular(D("10000"), credito, D("20.5"), ab.METODO_DIFERENCA)
        checar(c.a_recolher == D(esperado), f"{aliquota}%: {c.a_recolher}")
        checar(c.divisor is None and c.base_calculo == D("10000.00"), c)

    grupos = [("7", "10000"), ("4", "5000"), ("12", "8000"), ("12", "3000"),
              ("4", "4000")]
    total = sum(ab.calcular(D(base), D(base) * D(aliq) / 100, D("20.5"),
                            ab.METODO_DIFERENCA).a_recolher
                for aliq, base in grupos)
    checar(total == D("3770.00"), f"total do prototipo: {total}")
    reducao = ab.reducao_simulada(total, D("20"))
    checar((reducao, total - reducao) == (D("754.00"), D("3016.00")), reducao)

    # A memoria mostra quanto daria pelo OUTRO metodo (pendencia P-01).
    r = avaliar(fab.nota_sp_com_destaque())
    checar(r["memoria"]["comparativo"] == {
        "metodo": ab.METODO_DIFERENCA, "a_recolher": "135.00"},
        r["memoria"]["comparativo"])
    r = avaliar(fab.nota_sp_com_destaque(), SIMPLES)
    checar(r["a_recolher"] == D("135.00"), r["a_recolher"])
    checar(r["memoria"]["comparativo"]["a_recolher"] == "169.81", r["memoria"])

    # ------------------------------------------------------------------
    # Precisao: arredonda so no fim (conferido com fracoes exatas)

    for valor, credito in (("333.33", "23.33"), ("1234.57", "86.42"),
                           ("19.99", "1.40"), ("87654.32", "10518.52"),
                           ("0.07", "0.00"), ("457.13", "54.86"),
                           ("999.99", "40.00"), ("12.35", "0.86")):
        for metodo in ab.METODOS:
            c = ab.calcular(D(valor), D(credito), D("20.5"), metodo)
            esperado = exato(valor, credito, "20.5", metodo)
            checar(c.a_recolher == esperado,
                   f"{metodo} {valor}/{credito}: {c.a_recolher} != {esperado}")

    # Credito de referencia: e' intermediario e NAO e' arredondado antes da
    # conta. Nestes casos, arredondar o credito primeiro muda o centavo final
    # (R$ 10,08 a 4% e R$ 10,22 a 7%, achados por varredura).
    for valor, uf, orig, certo, torto in (
            ("10.08", "SP", "1", "2.09", "2.10"),
            ("10.22", "SP", "0", "1.74", "1.73")):
        xml = fab.xml_nfe([fab.item(v_prod=valor, grupo="ICMSSN102", cst="102",
                                    orig=orig)], uf=uf, crt="1")
        r = avaliar(xml)
        aliquota = r["memoria"]["aliquota_interestadual"]
        credito_exato = Fraction(valor) * Fraction(aliquota) / 100
        esperado = exato(valor, str(credito_exato), "20.5", ab.METODO_POR_DENTRO)
        checar(str(esperado) == certo, f"conferencia da amostra: {esperado}")
        checar(r["a_recolher"] == D(certo),
               f"{valor} a {aliquota}%: {r['a_recolher']} (com o credito "
               f"arredondado antes daria {torto})")

    # Meio centavo exato sobe: R$ 1,00 x 20,5% = 0,205 -> 0,21 (e nao 0,20).
    checar(ab.calcular(D("1.00"), D("0"), D("20.5"), ab.METODO_DIFERENCA)
           .a_recolher == D("0.21"), "arredondamento do meio centavo")
    checar(ab.arredondar(D("2.675")) == D("2.68")
           and ab.arredondar(D("2.665")) == D("2.67"), "meio para cima")

    # O MESMO credito na base e no abatimento (secao 3).
    c = ab.calcular(D("1000"), D("70"), D("20.5"), ab.METODO_POR_DENTRO)
    checar(c.valor_sem_icms == c.valor_operacao - c.credito, c)
    checar(c.a_recolher == c.icms_interno - c.credito, c)

    # ------------------------------------------------------------------
    # Sem destaque e sem autorizacao: nao calcula e NAO vira zero

    r = avaliar(fab.nota_go_sem_destaque(), SEM_PRESUNCAO)
    checar(r["a_recolher"] is None, f"deveria ficar sem valor: {r['a_recolher']}")
    checar(r["memoria"]["a_recolher"] is None and r["memoria"]["credito"] is None,
           r["memoria"])
    checar(ab.P_SEM_DESTAQUE in codigos(r, ab.IMPEDE), r["pendencias"])
    checar(ab.decisao_automatica(r["pendencias"], r["a_recolher"]) == "",
           "sem credito nao pode ser proposto")

    # ------------------------------------------------------------------
    # Excecoes: nada e' liberado automaticamente

    casos = [
        ("ST pelo CST", fab.item(grupo="ICMS10", cst="10", p_icms="7.00",
                                 v_icms="70.00"), ab.P_ICMS_ST),
        ("ST destacada", fab.item(p_icms="7.00", v_icms="70.00",
                                  extras="<vBCST>1400.00</vBCST><vICMSST>50.00</vICMSST>"),
         ab.P_ICMS_ST),
        ("isento", fab.item(grupo="ICMS40", cst="40"), ab.P_ISENTO),
        ("reducao de base", fab.item(grupo="ICMS20", cst="20", p_icms="7.00",
                                     v_icms="35.00"), ab.P_REDUCAO_BASE),
        ("diferimento", fab.item(grupo="ICMS51", cst="51"), ab.P_DIFERIMENTO),
        ("FCP", fab.item(p_icms="7.00", v_icms="70.00",
                         extras="<vFCP>20.00</vFCP>"), ab.P_FCP),
        ("CFOP interno", fab.item(p_icms="7.00", v_icms="70.00", cfop="5102"),
         ab.P_CFOP),
        ("aliquota divergente", fab.item(p_icms="12.00", v_icms="120.00"),
         ab.P_ALIQUOTA_DIVERGENTE),
    ]
    for nome, it, esperado in casos:
        r = avaliar(fab.xml_nfe([it], uf="SP"))
        checar(esperado in codigos(r, ab.DECISAO), f"{nome}: {r['pendencias']}")
        checar(ab.decisao_automatica(r["pendencias"], r["a_recolher"]) == "",
               f"{nome}: nao podia ser liberado sozinho")

    # Isento sem destaque continua sinalizado mesmo com a presuncao ligada:
    # ausencia de destaque nao se confunde com isencao.
    r = avaliar(fab.xml_nfe([fab.item(grupo="ICMS40", cst="40")], uf="SP"))
    checar(ab.P_ISENTO in codigos(r) and ab.pede_decisao(r["pendencias"]), r)

    # NF-e de devolucao/complementar pede decisao.
    r = avaliar(fab.xml_nfe([fab.item(p_icms="7.00", v_icms="70.00")], fin="4"))
    checar(ab.P_NFE_NAO_NORMAL in codigos(r, ab.DECISAO), r["pendencias"])

    # Finalidade nao informada impede.
    r = avaliar(fab.nota_sp_com_destaque(), finalidade="")
    checar(ab.P_FINALIDADE in codigos(r, ab.IMPEDE), r["pendencias"])

    # Dado faltante (sem NCM) impede.
    r = avaliar(fab.xml_nfe([fab.item(p_icms="7.00", v_icms="70.00", ncm="")]))
    checar(ab.P_DADO_FALTANTE in codigos(r, ab.IMPEDE), r["pendencias"])

    # Resultado negativo: sinalizado, com o numero a mostra, fora da soma.
    r = avaliar(fab.xml_nfe([fab.item(v_prod="100.00", p_icms="30.00",
                                      v_icms="30.00")]))
    checar(r["a_recolher"] is not None and r["a_recolher"] < 0, r["a_recolher"])
    checar(ab.P_VALOR_NEGATIVO in codigos(r, ab.IMPEDE), r["pendencias"])
    checar(ab.decisao_automatica(r["pendencias"], r["a_recolher"]) == "", r)

    # ------------------------------------------------------------------
    # Componentes do valor da operacao

    it = fab.item(v_prod="1000.00", p_icms="7.00", v_icms="70.00", ipi="50.00",
                  prod_extras="<vFrete>30.00</vFrete><vDesc>10.00</vDesc>"
                              "<vSeg>5.00</vSeg><vOutro>2.00</vOutro>")
    xml = fab.xml_nfe([it])
    r = avaliar(xml)
    checar(r["memoria"]["valor_operacao"] == "1077.00", r["memoria"])
    checar(r["memoria"]["componentes"] == {
        "produto": "1000.00", "desconto": "10.00", "frete": "30.00",
        "seguro": "5.00", "outras": "2.00", "ipi": "50.00"},
        r["memoria"]["componentes"])
    sem_ipi = ab.validar_parametros(ab.METODO_POR_DENTRO, True, {"ipi": False})
    r = avaliar(xml, sem_ipi)
    checar(r["memoria"]["valor_operacao"] == "1027.00", r["memoria"])
    checar("ipi" not in r["memoria"]["componentes"], r["memoria"]["componentes"])
    levanta(lambda: ab.validar_parametros(ab.METODO_POR_DENTRO, True, {"x": 1}),
            "COMPONENTE_INVALIDO", "componente desconhecido")
    levanta(lambda: ab.validar_parametros(""), "METODO_INVALIDO",
            "metodo nao escolhido")

    # ------------------------------------------------------------------
    # Tabela por vigencia e por produto

    linhas = ab.aliquotas_iniciais() + [
        {"tipo": "interna", "uf": "BA", "ncm": "", "percentual": "19",
         "vigencia_inicio": "2023-03-22", "vigencia_fim": "2024-02-06",
         "base_legal": "teste"},
        {"tipo": "interna", "uf": "BA", "ncm": "3924", "percentual": "12",
         "vigencia_inicio": "2026-01-01", "vigencia_fim": "",
         "base_legal": "teste"},
    ]
    tabela = ab.TabelaAliquotas(linhas)
    checar(tabela.interna("84713012", date(2024, 2, 6))["percentual"] == "19",
           "vigencia anterior")
    checar(tabela.interna("84713012", date(2024, 2, 7))["percentual"] == "20.5",
           "virada da aliquota")
    checar(tabela.interna("39241000", date(2026, 10, 5))["percentual"] == "12",
           "o prefixo de NCM vence a regra geral")
    checar(tabela.interna("39241000", date(2025, 10, 5))["percentual"] == "20.5",
           "antes da vigencia do NCM vale a geral")
    checar(tabela.interna("84713012", date(2020, 1, 1)) is None,
           "sem linha vigente nao ha aliquota")
    r = avaliar(fab.xml_nfe([fab.item(p_icms="7.00", v_icms="70.00")],
                            data="2020-01-15"))
    checar(ab.P_SEM_ALIQUOTA_INTERNA in codigos(r, ab.IMPEDE)
           and r["a_recolher"] is None, r)
    checar(tabela.interestadual("BA", "0", date(2026, 1, 1)) is None,
           "BA fica fora do escopo interestadual")

    semente = {(l["uf"], l["percentual"]) for l in ab.aliquotas_iniciais()
               if l["tipo"] == "interestadual"}
    checar(all((uf, "7") in semente for uf in ("SP", "RJ", "MG", "PR", "SC", "RS")),
           "UFs de 7%")
    checar(("ES", "12") in semente and ("GO", "12") in semente
           and ("IMPORTADO", "4") in semente, semente)
    checar(len(semente) == 27, f"26 UFs de origem + importado: {len(semente)}")

    ok = ab.validar_aliquota({"tipo": "interna", "ncm": "2203.00",
                              "percentual": "25", "vigencia_inicio": "01/01/2026",
                              "base_legal": "Lei X"})
    checar(ok["ncm"] == "220300" and ok["vigencia_inicio"] == "2026-01-01"
           and ok["uf"] == "BA", ok)
    levanta(lambda: ab.validar_aliquota({"tipo": "interestadual", "uf": "BA",
                                         "percentual": "12",
                                         "vigencia_inicio": "2026-01-01",
                                         "base_legal": "x"}),
            "UF_INVALIDA", "BA como origem")
    levanta(lambda: ab.validar_aliquota({"tipo": "interna", "percentual": "120",
                                         "vigencia_inicio": "2026-01-01",
                                         "base_legal": "x"}),
            "PERCENTUAL_INVALIDO", "aliquota acima de 100")
    levanta(lambda: ab.validar_aliquota({"tipo": "interna", "percentual": "20,5",
                                         "vigencia_inicio": "2026-01-01"}),
            "BASE_LEGAL_OBRIGATORIA", "sem base legal")
    levanta(lambda: ab.validar_aliquota({"tipo": "interna", "percentual": "20,5",
                                         "vigencia_inicio": "31/02/2026",
                                         "base_legal": "x"}),
            "VIGENCIA_INVALIDA", "data impossivel")

    # ------------------------------------------------------------------
    # Chave de acesso

    ch = fab.chave("SP", 1001)
    partes = ab.decompor_chave(ch)
    checar((partes.uf, partes.ano_mes, partes.cnpj_emitente, partes.modelo,
            partes.numero) == ("SP", "2026-10", fab.CNPJ_EMIT, "55", "1001"),
           partes)
    errada = ch[:-1] + ("0" if ch[-1] != "0" else "1")
    levanta(lambda: ab.decompor_chave(errada), ab.R_CHAVE, "DV errado")
    levanta(lambda: ab.decompor_chave(ch[:43]), ab.R_CHAVE, "43 digitos")
    espacada = " ".join(ch[i:i + 4] for i in range(0, 44, 4))
    colado = f"{ch}, {fab.chave('GO', 2)}\n{espacada}; 123"
    checar(ab.extrair_chaves(colado) == [ch, fab.chave("GO", 2), ch, "123"],
           ab.extrair_chaves(colado))

    # ------------------------------------------------------------------
    # Escopo da nota

    def recusa(xml: bytes):
        motivo = ab.recusa_da_nota(ler_nfe(xml))
        return motivo[0] if motivo else None

    um = [fab.item(p_icms="7.00", v_icms="70.00")]
    checar(recusa(fab.xml_nfe(um)) is None, "nota boa nao pode ser recusada")
    checar(recusa(fab.xml_nfe(um, uf="BA")) == ab.R_ORIGEM_BA, "origem BA")
    checar(recusa(fab.xml_nfe(um, uf_dest="SP", uf="GO")) == ab.R_DESTINO,
           "destino fora da BA")
    checar(recusa(fab.xml_nfe(um, cstat="101")) == ab.R_SITUACAO, "cancelada")
    checar(recusa(fab.xml_nfe(um, modelo="65")) == ab.R_MODELO, "NFC-e")
    checar(recusa(fab.xml_nfe(um, tp_nf="0")) == ab.R_ENTRADA, "nota de entrada")
    checar(recusa(fab.xml_nfe(um, cnpj_dest="52998224725")) == ab.R_SEM_CNPJ,
           "destinatario pessoa fisica")
    checar(recusa(fab.xml_nfe([])) == ab.R_SEM_ITENS, "sem itens")

    # ------------------------------------------------------------------
    # Leitor de XML

    nota = ler_nfe(xml)
    it0 = nota.itens[0]
    checar((nota.uf_origem, nota.uf_destino, nota.cnpj_dest, nota.crt_emit,
            nota.dt_emissao) == ("SP", "BA", fab.CNPJ_DEST, "3",
                                 date(2026, 10, 5)), nota)
    checar((it0.v_frete, it0.v_desc, it0.v_seg, it0.v_outro, it0.v_ipi)
           == (D("30.00"), D("10.00"), D("5.00"), D("2.00"), D("50.00")), it0)
    sem = ler_nfe(fab.nota_go_sem_destaque()).itens[0]
    checar(sem.v_icms is None and sem.aliq_icms is None,
           "ICMS ausente tem de continuar ausente, nao virar zero")
    for ruim, nome in ((b"", "vazio"), (b"<a><b></a>", "malformado"),
                       (b"<nota/>", "sem infNFe")):
        try:
            ler_nfe(ruim)
        except NFeInvalida:
            continue
        checar(False, f"XML {nome} deveria ser recusado")
    bomba = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM '
             b'"file:///c:/windows/win.ini">]><NFe><infNFe Id="NFe1">'
             b'<ide><mod>&e;</mod></ide></infNFe></NFe>')
    checar(ler_nfe(bomba).modelo == "", "entidade externa nao pode ser resolvida")

    # ------------------------------------------------------------------
    # Competencia, vencimento de referencia

    checar(ab.validar_competencia("10/2026") == "2026-10", "mm/aaaa")
    checar(ab.validar_competencia("2026-10") == "2026-10", "aaaa-mm")
    levanta(lambda: ab.validar_competencia("13/2026"), "COMPETENCIA_INVALIDA",
            "mes 13")
    checar(ab.vencimento_de_referencia("2026-10") == date(2026, 11, 25), "nov")
    checar(ab.vencimento_de_referencia("2026-12") == date(2027, 1, 25), "virada")
    checar(ab.centavos(D("169.81")) == 16981 and ab.de_centavos(16981)
           == D("169.81"), "centavos")
    checar(ab.para_decimal("1.234,56") == D("1234.56")
           and ab.para_decimal("") is None and ab.para_decimal("abc") is None,
           "para_decimal")

    # ------------------------------------------------------------------
    # Lancamento manual para conferencia

    sim = ab.simular(valor_operacao="1.000,00", uf_origem="go",
                     quando=date(2026, 10, 5), tabela=TABELA)
    checar(sim["tipo_credito"] == ab.CREDITO_CALCULADO
           and sim["credito"] == "120.00"
           and sim["metodos"][ab.METODO_POR_DENTRO]["a_recolher"] == "106.92"
           and sim["metodos"][ab.METODO_DIFERENCA]["a_recolher"] == "85.00", sim)
    sim = ab.simular(valor_operacao="1000", uf_origem="SP", icms_destacado="70",
                     quando=date(2026, 10, 5), tabela=TABELA)
    checar(sim["tipo_credito"] == ab.CREDITO_DESTACADO
           and sim["metodos"][ab.METODO_POR_DENTRO]["base_calculo"] == "1169.81",
           sim)
    sim = ab.simular(valor_operacao="1000", uf_origem="SP", origem_mercadoria="1",
                     quando=date(2026, 10, 5), tabela=TABELA)
    checar(sim["metodos"][ab.METODO_POR_DENTRO]["a_recolher"] == "207.55", sim)
    levanta(lambda: ab.simular(valor_operacao="1000", uf_origem="BA",
                               quando=date(2026, 10, 5), tabela=TABELA),
            ab.R_ORIGEM_BA, "simular com origem BA")
    levanta(lambda: ab.simular(valor_operacao="0", uf_origem="SP",
                               quando=date(2026, 10, 5), tabela=TABELA),
            "VALOR_INVALIDO", "simular com valor zero")
    levanta(lambda: ab.simular(valor_operacao="1000", uf_origem="SP",
                               quando=date(2020, 1, 1), tabela=TABELA),
            ab.P_SEM_ALIQUOTA_INTERNA, "simular fora da vigencia")

    # ------------------------------------------------------------------
    # Limite arquitetural: nucleo e persistencia nao conhecem a web

    for relativo in ("core/antecipacao_ba.py", "core/antecipacao_nfe.py",
                     "ferramentas/antecipacao_store.py",
                     "ferramentas/relatorio_antecipacao.py"):
        with open(os.path.join(RAIZ, "src", "auditoria_fiscal", relativo),
                  encoding="utf-8") as fh:
            fonte = fh.read()
        for proibido in ("fastapi", "starlette", "from ..web", "from .web",
                         "PySide"):
            checar(proibido not in fonte, f"{relativo} nao pode usar {proibido}")

    print("OK - antecipacao BA: formulas, pendencias, tabela, chave e leitor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
