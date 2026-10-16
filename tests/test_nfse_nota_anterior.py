"""Perfil pela nota ja emitida (spec 009, Parte 2): o leitor do XML.

Confere, com notas SINTETICAS (fixtures/nfse/notas_anteriores.py):
- Nota Salvador (ABRASF v1): campos do prestador, ISS retido, aliquota em
  fracao, regime especial convertido, codigos da turma com o cTribNac pela
  lista nacional e o modelo da discriminacao sem nomes;
- NFS-e nacional: tambem IM na DPS, regime de apuracao e tributos;
- varias notas: so preenche o que concorda; CNPJ de outro prestador;
- recusas: DOCTYPE, XML quebrado, sem NFS-e, grande demais, zip-bomba;
- nenhum CPF, nome do tomador ou do aluno no resultado.
"""

from __future__ import annotations

import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_nota_anterior as na  # noqa: E402
from fixtures import nfse as fx  # noqa: E402
from fixtures.nfse import notas_anteriores as nt  # noqa: E402

PESSOAIS = ("123.456.789-09", "12345678909", "ANA EXEMPLO", "Ana Exemplo",
            "PEDRO EXEMPLO", "Pedro Exemplo")


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def codigo_do_erro(funcao, *args, **kwargs) -> str | None:
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc.codigo
    return None


def sem_dados_pessoais(resultado, onde: str):
    texto = str(resultado)
    for pessoal in PESSOAIS:
        checar(pessoal not in texto, f"{onde}: dado pessoal {pessoal!r} no resultado")


def valor(s, campo):
    return s["campos"].get(campo, {}).get("valor")


