# Handoff para o Claude — Conciliação Fiscal

Você está implementando a feature `003-conciliacao-fiscal` no repositório
Auditoria-JB. Os documentos em `specs/003-conciliacao-fiscal/` são a fonte de
verdade desta entrega.

## Antes de alterar código

1. Leia integralmente:
   - `.specify/memory/constitution.md`;
   - `specs/003-conciliacao-fiscal/spec.md`;
   - `specs/003-conciliacao-fiscal/plan.md`;
   - `specs/003-conciliacao-fiscal/research.md`;
   - `specs/003-conciliacao-fiscal/data-model.md`;
   - `specs/003-conciliacao-fiscal/implementation-log.md`;
   - todos os arquivos em `contracts/`, `checklists/`, `acceptance/` e
     `references/`;
   - `specs/003-conciliacao-fiscal/tasks.md`.
2. Inspecione o código atual. A base usada na especificação foi o commit
   `f86750007b13c7045eaff5e5b204457ec9b9076b`; adapte somente diferenças reais.
3. Execute toda a suíte atual e registre o baseline antes de escrever código.
4. Execute `/speckit-analyze`. Corrija inconsistências documentais antes da
   implementação; não reduza requisitos de segurança ou integridade para fazer
   a análise passar.
5. Trabalhe numa branch própria. Não faça push, merge ou PR sem autorização do
   usuário.

## Regras não negociáveis

- Não executar o Flask, não criar segunda porta, não usar iframe e não criar
  outro login.
- O core fiscal não pode importar FastAPI nem módulos de `web/`.
- Não versionar planilhas reais, bancos, uploads, credenciais ou dados de
  clientes.
- Dinheiro é `Decimal` no domínio e centavos inteiros no SQLite.
- Uma fonte é identificada por SHA-256 e preservada de forma imutável.
- Arquivo diferente para o mesmo CNPJ e competência cria versão candidata e
  conflito; nunca sobrescreve a versão vigente automaticamente.
- A identidade de importador, revisor, aprovador e resolvedor vem sempre de
  `Usuario`, nunca do corpo da requisição.
- Aprovação, rejeição, resolução e promoção de versão gravam estado e evento
  fiscal na mesma transação.
- Bloqueio aberto ou conflito aberto impede aprovação.
- Toda sessão e todo job devem validar o usuário proprietário.
- O XLSX deve ser validado antes do `openpyxl`.
- Testes automatizados são obrigatórios e devem ser escritos antes da mudança
  correspondente.

## Ordem de execução

Implemente por fase e pare nos checkpoints de `tasks.md`:

1. Setup, fixtures e baseline.
2. Fundação: propriedade de sessões/jobs e infraestrutura.
3. US1: acesso nativo à sexta ferramenta.
4. US2: importação segura, parser e persistência versionada.
5. US3: consulta e proveniência.
6. US4: revisão, aprovação e exceções.
7. US5: conflitos e versões.
8. US6: exportação consolidada.
9. US7: preenchimento da planilha-mestre.
10. US8: painel e filtros.
11. Polish: documentação, desempenho, validação privada e regressão.

Use `/speckit-implement` com um intervalo pequeno de tarefas por vez. Depois de
cada história, execute seus testes específicos e os testes web afetados. Ao
final, rode a suíte completa e `/speckit-converge`.

## Definição de concluído

A feature só termina quando:

- todos os itens necessários de `tasks.md` estiverem marcados;
- `checklists/requirements.md` permanecer aprovado quanto à qualidade dos
  requisitos e todos os itens aplicáveis de
  `acceptance/security-data-integrity.md` tiverem evidência de implementação;
- a suíte anterior continuar passando;
- os novos testes cobrirem os dois layouts, duplicidade, concorrência,
  conflitos, autorização, auditoria e os dois tipos de exportação;
- a suíte sintética estiver verde e, se o diretório privado de amostras estiver
  disponível, T065 também estiver validada fora do Git; se não estiver, T065
  permanece explicitamente pendente como gate de aceite do proprietário;
- não houver Flask, iframe, nova porta, credencial ou arquivo fiscal real no
  diff;
- a documentação de implantação e backup estiver atualizada.
