# Auditoria Fiscal — Ferramentas (SPED, NF-e, SEFAZ)

Conjunto de ferramentas desktop (Windows) para auditoria e conferência fiscal.
As quatro ferramentas planejadas compartilham um **núcleo comum** de leitura de
SPED Fiscal e XML de NF-e, indexado pela **chave de acesso de 44 dígitos**.

## Status

| # | Ferramenta | Situação |
|---|------------|----------|
| 1 | **Comparador SPED × SEFAZ** (notas faltantes) | ✅ funcional (app, aba 1) |
| 2 | Comparador de versões de SPED (diff campo a campo) | ⏳ planejado |
| 3 | Livro Digital de Conferência Fiscal | ⏳ planejado |
| 4 | **Extração de itens para auditoria tributária** | ✅ funcional (app, aba 2) |

O app desktop tem **duas abas**: *Comparador SPED × SEFAZ* e *Extração de Itens*.

> A leitura da relação da SEFAZ (item 1) usa **detecção automática de colunas** —
> validada contra o formato real do cliente (aba "Arquivo Sefaz").
>
> Na extração (item 4), o SPED só traz itens das notas que têm registro **C170**
> (tipicamente NF-e de entrada, modelo 55). Vendas em **NFC-e (modelo 65)** não
> têm C170 — para o detalhe de itens dessas, use os **XMLs** como fonte.

## Estrutura

```
auditoria-fiscal/
├── executar.py                 # inicia o app desktop
├── requirements.txt
├── amostras/                   # coloque aqui os arquivos de exemplo
├── src/auditoria_fiscal/
│   ├── core/                   # nucleo compartilhado
│   │   ├── modelos.py          # NotaFiscal, ItemNota, Participante...
│   │   ├── sped_parser.py      # leitor do SPED Fiscal (EFD ICMS/IPI)
│   │   ├── nfe_xml.py          # leitor de XML da NF-e (4.00)
│   │   ├── sefaz_relacao.py    # leitor da relacao da SEFAZ (flexivel)
│   │   └── utils.py            # conversoes (decimal BR, data, encoding)
│   ├── ferramentas/
│   │   ├── comparador_sped_sefaz.py   # motor do item 1
│   │   ├── relatorio_excel.py         # relatorio de conferencia (item 1)
│   │   └── extracao_itens.py          # extracao de itens (item 4)
│   └── ui/
│       ├── app.py                     # janela principal (abas)
│       ├── comparador_widget.py       # aba do item 1
│       └── extracao_widget.py         # aba do item 4
└── tests/                      # testes com dados sinteticos
```

## Como executar

```powershell
# a partir da pasta do projeto
.\.venv\Scripts\python.exe executar.py
```

## Rodar os testes

```powershell
.\.venv\Scripts\python.exe tests\test_nucleo.py
.\.venv\Scripts\python.exe tests\test_xml.py
.\.venv\Scripts\python.exe tests\test_comparador.py
.\.venv\Scripts\python.exe tests\test_ui_smoke.py
```

## Gerar o .exe (depois de validado)

```powershell
.\.venv\Scripts\pip.exe install pyinstaller
.\.venv\Scripts\pyinstaller.exe --noconfirm --windowed --name "AuditoriaFiscal" `
  --paths src executar.py
```

## Registros do SPED lidos

`0000` (identificação) · `0150` (participantes) · `0200` (produtos/NCM) ·
`C100` (nota) · `C170` (itens). Demais registros são ignorados com segurança.
