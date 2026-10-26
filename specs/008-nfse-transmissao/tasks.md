# Tasks: Fase 2 — transmissão à produção restrita

Testes antes de cada parte (constituição, V). `[x]` = feito nesta branch.

## Base

- [x] T201 Spec, research, data model e plano (`specs/008-nfse-transmissao`)
- [x] T202 `cryptography` em `requirements.txt` e `devops/requirements-web.txt`
- [x] T203 Fixtures: AC, servidor e e-CNPJ de teste gerados na hora (nada de chave no Git)
- [x] T204 Sefin falsa: HTTPS com mTLS em loopback, `POST /nfse`, `GET /dps`, `GET /nfse`, DANFSe, falhas programáveis

## Núcleo

- [x] T205 Teste + `core/nfse_certificado.py`: PKCS#12, senha errada, sem chave, vencido, de AC, CNPJ do OtherName, `KeyUsage`
- [x] T206 Teste + `core/nfse_assinatura.py`: assina, confere, adulteração detectada, SHA-1/SHA-256, XSD continua válido

## Cliente e banco

- [x] T207 Teste + `ferramentas/nfse_sefin.py`: só produção restrita/loopback, mTLS, gzip/Base64, 201/400/403/500/tempo esgotado
- [x] T208 Teste + schema 2 e `transmitir_lote` no store: situações, idempotência, E0014, `enviando` velha, concorrência, descarte bloqueado

## Web

- [x] T209 Teste + rota de transmissão (job), permissão `nfse.transmitir`, downloads da NFS-e e do DANFSe
- [x] T210 Painel de transmissão no `webui/nfse.js`

## Fechamento

- [x] T211 Suíte inteira
- [ ] T212 Primeira transmissão real em produção restrita com o A1 da escola (JB-1) — confirma R-3, R-5, R-6
- [ ] T213 Deploy: `pip install cryptography` na VM antes de reiniciar
