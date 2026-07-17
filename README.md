# Auditoria Fiscal — Ferramentas (SPED, NF-e, SEFAZ)

Conjunto de ferramentas desktop (Windows) para auditoria e conferência fiscal.
As ferramentas compartilham um **núcleo comum** de leitura de
SPED Fiscal e XML de NF-e, indexado pela **chave de acesso de 44 dígitos**.

## Status

| # | Ferramenta | Situação |
|---|------------|----------|
| 1 | **Comparador SPED × SEFAZ** (notas faltantes) | ✅ funcional (app, aba 1) |
| 2 | **Comparador de versões de SPED** (diff campo a campo) | ✅ funcional (app, aba 2) |
| 3 | **Livro Digital de Conferência Fiscal** | ✅ funcional (app, aba 3) |
| 4 | **Extração de itens para auditoria tributária** | ✅ funcional (app, aba 4) |
| 5 | **Auditoria da tributação do cadastro de produtos (BA)** | ✅ funcional (app, aba 5) |

O app desktop tem **cinco abas**: *Comparador SPED × SEFAZ*, *Comparar versões
de SPED*, *Livro de Conferência*, *Extração de Itens* e *Auditoria de Produtos*.

## Auditoria de Produtos (aba 5)

Importa a base do **cadastro de produtos** do cliente (xlsx, xls, csv ou txt,
com detecção automática de colunas) e audita a tributação de cada item contra
as bases legais da pasta `dados/`: **Anexo I do RICMS/BA** (substituição
tributária, via CEST/NCM/descrição), TIPI, monofásicos, isenções, reduções de
base e diferimento. Aponta, por exemplo, produto de ST vendido como tributado
(e vice-versa), NCM/CEST/CST inválidos e alíquota inconsistente. Depois é
possível **corrigir** os itens (selecionados ou todos os de alta confiança),
**exportar o relatório** em Excel e **gerar uma nova base** corrigida no mesmo
layout do arquivo original (pronta para reimportar no sistema do cliente).

> As bases legais ficam em arquivos CSV editáveis na pasta `dados/`
> (ao lado do `.exe`, em `%LOCALAPPDATA%\AuditoriaFiscal\dados` ou na raiz do
> projeto). Para atualizar Anexo I, TIPI, alíquota padrão etc., basta editar
> esses arquivos — **sem alterar código**. Veja `dados/LEIA-ME.txt`.

No **Livro de Conferência**, importe o **SPED Fiscal** do cliente (por padrão,
somente as **notas de entrada**) ou uma pasta de XMLs; marque cada nota como
*conferida*, registre *observações* e filtre por pendentes/conferidas. O estado
é salvo em SQLite (`%LOCALAPPDATA%\AuditoriaFiscal\conferencia.db`),
persistindo entre sessões.

- **DANFE a partir do SPED**: o DANFE (PDF) é gerado a partir do **XML** da
  NF-e. Na fonte SPED, informe a pasta com os XMLs no campo **"XMLs p/
  DANFE"** — cada XML é **vinculado à sua nota pela chave de acesso** (busca
  recursiva na pasta). Se a pasta não for informada e o usuário pedir um
  DANFE, o sistema pergunta a pasta na hora e faz o vínculo de todas as notas.
- **Composição fiscal por CFOP → CST → alíquota**: painel abaixo da tabela
  mostra, para a nota selecionada, o valor total e cada agrupamento com valor
  contábil, base de cálculo, alíquota (`20,50%`) e valor do ICMS
  (`R$ 1.234,56`), sem misturar alíquotas diferentes do mesmo CFOP/CST.
  Divergências entre a soma dos grupos e o total (ou entre base × alíquota e
  o imposto) geram **alertas** — nunca bloqueio, pois podem decorrer de
  redução de base, diferimento, ST ou arredondamento (`core/composicao_fiscal.py`).
- **Correção de CFOP/CST/alíquota** (botão *Corrigir campo fiscal...*): com
  confirmação, motivo e usuário; opcionalmente **em lote** para todas as
  notas com o mesmo valor (registrada como correção *automática*). O valor
  original **nunca é apagado**: a trilha (original → corrigido, campo,
  usuário, data/hora, tipo, motivo, inconsistência, status) fica na tabela
  `correcao` do SQLite. A **precedência é centralizada** em
  `core/correcoes.py` (corrigido quando existir; senão o original) e vale
  para a tela, os PDFs e o SPED. Valores corrigidos aparecem em dourado com
  o original no tooltip.
- **Livro Fiscal (PDF)**: todas as notas carregadas, já corrigidas, na ordem
  CFOP → Valor Contábil → Base de Cálculo → Alíquota → Valor do ICMS, com a
  observação/inconsistência abaixo dos valores, **sem data de conferência** e
  sem separar o cabeçalho da nota dos seus valores entre páginas.
- **Relatório de Inconsistências (PDF)**: somente notas com observação e/ou
  correção — identificação completa (nº, série, chave, emitente, UF),
  detalhamento **por alíquota**, descrição da inconsistência e a trilha das
  correções.