def main() -> int:
    # ------------------------------------------------------------------
    # Nota Salvador, uma nota.
    notas = na.ler_arquivo(nt.nota_salvador())
    checar(len(notas) == 1 and notas[0].leiaute == na.LEIAUTE_ABRASF, notas)
    s = na.sugerir_perfil(notas, turmas=["Berçário", "Infantil II"])
    checar(valor(s, "cnpj") == fx.CNPJ, s["campos"])
    checar(valor(s, "razao_social") == "ESCOLA EXEMPLO LTDA", s["campos"])
    checar(valor(s, "inscricao_municipal") == nt.IM, s["campos"])
    checar(valor(s, "municipio_ibge") == nt.SALVADOR
           and valor(s, "municipio_prestacao_ibge") == nt.SALVADOR, s["campos"])
    checar(valor(s, "iss_retido") is False, "IssRetido 2 = não")
    checar(valor(s, "aliquota") == "5,00", "Aliquota 0.05 em fração = 5,00%")
    checar(valor(s, "reg_esp_trib") == 0, "optante sem regime especial = 0")
    checar("Nota Salvador" in s["campos"]["cnpj"]["fonte"]
           and "901" in s["campos"]["cnpj"]["fonte"], s["campos"]["cnpj"])
    for manual in ("informar_im", "reg_ap_trib_sn", "tributos_aprox", "p_tot_trib_sn",
                   "endereco_tomador", "serie_dps", "convenio_incidencia_ativo"):
        checar(manual not in s["campos"], f"{manual} não vem da Nota Salvador")
    checar(s["manuais"], "lista do que segue manual")
    checar(len(s["turmas"]) == 1, s["turmas"])
    t = s["turmas"][0]
    checar(t["nome"] == "Berçário" and t["c_trib_nac"] == "080101"
           and t["ref_item_lista"] == "0801" and t["ref_cnae"] == "8511200"
           and t["ref_ctiss"] == "0801001", t)
    checar(t.get("c_nbs") is None, "NBS só se o XML tiver")
    checar(valor(s, "modelo_discriminacao") == fx.MODELO_CRECHE,
           f"modelo: {valor(s, 'modelo_discriminacao')!r}")
    nf.validar_modelo(valor(s, "modelo_discriminacao"))
    sem_dados_pessoais(s, "Nota Salvador")

    # Sem as turmas no formulário, o nome da turma fica e há aviso.
    s = na.sugerir_perfil(notas)
    checar(valor(s, "modelo_discriminacao") ==
           "REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO MENOR: {ALUNO} NO PERÍODO "
           "DE {MES}/{ANO}.", valor(s, "modelo_discriminacao"))
    checar(any("{TURMA}" in a for a in s["avisos"]), s["avisos"])
    checar(s["turmas"][0]["nome"] is None, "sem turmas no formulário, sem nome")

    # Mês por extenso e responsável no texto.
    texto = ("Mensalidade de Setembro/2026 da aluna Lia Maria Exemplo, "
             "responsável ANA EXEMPLO.")
    m = na.modelo_da_discriminacao(texto, tomador="ANA EXEMPLO",
                                   competencia="2026-09", turmas=[])
    checar(m == "Mensalidade de {mes_extenso}/{ano} da aluna {aluno}, responsável "
                "{RESPONSAVEL}.", m)
    # Sem achar o aluno, ou com data que não é a competência, não há modelo.
    checar(na.modelo_da_discriminacao("SERVIÇOS DE BERÇÁRIO 09/2026", tomador="X Y",
                                      competencia="2026-09", turmas=[]) is None,
           "sem aluno, sem modelo")
    checar(na.modelo_da_discriminacao("AO MENOR PEDRO EXEMPLO EM 08/2026",
                                      tomador="X Y", competencia="2026-09",
                                      turmas=[]) is None, "data de outro mês")
    checar(na.modelo_da_discriminacao("AO MENOR PEDRO EXEMPLO CPF 123.456.789-09",
                                      tomador="X Y", competencia="2026-09",
                                      turmas=[]) is None, "CPF no texto")
    checar(na.modelo_da_discriminacao("AO MENOR DE 5 ANOS", tomador="X Y",
                                      competencia="2026-09", turmas=[]) is None,
           "'DE' não é nome")

    # Alíquota: fração, percentual, fora do limite.
    for bruto, esperado in (("0.05", "5,00"), ("5.00", "5,00"), ("2", "2,00"),
                            ("0.0201", "2,01")):
        s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(aliquota=bruto)))
        checar(valor(s, "aliquota") == esperado, f"alíquota {bruto} -> {valor(s, 'aliquota')}")
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(aliquota="7.5")))
    checar("aliquota" not in s["campos"] and any("lí" in a for a in s["avisos"]), s)

    # Regime especial convertido; MEI e não optante viram aviso.
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(regime_especial=6)))
    checar(valor(s, "reg_esp_trib") == 0, "6 (ME/EPP do Simples) = nenhum")
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(regime_especial=1)))
    checar(valor(s, "reg_esp_trib") == 3, "1 (microempresa municipal) = 3")
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(regime_especial=5)))
    checar("reg_esp_trib" not in s["campos"] and any("MEI" in a for a in s["avisos"]), s)
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(optante=2)))
    checar("reg_esp_trib" not in s["campos"]
           and any("não optante" in a for a in s["avisos"]), s["avisos"])

    # Item da lista -> cTribNac.
    for item in ("0801", "08.01", "8.01", "00801", "801"):
        checar(na.codigo_nacional(item, "8511200") == ("080101", []), item)
    checar(na.codigo_nacional("0801", "8531700")[0] == "080102", "superior")
    codigo, opcoes = na.codigo_nacional("0801", None)
    checar(codigo is None and [o[0] for o in opcoes] == ["080101", "080102"], opcoes)
    checar(na.codigo_nacional("0802", None) == ("080201", []), "desdobro único")
    codigo, opcoes = na.codigo_nacional("1.03", "6311900")
    checar(codigo is None and len(opcoes) == 2, "ambíguo fora do 08.01")
    checar(na.codigo_nacional("9999", None) == (None, []), "subitem inexistente")
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(cnae=None)))
    checar(s["turmas"][0]["c_trib_nac"] is None
           and any("080101" in a and "080102" in a for a in s["avisos"]), s["avisos"])

    # Códigos da reforma, se o XML tiver.
    s = na.sugerir_perfil(na.ler_arquivo(nt.nota_salvador(
        extra_servico="<CodigoNbs>1.2201.11.00</CodigoNbs><cIndOp>030101</cIndOp>"
                      "<cClassTrib>200028</cClassTrib>")))
    t = s["turmas"][0]
    checar(t["c_nbs"] == "122011100" and t["c_ind_op"] == "030101"
           and t["c_class_trib"] == "200028", t)

    # ------------------------------------------------------------------
    # Várias notas.
    a = {"numero": "901"}
    b = {"numero": "902", "tomador": "BRUNO EXEMPLO", "cpf": fx.CPF_BRUNO,
         "discriminacao": "REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO MENOR: "
                          "CAIO TESTE NO PERÍODO DE 09/2026."}
    notas = na.ler_arquivo(nt.lista_salvador(a, b))
    checar(len(notas) == 2, "duas notas, ISO-8859-1")
    s = na.sugerir_perfil(notas, turmas=["Berçário"])
    checar(valor(s, "iss_retido") is False and valor(s, "modelo_discriminacao")
           == fx.MODELO_CRECHE, s["campos"])
    checar(s["notas"]["usadas"] == 2 and "2 notas" in s["campos"]["cnpj"]["fonte"], s)
    checar(len(s["turmas"]) == 1 and s["turmas"][0]["notas"] == 2, s["turmas"])
    for pessoal in ("BRUNO EXEMPLO", "CAIO TESTE", "11144477735"):
        checar(pessoal not in str(s), f"dado pessoal {pessoal}")
    s = na.sugerir_perfil(na.ler_arquivo(nt.lista_salvador(a, {**b, "iss_retido": 1})))
    checar("iss_retido" not in s["campos"]
           and any("ISS retido" in x for x in s["avisos"]), s["avisos"])
    # Fundamental: outra combinação de códigos vira outra turma sugerida.
    s = na.sugerir_perfil(na.ler_arquivo(nt.lista_salvador(
        a, {**b, "cnae": "8513900", "discriminacao": "REFERENTE AOS SERVIÇOS PRESTADOS "
            "DE FUNDAMENTAL I AO MENOR: CAIO TESTE NO PERÍODO DE 09/2026."})),
        turmas=["Berçário", "Fundamental I"])
    checar(sorted(t["nome"] for t in s["turmas"]) == ["Berçário", "Fundamental I"]
           and all(t["c_trib_nac"] == "080101" for t in s["turmas"]), s["turmas"])
    # Outro prestador no arquivo: fica fora, com aviso; do CNPJ do perfil só.
    outro = {"numero": "50", "cnpj": "11444777000161", "razao_social": "OUTRA LTDA"}
    s = na.sugerir_perfil(na.ler_arquivo(nt.lista_salvador(a, b, outro)))
    checar(valor(s, "cnpj") == fx.CNPJ and s["notas"]["usadas"] == 2
           and any("outro" in x.lower() for x in s["avisos"]), s)
    checar(codigo_do_erro(na.sugerir_perfil, na.ler_arquivo(nt.nota_salvador()),
                          cnpj_perfil="11444777000161") == na.NOTA_DE_OUTRO_CNPJ,
           "perfil de outro CNPJ")

    # ------------------------------------------------------------------
    # NFS-e nacional (DPS do próprio gerador).
    notas = na.ler_arquivo(nt.nfse_nacional())
    checar(len(notas) == 1 and notas[0].leiaute == na.LEIAUTE_NACIONAL, notas)
    s = na.sugerir_perfil(notas, turmas=["Berçário"])
    checar(valor(s, "cnpj") == fx.CNPJ and valor(s, "inscricao_municipal") == nt.IM,
           s["campos"])
    checar(valor(s, "informar_im") is True, "IM na DPS de nota autorizada = tem CNC")
    checar(valor(s, "reg_ap_trib_sn") == 1 and valor(s, "reg_esp_trib") == 0, s["campos"])
    checar(valor(s, "tributos_aprox") == "pTotTribSN"
           and valor(s, "p_tot_trib_sn") == "6,00", s["campos"])
    checar(valor(s, "iss_retido") is False and valor(s, "aliquota") == "5,00",
           "pAliqAplic quando a DPS não leva pAliq")
    t = s["turmas"][0]
    checar(t["nome"] == "Berçário" and t["c_trib_nac"] == "080101"
           and t["c_nbs"] == "122011100", t)
    checar(valor(s, "modelo_discriminacao") == fx.MODELO_CRECHE,
           valor(s, "modelo_discriminacao"))
    checar(any("produção restrita" in x for x in s["avisos"]), "tpAmb 2 avisa")
    sem_dados_pessoais(s, "NFS-e nacional")
    s = na.sugerir_perfil(na.ler_arquivo(nt.nfse_nacional(tp_amb=1)))
    checar(not any("produção restrita" in x for x in s["avisos"]), "tpAmb 1 não avisa")
    # Sem IM na DPS: a nota saiu, então a escola não tem registro no CNC.
    s = na.sugerir_perfil(na.ler_arquivo(nt.nfse_nacional(
        perfil=fx.perfil_completo(informar_im=False))))
    checar(valor(s, "informar_im") is False, "sem IM na DPS = sem CNC")
    # pTotTrib (federal, estadual, municipal).
    s = na.sugerir_perfil(na.ler_arquivo(nt.nfse_nacional(perfil=fx.perfil_completo(
        tributos_aprox="pTotTrib", p_tot_trib_fed="4,00", p_tot_trib_est="0,00",
        p_tot_trib_mun="2,00"))))
    checar(valor(s, "tributos_aprox") == "pTotTrib" and valor(s, "p_tot_trib_fed") == "4,00"
           and valor(s, "p_tot_trib_mun") == "2,00", s["campos"])

    # Zip com as duas.
    pacote = nt.zip_de({"a.xml": nt.nota_salvador(), "pasta/b.xml": nt.nfse_nacional(),
                        "leia.txt": b"ignorado"})
    notas = na.ler_arquivo(pacote)
    checar(sorted(n.leiaute for n in notas) == sorted([na.LEIAUTE_ABRASF,
                                                       na.LEIAUTE_NACIONAL]), notas)
    # A mesma turma nos dois leiautes vira uma sugestão só, com os códigos de cada um.
    s = na.sugerir_perfil(notas, turmas=["Berçário"])
    checar(len(s["turmas"]) == 1, s["turmas"])
    t = s["turmas"][0]
    checar(t["notas"] == 2 and t["c_trib_nac"] == "080101" and t["c_nbs"] == "122011100"
           and t["ref_cnae"] == "8511200", t)
    # Códigos em conflito na mesma turma: ficam separados, com aviso.
    s = na.sugerir_perfil(na.ler_arquivo(nt.lista_salvador(
        {"numero": "1"}, {"numero": "2", "item": "0802"})), turmas=["Berçário"])
    checar(len(s["turmas"]) == 2 and any("Berçário" in a and "diferentes" in a
                                         for a in s["avisos"]), (s["turmas"], s["avisos"]))

    # ------------------------------------------------------------------
    # Recusas.
    doctype = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">'
               b'<!ENTITY b "&a;&a;&a;&a;">]><CompNfse>&b;</CompNfse>')
    checar(codigo_do_erro(na.ler_arquivo, doctype) == na.NOTA_ILEGIVEL, "DOCTYPE")
    checar(codigo_do_erro(na.ler_arquivo, b"<CompNfse><Nfse>") == na.NOTA_ILEGIVEL,
           "XML quebrado")
    checar(codigo_do_erro(na.ler_arquivo, b"") == na.NOTA_ILEGIVEL, "vazio")
    checar(codigo_do_erro(na.ler_arquivo, b"<NFe><infNFe/></NFe>") == na.NOTA_SEM_NFSE,
           "XML sem NFS-e")
    checar(codigo_do_erro(na.ler_arquivo, b" " * (na.MAX_ARQUIVO_BYTES + 1))
           == na.NOTA_GRANDE_DEMAIS, "arquivo grande")
    bomba = nt.zip_de({"a.xml": b"<a>" + b" " * (na.MAX_DESCOMPACTADO + 10) + b"</a>"})
    checar(len(bomba) < na.MAX_ARQUIVO_BYTES, "a bomba cabe no limite do arquivo")
    checar(codigo_do_erro(na.ler_arquivo, bomba) == na.NOTA_GRANDE_DEMAIS, "zip-bomba")
    muitos = nt.zip_de({f"{i}.xml": b"<a/>" for i in range(na.MAX_XMLS_ZIP + 1)})
    checar(codigo_do_erro(na.ler_arquivo, muitos) == na.NOTA_GRANDE_DEMAIS, "muitos XMLs")
    checar(codigo_do_erro(na.ler_arquivo, nt.zip_de({"a.txt": b"x"})) == na.NOTA_SEM_NFSE,
           "zip sem XML")
    quebrado = b"PK\x03\x04" + b"\x00" * 40
    checar(codigo_do_erro(na.ler_arquivo, quebrado) == na.NOTA_ILEGIVEL, "zip quebrado")
    with zipfile.ZipFile(__import__("io").BytesIO(pacote)) as z:
        checar(len(z.namelist()) == 3, "fixture do zip")

    print("OK - perfil pela nota já emitida (Nota Salvador ABRASF v1 e NFS-e nacional, "
          "várias notas, códigos pela lista nacional, modelo sem nomes, recusas) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
