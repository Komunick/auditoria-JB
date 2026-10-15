# Research: Emissão de NFS-e — Fase 1 (R1 a R5)

Pesquisa feita em 15/10/2026 nos arquivos oficiais da página
gov.br/nfse → Biblioteca → Documentação técnica → Documentação atual.

## Fontes

| Arquivo | Bytes | SHA-256 | Onde está |
|---|---|---|---|
| `nfse-esquemas_xsd-v1-01-20260209.zip` | 65 640 | `e7935cbd9470527c6cc32984c1b2263e614183bf0139ce2733eaaed2de9a8072` | XSD da pasta `Schemas/1.01/` em `dados/nfse/xsd/v1.01/`; zip fora do Git |
| `anexo_i-sefin_adn-dps_nfse-snnfse-v1-01-20260209.xlsx` | 215 196 | `de5bc492959eadc8bfa7540e16939995924f2188f743648eaf84d3b31e9eeb7c` | fora do Git (`Clientes\JB Fraga Contabilidade\Briefing\nfse-documentacao-oficial\`) |
| `anexo_b-nbs2-lista_servico_nacional-snnfse-v1-01-20260122.xlsx` | 85 008 | `e74b0be8ad204e458932efb1716225a3fb5703a84e5475ce5c4c6789d1c61b1a` | idem |

URL base: `https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/`.
O servidor recusa download fora do navegador (403); os arquivos foram baixados
pelo navegador e conferidos pelo SHA-256 calculado na própria página.

Referências abaixo: "XSD" = `tiposComplexos_v1.01.xsd` / `tiposSimples_v1.01.xsd`;
"RN #n" = linha n da aba `RN DPS_NFS-e` do Anexo I; "Ennnn" = código de erro.

## R1 — Leiaute da DPS

| Ponto | Resultado | Fonte |
|---|---|---|
| Raiz | `DPS` (tipo `TCDPS`), namespace `http://www.sped.fazenda.gov.br/nfse`, atributo `versao` = `1.01` | `DPS_v1.01.xsd`, `TVerNFSe` |
| Assinatura | `ds:Signature` é **0-1**: a DPS sem assinatura valida no XSD oficial; não precisa de esquema-invólucro | XSD `TCDPS` |
| Identificador | `Id` = `DPS` + cód. município emissor (7) + tipo de inscrição federal (1: CPF, 2: CNPJ) + inscrição (14, CPF com zeros à esquerda) + série (5) + número (15); 45 posições, `DPS[0-9]{42}` | XSD `TSIdDPS`; RN #139 (E0004) |
| Ordem do `infDPS` | `tpAmb`, `dhEmi`, `verAplic`, `serie`, `nDPS`, `dCompet`, `tpEmit`, `cLocEmi`, `prest`, `toma`, `serv`, `valores` (os opcionais não usados ficam fora) | XSD `TCInfDPS` |
| `tpAmb` | 1 produção, 2 homologação (produção restrita) | `TSTipoAmbiente` |
| `dhEmi` | `AAAA-MM-DDThh:mm:ss±hh:00`; não pode ser posterior ao processamento | `TSDateTimeUTC`; RN #141 (E0008) |
| `verAplic` | 1 a 20 caracteres | `TSVerAplic` |
| `dCompet` | `AAAA-MM-DD` | `TSData` |
| Prestador | `CNPJ`, `IM` (0-1), `regTrib`. **Não** informar `xNome` nem `end` quando o emitente é o prestador | RN #202 (E0121), #206 (E0128) |
| `IM` do prestador | Obrigatória se houver registro complementar no CNC do município emissor; **proibida** se não houver | RN #198 e #200 → R5 |
| `regTrib` | `opSimpNac` (3 = ME/EPP), `regApTribSN` (0-1), `regEspTrib` (1-1) | XSD `TCRegTrib` |
| Tomador | `CPF`, `xNome` (1 a 300), `end` (0-1), `fone`, `email` | XSD `TCInfoPessoa` |
| Endereço | `endNac` (`cMun` 7 dígitos, `CEP` 8 dígitos), `xLgr` (≤ 255), `nro` (≤ 60), `xCpl` (0-1, ≤ 156), `xBairro` (≤ 60); CEP tem de pertencer ao município | XSD `TCEndereco`; RN #260 (E0240) |
| Serviço | `locPrest/cLocPrestacao`, `cServ` com `cTribNac` (6 dígitos, 1-1), `cTribMun` (3 dígitos, 0-1), `xDescServ` (1 a 2000, aceita quebra de linha), `cNBS` (9 dígitos, 0-1) | XSD `TCServ`, `TCCServ` |
| Valores | `vServPrest/vServ` (`0`, `0.dd` ou inteiro com `.dd`); `trib/tribMun` (`tribISSQN`, `tpRetISSQN`, `pAliq` 0-1 no formato `5.00`); `trib/totTrib` **1-1** | XSD `TCInfoValores`, `TSDec15V2`, `TSDec1V2` |
| Texto | Tipos texto não aceitam espaço no começo nem no fim | `TSString` |

### Achado: padrão da série no XSD oficial

`TSSerieDPS` (`tiposSimples_v1.01.xsd`, linha 161) usa o padrão
`^0{0,4}\d{1,5}$`. No XML Schema, `^` e `$` não são âncoras: são caracteres
comuns. O libxml2 (usado pelo lxml) segue a norma e recusa `1`, `00001` e
`49999`; só aceita a série escrita como `^1$`. Testado em 15/10/2026 com
lxml 6.1.1 / libxml2 2.11.9. É o único padrão com `^` ou `$` nos XSD v1.01.

**Decisão**: o arquivo oficial não é editado. O validador carrega o XSD e,
em memória, troca só esse padrão por `0{0,4}\d{1,5}` (o que ele claramente
pretende dizer). Um teste confere que o arquivo oficial ainda tem o padrão
original; se o governo corrigir o XSD, o teste avisa para tirar o contorno.
A faixa da série (1 a 49999) é conferida à parte no perfil.

## R2 — Códigos do serviço

| Vídeo (Nota Salvador) | DPS nacional | Fonte |
|---|---|---|
| Item da lista 00801 – Ensino regular pré-escolar, fundamental, médio e superior | `cTribNac` = **080101** – Ensino regular pré-escolar, fundamental e médio (serve para berçário, infantil e fundamental) | Anexo B, aba `LISTA.SERV.NAC.`; Anexo I, aba `MUN.INCID_INFO.SERV.` |
| NBS 1.2201.11.00 – creche | `cNBS` = **122011100** | Anexo B, aba `LISTA.NBS_v2.0` |
| CTISS 0801-0/01 | Sem correspondência direta: `cTribMun` tem 3 dígitos, é opcional e, se informado, tem de existir na lista de Salvador e não pode ser `000` | XSD `TCCodTribMun`; RN #318, #319 |
| CNAE 8511200 / 8513900 | A DPS não tem campo de CNAE | XSD |

Outros NBS da mesma família, para a JB escolher por turma (JB-3): 1.2201.12.00
(pré-escola), 1.2201.19.00 (educação infantil não classificada antes),
1.2201.20.00 (ensino fundamental). Qual turma usa qual é decisão do contador.

**Decisão da Fase 1**: `cTribMun` não é enviado (é opcional e o código do
Nota Salvador não cabe nele). A turma fica completa com `cTribNac`; `cNBS` vai
quando cadastrado.

## R3 — Grupo IBS/CBS

- `IBSCBS` é **0-1** no `infDPS` (XSD) e nenhuma regra do Anexo I o exige
  para ME/EPP. Só é aceito com competência a partir de 01/01/2026 e DPS 1.01
  (RN #542 e #543), e, se informado, exige `cNBS` (RN #324).
- O grupo pede, além do indicador de operação e da classificação tributária,
  `finNFSe`, `indDest` e o CST do IBS/CBS, que o vídeo não mostra.
- A nota do vídeo saiu com os campos de IBS/CBS vazios **[confirmado]**.

**Decisão da Fase 1**: a DPS não leva o grupo IBS/CBS. Se o contador disser
que ele deve ir antes de 2027, é tarefa nova (com CST e destinatário). Os
códigos 030101 e 200028 ficam guardados na turma.

## R4 — Série, número e competência

- Série: **00001 a 49999** para emissão por aplicativo próprio (RN #144,
  E0010). A série é escolhida no cadastro do perfil, sem valor padrão.
- Série + número + município emissor + CNPJ não podem repetir uma DPS que já
  virou nota (RN #145, E0014).
- Número: `[1-9][0-9]{0,14}`.
- `dCompet` não pode ser posterior à data de `dhEmi` (RN #147, E0015). Com a
  proposta "primeiro dia do mês da competência", competência de mês futuro
  vira bloqueio (`COMPETENCIA_FUTURA`). A data de competência também não pode
  ser anterior ao convênio do município nem à inscrição do CNPJ (RN #148 a
  #153), o que só o Sistema Nacional confere.
- `dhEmi` com o fuso de Salvador (`-03:00`).

## Alíquota e tributos aproximados (subsídio para JB-8)

`pAliq` (RN #501 a #513) para ME/EPP (`opSimpNac = 3`), sem benefício
municipal:

| `regApTribSN` | Convênio do município de incidência | ISS retido | `pAliq` |
|---|---|---|---|
| 1 (ISS pelo Simples) | ativo | não | **proibida** (E0625) |
| 1 | ativo | sim | obrigatória, mínimo 1,8% (E0621) |
| 1 | não ativo | não | proibida (E0631) |
| 1 | não ativo | sim | obrigatória |
| 2 ou 3 (ISS fora do Simples) | ativo | — | proibida |
| 2 ou 3 | não ativo | — | obrigatória |

Também: alíquota nunca acima de 5% (E0595), e proibida com regime especial
diferente de 0 (E0604). `regApTribSN` é obrigatório para ME/EPP (E0166), e com
`regApTribSN = 1` o `regEspTrib` tem de ser 0 (E0175).

Na creche, se o contador confirmar `regApTribSN = 1` com ISS não retido, a
DPS vai **sem** alíquota, seja qual for o convênio, o que bate com a nota do
vídeo (ISS não destacado). O sistema aplica essa tabela; não há mais um campo
"informar alíquota" no perfil.

`totTrib` é obrigatório. Para ME/EPP, `indTotTrib` é proibido (E0712); sobram
`pTotTribSN` (percentual do Simples), `pTotTrib` (três percentuais) e
`vTotTrib` (três valores). A Fase 1 aceita `pTotTribSN` e `pTotTrib`; qual
usar e com que percentuais é JB-8.

## R5 — Situação no Sistema Nacional (nova)

Dois fatos que mudam a DPS e que só o Sistema Nacional responde:

1. **Convênio de Salvador ativo** na data de competência. Só importa para a
   alíquota quando há retenção ou `regApTribSN` 2 ou 3 (tabela acima).
2. **Registro complementar da escola no CNC de Salvador**: define se a IM vai
   ou não na DPS (RN #198 e #200).

Os dois ficam no perfil sem valor padrão. Podem ser conferidos no portal ou,
na Fase 2, pela API com o certificado.