- **SPED Fiscal corrigido**: reescreve o arquivo SPED importado aplicando as
  correções de CFOP/CST nos **C170**, reagrupando os **C190** (grupos que
  coincidem são mesclados, sem duplicidade) e recalculando os contadores
  (C990/9900/9999). O leiaute e os registros não tratados são preservados
  byte a byte; o arquivo original nunca é sobrescrito. **Limitação
  documentada**: correções de *alíquota* não vão ao SPED (afetariam a
  apuração E110) — são listadas para tratamento com o responsável fiscal.

> O sistema não possui autenticação de usuários: o "usuário responsável" da
> correção é o nome informado no diálogo (padrão: usuário do Windows).

> A leitura da relação da SEFAZ (item 1) usa **detecção automática de colunas** —
> validada contra o formato real do cliente (aba "Arquivo Sefaz").
>
> Na extração (item 4), o SPED só traz itens das notas que têm registro **C170**
> (tipicamente NF-e de entrada, modelo 55). Vendas em **NFC-e (modelo 65)** não
> têm C170 — para o detalhe de itens dessas, use os **XMLs** como fonte.

## Filtro "Considerar apenas documentos de entrada no SPED"

As quatro ferramentas que leem SPED permitem restringir a análise aos
**documentos de entrada** (opção com esse texto na própria tela):

| Aba | Onde fica a opção | Padrão |
|---|---|---|
| 1 · SPED × SEFAZ | checkbox na seleção de arquivos | **marcada** (a relação da SEFAZ só traz entradas) |
| 2 · Comparar SPEDs | checkbox na seleção de arquivos | desmarcada (todas as operações) |
| 3 · Livro de Conferência | checkbox (habilita ao escolher a fonte SPED) | **marcada** (conferência foca as entradas) |
| 4 · Extração de Itens | operação **"Apenas entradas"** com fonte SPED | "Todas" |

- **Classificação** (dados do próprio SPED, nesta ordem): `IND_OPER` do C100
  (0 = entrada, 1 = saída); sem `IND_OPER`, decide pelo **CFOP** dos itens
  (1/2/3 = entrada, 5/6/7 = saída); sem nenhuma informação, a nota é mantida.
- Com o filtro ativo, telas e relatórios Excel indicam
  **"Filtro aplicado: somente documentos de entrada no SPED"** e os totais
  refletem apenas os documentos incluídos.
- Se nenhum documento de entrada for localizado, o sistema avisa:
  *"Nenhum documento de entrada foi localizado no SPED para os filtros
  selecionados."* — nada de resultado vazio sem explicação.
- Com a opção desmarcada, o comportamento padrão é mantido (todos os
  documentos elegíveis da regra geral). Critério e textos centralizados em
  `core/filtro_sped.py`.

## Estrutura

```
auditoria-fiscal/
├── executar.py                 # inicia o app desktop
├── requirements.txt
├── amostras/                   # coloque aqui os arquivos de exemplo
├── dados/                      # bases legais editaveis (item 5)
│   ├── anexo1_ba.csv           # Anexo I RICMS/BA (ST) — amostra CEST/NCM
│   ├── ncm_tipi.csv            # TIPI (ativa validacao com 1000+ linhas)
│   ├── monofasico.csv          # combustiveis (ICMS monofasico)
│   ├── isencao_ba.csv          # isencoes BA
│   ├── reducao_base_ba.csv     # reducoes de base BA
│   ├── diferimento_ba.csv      # diferimento BA
│   ├── parametros.json         # UF, aliquota interna padrao
│   └── LEIA-ME.txt             # como atualizar as bases sem mexer no codigo
├── src/auditoria_fiscal/
│   ├── core/                   # nucleo compartilhado
│   │   ├── modelos.py          # NotaFiscal, ItemNota, Participante...
│   │   ├── sped_parser.py      # leitor do SPED Fiscal (EFD ICMS/IPI)
│   │   ├── filtro_sped.py      # filtro "apenas documentos de entrada"
│   │   ├── nfe_xml.py          # leitor de XML da NF-e (4.00)
│   │   ├── composicao_fiscal.py# agrupamento CFOP -> CST -> aliquota (item 3)
│   │   ├── correcoes.py        # correcoes com auditoria e precedencia (item 3)
│   │   ├── sefaz_relacao.py    # leitor da relacao da SEFAZ (flexivel)
│   │   ├── cadastro_produtos.py# leitor/regravador da base de produtos (item 5)
│   │   ├── base_legal.py       # carga das bases legais de dados/ (item 5)
│   │   └── utils.py            # conversoes (decimal BR, data, encoding)
│   ├── ferramentas/
│   │   ├── comparador_sped_sefaz.py   # motor do item 1
│   │   ├── relatorio_excel.py         # relatorio de conferencia (item 1)
│   │   ├── comparador_sped_sped.py    # motor do item 2 (diff)
│   │   ├── relatorio_diff_excel.py    # relatorio de diff (item 2)
│   │   ├── conferencia_store.py       # persistencia SQLite (item 3, + correcoes)
│   │   ├── danfe.py                   # geracao de DANFE do XML (item 3)
│   │   ├── livro_fiscal.py            # Livro Fiscal em PDF (item 3)
│   │   ├── livro_inconsistencias.py   # relatorio de inconsistencias em PDF (item 3)
│   │   ├── sped_corrigido.py          # SPED com correcoes aplicadas (item 3)
│   │   ├── extracao_itens.py          # extracao de itens (item 4)
│   │   ├── auditoria_produtos.py      # motor de auditoria (item 5)
│   │   ├── correcao_produtos.py       # correcoes + historico (item 5)
│   │   └── relatorio_produtos.py      # relatorio Excel (item 5)
│   └── ui/
│       ├── app.py                     # janela principal (abas)
│       ├── comparador_widget.py       # aba do item 1
│       ├── diff_widget.py             # aba do item 2
│       ├── conferencia_widget.py      # aba do item 3
│       ├── extracao_widget.py         # aba do item 4
│       └── produtos_widget.py         # aba do item 5
└── tests/                      # testes com dados sinteticos
```

