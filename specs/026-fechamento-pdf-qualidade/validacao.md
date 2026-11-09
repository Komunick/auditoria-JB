# Validação — 09/11/2026

Base: `origin/dev` em `4720927`. Branch local: `hermes/fechamento-pdf-qualidade`.
Dados sintéticos em diretório temporário; nenhum dado real, produção, SMTP ou Linear.

## RED/GREEN

`tests/test_qualidade_filtro_substituto.py` cria setor com titular e substituto
vigente, uma ocorrência, um plano, uma tarefa e lançamentos de horas.

- Código original: falha em "Filtro por substituto perdeu a ocorrência do titular".
- Com a correção: passa. Cobre lista de ocorrências e planos, painel, planilha Excel
  (aba Tarefas), horas pessoais, fim da vigência da substituição (o filtro deixa de
  trazer os itens do titular) e o catálogo completo dos cinco setores, sem duplicatas.

## Regressão

Suíte local completa, 114 scripts de `tests/`: **108 aprovados e 6 com falha**.
As seis falhas ocorrem do mesmo modo em `origin/dev` sem alterações e vêm do
ambiente de teste, não do código: cinco de NFS-e (`SSLCertVerificationError` ao
consultar ADN e Sefin: `test_nfse_parametros`, `test_nfse_sefin`,
`test_nfse_transmissao`, `test_web_nfse_transmissao`; `test_web_nfse_sugestao` também
falha sem alterações, provavelmente pela mesma consulta externa, causa não investigada)
e `test_ui_smoke` (PySide6 não instalado). Todos os scripts de
qualidade, tarefas, relatórios, permissões e anexos passaram.

## Limites

- Não houve conferência em produção nem preview em navegador nesta etapa.
- A interface do catálogo não foi alterada; a quebra de linha da lista foi lida no
  código, não vista na tela.
- A análise de cobertura dos marcadores foi feita por leitura do código e dos testes;
  as divergências que viraram alteração foram reproduzidas por teste.
