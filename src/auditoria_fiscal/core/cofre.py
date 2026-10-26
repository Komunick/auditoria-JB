"""Cofre de senhas dos clientes: AES-256-GCM, chave fora do banco (spec 012).

Decisao do dono (2026-10-22): as senhas de portais ficam no proprio sistema,
criptografadas, com permissao e registro de quem consultou. Este modulo e' so
a parte criptografica; permissao e trilha moram na rota e no store.

Regras:

- A chave vem do AMBIENTE (`AUDITORIA_COFRE_CHAVE`, 32 bytes em base64
  urlsafe), nunca do banco, do Git ou da pasta de dados. Backup do banco sem a
  chave nao revela nada; chave guardada junto do backup anula o cofre.
- Cada cifra registra a impressao da chave que a fez. Chaves antigas
  (`AUDITORIA_COFRE_CHAVES_ANTERIORES`, separadas por virgula) so decifram:
  assim da para trocar de chave sem perder senha.
- O AAD amarra a cifra ao cliente e ao campo: copiar a cifra de uma linha para
  outra no banco faz a decifracao falhar, em vez de mostrar a senha de um
  cliente na ficha de outro.
- Sem chave valida o cofre fica INDISPONIVEL. Nao existe modo "sem
  criptografia".

Gerar uma chave nova: `python -m auditoria_fiscal.core.cofre --gerar-chave`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
from dataclasses import dataclass

VAR_CHAVE = "AUDITORIA_COFRE_CHAVE"
VAR_ANTERIORES = "AUDITORIA_COFRE_CHAVES_ANTERIORES"
TAMANHO_CHAVE = 32
TAMANHO_NONCE = 12


class CofreIndisponivel(RuntimeError):
    """Sem chave (ou chave invalida): o cofre nao trabalha."""


class SegredoIlegivel(ValueError):
    """Cifra que nao confere com a chave, o cliente ou o campo."""


@dataclass(frozen=True)
class Cifrado:
    cifra: bytes
    nonce: bytes
    chave_id: str

    def __repr__(self) -> str:      # nunca despeja bytes em log
        return f"Cifrado(chave_id={self.chave_id!r}, {len(self.cifra)} bytes)"


def gerar_chave() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(TAMANHO_CHAVE)).decode()


def decodificar_chave(texto: str) -> bytes:
    bruto = (texto or "").strip()
    try:
        chave = base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4))
    except (binascii.Error, ValueError) as exc:
        raise CofreIndisponivel(
            f"{VAR_CHAVE} não é base64 válido.") from exc
    _conferir(chave)
    return chave


def _conferir(chave: bytes) -> None:
    if len(chave) != TAMANHO_CHAVE:
        raise CofreIndisponivel(
            f"A chave do cofre precisa ter {TAMANHO_CHAVE} bytes "
            f"(veio com {len(chave)}). Gere uma com --gerar-chave.")
    if len(set(chave)) < 8:
        raise CofreIndisponivel(
            "A chave do cofre é fraca demais (bytes repetidos). "
            "Gere uma com --gerar-chave.")


def impressao(chave: bytes) -> str:
    """Identifica a chave sem revela-la: 8 hex do SHA-256."""
    return hashlib.sha256(b"auditoria-jb-cofre:" + chave).hexdigest()[:8]


class Cofre:
    def __init__(self, chave: bytes, anteriores=()):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        _conferir(chave)
        self._atual = AESGCM(chave)
        self.chave_id = impressao(chave)
        self._por_id = {self.chave_id: self._atual}
        for antiga in anteriores:
            _conferir(antiga)
            self._por_id.setdefault(impressao(antiga), AESGCM(antiga))

    def __repr__(self) -> str:
        return f"Cofre(chave_id={self.chave_id!r}, chaves={len(self._por_id)})"

    @classmethod
    def de_ambiente(cls, ambiente=None) -> "Cofre":
        ambiente = os.environ if ambiente is None else ambiente
        bruto = (ambiente.get(VAR_CHAVE) or "").strip()
        if not bruto:
            raise CofreIndisponivel(
                f"Cofre de senhas desligado: falta a variável {VAR_CHAVE} no "
                "servidor. O administrador do servidor precisa configurá-la.")
        atual = decodificar_chave(bruto)
        anteriores = [decodificar_chave(p) for p in
                      (ambiente.get(VAR_ANTERIORES) or "").split(",")
                      if p.strip()]
        return cls(atual, anteriores)

    def cifrar(self, texto: str, aad: str) -> Cifrado:
        nonce = secrets.token_bytes(TAMANHO_NONCE)
        cifra = self._atual.encrypt(nonce, str(texto).encode("utf-8"),
                                    aad.encode("utf-8"))
        return Cifrado(cifra=cifra, nonce=nonce, chave_id=self.chave_id)

    def decifrar(self, cifrado: Cifrado, aad: str) -> str:
        from cryptography.exceptions import InvalidTag

        motor = self._por_id.get(cifrado.chave_id)
        if motor is None:
            raise SegredoIlegivel(
                "Esta senha foi cifrada com uma chave que o servidor não tem "
                f"(chave {cifrado.chave_id}).")
        try:
            claro = motor.decrypt(cifrado.nonce, cifrado.cifra,
                                  aad.encode("utf-8"))
        except InvalidTag as exc:
            raise SegredoIlegivel(
                "A senha guardada não confere com a chave do cofre (dado "
                "alterado ou fora do lugar).") from exc
        return claro.decode("utf-8")

    def precisa_recifrar(self, cifrado: Cifrado) -> bool:
        return cifrado.chave_id != self.chave_id


def main(argv=None) -> int:
    import sys

    argumentos = list(sys.argv[1:] if argv is None else argv)
    if argumentos != ["--gerar-chave"]:
        print("Uso: python -m auditoria_fiscal.core.cofre --gerar-chave")
        return 2
    print(gerar_chave())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