## Como executar

```powershell
# a partir da pasta do projeto
.\.venv\Scripts\python.exe executar.py
```

## Rodar os testes

```powershell
# nucleo e ferramentas (dados sinteticos)
.\.venv\Scripts\python.exe tests\test_nucleo.py       # leitor SPED
.\.venv\Scripts\python.exe tests\test_xml.py          # leitor XML NF-e
.\.venv\Scripts\python.exe tests\test_comparador.py   # item 1
.\.venv\Scripts\python.exe tests\test_diff_sped.py    # item 2
.\.venv\Scripts\python.exe tests\test_conferencia.py  # item 3 (persistencia)
.\.venv\Scripts\python.exe tests\test_danfe.py        # item 3 (DANFE do XML)
.\.venv\Scripts\python.exe tests\test_associar_xml.py # item 3 (XML x SPED por chave)
.\.venv\Scripts\python.exe tests\test_livro_inconsistencias.py  # item 3 (livro PDF)
.\.venv\Scripts\python.exe tests\test_composicao_fiscal.py  # item 3 (CFOP/CST/aliquota)
.\.venv\Scripts\python.exe tests\test_correcoes.py          # item 3 (correcoes/auditoria)
.\.venv\Scripts\python.exe tests\test_livro_fiscal.py       # item 3 (Livro Fiscal PDF)
.\.venv\Scripts\python.exe tests\test_sped_corrigido.py     # item 3 (SPED corrigido)
.\.venv\Scripts\python.exe tests\test_extracao.py     # item 4
.\.venv\Scripts\python.exe tests\test_filtro_entradas.py  # filtro de entradas (SPED)
.\.venv\Scripts\python.exe tests\test_cadastro_produtos.py   # item 5 (leitor da base)
.\.venv\Scripts\python.exe tests\test_base_legal.py          # item 5 (bases legais)
.\.venv\Scripts\python.exe tests\test_auditoria_produtos.py  # item 5 (motor + correcao)
.\.venv\Scripts\python.exe tests\test_relatorio_produtos.py  # item 5 (relatorio)
.\.venv\Scripts\python.exe tests\test_ui_smoke.py     # interface (5 abas)

# versao web (sobe o app com TestClient; dados_web isolado no temp)
.\.venv\Scripts\python.exe tests\test_web_conferencia.py  # plataforma + item 3
.\.venv\Scripts\python.exe tests\test_web_comparador.py   # item 1 na web
.\.venv\Scripts\python.exe tests\test_web_diff.py         # item 2 na web
.\.venv\Scripts\python.exe tests\test_web_extracao.py     # item 4 na web
.\.venv\Scripts\python.exe tests\test_web_produtos.py     # item 5 na web
.\.venv\Scripts\python.exe tests\test_web_permissoes.py   # permissoes + historico

# validacoes com o SPED real (ajuste o caminho nos scripts)
.\.venv\Scripts\python.exe tests\validacao_real.py    # pipeline item 1
.\.venv\Scripts\python.exe tests\diff_real.py         # item 2 em escala real
```

## Gerar o .exe (executável Windows)

```powershell
.\empacotar.ps1
```

Gera um único arquivo **`dist\AuditoriaFiscal.exe`** (~85 MB), sem necessidade de
Python instalado — é só dar duplo clique. O script usa PyInstaller com
`--collect-all brazilfiscalreport` para incluir as fontes usadas na geração do
DANFE e `--add-data "dados;dados"` para embutir as bases legais da auditoria de
produtos. Para atualizar as bases sem gerar novo `.exe`, coloque uma pasta
`dados/` ao lado do executável (ou em `%LOCALAPPDATA%\AuditoriaFiscal\dados`) —
ela tem prioridade sobre a versão embutida. (O `.exe` e as pastas
`build/`/`dist/` não são versionados.)

## Registros do SPED lidos

`0000` (identificação) · `0150` (participantes) · `0200` (produtos/NCM) ·
`C100` (nota) · `C170` (itens). Demais registros são ignorados com segurança.
