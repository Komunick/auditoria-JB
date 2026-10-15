# Implementation Plan: Emissão de NFS-e — Fase 1

**Branch**: `006-emissao-nfse` | **Base**: `dev` (c5c6b16, sete ferramentas)

## Summary

Oitava ferramenta nativa, seguindo a arquitetura que a conciliação e o
patrimônio já provaram: núcleo puro em `core/`, persistência em
`ferramentas/`, rotas em `web/` e uma aba em `webui/`. Banco próprio em
`dados_web/nfse.db` e origens imutáveis em `dados_web/nfse/origens/`.

O fluxo é: perfil versionado → importação (planilha-modelo ou texto colado)
→ conferência gravada em rodadas → revisão com correções que preservam a
origem → aprovação, que gera e valida todas as DPS na mesma transação.
Nenhum módulo da Fase 1 abre conexão de rede, lê certificado ou assina XML.

## Technical Context

**Linguagem**: Python 3.11+.

**Dependências**: nenhuma nova. `lxml` monta o XML e valida contra o XSD;
`openpyxl` lê a planilha e gera a planilha-modelo e o resumo. A biblioteca de
assinatura (`signxml` ou `xmlsec`) é decisão da Fase 2.

**Storage**: `dados_web/nfse.db`; planilhas de origem em
`dados_web/nfse/origens/<sha256>.xlsx`; textos colados dentro do banco.

**Leiaute oficial**: pacote `NFSe-ESQUEMAS_XSD-v1.01-20260209` e
`ANEXO_I-SEFIN_ADN-DPS_NFSe-SNNFSe-v1.01-20260209`, publicados em
gov.br/nfse → Documentação atual (conferido em 15/10/2026). Os XSD são
públicos e sem dado pessoal; ficam versionados em `dados/nfse/xsd/v1.01/`
com o SHA-256 do zip e a URL de origem.

**Testing**: scripts com `main()` e saída `OK/FALHOU`, TestClient nos testes
web, fixtures sintéticas em `tests/fixtures/nfse/`, dados isolados por
`AUDITORIA_WEB_DADOS`.

**Constraints**: sem processo, porta ou framework novos; sem regressão nas
sete ferramentas; centavos inteiros no banco; nenhuma chamada de rede.

## Constitution Check

- **I. Correção fiscal e rastreabilidade**: PASS. Cada valor importado
  guarda origem (SHA-256), posição (aba e célula, ou bloco e linha), rótulo e
  regra. Correção não apaga a origem. Cada DPS guarda a versão do perfil, do
  leiaute e do gerador. Ausência nunca vira zero. Dinheiro em centavos.
- **II. Núcleo independente**: PASS. `core/nfse*.py` e
  `ferramentas/nfse_store.py` não importam FastAPI. Teste de limites
  arquiteturais incluído.
- **III. Autorização no servidor**: PASS. Cinco slugs cumulativos com a aba;
  usuário novo recebe só a aba; identidade sempre da sessão.
- **IV. Imutabilidade e auditoria transacional**: PASS. Perfil versionado;
  origens, correções, rodadas de conferência, DPS e eventos append-only, com
  triggers; aprovação, DPS e eventos numa transação só.
- **V. Testes antes**: PASS. Cada fase de `tasks.md` começa pelo teste que
  falha.
- **VI. Compatibilidade**: PASS. Mesmo processo e pasta de dados; schema
  aditivo; backup atualizado.
- **Restrições técnicas**: planilha validada antes do openpyxl e texto com
  teto de tamanho; Excel neutralizado; aprovação tudo ou nada e exportação
  atômica. A exposição em produção com dados reais depende do endurecimento
  de segurança (Fase 0 do briefing), registrado como portão em `tasks.md`.

## Decisões

### Perfil versionado, decisões sem padrão

O perfil tem uma identidade (CNPJ) e versões imutáveis. Alterar qualquer
campo ou turma cria a versão seguinte. Cada rodada de conferência e cada DPS
apontam a versão usada; sem isso, não daria para dizer de qual configuração
saiu uma nota.

Os campos que dependem de JB-2, JB-8, R3 e R4 aceitam `NULL`, e `NULL`
significa "pendente". A função pura `pendencias_do_perfil()` lista o que
falta, com a origem de cada item (JB-n ou Rn), e o gerador recusa perfil com
pendência. Não existe valor padrão no código para esses campos, e um teste
garante isso.

