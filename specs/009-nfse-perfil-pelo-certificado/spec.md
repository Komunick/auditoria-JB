# Feature Specification: preencher o perfil de emissão pelo certificado

**Feature Branch**: `009-nfse-perfil-pelo-certificado` (sobre `008-nfse-transmissao`)
**Criada em**: 16/10/2026
**Pedido**: "faça com que as informações de perfil sejam puxadas automaticamente do
sistema da Sefaz; verifique se é possível ao inserir o certificado e, sendo, insira
o campo de certificado no site."

## O que dá e o que não dá (pesquisa de 16/10/2026)

| Campo do perfil | De onde | Automático? |
|---|---|---|
| CNPJ | certificado (OtherName 2.16.76.1.3.3) | **sim**, sem rede |
| Razão social | certificado (CN do e-CNPJ: `NOME EMPRESARIAL:CNPJ`) | **sim**, sem rede |
| Convênio do município ativo (metade do R5) | ADN, parametrização: `GET /{municipio}/convenio` | **sim**, com o certificado no mTLS |
| Alíquota (%) | ADN, parametrização: `GET /{municipio}/{II.SS.DD.CCC}/{AAAA-MM-DD}/aliquota` | **sim**, por código de serviço e competência |
| Retenções do município | ADN, parametrização: `GET /{municipio}/{AAAA-MM-DD}/retencoes` | só como **aviso** (o tomador da creche é pessoa física) |
| IM e registro no CNC (outra metade do R5) | não há consulta de contribuinte por CNPJ na API | **não** |
| Regime de apuração no Simples, regime especial, tributos aproximados (JB-8) | decisão do contador | **não** |
| Endereço do tomador (JB-2), série, modelo da discriminação | decisão da JB | **não** |
| Município emissor | cadastro do CNPJ; não há API oficial com o certificado | **não** (o formulário já vem com Salvador) |
| Turmas e códigos (JB-3) | tabela da escola | **não** |

Fontes: manual oficial do contribuinte (Emissor Público API v1.2, out/2025) — que
ainda descreve `/parametros_municipais/...` e consulta por CPF/CNPJ, **desatualizado**;
o serviço foi movido para o ADN (`GET /ParametrosMunicipais` na Sefin responde 501
com o endereço novo). Caminhos e formatos conferidos no serviço real, em
30/09/2026, pelo projeto aberto `edusouza/nfse-emissor-go`
(`docs/convenio-municipal.md` e o swagger versionado lá): código de serviço com
pontos (`08.01.01.000`, `cTribNac` + complemento municipal `000`), competência
`AAAA-MM-DD`, alíquota em percentual
(`{"aliquotas":{"08.01.01.000":[{"Aliq":5.00,...}]}}`), município sem convênio
ativo responde 404 com o motivo em `mensagem`. Fonte de terceiro: o que não for
confirmado na primeira consulta real fica registrado como aberto.

## Decisões

- **Consulta em produção** (`https://adn.nfse.gov.br/parametrizacao`). Só `GET` de
  parâmetros públicos do município, nada é emitido; os dados da produção restrita
  são de teste e dariam alíquota errada. O cliente desta consulta só aceita o ADN
  (produção ou restrita, ou loopback nos testes) e só faz `GET`.
- **Nada é gravado sem a pessoa ver.** A consulta devolve sugestões que preenchem o
  formulário, marcadas com a fonte; o perfil só nasce (ou ganha versão) quando ela
  clica em salvar, como sempre.
- **O certificado não fica guardado**, como na transmissão (spec 008): lido em
  memória, PEM temporário cifrado e apagado, descartado no fim do pedido.
- Mesma permissão de quem cadastra perfis (`nfse.perfis`).
- Uma falha de consulta vira aviso; o que veio do certificado continua valendo.

## Aceite

1. `.pfx` válido → CNPJ e razão social sugeridos, com a fonte "certificado".
2. Convênio ativo/inativo e alíquota do(s) código(s) das turmas sugeridos, com a
   fonte "ADN (produção)"; códigos com alíquotas diferentes viram aviso.
3. Senha errada, arquivo inválido → erro antes de qualquer conexão.
4. ADN fora do ar ou 500 → avisos; CNPJ e razão social continuam sugeridos.
5. Nada é gravado: nenhum perfil novo, nenhum arquivo de certificado em disco.
6. A tela preenche o formulário, destaca o que veio de fora e lista o que segue
   manual.

## Em aberto

- Primeira consulta real com o A1 da escola (JB-1): confirma formato e valores.
- Chaves de `regimesEspeciais` e códigos de `tiposRetencao` (não documentados).
