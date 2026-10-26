"""Cofre de senhas: AES-256-GCM com chave do ambiente (spec 012, FR-005/006).

O que importa provar: o texto cifrado nao contem a senha, nunca se repete,
nao pode ser trocado de lugar (AAD), chave errada falha alto em vez de
devolver lixo, chave antiga ainda decifra e, sem chave, o cofre recusa
trabalhar em vez de cair para "sem criptografia".
"""

from __future__ import annotations

import base64
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import cofre as cf  # noqa: E402

SENHA = "Prefeitura#2026 çã "


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def levanta(excecao, funcao, *args, **kwargs) -> bool:
    try:
        funcao(*args, **kwargs)
    except excecao:
        return True
    return False


def main() -> int:
    chave = cf.gerar_chave()
    checar(len(cf.decodificar_chave(chave)) == 32, "chave de 256 bits")
    cofre = cf.Cofre(cf.decodificar_chave(chave))

    # ------------------------------------------------------------------
    # Ida e volta, exatamente

    c1 = cofre.cifrar(SENHA, "7:prefeitura:1")
    checar(cofre.decifrar(c1, "7:prefeitura:1") == SENHA,
           "a senha volta exatamente, com acento e espaco no fim")
    checar(SENHA.encode() not in c1.cifra and b"Prefeitura" not in c1.cifra,
           "o texto cifrado nao pode conter a senha")
    checar(len(c1.nonce) == 12, "nonce de 96 bits")
    checar(c1.chave_id == cofre.chave_id and len(c1.chave_id) == 8,
           "cada cifra registra qual chave a fez")

    c2 = cofre.cifrar(SENHA, "7:prefeitura:1")
    checar(c1.nonce != c2.nonce and c1.cifra != c2.cifra,
           "a mesma senha cifrada duas vezes nao pode dar o mesmo resultado")

    checar(cofre.decifrar(cofre.cifrar("", "x"), "x") == "", "senha vazia")

    # ------------------------------------------------------------------
    # AAD: o texto cifrado nao pode mudar de cliente ou de campo

    checar(levanta(cf.SegredoIlegivel, cofre.decifrar, c1, "8:prefeitura:1"),
           "cifra movida para outro cliente tem de falhar")
    checar(levanta(cf.SegredoIlegivel, cofre.decifrar, c1, "7:sefaz:1"),
           "cifra movida para outro campo tem de falhar")
    adulterada = cf.Cifrado(cifra=bytes([c1.cifra[0] ^ 1]) + c1.cifra[1:],
                            nonce=c1.nonce, chave_id=c1.chave_id)
    checar(levanta(cf.SegredoIlegivel, cofre.decifrar, adulterada,
                   "7:prefeitura:1"), "byte alterado tem de falhar")

    # ------------------------------------------------------------------
    # Troca de chave

    nova = cf.Cofre(cf.decodificar_chave(cf.gerar_chave()))
    checar(levanta(cf.SegredoIlegivel, nova.decifrar, c1, "7:prefeitura:1"),
           "chave errada falha alto, sem devolver lixo")
    rotacionado = cf.Cofre(cf.decodificar_chave(cf.gerar_chave()),
                           anteriores=[cf.decodificar_chave(chave)])
    checar(rotacionado.decifrar(c1, "7:prefeitura:1") == SENHA,
           "a chave anterior ainda decifra depois da troca")
    checar(rotacionado.cifrar("x", "a").chave_id == rotacionado.chave_id
           != cofre.chave_id, "cifra nova sai sempre com a chave atual")
    checar(rotacionado.precisa_recifrar(c1) and not
           rotacionado.precisa_recifrar(rotacionado.cifrar("x", "a")),
           "o cofre aponta o que ainda esta na chave antiga")

    # ------------------------------------------------------------------
    # Ambiente

    checar(levanta(cf.CofreIndisponivel, cf.Cofre.de_ambiente, {}),
           "sem a variavel o cofre fica indisponivel (nunca 'sem cripto')")
    checar(levanta(cf.CofreIndisponivel, cf.Cofre.de_ambiente,
                   {cf.VAR_CHAVE: "curta"}), "chave curta recusada")
    fraca = base64.urlsafe_b64encode(b"\x00" * 32).decode()
    checar(levanta(cf.CofreIndisponivel, cf.Cofre.de_ambiente,
                   {cf.VAR_CHAVE: fraca}), "chave de bytes repetidos recusada")
    do_ambiente = cf.Cofre.de_ambiente({
        cf.VAR_CHAVE: cf.gerar_chave(),
        cf.VAR_ANTERIORES: f" {chave} , ",
    })
    checar(do_ambiente.decifrar(c1, "7:prefeitura:1") == SENHA,
           "chaves anteriores vem do ambiente, separadas por virgula")
    checar(levanta(cf.CofreIndisponivel, cf.Cofre.de_ambiente, {
        cf.VAR_CHAVE: cf.gerar_chave(), cf.VAR_ANTERIORES: "lixo"}),
        "chave anterior invalida tambem impede subir")

    # A mensagem de erro nunca carrega a chave.
    try:
        cf.Cofre.de_ambiente({cf.VAR_CHAVE: chave[:-4]})
    except cf.CofreIndisponivel as exc:
        checar(chave[:10] not in str(exc), "a mensagem nao pode citar a chave")
    checar(chave not in repr(cofre), "repr do cofre nao mostra a chave")

    print("OK - cofre (AES-256-GCM, nonce unico, AAD por cliente e campo, "
          "chave errada falha, troca de chave, indisponivel sem chave) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