### Proveniência por campo

A linha guarda os valores brutos como chegaram e um JSON de proveniência por
campo: célula e rótulo da coluna, ou linha do texto e rótulo, mais a regra de
leitura. É o que a constituição pede para valor extraído ("arquivo, hash,
aba, célula, rótulo e regra"), e é o que permite responder "de onde veio este
CPF?" depois de uma correção.

### Conferência pura, gravada em rodadas

`core/nfse_conferencia.py` recebe a versão do perfil, as linhas com seus
valores efetivos e o conjunto de chaves já aprovadas, e devolve valores
normalizados e apontamentos. Não lê banco. O store grava cada execução como
uma rodada (`conferencia`, `conferencia_linha`, `apontamento`), e o lote
aponta a rodada atual. Reconferir cria rodada nova; a anterior fica.

### Correção não apaga a origem

Correção é append-only (`correcao`), com campo de uma lista fechada, valor
anterior, valor novo, motivo e autor. O valor efetivo é a última correção do
campo ou, sem correção, o valor de origem, a mesma precedência de
`core/correcoes.py`. Exclusão de linha é uma correção do campo `excluida`.
Toda correção dispara uma rodada nova de conferência na mesma transação.

### Aprovação gera as DPS na mesma transação

`BEGIN IMMEDIATE`; conferir estado, revisão do lote, versão do perfil e
ausência de bloqueio; reservar as chaves de duplicata; reservar os números;
montar e validar cada DPS; gravar DPS, lote aprovado e eventos; `COMMIT`.
Qualquer falha desfaz tudo e o lote continua em revisão. Gerar linha a linha
deixaria um lote meio aprovado, que é saída parcial apresentada como válida.

### Duplicata e numeração garantidas pelo banco

- `chave_aprovada` tem índice único parcial em `(perfil_id, chave)` para
  chaves não liberadas. Duas aprovações simultâneas com a mesma chave: a
  segunda falha no `INSERT` e vira 409. Descartar um lote aprovado libera as
  chaves dele (preenche `liberada_em`), sem apagar.
- `numeracao_dps` guarda o último número por perfil, ambiente e série, e
  `dps` tem `UNIQUE(perfil_id, ambiente, serie, numero)`. Número reservado
  nunca volta, mesmo em lote descartado.

### Revisão otimista no lote

`lote.revision` sobe a cada mutação do lote ou das linhas. Correção,
exclusão, reconferência, aprovação e descarte enviam a revisão que a tela
viu; diferente da atual, 409 com a revisão nova.

### DPS determinística

O gerador não lê relógio nem gera aleatório: `dh_emi` (instante da
aprovação) entra como parâmetro e fica gravado. Ordem dos elementos fixa,
sem indentação, UTF-8, decimais com ponto e duas casas. Mesma entrada, mesmos
bytes, o que permite teste com arquivo de referência e reprodução de
qualquer DPS a partir do que está gravado.

### Validação no XSD sem editar os arquivos do governo

O XSD fica versionado como foi publicado. O `XMLSchema` do lxml é carregado
com resolvedor só de arquivos locais e `no_network`. Se R1 mostrar que o XSD
exige `Signature` na DPS, a Fase 1 valida o `infDPS` por um esquema-invólucro
local que importa o oficial e declara um elemento do tipo de `infDPS`; o
oficial não é alterado.

### Sem rede, provado por teste

Dois testes: um estático (os módulos `nfse*` não importam `httpx`, `socket`,
`urllib`, `requests` nem `ssl`) e um em execução (o fluxo completo pela API
roda com `socket.socket.connect` trocado por uma função que falha). O
`nfse_emissor_nacional.py` do briefing é da Fase 2 e não é criado agora.

### Validadores compartilhados

A NFS-e precisa de quatro coisas que já existem em outras ferramentas:
dígito do CPF (`core/patrimonio.py:normalizar_cpf`), dígito do CNPJ e leitura
de decimal brasileiro (`core/conciliacao_sefaz.py:normalizar_cnpj` e
`para_decimal`) e a validação do pacote `.xlsx`
(`core/conciliacao_sefaz.py:validar_pacote_xlsx`). Importar de outra
ferramenta acopla domínios; copiar duplica controle de segurança. Seguindo o
precedente do `planilha_segura` na spec 004:

- CPF, CNPJ e decimal vão para `core/documentos_br.py`, com erro neutro;
- `validar_pacote_xlsx` vai para `core/planilha_segura.py`;
- os módulos de origem mantêm os mesmos nomes, mensagens e exceções,
  delegando. As suítes do patrimônio e da conciliação são a regressão.

### Dados pessoais

Nomes de crianças, CPFs, endereços e celulares ficam só em `nfse.db` e nas
origens, dentro de `dados_web` (fora do Git, no backup). A trilha geral
recebe IDs e contagens (`lote=12 linhas=30`), nunca o conteúdo. Mensagens de
erro do servidor seguem a mesma regra. Prazo de guarda: JB-13.

### Permissões

| Slug | Uso |
|---|---|
| `aba.nfse` | portão da ferramenta |
| `nfse.perfis` | criar perfil e versões |
| `nfse.importar` | importar, corrigir, excluir linha, reconferir, descartar lote em revisão |
| `nfse.aprovar_emitir` | aprovar e gerar DPS; descartar lote aprovado. Na Fase 2, transmitir |
| `nfse.exportar` | baixar XML, zip e planilha-resumo **[proposta]** |

A planilha-modelo em branco exige só `aba.nfse`. Usuário novo recebe, por
sugestão da tela, apenas `aba.nfse`. Quem recebe o resto depende de JB-5.

### Oitava aba

Rótulo `8. Emissao de NFS-e` em `permissoes.py` (o padrão do arquivo é sem
acento) e `8. Emissão de NFS-e` na tela. Observação: o clone do Cadastro JB,
fora do Git, tem uma oitava ferramenta (Cadastros). Se ela for portada para o
Git antes deste PR, esta passa a ser a nona, e só o rótulo muda.

## Rotas (contrato resumido)

Todas sob `/api/nfse`, todas exigem sessão e `aba.nfse`.

| Método e rota | Slug adicional | Faz |
|---|---|---|
| `GET /perfis` | — | lista perfis com pendências |
| `GET /perfis/{id}` | — | perfil, versões e turmas |
| `POST /perfis` | `nfse.perfis` | cria perfil (versão 1) |
| `POST /perfis/{id}/versoes` | `nfse.perfis` | cria versão nova |
| `GET /planilha-modelo` | — | baixa a planilha-modelo em branco |
| `POST /lotes/planilha` | `nfse.importar` | multipart com `perfil_id` e o `.xlsx` |
| `POST /lotes/texto` | `nfse.importar` | JSON com `perfil_id` e `texto` |
| `GET /lotes` | — | lista com filtros por allowlist e paginação |
| `GET /lotes/{id}` | — | linhas, valores efetivos, apontamentos, origem e totais |
| `POST /lotes/{id}/linhas/{linha_id}/correcoes` | `nfse.importar` | corrige campo ou exclui/reinclui linha; exige `revision` e `motivo` |
| `POST /lotes/{id}/reconferir` | `nfse.importar` | nova rodada com a versão atual do perfil |
| `POST /lotes/{id}/aprovar` | `nfse.aprovar_emitir` | aprova e gera as DPS; exige `revision` |
| `POST /lotes/{id}/descartar` | `nfse.importar` (em revisão) ou `nfse.aprovar_emitir` (aprovado) | descarta com motivo |
| `GET /lotes/{id}/dps.zip` | `nfse.exportar` | zip com as DPS |
| `GET /lotes/{id}/resumo.xlsx` | `nfse.exportar` | planilha-resumo |
| `GET /dps/{id}.xml` | `nfse.exportar` | XML de uma DPS |

Códigos: 401 sem sessão, 403 sem permissão, 404 recurso de outro perfil ou
inexistente, 409 revisão desatualizada ou corrida perdida, 422 regra de
negócio (bloqueio, pendência de perfil, lote vazio), 413 arquivo ou texto
grande demais.

## Pesquisas na documentação oficial (parte da Fase 1)

Não dependem da JB. O resultado vai para `specs/006-emissao-nfse/research.md`
(criado pela tarefa T001) antes do código que depende dele.

| # | O que fixar | Fonte |
|---|---|---|
| R1 | Tags, tamanhos, obrigatoriedade e formato dos grupos usados (`infDPS`, prestador, tomador, serviço, valores); composição do identificador da DPS; namespace; se `Signature` é obrigatória no XSD; formato de `dhEmi`, `dCompet` e decimais; tamanho máximo da discriminação | XSD v1.01 e Anexo I v1.01 |
| R2 | Correspondência dos códigos do vídeo (item 08.01 da LC 116, CTISS 0801-0/01, NBS 1.2201.11.00) com o código de tributação nacional, o código municipal e o NBS da DPS; se Salvador exige código municipal | Anexo B (NBS e lista nacional) v1.01 e Anexo I |
| R3 | Se o grupo do IBS/CBS (indicador de operação 030101, classificação 200028, regime de apuração do IBS/CBS no Simples) é obrigatório, opcional ou recusado na DPS de ME/EPP antes de 01/2027 | Anexo I, Anexo C e manual da API |
| R4 | Faixas e tamanho da série e do número da DPS; regra do `dCompet` (dia dentro do mês, limites passado e futuro); fuso de `dhEmi`. Proposta até lá: `dCompet` = primeiro dia do mês da competência | Anexo I e manual de contribuintes da API v1.2 |

Se R3 ou R4 deixarem uma escolha ao contribuinte, a escolha vai para o
contador junto com JB-8. Nada disso vira padrão no código.

## Project Structure

```text
src/auditoria_fiscal/
├── core/
│   ├── documentos_br.py        # novo (extraído): CPF, CNPJ, decimal BR
│   ├── planilha_segura.py      # recebe validar_pacote_xlsx
│   ├── nfse.py                 # novo: tipos, catálogo de apontamentos, normalização,
│   │                           #       pendências do perfil, modelo da discriminação
│   ├── nfse_entrada.py         # novo: planilha-modelo e texto colado -> linhas brutas
│   ├── nfse_conferencia.py     # novo: regras -> valores normalizados + apontamentos
│   └── nfse_dps.py             # novo: perfil + linha + numeração -> XML; validação no XSD
├── ferramentas/
│   ├── nfse_store.py           # novo: SQLite de data-model.md
│   └── relatorio_nfse.py       # novo: planilha-modelo, resumo e zip
└── web/
    ├── rotas_nfse.py           # novo
    ├── servidor.py             # registrar router antes do mount estático
    ├── permissoes.py           # GRUPO_NFSE + 5 slugs
    ├── auditoria.py            # ações auditáveis
    └── infra.py                # caminho_db_nfse(), pasta_origens_nfse()

dados/nfse/xsd/v1.01/           # XSD oficial, LEIA-ME com URL, data e SHA-256

webui/
├── index.html                  # botão, section e script da oitava ferramenta
├── nfse.js                     # novo: Perfis, Importar, Lotes
└── estilo.css                  # estilos nfse-* necessários

tests/
├── fixtures/nfse/              # planilhas, textos e perfis fictícios
├── test_documentos_br.py
├── test_nfse.py                # núcleo, pendências, limites arquiteturais, sem rede
├── test_nfse_entrada.py
├── test_nfse_conferencia.py
├── test_nfse_dps.py
├── test_nfse_store.py
├── test_relatorio_nfse.py
└── test_web_nfse.py
```

## Complexity Tracking

| Decisão | Por que é necessária | Alternativa rejeitada |
|---|---|---|
| Banco dedicado | Ciclo de vida, trilha e backup próprios | Misturar com conciliação ou patrimônio acopla domínios sem relação |
| Perfil versionado | DPS reproduzível a partir do que está gravado | Editar no lugar perde de qual configuração a DPS saiu |
| Proveniência por campo | Constituição I | Proveniência só por linha não diz de onde veio cada valor |
| Rodadas de conferência | Reconferir sem apagar o resultado anterior | Sobrescrever apontamentos esconde por que um lote foi aprovado |
| XSD versionado no repositório | Validação offline e com versão fixa | Baixar na hora exige rede e muda sem aviso |
| Aprovação tudo ou nada | Falha sem saída parcial | Gerar linha a linha deixa lote meio aprovado |
| Extração de validadores | Um controle, uma implementação | Importar de outra ferramenta acopla domínios; copiar envelhece |

## Fica para a Fase 2

Assinatura (`signxml` × `xmlsec`), mTLS com o A1 da escola, `POST /nfse` na
produção restrita, consulta da DPS antes de reenviar, guarda do XML e do PDF
da NFS-e, estados `transmitido` e `rejeitado`, e a regra de `dhEmi` na hora
da transmissão (reaproveitar o XML desta fase ou gerar de novo).
