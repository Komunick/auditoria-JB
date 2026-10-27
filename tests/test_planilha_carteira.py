"""Spec 013: carteiras sinteticas XLS e XLSX, limites e sugestoes sem gravacao."""
import os
import base64
import re
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
from auditoria_fiscal.core import planilha_carteira as pc
from auditoria_fiscal.core.tarefas import ErroTarefas


CABECALHO = ["Empresas", "Contato", "Local", "Atividade", "E-mail", "Folha", "E-consignado", "Boleto sindical", "Observacao"]
LINHAS = [
    ["Carteira sintetica"], CABECALHO,
    ["Empresa Sintetica Alfa", "Contato Teste", "Municipio Teste", "Comercio", "contato@example.test", "X", "X", "X", "Adiantamento quinzenal; sem movimento"],
    ["Empresa Sintetica Beta", "", "", "", "email-invalido", "", "", "", "Lucro real; contribuicao negocial"],
]

# Livro OLE/BIFF8 sintetico, gerado com xlwt 1.3.0; a execucao do teste
# nao depende de xlwt. A linha 4 tem formulas em Empresas e E-mail.
XLS_OLE = (
    "eJztWE1oE0EUfrP5belPGhOhFcNSsGqtgnjx0qZaYi/aVisoIui2nUNokg2bpagXqzVHQfAgipdCL16qXvxBD3rzIFT0IAhCq0dP"
    "goKHNut7b39MtYXmkKqw32bezHvz3pufNzM72TcLbYuzDzuW4Df0QQAqVgOEq2QCU4PLxADrLYuKbh7FZPn4r9AQxUCGQ/Cs+XWE"
    "YkjxXgIFHgRfIgX4hOksFGFIL0h1E3GY+6AJ6kMvUgF3UdIC7dyrONNxpluY3mfN50z7WXKdaS/qLoozsJAe6j7orOLTSifXtQD5"
    "fcw2H1iyH5Lwilbx5RvC1g3BISOr5f7NilSwCeYA4zYoC9LQcouQwADOwXdLBfjm7tQXqi/fXLkAlP9YLY+sIb+pBAGmwTrPC7yM"
    "Z2pfkGqiMKAZpswa2jLcgkawj904eGK1lC2Y0syOa3jmZvJFQ5a0Eq6DAb1gaqaOmzizN69lc2g6PFaSxpQ2rulJT1Uddc3V4aOZ"
    "Zs9OPSlLpkzgzrL5fnlByxdzcp+JclQblXk1r09l87Jg6twtPj1iq06PZt5VTUgnoJXLbby3Yjis5Xtf3x4bG0mfY8k0vzHs98oO"
    "mgqw4ApZoHEL1wQ92s0We5heZa/buNzBNIE7AvOukaRTODLDOte4tgvbOcB4l95ZVd6F5fKX409S5c/p3VieH1y6lJh/n56FTpzw"
    "CbSnZwZ6RI+4c5vwNO3mwjmDPjJt/+M8iioxZ2yWHW3RCiscSsD5AEdD8OhWawjWIGpz7vzZnIJcwOMCyAUdX8oavhT2FXL07ViE"
    "PY58RTyOfEUdX9RCoMpXGLazzG6b3vJ2VQRSgn4BchHw3NvqyvrqfUocHlHn8Kz+hUbw4cOHDx8+fPjwUW/QPZMuYnRRo5sk3RXp"
    "Ckf3Qvqus4Kp8rc/UvioG06Ajo+Jf0wzUMDcgIs1rZ+tEBKuL7FBG/d7IeEUtm7AJIxxPyZrapuA/8JE9Xg2bBiruan1UHP7lVr6"
    "Wef2fwLNefi5"
)


def escrever_xls(caminho, linhas):
    """BIFF2 sintetico: um .xls valido, sem dependencia de escrita no servidor."""
    def registro(tipo, dados=b""):
        return struct.pack("<HH", tipo, len(dados)) + dados
    conteudo = registro(0x0009, struct.pack("<HH", 2, 0x0010))
    conteudo += registro(0x0042, struct.pack("<H", 1252))
    for r, linha in enumerate(linhas):
        for c, valor in enumerate(linha):
            texto = str(valor).encode("cp1252")
            conteudo += registro(0x0004, struct.pack("<HH", r, c) + b"\0\0\0" + bytes([len(texto)]) + texto)
    conteudo += registro(0x000A)
    Path(caminho).write_bytes(conteudo)


def escrever_xlsx(caminho, linhas):
    livro = Workbook()
    livro.active.title = "Carteira"
    for linha in linhas:
        livro.active.append(linha)
    livro.save(caminho)
    livro.close()


