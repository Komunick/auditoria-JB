"""Transmissao de um lote aprovado a producao restrita (spec 008, plan.md).

DPS por DPS, em ordem de numero:

- `autorizada`: pula. `rejeitada`: so com `incluir_rejeitadas`.
- `incerta` (ou `enviando` de um processo que caiu): consulta antes. Achou a
  NFS-e -> baixa e autoriza SEM reenviar. Nao achou -> envia.
- `enviando` recente: outra transmissao esta nela; pula.
- envio: assina, reserva (`enviando`), `POST /nfse`.
  201 -> guarda a NFS-e (e tenta o DANFSe); E0014 -> consulta e baixa;
  400 -> rejeitada; 403 ou sem conexao -> volta como estava e PARA;
  sem resposta/5xx -> incerta e PARA (nao martela um servidor fora do ar).

Sem FastAPI: quem chama e' o job da rota (ou um teste). O certificado entra
como objeto e sai de escopo no fim; nada dele vai para o banco alem do
resumo publico (CNPJ, titular, validade, impressao).
"""

from __future__ import annotations

import datetime as dt

from ..core import nfse as nf
from ..core import nfse_assinatura as na
from ..core import nfse_certificado as nc
from . import nfse_sefin as sf
from . import nfse_store as ns


def _agora_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def transmitir_lote(store: ns.NfseStore, lote_id: int, cliente: sf.ClienteSefin,
                    certificado: nc.CertificadoA1, *, usuario_id: int, usuario_login: str,
                    algoritmo: str = na.ALGORITMO_PADRAO,
                    incluir_rejeitadas: bool = False) -> dict:
    quem = {"usuario_id": usuario_id, "usuario_login": usuario_login}
    lote = store.lote_para_transmitir(lote_id)
    nc.conferir_para_emissao(certificado, lote["cnpj"], dt.datetime.now(dt.timezone.utc))
    cert_resumo = certificado.resumo()
    base = {"destino": cliente.destino, "certificado": cert_resumo, **quem}
    itens = store.dps_para_transmitir(lote_id)
    store.registrar_evento("transmissao_iniciada", lote_id,
                           {"dps": len(itens), "destino": cliente.destino,
                            "certificado": cert_resumo["impressao"][:16],
                            "algoritmo": algoritmo, "incluir_rejeitadas": incluir_rejeitadas},
                           **quem)

    resumo = {"lote_id": lote_id, "autorizadas": 0, "rejeitadas": 0, "incertas": 0,
              "ja_existiam": 0, "puladas": 0, "interrompida": None, "danfse_faltando": 0}

    def guardar_nfse(dps_id: int, chave: str, xml: bytes, **tentativa) -> None:
        nfse_id = store.registrar_tentativa(dps_id, nova_situacao=ns.AUTORIZADA,
                                            chave_acesso=chave, nfse_xml=xml,
                                            **tentativa, **base)
        pdf = cliente.baixar_danfse(chave)
        if pdf and nfse_id:
            store.registrar_danfse(nfse_id, pdf)
        else:
            resumo["danfse_faltando"] += 1

    def resolver_por_consulta(d: dict, situacao_se_falhar: str) -> str:
        """'autorizada', 'enviar' ou 'parar'."""
        iniciada = _agora_iso()
        c = cliente.consultar_dps(d["id_dps"])
        if c.resultado == sf.NAO_EXISTE:
            store.registrar_tentativa(d["id"], operacao="consulta", resultado="nao_existe",
                                      nova_situacao=situacao_se_falhar, http_status=404,
                                      iniciada_em=iniciada, **base)
            return "enviar"
        if c.resultado == sf.EXISTE:
            n = cliente.baixar_nfse(c.chave_acesso)
            if n.resultado == sf.EXISTE:
                guardar_nfse(d["id"], c.chave_acesso, n.xml, operacao="consulta",
                             resultado="ja_existia", http_status=200, iniciada_em=iniciada)
                resumo["ja_existiam"] += 1
                return "autorizada"
            c = n
        store.registrar_tentativa(d["id"], operacao="consulta", resultado=c.resultado,
                                  nova_situacao=ns.INCERTA, http_status=c.http_status,
                                  mensagem=c.mensagem, iniciada_em=iniciada, **base)
        resumo["interrompida"] = f"consulta sem resposta conclusiva: {c.mensagem or c.resultado}"
        return "parar"

    for d in itens:
        situacao = d["situacao"]
        if situacao == ns.AUTORIZADA or situacao == ns.ENVIANDO or (
                situacao == ns.REJEITADA and not incluir_rejeitadas):
            resumo["puladas"] += 1
            continue
        if situacao == ns.INCERTA:
            proximo = resolver_por_consulta(d, ns.INCERTA)
            if proximo == "parar":
                resumo["incertas"] += 1
                break
            if proximo == "autorizada":
                continue

        xml = bytes(store.dps(d["id"])["xml"])
        assinado = na.assinar_dps(xml, certificado, algoritmo=algoritmo)
        try:
            anterior = store.reservar_envio(
                d["id"], permitidas={ns.GERADA, ns.INCERTA, ns.REJEITADA})
        except nf.ErroNfse as exc:
            if exc.codigo in (ns.EM_ENVIO, ns.SITUACAO_NAO_ENVIA):
                resumo["puladas"] += 1      # outra transmissao chegou antes
                continue
            raise
        iniciada = _agora_iso()
        r = cliente.enviar(assinado)
        tentativa = dict(operacao="envio", resultado=r.resultado, http_status=r.http_status,
                         erros=r.erros, alertas=r.alertas, mensagem=r.mensagem,
                         xml_assinado=assinado, algoritmo=algoritmo,
                         versao_aplicativo=r.versao_aplicativo,
                         dh_processamento=r.dh_processamento, iniciada_em=iniciada)

        if r.resultado == sf.AUTORIZADA:
            guardar_nfse(d["id"], r.chave_acesso, r.nfse_xml, **tentativa)
            resumo["autorizadas"] += 1
        elif r.resultado == sf.REJEITADA and r.duplicada:
            # A Sefin ja tem esta serie/numero: a nota existe; buscar.
            store.registrar_tentativa(d["id"], nova_situacao=ns.INCERTA, **tentativa, **base)
            if resolver_por_consulta(d, ns.INCERTA) != "autorizada":
                resumo["incertas"] += 1
                break
        elif r.resultado == sf.REJEITADA:
            store.registrar_tentativa(d["id"], nova_situacao=ns.REJEITADA, **tentativa, **base)
            resumo["rejeitadas"] += 1
        elif r.resultado in (sf.CERTIFICADO_RECUSADO, sf.SEM_CONEXAO):
            # Nada foi processado: a DPS volta como estava.
            store.registrar_tentativa(d["id"], nova_situacao=anterior, **tentativa, **base)
            resumo["interrompida"] = r.mensagem
            break
        else:
            store.registrar_tentativa(d["id"], nova_situacao=ns.INCERTA, **tentativa, **base)
            resumo["incertas"] += 1
            resumo["interrompida"] = r.mensagem or "resultado incerto"
            break

    store.registrar_evento(
        "transmissao_interrompida" if resumo["interrompida"] else "transmissao_concluida",
        lote_id, {k: v for k, v in resumo.items() if k != "lote_id"}, **quem)
    resumo["itens"] = [{k: d[k] for k in ("id", "numero", "situacao", "chave_acesso",
                                          "erros", "mensagem")}
                       for d in store.dps_para_transmitir(lote_id)]
    return resumo
