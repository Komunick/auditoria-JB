# Implementation Plan: Fase 2 — transmissão à produção restrita

**Branch**: `008-nfse-transmissao` (de `dev` 0b7f4e0) | **Spec**: `spec.md`

## Contexto técnico

Python 3.11+, FastAPI no processo existente, SQLite (`nfse.db`), lxml.
Dependência nova: `cryptography` (research.md, R-4). Sem processo nem porta
nova: a transmissão roda num job (thread) do próprio servidor, como os
processamentos das outras ferramentas.

## Constituição

| Princípio | Como fica |
|---|---|
| I. Rastreabilidade | cada tentativa guarda o XML assinado e a resposta oficial |
| II. Núcleo sem interface | certificado e assinatura em `core/`; cliente HTTP e banco em `ferramentas/`; só `rotas_nfse.py` conhece FastAPI |
| III. Autorização no servidor | permissão nova `nfse.transmitir`, não dada a ninguém automaticamente |
| IV. Imutável e transacional | tentativa e situação na mesma transação; `autorizada` terminal |
| V. Testes antes | `test_nfse_certificado`, `test_nfse_assinatura`, `test_nfse_sefin`, `test_web_nfse_transmissao` |
| VI. Implantação simples | schema aditivo; uma dependência nova; nada novo para operar |

## Estrutura

```
src/auditoria_fiscal/core/nfse_certificado.py   leitura e conferência do A1
src/auditoria_fiscal/core/nfse_assinatura.py    XMLDSig da DPS (assinar e conferir)
src/auditoria_fiscal/ferramentas/nfse_sefin.py  cliente da Sefin (mTLS, http.client)
src/auditoria_fiscal/ferramentas/nfse_store.py  schema 2 + transmitir/situação
src/auditoria_fiscal/web/rotas_nfse.py          rota de transmissão (job) e downloads
webui/nfse.js                                   painel de transmissão no lote aprovado
tests/fixtures/nfse/certificados.py             AC, servidor e e-CNPJ de teste gerados na hora
tests/fixtures/nfse/sefin_falsa.py              Sefin falsa em HTTPS com mTLS (loopback)
```

## Fluxo do job

1. Rota recebe `.pfx`, senha, `revision` do lote e `incluir_rejeitadas`;
   confere permissão, estado do lote e o certificado (FR-203) antes de criar o
   job — erro de certificado volta na hora, sem job.
2. Job, DPS por DPS em ordem de número:
   - `autorizada`: pula;
   - `incerta` (ou `enviando` velha): `GET /dps/{id}`; achou → `GET /nfse/{chave}`,
     guarda, `autorizada`; não achou → envia;
   - `gerada` (ou `rejeitada` com o pedido): marca `enviando` (transação curta
     que falha se outra transmissão pegou a DPS), assina, `POST /nfse`;
   - 201 → guarda NFS-e e tenta o DANFSe; 400 com E0014 → consulta; 400 →
     `rejeitada`; 403 → volta para a situação anterior e interrompe; sem
     resposta/5xx → `incerta` e interrompe.
3. O certificado sai de escopo no fim do job (sucesso ou erro).

## Fica para depois

Produção (Fase 3), guardar o A1 com autorização (JB-1), A3, eventos e
cancelamento (Fase 4), consulta avulsa de DPS sem transmitir.