def recusa(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ErroTarefas:
        return
    raise AssertionError(f"Planilha invalida aceita: {args}")


def main():
    with tempfile.TemporaryDirectory(prefix="carteira_sintetica_") as pasta:
        for extensao, escrever in ((".xls", escrever_xls), (".xlsx", escrever_xlsx)):
            caminho = os.path.join(pasta, "carteira" + extensao)
            escrever(caminho, LINHAS)
            leitura = pc.ler_planilha_carteira(caminho)
            resumo = leitura.resumo()
            assert leitura.linha_cabecalho == 2
            assert len(leitura.linhas) == 2 and len(leitura.hash_arquivo) == 64
            alfa, beta = leitura.linhas
            assert alfa.nome == "Empresa Sintetica Alfa"
            assert alfa.contato_nome == "Contato Teste" and alfa.contato_email == "contato@example.test"
            assert alfa.sugestoes_caracteristicas == ["Adiantamento quinzenal", "Sem movimento"]
            assert beta.sugestoes_caracteristicas == ["Lucro real", "Contribuição negocial"]
            assert beta.pendencias and beta.contato_email == ""
            assert beta.contato_email_informado == "email-invalido"
            assert alfa.origem["celulas"]["nome"] == "A3" and alfa.origem["hash_arquivo"] == leitura.hash_arquivo
            assert set(leitura.colunas_ignoradas) == {"Folha", "E-consignado", "Boleto sindical"}
            assert "folha" not in resumo["linhas"][0]
            assert Path(caminho).exists(), "O chamador controla o ciclo de vida do upload"
            recusa(pc.ler_planilha_carteira, caminho, max_bytes=10)

        formula = os.path.join(pasta, "formula.xlsx")
        escrever_xlsx(formula, [["Empresas", "Contato", "E-mail"], ["=HYPERLINK(\"https://example.test\")", "Teste", "=1+1"]])
        row = pc.ler_planilha_carteira(formula).linhas[0]
        assert row.nome == "" and row.contato_email == "" and len(row.pendencias) == 2
        ole = os.path.join(pasta, "ole.xls")
        Path(ole).write_bytes(zlib.decompress(base64.b64decode(XLS_OLE)))
        leitura_ole = pc.ler_planilha_carteira(ole)
        assert leitura_ole.linhas[0].nome == "Empresa Sintetica OLE"
        assert leitura_ole.linhas[0].contato_email == "contato@example.test"
        formula_ole = leitura_ole.linhas[1]
        assert formula_ole.nome == "" and formula_ole.contato_email == "" and len(formula_ole.pendencias) == 2

        dimensao = os.path.join(pasta, "dimensao.xlsx")
        escrever_xlsx(dimensao, LINHAS)
        with zipfile.ZipFile(dimensao) as origem:
            entradas = {n: origem.read(n) for n in origem.namelist()}
        entradas["xl/worksheets/sheet1.xml"] = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="A1:E3"', entradas["xl/worksheets/sheet1.xml"])
        with zipfile.ZipFile(dimensao, "w", zipfile.ZIP_DEFLATED) as destino:
            for nome, dados in entradas.items():
                destino.writestr(nome, dados)
        assert len(pc.ler_planilha_carteira(dimensao).linhas) == 2, "Dimensao declarada nao pode truncar linhas reais"
        sem_cabecalho = os.path.join(pasta, "sem-cabecalho.xlsx")
        escrever_xlsx(sem_cabecalho, [["Qualquer coluna"], ["Teste"]])
        recusa(pc.ler_planilha_carteira, sem_cabecalho)
        duplicado = os.path.join(pasta, "duplicado.xlsx")
        escrever_xlsx(duplicado, [["Empresas", "Empresa"], ["A", "B"]])
        recusa(pc.ler_planilha_carteira, duplicado)
        for nome, conteudo in (("falso.xls", b"not an excel file"), ("vazio.xlsx", b""), ("texto.csv", b"a,b")):
            caminho = os.path.join(pasta, nome)
            Path(caminho).write_bytes(conteudo)
            recusa(pc.ler_planilha_carteira, caminho)
        perigoso = os.path.join(pasta, "macro.xlsx")
        escrever_xlsx(perigoso, LINHAS)
        with zipfile.ZipFile(perigoso, "a") as pacote:
            pacote.writestr("xl/vbaProject.bin", b"synthetic")
        recusa(pc.ler_planilha_carteira, perigoso)
        colunas = os.path.join(pasta, "colunas.xlsx")
        escrever_xlsx(colunas, [["Empresas"] + ["Campo"] * 1000])
        recusa(pc.ler_planilha_carteira, colunas)

        clientes = [{"id": 1, "nome": "Empresa Sintética Alfa", "documento": ""},
                    {"id": 2, "nome": "Empresa Sintetica Beta", "documento": ""},
                    {"id": 3, "nome": "Outra empresa", "documento": "123"},
                    {"id": 4, "nome": "Empresa Sintetica Gamma", "documento": ""}]
        sugestoes = pc.sugerir_clientes({"nome": "  empresa sintética alfa ", "documento": ""}, clientes)
        assert sugestoes[0]["cliente_id"] == 1 and sugestoes[0]["tipo"] == "nome"
        assert len(sugestoes) <= 3
        assert pc.sugerir_clientes({"nome": "Outro", "documento": "123"}, clientes)[0]["cliente_id"] == 3
        assert pc.sugerir_clientes({"nome": "", "documento": ""}, clientes) == []
    print("OK - carteiras XLS/XLSX sinteticas, origem, sugestoes, email, formulas e pacotes invalidos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
