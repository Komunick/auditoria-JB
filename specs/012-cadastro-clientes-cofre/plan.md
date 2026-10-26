# Implementation Plan: Cadastro de Clientes, Cofre de Senhas e Vencimentos

**Branch**: `012-cadastro-clientes-cofre` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

## Summary

Nona ferramenta ("9. Clientes") no processo FastAPI existente: cadastro de
clientes com banco próprio (`dados_web/clientes.db`), cofre de senhas com
AES-256-GCM, certificados digitais com leitura de `.cer`/`.pfx`, painel de
vencimentos e duas importações com prévia (planilha atual e arquivo do coletor
local). O coletor é um comando de linha rodado à mão no escritório.

## Technical Context

- Python 3.11/3.12, FastAPI, SQLite (WAL, `busy_timeout`, `BEGIN IMMEDIATE`),
  openpyxl, frontend estático sem build.
- Dependência nova: `cryptography>=42` (AES-GCM e leitura de certificado). É a
  mesma que o PR #6 traz para a assinatura da NFS-e.
- Testes: scripts `tests/test_*.py`, um por arquivo, rodados com o Python do
  `.venv` e pasta de dados temporária (`AUDITORIA_WEB_DADOS`).

## Constitution Check

| Princípio | Como a feature cumpre |
|---|---|
| I. Rastreabilidade | Cada valor importado guarda hash do arquivo, linha e coluna; certificado guarda a origem (manual, arquivo, coleta) e o hash do `.pfx`. Nada é inventado: valor ilegível vira pendência. |
| II. Núcleo sem interface | `core/clientes.py`, `core/cofre.py`, `core/planilha_clientes.py`, `core/certificados.py` e `core/coletor_certificados.py` não importam FastAPI. |
| III. Autorização no servidor | Seis slugs novos, nenhum concedido a usuário existente nem ao padrão de usuário novo; revelar senha confere `cofre.ver` no servidor a cada pedido. |
| IV. Trilha transacional | Alteração do cadastro, troca de senha e revelação gravam a linha da trilha na mesma transação. Trilhas com trigger que impede UPDATE/DELETE. |
| V. Testes antes | Cada módulo nasce com o teste do comportamento; fixtures sintéticas. |
| VI. Implantação simples | Mesmo processo; banco novo aditivo; chave por variável de ambiente; coletor não é serviço. |

## Decisões

1. **Chave do cofre**: `AUDITORIA_COFRE_CHAVE` (32 bytes em base64 urlsafe).
   Cada texto cifrado guarda a impressão da chave (8 primeiros hex do SHA-256);
   `AUDITORIA_COFRE_CHAVES_ANTERIORES` (lista separada por vírgula) só decifra,
   para trocar de chave sem perder senhas. Sem chave, o cofre fica indisponível
   (503) e o resto da aba funciona. O comando `coletar-certificados.py` não usa a
   chave. A chave nova sai do one-liner de `secrets` do README-servidor (ou de
   `PYTHONPATH=src python -m auditoria_fiscal.core.cofre --gerar-chave`).
2. **Dados associados (AAD)**: `cliente_id:campo:segredo_id`. Trocar o texto
   cifrado de linha faz a decifração falhar.
3. **Confirmação de senha antes de revelar** (proposta P-04, ligada por
   padrão): `POST /api/clientes/cofre/desbloquear` confere a senha do usuário e
   libera revelações por 15 minutos, em memória do processo (reinício exige nova
   confirmação). Limite de 30 revelações por usuário por hora, contado na
   própria trilha de acessos.
4. **Prévia de importação em memória**: o arquivo é lido, validado e apagado
   no mesmo pedido; a prévia fica na memória do processo por 30 minutos, presa
   ao usuário que enviou, com as senhas **já cifradas**. Confirmar grava tudo em
   uma transação.
5. **Cor da linha**: vermelho = baixado, laranja = inativo, cinza = não é mais
   cliente, rosa-claro = município Lauro de Freitas. Branco e quase branco =
   ativo. Outra cor = ativo com pendência "cor fora da legenda" (P-06).
6. **Duplicados na planilha** (P-08): a primeira linha do CNPJ entra; as
   seguintes vêm marcadas para ignorar, e a pessoa pode trocar a escolha.
7. **Vencimentos**: só certificados no painel e no aviso (P-07); licenças
   municipais são importadas e aparecem na ficha. Faixas padrão 15/20/30 dias,
   configuráveis. "Hoje" no fuso de Salvador (UTC-3).
8. **Coletor**: leva CNPJ, titular, AC, validade, série e hash; **não leva**
   senha nem arquivo (P-13). A importação casa pelo CNPJ do certificado.
9. **Relatório de acessos ao cofre**: exige `admin.historico`, como o resto da
   trilha de uso.

## Project Structure

```
src/auditoria_fiscal/core/clientes.py              regras: documento, situação de campo, faixas
src/auditoria_fiscal/core/cofre.py                 AES-256-GCM e chave do ambiente
src/auditoria_fiscal/core/planilha_clientes.py     leitura da planilha atual (cor, oculta, rótulos)
src/auditoria_fiscal/core/certificados.py          leitura de .cer/.pfx (ICP-Brasil)
src/auditoria_fiscal/core/coletor_certificados.py  varredura da pasta + _info
src/auditoria_fiscal/ferramentas/clientes_store.py SQLite clientes.db
src/auditoria_fiscal/ferramentas/relatorio_clientes.py exportação sem senhas
src/auditoria_fiscal/web/rotas_clientes.py         rotas /api/clientes/**
webui/clientes.js                                  aba 9
coletar-certificados.py                            comando do coletor
tests/test_clientes.py, test_cofre.py, test_planilha_clientes.py,
tests/test_certificados.py, test_coletor_certificados.py,
tests/test_clientes_store.py, test_web_clientes.py
```

## Riscos

- Chave perdida = senhas perdidas; chave junto do backup = cofre inútil
  (P-10). Documentado no README-servidor.
- Prévia em memória some num reinício (o usuário reenvia o arquivo).
- O formato do `_info` foi visto em uma foto só; o leitor aceita os rótulos
  conhecidos e manda o resto para o relatório.
