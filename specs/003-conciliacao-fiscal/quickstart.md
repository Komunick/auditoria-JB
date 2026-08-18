# Quickstart de implementação e validação

## 1. Preparar o clone

No PowerShell, a partir do repositório Auditoria-JB:

```powershell
git status --short
git rev-parse HEAD
$env:SPECIFY_FEATURE_DIRECTORY = "specs/003-conciliacao-fiscal"
```

Não descarte alterações já existentes. Crie uma branch de trabalho conforme a
política do usuário.

O repositório já contém a integração Claude do Spec Kit. Se precisar atualizar
a ferramenta, use o fluxo oficial do GitHub Spec Kit e uma versão fixada; isso
não é pré-requisito para implementar esta feature.

## 2. Ler e analisar

No Claude Code:

```text
/speckit-analyze
```

Leia o relatório. Corrija inconsistências entre spec, plano, modelo, contratos
e tarefas antes do código. Não remova controles de integridade para resolver
alertas.

## 3. Obter baseline

Use o Python do ambiente do projeto. O padrão do repositório é executar cada
script diretamente:

```powershell
Get-ChildItem tests\test_*.py | ForEach-Object {
    & .\.venv\Scripts\python.exe $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $($_.Name)" }
}
```

Testes dependentes de Firebird podem pular quando o runtime não estiver
disponível; registre o motivo. Uma falha anterior não deve ser atribuída à nova
feature, mas precisa ser documentada.

## 4. Implementar por checkpoints

Primeira rodada:

```text
/speckit-implement Implemente apenas T001 a T011. Escreva os testes primeiro, execute os testes afetados e pare no checkpoint.
```

Depois, avance uma história/fase por vez:

```text
/speckit-implement Implemente a próxima fase incompleta de tasks.md, execute os testes específicos e pare no checkpoint.
```

Não pedir uma implementação monolítica de todas as tarefas numa única rodada.

## 5. Fixtures sintéticas mínimas

Criar no teste, sem copiar fontes reais:

- `quadro_50_5_valido.xlsx`;
- `quadro_50_3_dimp_valido.xlsx` com pelo menos duas instituições e uma linha de
  voucher;
- `modelo_mestre_valido.xlsx` com duas seções anuais;
- variações inválidas geradas programaticamente (CNPJ, competência, fechamento,
  macro/link/pacote falso);
- `mesma_competencia_retificada.xlsx` com uma diferença de R$ 0,01 ou mais para
  exercitar o conflito.

Use CNPJ sintético válido, como `11.222.333/0001-81`, razão social fictícia e
valores não derivados dos clientes reais.

## 6. Cenário ponta a ponta obrigatório

1. Bootstrap/login de admin.
2. Criar usuário com apenas `aba.conciliacao` e `conciliacao.importar`.
3. Abrir a sexta aba e criar sessão.
4. Enviar 50-5, 50-3, duplicata renomeada, retificação e XLSX inválido.
5. Processar job e conferir resumo `2 processados / 1 duplicado / 1 conflito /
   1 rejeitado` (ajuste se fixtures adicionais forem incluídas).
6. Conferir valores e proveniência.
7. Verificar que o importador não pode aprovar nem resolver.
8. Conceder permissões ao revisor e resolver o conflito.
9. Aprovar a versão vigente sem bloqueios.
10. Exportar consolidado e reabri-lo.
11. Preencher a cópia do modelo para um CNPJ.
12. Conferir trilha geral e trilha fiscal.
13. Confirmar que segundo usuário não acessa sessão/job do primeiro.

## 7. Validação local com arquivos reais

Os arquivos reais ficam fora do Git. Consulte
`references/source-inventory.md`. O teste local deve:

- verificar os SHA-256 antes de usar os resultados de referência;
- processar os 12 nomes fornecidos;
- produzir 10 fontes/conciliações únicas devido às duas duplicatas exatas;
- comparar os campos dos quatro relatórios DIMP com a planilha mestre,
  incluindo PIX e total não PIX por instituição;
- preencher uma cópia do modelo fornecido e nunca alterá-lo.

Não adicionar caminhos absolutos dos Downloads aos testes versionados. Aceitar
um diretório opcional por variável de ambiente, por exemplo
`AUDITORIA_CONCILIACAO_AMOSTRAS`, apenas em script de validação local ignorado
ou que pule quando ausente.

## 8. Testes novos esperados

```powershell
& .\.venv\Scripts\python.exe tests\test_conciliacao_sefaz.py
& .\.venv\Scripts\python.exe tests\test_conciliacao_store.py
& .\.venv\Scripts\python.exe tests\test_relatorio_conciliacao.py
& .\.venv\Scripts\python.exe tests\test_web_conciliacao.py
& .\.venv\Scripts\python.exe tests\test_web_permissoes.py
```

Depois, executar toda a suíte.

## 9. Smoke web

```powershell
.\servidor.ps1
```

Validar no navegador:

- tema claro e escuro;
- menu expandido e recolhido;
- tela estreita;
- estados de loading, vazio, erro e sucesso;
- permissões retiradas durante a sessão;
- confirmação e justificativa;
- downloads e nomes de arquivos.

## 10. Revisão final

```powershell
git status --short
git diff --check
git diff --stat
git diff -- requirements.txt
```

Confirmar:

- nenhuma dependência Flask/Waitress nova;
- nenhuma segunda porta ou processo;
- nenhuma planilha, banco, upload ou credencial;
- nenhum `tempfile.mktemp` novo;
- migrações idempotentes;
- documentação de backup atualizada;
- todos os testes verdes.

No Claude:

```text
/speckit-converge
```

Se o comando acrescentar tarefas, implemente-as e repita a validação antes de
declarar conclusão.
