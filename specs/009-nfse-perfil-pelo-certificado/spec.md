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

---

# Parte 2: preencher o perfil por uma nota já emitida

**Pedido (16/10/2026)**: "Faça o perfil de emissão se preencher pelo XML de uma nota
já emitida pela escola na Nota Salvador."

O certificado não diz IM, regime, ISS retido nem códigos. Uma nota que a escola já
emitiu diz quase tudo isso. A pessoa envia o XML (ou um `.zip` de XMLs) e o
formulário se preenche, como na Parte 1: nada é gravado até salvar.

## Leiautes aceitos

- **Nota Salvador**: leiaute **ABRASF versão 1** (o provedor de Salvador segue a v1;
  fonte: Projeto ACBr, provedor `ISSSalvador`, que também divide a alíquota por 100,
  então `Aliquota` vem em fração: `0.05` = 5%). O leitor procura cada `InfNfse` em
  qualquer raiz (`CompNfse`, `ListaNfse`, `ConsultarNfseResposta`...), com ou sem
  namespace.
- **NFS-e nacional** (`NFSe/infNFSe/DPS/infDPS`), a que a escola emite a partir de
  01/11/2026 e a que o ADN devolve. Assim o recurso continua servindo depois da
  mudança.

## O que a nota dá

| Campo do perfil | Nota Salvador (ABRASF v1) | NFS-e nacional |
|---|---|---|
| CNPJ, razão social | `PrestadorServico` | `emit` |
| Inscrição municipal | `IdentificacaoPrestador/InscricaoMunicipal` | `emit/IM` |
| IM vai na DPS (R5) | **não**: ter IM em Salvador não prova registro no CNC | **sim**: `prest/IM` presente na DPS de uma nota autorizada prova que há registro (RN #198 e #200) |
| Município emissor / da prestação | `OrgaoGerador` (ou endereço do prestador) / `Servico/CodigoMunicipio` | `cLocEmi` / `cLocPrestacao` |
| ISS retido | `IssRetido` (1 sim, 2 não) | `tpRetISSQN` (1 não, 2 tomador; 3 intermediário vira aviso) |
| Alíquota | `Aliquota` (fração ou percentual, ver abaixo) | `pAliq` da DPS ou `pAliqAplic` da nota |
| Regime especial | `RegimeEspecialTributacao`, convertido para o nacional; ausente com optante = 0 | `regEspTrib` |
| Regime de apuração no Simples, tributos aproximados | **não** (não existem no leiaute) | `regApTribSN`, `pTotTribSN` ou `pTotTrib` |
| Códigos da turma | `ItemListaServico`, `CodigoCnae`, `CodigoTributacaoMunicipio` como referência; `cTribNac` pela lista nacional; NBS, indicador de operação e classificação tributária se o XML tiver | `cTribNac`, `cNBS`, `cIndOp`, `cClassTrib` |
| Modelo da discriminação | `Discriminacao`, com os nomes trocados pelos campos | `xDescServ`, idem |

Sem fonte em nenhum dos dois, e por isso manuais: endereço do tomador (JB-2), série
da DPS, convênio (Parte 1) e o nome das turmas.

## Regras

- **Alíquota**: valor abaixo de 1 é fração (`0.05` → 5,00%); de 1 a 5 é percentual;
  acima de 5% (E0595) vira aviso e não preenche.
- **`cTribNac` pelo item da lista**: `dados/nfse/lista_servico_nacional.json`, gerado
  do Anexo B v1.01 (SHA-256 conferido com research.md da spec 006). Subitem com um
  desdobro só → preenche. Com mais de um, só o subitem 08.01 tem regra: CNAE 85.1 e
  85.2 (educação infantil, fundamental, médio) → `080101`; 85.3 (superior) →
  `080102`, pelas descrições do próprio Anexo B. Os outros viram aviso com as opções.
- **Várias notas**: valem as do CNPJ mais frequente (ou o do perfil aberto, se houver;
  arquivo só com notas de outro CNPJ é recusado). Um campo só é preenchido se todas as
  notas concordam; divergência vira aviso. Cada combinação diferente de códigos vira
  uma turma sugerida.
- **Modelo**: troca o nome do tomador por `{RESPONSAVEL}`, a competência por
  `{MES}/{ANO}` ou `{MES_EXTENSO}/{ANO}`, os nomes das turmas do formulário por
  `{TURMA}` e o nome depois de "menor", "aluno(a)", "criança", "estudante" ou
  "dependente" por `{ALUNO}`, mantendo maiúsculas. Só preenche se achar o aluno e o
  resultado não tiver mais nenhum nome do tomador nem número com cara de CPF; senão,
  aviso.
- **Optante**: o perfil só aceita ME/EPP do Simples. Nota de não optante ou de MEI vira
  aviso e o regime não é sugerido.
- **Nota da produção restrita** (`tpAmb` = 2): aviso de que os dados são de teste.

## Segurança e dados pessoais

- Nada é gravado: nem perfil, nem arquivo. A nota vive só no pedido.
- A resposta e a trilha não levam CPF, nome do tomador, nome do aluno nem o texto
  original da discriminação. Só o modelo já sem nomes, os códigos e os campos do
  prestador. A trilha registra só contagens.
- XML com `DOCTYPE` é recusado; parser sem rede e sem entidades. Limites: 5 MB por
  arquivo; no `.zip`, até 1000 XMLs e 20 MB descompactados, contados na leitura (o
  tamanho declarado no zip não é confiado).
- Mesma permissão de quem cadastra perfis (`nfse.perfis`), ação
  `nfse.perfil_nota_anterior` na trilha.

## Aceite (Parte 2)

1. XML da Nota Salvador com uma nota → CNPJ, razão social, IM, municípios, ISS
   retido, alíquota, regime especial, códigos da turma (com `080101` pelo CNAE) e o
   modelo da discriminação, cada um com a fonte.
2. NFS-e nacional → também IM na DPS, regime de apuração e tributos aproximados.
3. Várias notas que concordam preenchem; as que divergem viram aviso.
4. `DOCTYPE`, XML quebrado, arquivo sem NFS-e, arquivo grande, zip-bomba → recusa
   com mensagem, nada lido.
5. Nada gravado; nenhum CPF ou nome do tomador ou do aluno na resposta, no banco ou
   na trilha.
6. A tela preenche o formulário, marca em verde, põe os códigos na turma e lista o
   que segue manual.

## Em aberto (Parte 2)

- Ainda não vi um XML real exportado da Nota Salvador. O leitor segue o ABRASF v1 e o
  ACBr. Os nomes das tags de NBS, indicador de operação e classificação tributária,
  que o portal mostra desde a reforma, são procurados por nomes prováveis. O
  primeiro XML real da escola confirma.
