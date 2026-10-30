"""Confirmação transacional de empresas da Base Fiscal, independente da web.

O chamador relê os dois arquivos e entrega a prévia pura da spec 020. A
assinatura vem da preparação mantida pelo servidor, nunca de linhas enviadas
pelo navegador. A transação confere novamente o cadastro antes de inserir.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from ..core import clientes as cl
from ..core import correcoes_base_fiscal as cbf
from ..core.documentos_br import DocumentoInvalido, digitos_cnpj
from .clientes_store import agora


_HASH = re.compile(r"[0-9a-f]{64}")
_CAMPOS_CADASTRO = ("id", "nome", "documento", "contato_nome", "situacao", "revision")
_CAMPOS_LINHA = ("id", "aba", "linha", "status", "efetivo", "decisao", "observacao")
_ESTADOS = {"incluir", "existente", "ignorar", "pendente", "conflito"}


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _bloqueada(mensagem: str) -> cl.ErroClientes:
    return cl.ErroClientes("BASE_FISCAL_BLOQUEADA", mensagem)


def _linhas(previa: dict) -> list[dict]:
    if not isinstance(previa, dict) or previa.get("formato") != "base_fiscal_importacao_v1":
        raise _bloqueada("A conferência da Base Fiscal é inválida. Gere uma nova prévia.")
    if any(not isinstance(previa.get(c), str) or not _HASH.fullmatch(previa[c])
           for c in ("hash_arquivo", "hash_correcoes")):
        raise _bloqueada("A conferência não identifica os dois arquivos originais.")
    linhas = previa.get("linhas")
    if not isinstance(linhas, list) or len(linhas) > 10000:
        raise _bloqueada("A conferência excede o limite de registros ou está inválida.")
    ids = set()
    for linha in linhas:
        if (not isinstance(linha, dict) or not isinstance(linha.get("id"), str)
                or not linha["id"] or linha["id"] in ids
                or linha.get("status") not in _ESTADOS
                or not isinstance(linha.get("efetivo"), dict)):
            raise _bloqueada("A conferência contém uma ocorrência inválida ou repetida.")
        ids.add(linha["id"])
    return linhas


def assinatura_previa(previa: dict) -> str:
    """Assina a classificação e o snapshot; nomes e horário não participam.

    Cadastro ``None`` é parte da assinatura e representa explicitamente a
    ausência encontrada. Origens enriquecidas posteriormente não alteram a
    assinatura: seus conteúdos já são vinculados pelos hashes dos arquivos.
    """
    linhas = []
    for linha in _linhas(previa):
        item = {campo: linha.get(campo) for campo in _CAMPOS_LINHA}
        cadastro = linha.get("cadastro")
        item["cadastro"] = ({campo: cadastro.get(campo) for campo in _CAMPOS_CADASTRO}
                            if cadastro is not None else None)
        linhas.append(item)
    objeto = {"hash_arquivo": previa["hash_arquivo"], "hash_correcoes": previa["hash_correcoes"],
              "linhas": sorted(linhas, key=lambda linha: linha["id"])}
    return hashlib.sha256(_json(objeto).encode("utf-8")).hexdigest()


def validar_apta(previa: dict) -> None:
    """Lote inteiro precisa estar resolvido e conter alguma inclusão.

    Nunca usa as contagens agregadas como autoridade. Ocorrências explicitamente
    ignoradas podem conservar os problemas da fonte, pois não serão incluídas.
    """
    incluir = 0
    documentos = set()
    for linha in _linhas(previa):
        estado = linha["status"]
        if estado in {"pendente", "conflito"}:
            raise _bloqueada("Resolva todas as pendências e conflitos antes de preparar a importação.")
        if estado == "ignorar":
            if linha.get("decisao") != "ignorar" or not str(linha.get("observacao") or "").strip():
                raise _bloqueada("Ignorar uma ocorrência exige decisão e justificativa explícitas.")
            continue
        efetivo = linha["efetivo"]
        documento = efetivo.get("documento")
        try:
            if not isinstance(documento, str) or not re.fullmatch(r"[0-9]{14}", documento):
                raise DocumentoInvalido("Documento inválido")
            digitos_cnpj(documento)
        except DocumentoInvalido as exc:
            raise _bloqueada("A conferência contém um CNPJ inválido.") from exc
        if documento in documentos:
            raise _bloqueada("Há ocorrências repetidas sem decisão de qual manter.")
        documentos.add(documento)
        nome, contato = efetivo.get("nome"), efetivo.get("contato_nome")
        if (not isinstance(nome, str) or not nome.strip() or len(nome) > 160
                or not isinstance(contato, str) or len(contato) > 160
                or linha.get("pendencias")):
            raise _bloqueada("A conferência contém campos inválidos ou pendentes.")
        if estado == "incluir":
            incluir += 1
    if not incluir:
        raise cl.ErroClientes("BASE_FISCAL_SEM_INCLUSAO",
                              "A conferência não possui novas empresas para incluir.")


def enriquecer_origens(previa: dict, leitura) -> dict:
    """Conserva células e valores lidos sem modificar a leitura ou a prévia."""
    linhas = _linhas(previa)
    por_id = {linha.id: linha for linha in leitura.linhas}
    if (previa["hash_arquivo"] != leitura.hash_arquivo
            or {linha["id"] for linha in linhas} != set(por_id)):
        raise _bloqueada("A origem não corresponde à conferência da Base Fiscal.")
    resultado = deepcopy(previa)
    for linha in resultado["linhas"]:
        linha["origem"] = deepcopy(por_id[linha["id"]].origem)
    return resultado


def _consultar(conn, base: dict) -> list[dict]:
    documentos = sorted({linha["efetivo"]["documento"] for linha in base["linhas"]
                         if isinstance(linha["efetivo"].get("documento"), str)
                         and re.fullmatch(r"[0-9]{14}", linha["efetivo"]["documento"])})
    clientes = []
    campos = ",".join(_CAMPOS_CADASTRO)
    for inicio in range(0, len(documentos), 400):
        lote = documentos[inicio:inicio + 400]
        marcadores = ",".join("?" for _ in lote)
        clientes.extend(dict(linha) for linha in conn.execute(
            f"SELECT {campos} FROM cliente WHERE documento IN ({marcadores}) ORDER BY documento,id", lote))
    return clientes


def _nome_arquivo(valor: str) -> str:
    return str(valor or "").replace("\\", "/").rsplit("/", 1)[-1][:200]


def importar_base_fiscal(store, previa_base: dict, assinatura_esperada: str, *,
                        nome_arquivo: str, nome_correcoes: str,
                        usuario_id: int, usuario_login: str, revalidar=None) -> dict:
    """Insere apenas novos clientes e confirma a trilha e o recibo atomicamente.

    A repetição é reconhecida antes de comparar revisões: depois de uma carga
    concluída, o cadastro pode ter mudado legitimamente. O recibo é a autoridade
    sobre o que aquela operação fez, sem executar novamente seus efeitos.
    ``revalidar`` permite ao chamador conferir sua autoridade depois da espera
    pela trava de escrita, antes de qualquer efeito ou leitura de recibo.
    """
    _linhas(previa_base)
    if not isinstance(assinatura_esperada, str) or not _HASH.fullmatch(assinatura_esperada):
        raise _bloqueada("A preparação da importação não possui uma assinatura válida.")
    nomes = {"nome_arquivo": _nome_arquivo(nome_arquivo), "nome_correcoes": _nome_arquivo(nome_correcoes)}
    base = deepcopy(previa_base)

    def confirmar(conn):
        if revalidar is not None:
            revalidar()
        anterior = conn.execute(
            "SELECT id, resultado FROM importacao_base_fiscal WHERE hash_arquivo=? AND hash_correcoes=?",
            (base["hash_arquivo"], base["hash_correcoes"])).fetchone()
        if anterior is not None:
            return {**json.loads(anterior["resultado"]), "importacao_id": int(anterior["id"]), "repetida": True}

        # A entrada deve ser a prévia pura, reparsada dos arquivos. Não herdar
        # classificação cadastral antiga se um chamador interno a conservar.
        for linha in base["linhas"]:
            linha["cadastro"] = None
            if linha["status"] in {"existente", "conflito"}:
                linha["status"] = "pendente" if linha.get("pendencias") else "incluir"
        atual = cbf.comparar_cadastro(base, _consultar(conn, base))
        if assinatura_previa(atual) != assinatura_esperada:
            raise cl.ErroClientes("BASE_FISCAL_DESATUALIZADA",
                                  "O cadastro mudou após a preparação. Gere e confira uma nova prévia.")
        validar_apta(atual)

        instante = agora()
        contagens = {"incluidas": 0, "existentes": 0, "ignoradas": 0}
        for linha in atual["linhas"]:
            if linha["status"] == "existente":
                contagens["existentes"] += 1
                linha["cliente_id"] = linha["cadastro"]["id"]
            elif linha["status"] == "ignorar":
                contagens["ignoradas"] += 1
            else:
                efetivo = linha["efetivo"]
                limpo = store._validar_cliente({campo: efetivo[campo] for campo in ("nome", "documento", "contato_nome")})
                origem = {"tipo": "base_fiscal", "hash_arquivo": base["hash_arquivo"],
                          "hash_correcoes": base["hash_correcoes"], **nomes,
                          "ocorrencia": deepcopy(linha)}
                linha["cliente_id"] = store._inserir_cliente(
                    conn, limpo, situacao=cl.SITUACAO_ATIVO,
                    documento_informado=linha["original"]["documento"], origem=origem,
                    usuario_id=usuario_id, usuario_login=usuario_login)
                contagens["incluidas"] += 1

        resultado = {"formato": "base_fiscal_resultado_v1", "repetida": False,
                     "contagens": contagens, "hash_arquivo": base["hash_arquivo"],
                     "hash_correcoes": base["hash_correcoes"], "criado_em": instante}
        proveniencia = {**nomes, "hash_arquivo": base["hash_arquivo"], "hash_correcoes": base["hash_correcoes"],
                       "assinatura_previa": assinatura_esperada, "linhas": atual["linhas"]}
        cursor = conn.execute(
            "INSERT INTO importacao_base_fiscal(hash_arquivo,hash_correcoes,nome_arquivo,nome_correcoes,"
            "usuario_id,usuario_login,criada_em,resultado,proveniencia) VALUES(?,?,?,?,?,?,?,?,?)",
            (base["hash_arquivo"], base["hash_correcoes"], nomes["nome_arquivo"], nomes["nome_correcoes"],
             usuario_id, usuario_login, instante, _json(resultado), _json(proveniencia)))
        importacao_id = int(cursor.lastrowid)
        store._registrar(conn, "importacao_base_fiscal", importacao_id, "confirmada", "",
                         _json({"hash_arquivo": base["hash_arquivo"], "hash_correcoes": base["hash_correcoes"],
                                "contagens": contagens}), usuario_id, usuario_login)
        return {**resultado, "importacao_id": importacao_id}

    return store._transacao(confirmar)
