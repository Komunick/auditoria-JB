# Research: Fase 2 — transmissão à produção restrita

Fontes oficiais consultadas em 16/10/2026: Anexo I v1.01 (20260209), guardado
em `Briefing\nfse-documentacao-oficial`; Manual de Contribuintes — Emissor
Público API v1.2 (out/2025, gov.br/nfse). O Swagger da Sefin
(`sefin.producaorestrita.nfse.gov.br/API/SefinNacional/docs/index`) respondeu
403 sem certificado; onde o manual nacional não detalha, a fonte está dita.

## R-1. A DPS da Fase 1 pode ser enviada depois?

Sim. A única regra de `dhEmi` no Anexo I é a E0008: a emissão tem de ser
anterior ou igual ao processamento. Não há idade máxima. A DPS aprovada
(imutável, com hash) é assinada no momento do envio; o conteúdo não muda.

## R-2. Serviços usados (manual nacional, seções 1.3 e 1.4)

| Método | Uso aqui |
|---|---|
| `POST /nfse` | recepção síncrona da DPS; devolve a NFS-e |
| `GET /dps/{id}` | chave de acesso da NFS-e gerada a partir da DPS (só para ator da nota, pelo certificado da conexão) |
| `HEAD /dps/{id}` | se a NFS-e existe, sem a chave (não usado: o GET já responde) |
| `GET /nfse/{chaveAcesso}` | XML da NFS-e |

Base da produção restrita: `https://sefin.producaorestrita.nfse.gov.br/SefinNacional`.

Corpo do `POST /nfse` e respostas (manual de Contribuintes de Campo Grande,
jul/2026, que segue o padrão nacional, e bibliotecas abertas):

- pedido: `{"dpsXmlGZipB64": "<DPS assinada, gzip, Base64>"}`;
- 201: `tipoAmbiente`, `versaoAplicativo`, `dataHoraProcessamento`, `idDps`,
  `chaveAcesso`, `nfseXmlGZipB64`, `alertas`;
- 400: não foi possível criar a NFS-e (lista de erros com código e descrição);
- 403: certificado digital da transmissão inválido ou fora do padrão;
- 500: falha no processamento.

**R-6 (aberto)**: os nomes exatos dos campos da lista de erros não foram vistos
em fonte oficial. A leitura aceita `erros`/`Erros`/`erro` e, em cada item,
`codigo`/`Codigo` e `descricao`/`Descricao` (+ `complemento`).

## R-3. Assinatura (Anexo I, RN DPS_NFS-e)

- `Signature` é 0-1 no XSD, mas **obrigatória** quando enviada à API (E0717)
  e feita com o certificado do **emitente** (E0718).
- Certificado da assinatura: versão 3, não pode ser de AC, `KeyUsage` com
  "Assinatura Digital" e "Não Recusa", extensão de CNPJ (OtherName OID
  2.16.76.1.3.3), válido e da ICP-Brasil (E0715/E0716).
- Certificado do mTLS (RN_RECEPCAO_DPS): os mesmos critérios, com
  `KeyUsage`/uso estendido de "Autenticação Cliente" (E1200 a E1209).

Estrutura (manual de Campo Grande, seção 4): `Signature` dentro da raiz
`DPS`, irmã de `infDPS`, sem prefixo de namespace; `Reference URI="#<Id do
infDPS>"`; transforms `enveloped-signature` e C14N 1.0
(`http://www.w3.org/TR/2001/REC-xml-c14n-20010315`); C14N 1.0 no `SignedInfo`.

**Algoritmo — fontes divergem.** O manual de Campo Grande diz RSA-SHA1 com
digest SHA-1; bibliotecas abertas que dizem emitir no Sistema Nacional usam
RSA-SHA256. O Anexo I não fixa o algoritmo. Decisão: SHA-256 por padrão,
SHA-1 por `AUDITORIA_NFSE_ASSINATURA=sha1`, sem mudar código. A primeira
transmissão real decide (E0714 = assinatura inválida).

## R-4. Transporte

`http.client` + `ssl` da biblioteca padrão: o mTLS precisa só de um
`SSLContext` com a cadeia do cliente, e isso evita uma biblioteca HTTP nova no
servidor. O `ssl` do Python só carrega chave de arquivo: a chave vai para um
PEM **cifrado com senha aleatória** de uso único, numa pasta temporária
privada, e é apagada logo após `load_cert_chain`.

A única dependência nova é `cryptography` (PKCS#12, X.509 e RSA), em
`requirements.txt` e `devops/requirements-web.txt`.

## R-5. DANFSe

O PDF não vem no `POST /nfse`. Relatos de integradores dão o endereço de
produção como `https://adn.nfse.gov.br/danfse/{chave}` (antes com 501); para a
produção restrita, `https://adn.producaorestrita.nfse.gov.br/danfse/{chave}`
**não confirmado**. O download é uma tentativa: falha fica registrada e não
muda a situação da nota.

## R-7. Achado: canonização de sub-árvore no libxml2 (16/10/2026)

Com o lxml 6.1.1 / libxml2 2.11.9 (o `.venv` do Windows),
`etree.tostring(elemento, method="c14n")` num **subelemento** sai errado
quando há namespace padrão redeclarado: os netos do `SignedInfo` ganham
`xmlns=""` e o próprio `infDPS` difere do C14N da biblioteca padrão. A
assinatura conferia consigo mesma, mas qualquer verificador correto (a Sefin)
calcularia outros bytes e recusaria (E0714). O signxml usa o mesmo caminho e
também não serve de juiz.

**Decisão**: canonizar uma cópia do elemento como documento próprio (os
namespaces em escopo vão para a raiz), que confere com o
`xml.etree.ElementTree.canonicalize` (expat, sem libxml2).
`test_nfse_assinatura` refaz digest e assinatura por esse caminho
independente e falha com a canonização antiga. A VM roda libxml2 2.14.6; o
teste vale lá também.

## R-8. Permissão própria para transmitir

A spec 006 previa que `nfse.aprovar_emitir` passaria a transmitir na Fase 2.
Ficou um slug novo, `nfse.transmitir`: herdar daria a quem já aprova o poder
de usar o certificado da escola sem ninguém conceder (constituição, III), e a
JB pode querer separar quem aprova de quem transmite (JB-5).

## R-6. Idempotência

E0014: série + número + município + CNPJ já usados numa NFS-e. Junto com o
`GET /dps/{id}`, isso dá a regra: resultado incerto nunca é reenviado sem
consulta; E0014 vira "já existia" e a NFS-e é baixada.
