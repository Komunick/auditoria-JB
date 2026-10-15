"""Nucleo puro da Emissao de NFS-e (spec 006): perfil, pendencias, regra da
aliquota, normalizacao, competencia, CPF, valor, turma, discriminacao e os
limites arquiteturais (sem interface e sem rede).
"""

from __future__ import annotations

import ast
import datetime as dt
import glob
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from fixtures import nfse as fx  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro(funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc
    return None


def testar_normalizacao() -> None:
    texto, removeu = nf.normalizar_texto("  Ana​  Exemplo \u0007")
    checar(texto == "Ana Exemplo" and removeu, (texto, removeu))
    texto, removeu = nf.normalizar_texto("Pedro Exemplo")
    checar(texto == "Pedro Exemplo" and not removeu,
           f"espaco nao separavel vira espaco, sem aviso: {(texto, removeu)}")
    checar(nf.normalizar_texto(None) == ("", False), "None")
    checar(nf.chave_comparacao("BERÇÁRIO ") == nf.chave_comparacao("bercario"),
           "comparacao ignora caixa, acento e espaco")
    checar(nf.chave_comparacao("Ana  Exemplo") == "ana exemplo",
           nf.chave_comparacao("Ana  Exemplo"))


def testar_competencia() -> None:
    casos = {
        "11/2026": "2026-11", "1/2027": "2027-01", "2026-11": "2026-11",
        "NOVEMBRO/2026": "2026-11", "nov/2026": "2026-11",
        "novembro de 2026": "2026-11", "Março/2027": "2027-03",
        "marco/2027": "2027-03", " 09/2026 ": "2026-09",
    }
    for texto, esperado in casos.items():
        checar(nf.ler_competencia(texto) == esperado,
               f"{texto!r} -> {nf.ler_competencia(texto)}")
    checar(nf.ler_competencia("2026-11-01", tipo="data") == "2026-11",
           "celula de data da planilha")
    checar(nf.ler_competencia(dt.date(2026, 11, 20)) == "2026-11", "date")
    for ruim in ("11/26", "2026", "novembro", "13/2026", "00/2026", "11-2026x",
                 "2026-11-01"):
        e = erro(nf.ler_competencia, ruim)
        checar(e is not None and e.codigo == nf.COMPETENCIA_INVALIDA,
               f"{ruim!r} deveria ser competencia invalida")
    for vazio in ("", "  ", None):
        e = erro(nf.ler_competencia, vazio)
        checar(e is not None and e.codigo == nf.COMPETENCIA_AUSENTE, repr(vazio))


def testar_cpf_e_valor() -> None:
    checar(nf.ler_cpf("123.456.789-09") == ("12345678909", False), "CPF texto")
    checar(nf.ler_cpf("1234567890", tipo="numero") == ("01234567890", True),
           "celula numerica perde o zero inicial; completa e avisa")
    for ruim, codigo in (("1234567890", nf.CPF_INVALIDO),
                         ("123.456.789-00", nf.CPF_INVALIDO),
                         ("", nf.CPF_AUSENTE), (None, nf.CPF_AUSENTE)):
        e = erro(nf.ler_cpf, ruim)
        checar(e is not None and e.codigo == codigo, f"CPF {ruim!r}")

    casos = {"R$ 1.250,00": 125000, "980,50": 98050, "1250": 125000,
             "R$1250,5": 125050}
    for texto, esperado in casos.items():
        checar(nf.ler_valor(texto) == esperado, f"{texto!r} -> {nf.ler_valor(texto)}")
    checar(nf.ler_valor("1250.5", tipo="numero") == 125050, "celula numerica")
    for ruim, codigo in (("0", nf.VALOR_NAO_POSITIVO),
                         ("0,00", nf.VALOR_NAO_POSITIVO),
                         ("-10,00", nf.VALOR_NAO_POSITIVO),
                         ("1.250", nf.VALOR_INVALIDO),
                         ("abc", nf.VALOR_INVALIDO),
                         ("10,005", nf.VALOR_INVALIDO),
                         ("", nf.VALOR_AUSENTE), (None, nf.VALOR_AUSENTE),
                         ("=SOMA(A1:A2)", nf.VALOR_AUSENTE)):
        e = erro(nf.ler_valor, ruim)
        checar(e is not None and e.codigo == codigo,
               f"valor {ruim!r}: {e.codigo if e else 'aceito'} (esperado {codigo})")
    e = erro(nf.ler_valor, "10.005", tipo="numero")
    checar(e is not None and e.codigo == nf.VALOR_INVALIDO, "numero sub-centavo")


def testar_perfil_valido() -> None:
    p = nf.validar_perfil(fx.perfil_completo())
    checar(p.cnpj == "11222333000181", p.cnpj)
    checar(p.aliquota_centesimos == 500, p.aliquota_centesimos)
    checar(p.p_tot_trib_sn == 600, p.p_tot_trib_sn)
    checar(p.serie_dps == "900", p.serie_dps)
    checar(len(p.turmas) == 3, p.turmas)
    bercario = p.turmas[0]
    checar(bercario.c_nbs == "122011100", f"NBS sem pontos: {bercario.c_nbs}")
    checar(bercario.apelidos == ("Bercario I", "Berçário 1"), bercario.apelidos)
    checar(nf.pendencias_do_perfil(p) == [], nf.pendencias_do_perfil(p))


def testar_perfil_sem_valor_padrao() -> None:
    """Decisao que depende da JB ou do Sistema Nacional nao ganha padrao."""
    p = nf.validar_perfil(fx.perfil_cru())
    for campo in ("endereco_tomador", "reg_ap_trib_sn", "reg_esp_trib",
                  "tributos_aprox", "informar_im", "convenio_incidencia_ativo",
                  "aliquota_centesimos", "inscricao_municipal"):
        checar(getattr(p, campo) is None,
               f"{campo} deveria ficar vazio, nao {getattr(p, campo)!r}")
    pend = {x.campo: x.origem for x in nf.pendencias_do_perfil(p)}
    esperado = {"endereco_tomador": "JB-2", "reg_ap_trib_sn": "JB-8",
                "reg_esp_trib": "JB-8", "tributos_aprox": "JB-8",
                "informar_im": "R5"}
    checar(pend == esperado, f"pendencias {pend}")
    for x in nf.pendencias_do_perfil(p):
        checar(x.descricao, f"pendencia sem descricao: {x}")


def testar_pendencias_condicionais() -> None:
    base = fx.perfil_completo

    p = nf.validar_perfil(base(tributos_aprox="pTotTrib", p_tot_trib_sn=None))
    pend = {x.campo for x in nf.pendencias_do_perfil(p)}
    checar(pend == {"p_tot_trib_fed", "p_tot_trib_est", "p_tot_trib_mun"}, pend)

    p = nf.validar_perfil(base(tributos_aprox="pTotTribSN", p_tot_trib_sn=None))
    checar({x.campo for x in nf.pendencias_do_perfil(p)} == {"p_tot_trib_sn"},
           "pTotTribSN sem percentual")

    # Retido com ISS pelo Simples: a regra oficial manda informar a aliquota.
    p = nf.validar_perfil(base(iss_retido=True, aliquota=None))
    pend = {x.campo: x.origem for x in nf.pendencias_do_perfil(p)}
    checar(pend == {"aliquota": "JB-8"}, pend)

    # ISS fora do Simples: a regra depende do convenio (R5).
    p = nf.validar_perfil(base(reg_ap_trib_sn=2, reg_esp_trib=0,
                               convenio_incidencia_ativo=None))
    pend = {x.campo: x.origem for x in nf.pendencias_do_perfil(p)}
    checar(pend == {"convenio_incidencia_ativo": "R5"}, pend)

    p = nf.validar_perfil(base(informar_im=True, inscricao_municipal=""))
    checar({x.campo for x in nf.pendencias_do_perfil(p)} == {"inscricao_municipal"},
           "IM marcada para ir na DPS mas vazia")

    # Sem IM na DPS, a IM vazia nao e' pendencia.
    p = nf.validar_perfil(base(informar_im=False, inscricao_municipal=None))
    checar(nf.pendencias_do_perfil(p) == [], nf.pendencias_do_perfil(p))


def testar_regra_aliquota() -> None:
    """Tabela de pAliq do Anexo I (research.md), linha a linha."""
    def regra(**kw):
        return nf.regra_aliquota(nf.validar_perfil(fx.perfil_completo(**kw)))

    casos = [
        (dict(reg_ap_trib_sn=1, iss_retido=False, convenio_incidencia_ativo=True), nf.ALIQ_NAO_INFORMAR),
        (dict(reg_ap_trib_sn=1, iss_retido=False, convenio_incidencia_ativo=False), nf.ALIQ_NAO_INFORMAR),
        (dict(reg_ap_trib_sn=1, iss_retido=False, convenio_incidencia_ativo=None), nf.ALIQ_NAO_INFORMAR),
        (dict(reg_ap_trib_sn=1, iss_retido=True, convenio_incidencia_ativo=True), nf.ALIQ_INFORMAR),
        (dict(reg_ap_trib_sn=1, iss_retido=True, convenio_incidencia_ativo=False), nf.ALIQ_INFORMAR),
        (dict(reg_ap_trib_sn=2, reg_esp_trib=0, convenio_incidencia_ativo=True), nf.ALIQ_NAO_INFORMAR),
        (dict(reg_ap_trib_sn=2, reg_esp_trib=0, convenio_incidencia_ativo=False), nf.ALIQ_INFORMAR),
        (dict(reg_ap_trib_sn=3, reg_esp_trib=0, convenio_incidencia_ativo=None), nf.ALIQ_DEPENDE),
        (dict(reg_ap_trib_sn=2, reg_esp_trib=6, convenio_incidencia_ativo=False), nf.ALIQ_NAO_INFORMAR),
        (dict(reg_ap_trib_sn=None), nf.ALIQ_PENDENTE),
    ]
    for kw, esperado in casos:
        obtido = regra(**kw)
        checar(obtido == esperado, f"{kw}: {obtido} (esperado {esperado})")


def testar_perfil_invalido() -> None:
    base = fx.perfil_completo
    casos = [
        (base(cnpj="11.222.333/0001-80"), "cnpj"),
        (base(serie_dps="0"), "serie_dps"),
        (base(serie_dps="50000"), "serie_dps"),
        (base(serie_dps="abc"), "serie_dps"),
        (base(serie_dps=None), "serie_dps"),
        (base(aliquota="5,01"), "aliquota"),
        (base(aliquota="0"), "aliquota"),
        (base(reg_ap_trib_sn=1, reg_esp_trib=6), "reg_esp_trib"),
        (base(reg_ap_trib_sn=4), "reg_ap_trib_sn"),
        (base(reg_esp_trib=7), "reg_esp_trib"),
        (base(municipio_ibge="123"), "municipio_ibge"),
        (base(emissor="nota_salvador"), "emissor"),
        (base(op_simp_nac=2), "op_simp_nac"),
        (base(endereco_tomador="talvez"), "endereco_tomador"),
        (base(tributos_aprox="indTotTrib"), "tributos_aprox"),
        (base(p_tot_trib_sn="100,00"), "p_tot_trib_sn"),
        (base(razao_social="  "), "razao_social"),
        (base(iss_retido=None), "iss_retido"),
        (base(modelo_discriminacao="DE {MÊS}/{ANO}"), "modelo_discriminacao"),
    ]
    for dados, campo in casos:
        e = erro(nf.validar_perfil, dados)
        checar(e is not None and e.codigo == nf.PERFIL_INVALIDO and e.campo == campo,
               f"{campo}: {(e.codigo, e.campo, e.mensagem) if e else 'aceito'}")

    turmas_repetidas = fx.perfil_completo()
    turmas_repetidas["turmas"].append({"nome": "berçário", "c_trib_nac": "080101",
                                       "c_nbs": "122011100"})
    e = erro(nf.validar_perfil, turmas_repetidas)
    checar(e is not None and e.campo == "turmas", "nome de turma repetido")

    apelido_de_outra = fx.perfil_completo()
    apelido_de_outra["turmas"][1]["apelidos"] = ["Bercario"]
    e = erro(nf.validar_perfil, apelido_de_outra)
    checar(e is not None and e.campo == "turmas", "apelido igual a outra turma")

    codigo_ruim = fx.perfil_completo()
    codigo_ruim["turmas"][0]["c_trib_nac"] = "8011"
    e = erro(nf.validar_perfil, codigo_ruim)
    checar(e is not None and e.campo == "turmas", "cTribNac com 4 digitos")

    sem_turma = fx.perfil_completo(turmas=[])
    e = erro(nf.validar_perfil, sem_turma)
    checar(e is not None and e.campo == "turmas", "perfil sem turma")


def testar_modelo_discriminacao() -> None:
    nf.validar_modelo(fx.MODELO_CRECHE)
    for ruim in ("", "   ", "DE {MÊS}", "DE {Aluno}", "DE {aluno", "DE aluno}",
                 "{TURMA}{desconhecido}", "{}"):
        e = erro(nf.validar_modelo, ruim)
        checar(e is not None and e.codigo == nf.MODELO_INVALIDO, f"modelo {ruim!r}")

    texto = nf.montar_discriminacao(fx.MODELO_CRECHE, turma="Berçário",
                                    aluno="Pedro Exemplo",
                                    responsavel="Ana Exemplo",
                                    competencia="2026-11")
    esperado = ("REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO MENOR: "
                "PEDRO EXEMPLO NO PERÍODO DE 11/2026.")
    checar(texto == esperado, texto)
    texto = nf.montar_discriminacao(
        "{turma} - {aluno} ({mes_extenso}/{ano}) resp. {responsavel} {competencia} {MES_EXTENSO}",
        turma="Berçário", aluno="Pedro Exemplo", responsavel="Ana Exemplo",
        competencia="2026-03")
    checar(texto == "Berçário - Pedro Exemplo (março/2026) resp. Ana Exemplo 03/2026 MARÇO",
           texto)


def testar_turmas() -> None:
    p = nf.validar_perfil(fx.perfil_completo())
    for texto, nome in (("BERCARIO", "Berçário"), ("berçário 1", "Berçário"),
                        ("Bercario I", "Berçário"), ("Infantil 2", "Infantil II"),
                        (" infantil ii ", "Infantil II")):
        turma = nf.resolver_turma(texto, p.turmas)
        checar(turma is not None and turma.nome == nome, f"{texto!r} -> {turma}")
    for texto in ("Infantil", "Berçá", "", None):
        checar(nf.resolver_turma(texto, p.turmas) is None,
               f"{texto!r} nao pode ser adivinhado")
    por_nome = {t.nome: t for t in p.turmas}
    checar(not nf.turma_pendente(por_nome["Berçário"]), "bercario completo")
    checar(nf.turma_pendente(por_nome["Fundamental I"]), "fundamental sem NBS")

    casos = {
        "Pedro Exemplo - BERÇÁRIO": ("Pedro Exemplo", "BERÇÁRIO"),
        "Caio Teste - Bercario I": ("Caio Teste", "Bercario I"),
        "Pedro Exemplo – Infantil 2": ("Pedro Exemplo", "Infantil 2"),
        "Pedro Exemplo / Infantil II": ("Pedro Exemplo", "Infantil II"),
        "Ana Maria - Souza": ("Ana Maria - Souza", None),
        "Lia Exemplo": ("Lia Exemplo", None),
    }
    for texto, esperado in casos.items():
        obtido = nf.separar_turma_do_aluno(texto, p.turmas)
        checar(obtido == esperado, f"{texto!r} -> {obtido}")


def testar_catalogo() -> None:
    esperados = {
        "CPF_AUSENTE": "bloqueio", "CPF_INVALIDO": "bloqueio",
        "CPF_COMPLETADO": "aviso", "VALOR_AUSENTE": "bloqueio",
        "VALOR_INVALIDO": "bloqueio", "VALOR_NAO_POSITIVO": "bloqueio",
        "COMPETENCIA_AUSENTE": "bloqueio", "COMPETENCIA_INVALIDA": "bloqueio",
        "COMPETENCIA_DIVERGENTE": "aviso", "COMPETENCIA_FUTURA": "bloqueio",
        "TURMA_AUSENTE": "bloqueio", "TURMA_DESCONHECIDA": "bloqueio",
        "TURMA_PENDENTE": "bloqueio", "RESPONSAVEL_AUSENTE": "bloqueio",
        "ALUNO_AUSENTE": "bloqueio", "NOME_LONGO": "bloqueio",
        "ENDERECO_INCOMPLETO": "aviso", "ENDERECO_NAO_ESTRUTURADO": "aviso",
        "DUPLICATA_NO_LOTE": "bloqueio", "DUPLICATA_APROVADA": "bloqueio",
        "DISCRIMINACAO_LONGA": "bloqueio", "ROTULO_REPETIDO": "bloqueio",
        "TEXTO_NAO_RECONHECIDO": "aviso", "CARACTERE_REMOVIDO": "aviso",
    }
    checar(nf.CATALOGO == esperados,
           f"catalogo difere de data-model.md: {set(nf.CATALOGO) ^ set(esperados)}")


def testar_limites_arquiteturais() -> None:
    """O nucleo da NFS-e nao conhece interface, banco nem rede (FR-038)."""
    proibidos = ("fastapi", "starlette", "flask", "pydantic", "uvicorn",
                 "PySide6", "sqlite3", "httpx", "socket", "urllib", "requests",
                 "ssl", "http", "aiohttp", "signxml", "xmlsec")
    arquivos = glob.glob(os.path.join(RAIZ, "src", "auditoria_fiscal", "core",
                                      "nfse*.py"))
    checar(arquivos, "nenhum core/nfse*.py encontrado")
    for caminho in arquivos:
        nome = os.path.basename(caminho)
        with open(caminho, encoding="utf-8") as arq:
            arvore = ast.parse(arq.read())
        for no in ast.walk(arvore):
            modulos = []
            if isinstance(no, ast.Import):
                modulos = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                modulos = ["." * no.level + (no.module or "")]
            for modulo in modulos:
                raiz_mod = modulo.lstrip(".").split(".")[0]
                checar(raiz_mod not in proibidos,
                       f"core/{nome} nao pode importar {modulo}")
                checar("web" not in modulo, f"core/{nome} nao pode importar {modulo}")


def main() -> int:
    testar_normalizacao()
    testar_competencia()
    testar_cpf_e_valor()
    testar_perfil_valido()
    testar_perfil_sem_valor_padrao()
    testar_pendencias_condicionais()
    testar_regra_aliquota()
    testar_perfil_invalido()
    testar_modelo_discriminacao()
    testar_turmas()
    testar_catalogo()
    testar_limites_arquiteturais()
    print("OK - nucleo da NFS-e (normalizacao, competencia, CPF e valor sem "
          "chute, perfil sem valor padrao para JB-2/JB-8/R5, regra oficial da "
          "aliquota, validacao do perfil, modelo da discriminacao, turmas sem "
          "busca aproximada, catalogo e limites sem interface nem rede) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
