"""Persistencia do Patrimonio (SQLite dedicado, sem camada web).

Cobre schema idempotente, etiqueta sequencial e imutavel, serie unica,
hierarquia de dois niveis, UM responsavel ativo por bem sob concorrencia,
movimentacao append-only, baixa terminal, revision otimista, inventario com
universo congelado e as consultas com filtros por allowlist.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import patrimonio as pt  # noqa: E402
from auditoria_fiscal.ferramentas import patrimonio_store as ps  # noqa: E402

ANA = {"usuario_id": 7, "usuario_login": "ana"}


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def abrir(pasta: str) -> ps.PatrimonioStore:
    return ps.PatrimonioStore(db_path=os.path.join(pasta, "patrimonio.db"))


def bem_exemplo(**ajustes) -> dict:
    base = {"descricao": "Notebook Dell Latitude 5440", "tipo": "Notebook",
            "conservacao": "novo", "valor_aquisicao": "4.500,00"}
    base.update(ajustes)
    return base


def erro_de(funcao, *args, **kwargs) -> str:
    try:
        funcao(*args, **kwargs)
    except pt.ErroPatrimonio as exc:
        return exc.codigo
    return ""


def testar_schema(pasta: str) -> None:
    caminho = os.path.join(pasta, "patrimonio.db")
    for _ in range(3):
        ps.PatrimonioStore(db_path=caminho).fechar()
    with sqlite3.connect(caminho) as conn:
        tabelas = {l[0] for l in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        esperadas = {"local", "pessoa", "bem", "responsabilidade",
                     "movimentacao", "inventario", "inventario_item"}
        checar(not (esperadas - tabelas), f"tabelas ausentes: {esperadas - tabelas}")
        checar(conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal",
               "deveria estar em WAL")


def testar_etiqueta_e_hierarquia(pasta: str) -> None:
    store = abrir(os.path.join(pasta, "b1"))
    try:
        a = store.criar_bem(bem_exemplo(), **ANA)
        b = store.criar_bem(bem_exemplo(descricao="Monitor 24"), **ANA)
        checar(a["etiqueta"] == "JBF-000001", a["etiqueta"])
        checar(b["etiqueta"] == "JBF-000002", b["etiqueta"])

        # Periferico tem sequencia PROPRIA.
        p = store.criar_bem(bem_exemplo(descricao="Fonte", pai_id=a["id"]),
                            **ANA)
        checar(p["etiqueta"] == "PER-000001", p["etiqueta"])
        p2 = store.criar_bem(bem_exemplo(descricao="Mouse", pai_id=a["id"]),
                             **ANA)
        checar(p2["etiqueta"] == "PER-000002", p2["etiqueta"])

        # Dois niveis: periferico de periferico e' recusado.
        checar(erro_de(store.criar_bem,
                       bem_exemplo(descricao="Cabo", pai_id=p["id"]), **ANA)
               == pt.HIERARQUIA_INVALIDA, "tres niveis deveriam ser recusados")

        # ETIQUETA IMUTAVEL — a garantia mora no banco.
        conn = sqlite3.connect(os.path.join(pasta, "b1", "patrimonio.db"))
        try:
            for sql in ("UPDATE bem SET etiqueta='JBF-999999' WHERE id=1",
                        "UPDATE bem SET numero_etiqueta=99 WHERE id=1",
                        "DELETE FROM bem WHERE id=1"):
                try:
                    conn.execute(sql)
                    conn.commit()
                    checar(False, f"'{sql}' deveria ter sido recusado")
                except sqlite3.IntegrityError:
                    conn.rollback()
        finally:
            conn.close()

        # Serie unica.
        store.criar_bem(bem_exemplo(descricao="Impressora",
                                    numero_serie="SN-001"), **ANA)
        checar(erro_de(store.criar_bem,
                       bem_exemplo(descricao="Outra", numero_serie="SN-001"),
                       **ANA) == "SERIE_DUPLICADA", "serie repetida")
        # Serie vazia nao colide com outra serie vazia.
        store.criar_bem(bem_exemplo(descricao="Sem serie A"), **ANA)
        store.criar_bem(bem_exemplo(descricao="Sem serie B"), **ANA)

        # Cadastro ja nasce com a movimentacao de aquisicao na trilha.
        detalhe = store.detalhar(a["id"])
        checar(detalhe["situacao"] == pt.SITUACAO_DISPONIVEL, detalhe["situacao"])
        checar(len(detalhe["movimentacoes"]) == 1, detalhe["movimentacoes"])
        checar(detalhe["movimentacoes"][0]["tipo"] == pt.MOV_AQUISICAO,
               detalhe["movimentacoes"][0])
        checar(len(detalhe["perifericos"]) == 2, detalhe["perifericos"])
    finally:
        store.fechar()


def testar_responsabilidade(pasta: str) -> None:
    store = abrir(os.path.join(pasta, "b2"))
    try:
        bem = store.criar_bem(bem_exemplo(), **ANA)
        maria = store.criar_pessoa("Maria Silva", cpf="529.982.247-25",
                                   setor="Fiscal")
        joao = store.criar_pessoa("Joao Souza", setor="Contábil")

        store.movimentar(bem["id"], pt.MOV_ATRIBUICAO, pessoa_id=maria,
                         observacao="Entrega inicial.", **ANA)
        atual = store.responsavel_atual(bem["id"])
        checar(atual and atual["pessoa_id"] == maria, atual)
        checar(store.obter_bem(bem["id"])["situacao"] == pt.SITUACAO_EM_USO,
               "situacao deveria virar em_uso")

        # UM responsavel por vez: atribuir de novo sem devolver e' recusado.
        codigo = erro_de(store.movimentar, bem["id"], pt.MOV_ATRIBUICAO,
                         pessoa_id=joao, **ANA)
        checar(codigo == pt.TRANSICAO_INVALIDA,
               f"atribuir com responsavel ativo: {codigo}")

        # Devolver encerra SEM apagar.
        store.movimentar(bem["id"], pt.MOV_DEVOLUCAO, pessoa_id=maria,
                         observacao="Devolveu.", **ANA)
        checar(store.responsavel_atual(bem["id"]) is None, "sem responsavel")
        historico = store.detalhar(bem["id"])["responsabilidades"]
        checar(len(historico) == 1, historico)
        checar(historico[0]["encerrada_em"], "a responsabilidade tem fim")
        checar(historico[0]["encerrada_por_login"] == "ana", historico[0])

        # Reatribuir cria um NOVO registro, preservando o anterior.
        store.movimentar(bem["id"], pt.MOV_ATRIBUICAO, pessoa_id=joao, **ANA)
        historico = store.detalhar(bem["id"])["responsabilidades"]
        checar(len(historico) == 2, f"deveria ter 2 registros: {len(historico)}")

        # Colaborador desligado nao recebe bem novo.
        store.desativar_pessoa(maria)
        outro = store.criar_bem(bem_exemplo(descricao="Monitor"), **ANA)
        checar(erro_de(store.movimentar, outro["id"], pt.MOV_ATRIBUICAO,
                       pessoa_id=maria, **ANA) == "PESSOA_INATIVA",
               "desligado nao recebe bem")

        # Mas o que ele ja tinha continua sob responsabilidade dele.
        terceiro = store.criar_bem(bem_exemplo(descricao="Teclado"), **ANA)
        pedro = store.criar_pessoa("Pedro Lima")
        store.movimentar(terceiro["id"], pt.MOV_ATRIBUICAO, pessoa_id=pedro,
                         **ANA)
        resultado = store.desativar_pessoa(pedro)
        checar(len(resultado["bens_pendentes"]) == 1,
               f"desligar nao pode zerar a responsabilidade: {resultado}")
        checar(store.responsavel_atual(terceiro["id"])["pessoa_id"] == pedro,
               "o bem continua com quem saiu ate alguem registrar a devolucao")
    finally:
        store.fechar()


def testar_concorrencia(pasta: str) -> None:
    """Duas atribuicoes simultaneas: o banco garante um dono so."""
    base = os.path.join(pasta, "b3")
    store = abrir(base)
    try:
        bem = store.criar_bem(bem_exemplo(), **ANA)
        pessoas = [store.criar_pessoa(f"Pessoa {i}") for i in range(4)]
    finally:
        store.fechar()

    sucessos: list = []
    recusas: list = []
    barreira = threading.Barrier(len(pessoas))

    def _atribuir(indice: int) -> None:
        proprio = abrir(base)
        try:
            barreira.wait(timeout=10)
            proprio.movimentar(bem["id"], pt.MOV_ATRIBUICAO,
                               pessoa_id=pessoas[indice], **ANA)
            sucessos.append(indice)
        except (pt.ErroPatrimonio, ps.ConcorrenciaError) as exc:
            recusas.append(type(exc).__name__)
        finally:
            proprio.fechar()

    threads = [threading.Thread(target=_atribuir, args=(i,))
               for i in range(len(pessoas))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    checar(len(sucessos) == 1,
           f"exatamente uma atribuicao deveria vencer: {sucessos} {recusas}")
    checar(len(recusas) == len(pessoas) - 1, recusas)

    store = abrir(base)
    try:
        ativas = store._conn.execute(          # noqa: SLF001 — checagem direta
            "SELECT COUNT(*) AS n FROM responsabilidade"
            " WHERE bem_id=? AND encerrada_em IS NULL",
            (bem["id"],)).fetchone()["n"]
        checar(ativas == 1, f"deveria haver UMA responsabilidade ativa: {ativas}")
    finally:
        store.fechar()


def testar_movimentacoes_e_baixa(pasta: str) -> None:
    base = os.path.join(pasta, "b4")
    store = abrir(base)
    try:
        bem = store.criar_bem(bem_exemplo(), **ANA)
        pessoa = store.criar_pessoa("Carla Dias")
        sala = store.criar_local("Sala Fiscal")

        store.movimentar(bem["id"], pt.MOV_ATRIBUICAO, pessoa_id=pessoa, **ANA)
        store.movimentar(bem["id"], pt.MOV_EMPRESTIMO, pessoa_id=pessoa,
                         observacao="Home office.", **ANA)
        checar(store.obter_bem(bem["id"])["situacao"] == pt.SITUACAO_EMPRESTADO,
               "emprestado")
        store.movimentar(bem["id"], pt.MOV_RETORNO_EMPRESTIMO,
                         pessoa_id=pessoa, **ANA)
        store.movimentar(bem["id"], pt.MOV_MANUTENCAO,
                         observacao="Troca de tela.", **ANA)
        checar(store.obter_bem(bem["id"])["situacao"] == pt.SITUACAO_MANUTENCAO,
               "manutencao")
        store.movimentar(bem["id"], pt.MOV_RETORNO_MANUTENCAO, **ANA)
        store.movimentar(bem["id"], pt.MOV_TRANSFERENCIA, local_id=sala,
                         observacao="Mudou de sala.", **ANA)
        checar(store.obter_bem(bem["id"])["local_id"] == sala, "local mudou")
        checar(store.obter_bem(bem["id"])["situacao"] == pt.SITUACAO_DISPONIVEL,
               "transferencia nao muda a situacao")

        # Baixa exige justificativa.
        checar(erro_de(store.movimentar, bem["id"], pt.MOV_BAIXA, **ANA)
               == pt.JUSTIFICATIVA_OBRIGATORIA, "baixa sem justificativa")
        store.movimentar(bem["id"], pt.MOV_BAIXA,
                         observacao="Equipamento obsoleto, doado.", **ANA)
        checar(store.obter_bem(bem["id"])["situacao"] == pt.SITUACAO_BAIXADO,
               "baixado")

        # BAIXA E TERMINAL.
        for movimento in (pt.MOV_ATRIBUICAO, pt.MOV_MANUTENCAO,
                          pt.MOV_TRANSFERENCIA, pt.MOV_BAIXA):
            codigo = erro_de(store.movimentar, bem["id"], movimento,
                             pessoa_id=pessoa, observacao="x", **ANA)
            checar(codigo == pt.BEM_BAIXADO,
                   f"{movimento} apos baixa: {codigo}")
        checar(erro_de(store.editar_bem, bem["id"], bem_exemplo())
               == pt.BEM_BAIXADO, "bem baixado nao e editado")

        # A trilha registrou tudo, na ordem, com autor.
        movimentos = store.detalhar(bem["id"])["movimentacoes"]
        tipos = [m["tipo"] for m in reversed(movimentos)]
        checar(tipos == [pt.MOV_AQUISICAO, pt.MOV_ATRIBUICAO,
                         pt.MOV_EMPRESTIMO, pt.MOV_RETORNO_EMPRESTIMO,
                         pt.MOV_MANUTENCAO, pt.MOV_RETORNO_MANUTENCAO,
                         pt.MOV_TRANSFERENCIA, pt.MOV_BAIXA],
               f"trilha fora de ordem: {tipos}")
        checar(all(m["usuario_login"] == "ana" for m in movimentos),
               "o autor vem do snapshot, nunca do corpo")
    finally:
        store.fechar()

    # MOVIMENTACAO APPEND-ONLY, garantido pelo banco.
    conn = sqlite3.connect(os.path.join(base, "patrimonio.db"))
    try:
        for sql in ("UPDATE movimentacao SET tipo='nada'",
                    "DELETE FROM movimentacao"):
            try:
                conn.execute(sql)
                conn.commit()
                checar(False, f"'{sql}' deveria ter sido recusado")
            except sqlite3.IntegrityError:
                conn.rollback()
    finally:
        conn.close()


def testar_revision(pasta: str) -> None:
    store = abrir(os.path.join(pasta, "b5"))
    try:
        bem = store.criar_bem(bem_exemplo(), **ANA)
        atual = store.obter_bem(bem["id"])["revision"]
        store.editar_bem(bem["id"], bem_exemplo(descricao="Notebook novo nome"),
                         revision=atual)
        try:
            store.editar_bem(bem["id"], bem_exemplo(descricao="Outro"),
                             revision=atual)
            checar(False, "revision velha deveria dar conflito")
        except ps.ConcorrenciaError as exc:
            checar(exc.revision_atual == atual + 1, exc.revision_atual)
    finally:
        store.fechar()


def testar_inventario(pasta: str) -> None:
    store = abrir(os.path.join(pasta, "b6"))
    try:
        bens = [store.criar_bem(bem_exemplo(descricao=f"Bem {i}"), **ANA)
                for i in range(4)]
        store.movimentar(bens[3]["id"], pt.MOV_BAIXA,
                         observacao="Fora de uso.", **ANA)

        inv = store.abrir_inventario(usuario_login="ana")
        resumo = store.resumo_inventario(inv)
        checar(resumo["total"] == 3,
               f"baixado nao entra no inventario: {resumo['total']}")

        # Uma sessao aberta por vez.
        checar(erro_de(store.abrir_inventario, usuario_login="ana")
               == "INVENTARIO_ABERTO", "segunda sessao deveria ser recusada")

        # Bem cadastrado DEPOIS nao entra na sessao.
        novo = store.criar_bem(bem_exemplo(descricao="Cadastrado depois"),
                               **ANA)
        try:
            store.conferir(inv, novo["id"], "localizado", usuario_login="ana")
            checar(False, "bem novo nao deveria estar no inventario")
        except LookupError:
            pass

        store.conferir(inv, bens[0]["id"], "localizado", usuario_login="ana")
        store.conferir(inv, bens[1]["id"], "nao_localizado",
                       observacao="Não estava na sala.", usuario_login="ana")
        checar(erro_de(store.conferir, inv, bens[2]["id"], "sumiu",
                       usuario_login="ana") == "RESULTADO_INVALIDO",
               "resultado fora do catalogo")

        resumo = store.fechar_inventario(inv, usuario_login="ana")
        checar(resumo["estado"] == "fechado", resumo["estado"])
        checar(resumo["contagens"].get("localizado") == 1, resumo["contagens"])
        checar(resumo["contagens"].get("nao_localizado") == 1, resumo)
        checar(resumo["contagens"].get("pendente") == 1, resumo)

        # Fechada e' imutavel; e agora da para abrir outra.
        checar(erro_de(store.conferir, inv, bens[2]["id"], "localizado",
                       usuario_login="ana") == "INVENTARIO_FECHADO",
               "conferir em sessao fechada")
        segundo = store.abrir_inventario(usuario_login="ana")
        checar(segundo != inv, "nova sessao")
        checar(store.resumo_inventario(segundo)["total"] == 4,
               "a nova sessao inclui o bem cadastrado depois")
    finally:
        store.fechar()


def testar_consultas(pasta: str) -> None:
    store = abrir(os.path.join(pasta, "b7"))
    try:
        sala = store.criar_local("Sala 1")
        pessoa = store.criar_pessoa("Ana Paula")
        for i in range(6):
            tipo = "Notebook" if i % 2 else "Monitor"
            store.criar_bem(bem_exemplo(descricao=f"Equipamento {i}",
                                        tipo=tipo, local_id=sala,
                                        valor_aquisicao="1.000,00"), **ANA)
        primeiro = store.listar(limite=1)["itens"][0]
        store.movimentar(primeiro["id"], pt.MOV_ATRIBUICAO, pessoa_id=pessoa,
                         **ANA)
        ultimo = store.listar(limite=100)["itens"][-1]
        store.movimentar(ultimo["id"], pt.MOV_BAIXA, observacao="Quebrado.",
                         **ANA)

        # Baixado some por padrao, mas continua consultavel.
        checar(store.listar()["total"] == 5, store.listar()["total"])
        checar(store.listar(incluir_baixados=True)["total"] == 6,
               "com incluir_baixados o total volta")

        # Sao 3 notebooks, mas o ultimo foi baixado: o filtro respeita a
        # exclusao padrao dos baixados, e voltar a inclui-los devolve os 3.
        checar(store.listar(tipo="Notebook")["total"] == 2,
               store.listar(tipo="Notebook")["total"])
        checar(store.listar(tipo="Notebook",
                            incluir_baixados=True)["total"] == 3,
               "com baixados, os 3 notebooks aparecem")
        checar(store.listar(situacao=pt.SITUACAO_EM_USO)["total"] == 1,
               "filtro por situacao")
        checar(store.listar(pessoa_id=pessoa)["total"] == 1,
               "filtro por responsavel")
        checar(store.listar(local_id=sala)["total"] == 5, "filtro por local")
        checar(store.listar(texto="Equipamento 2")["total"] == 1, "busca")
        checar(store.listar(texto="JBF-000001")["total"] == 1,
               "busca pela etiqueta")
        checar(store.listar(texto="%")["total"] == 0,
               "'%' digitado nao pode casar com tudo")

        try:
            store.listar(coluna_inventada="x")
            checar(False, "filtro fora da allowlist deveria ser recusado")
        except ValueError:
            pass

        # Paginacao nem duplica nem omite.
        vistos = []
        pagina = store.listar(limite=2, pagina=1)
        for numero in range(1, pagina["paginas"] + 1):
            atual = store.listar(limite=2, pagina=numero)
            vistos += [i["id"] for i in atual["itens"]]
        checar(len(vistos) == len(set(vistos)) == 5, vistos)

        resumo = store.resumo()
        checar(resumo["total"] == 5, resumo)
        checar(resumo["em_uso"] == 1, resumo)
        checar(resumo["baixados"] == 1, resumo)
        checar(resumo["valor_total"] == 500000,
               f"valor em centavos dos 5 ativos: {resumo['valor_total']}")

        # A linha da lista ja diz quem esta com o bem.
        linha = store.listar(pessoa_id=pessoa)["itens"][0]
        checar(linha["responsavel_nome"] == "Ana Paula", linha)
        checar(linha["local_nome"] == "Sala 1", linha)

        pessoas = store.listar_pessoas()
        checar(pessoas[0]["bens_ativos"] == 1, pessoas[0])
        locais = store.listar_locais()
        checar(locais[0]["bens"] == 5, locais[0])

        # Leitura por etiqueta (o QR da etiqueta fisica).
        achado = store.obter_por_etiqueta("jbf-000001")
        checar(achado["etiqueta"] == "JBF-000001", achado["etiqueta"])
        try:
            store.obter_por_etiqueta("JBF-999999")
            checar(False, "etiqueta inexistente deveria falhar")
        except LookupError:
            pass
    finally:
        store.fechar()


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="patrimonio_store_")
    try:
        testar_schema(os.path.join(pasta, "b0"))
        testar_etiqueta_e_hierarquia(pasta)
        testar_responsabilidade(pasta)
        testar_concorrencia(pasta)
        testar_movimentacoes_e_baixa(pasta)
        testar_revision(pasta)
        testar_inventario(pasta)
        testar_consultas(pasta)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    print("OK - store do patrimonio (schema idempotente, etiqueta sequencial e "
          "imutavel no banco, serie unica, dois niveis, UM responsavel ativo "
          "sob concorrencia, trilha append-only, baixa terminal, revision "
          "otimista, inventario com universo congelado e consultas filtradas) "
          "passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
