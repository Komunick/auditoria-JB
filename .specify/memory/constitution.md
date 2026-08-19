<!--
Sync Impact Report
- Versão: template sem ratificação -> 1.0.0
- Princípios definidos: 6
- Seções adicionadas: Restrições técnicas e de segurança; Fluxo de
  desenvolvimento e qualidade; Governança
- Templates verificados: plan/spec/tasks/checklists do pacote 003
- Pendências: nenhuma; se o repositório atual já possuir constituição
  ratificada, fazer merge humano antes de substituir
-->

# Constituição do Auditoria-JB

## Princípios fundamentais

### I. Correção fiscal e rastreabilidade integral

Toda informação fiscal exibida, persistida ou exportada deve ser reproduzível
a partir de uma fonte identificada. Valores extraídos registram arquivo, hash,
aba, célula, rótulo e regra; valores derivados registram fórmula e fatos de
origem. Nenhuma automação pode inventar um valor ausente, converter ausência em
zero ou aceitar divergência silenciosamente. Operações monetárias usam precisão
decimal de centavos.

### II. Núcleo independente das interfaces

Regras fiscais, parsers, modelos e geradores pertencem a `core/` ou
`ferramentas/` e não importam FastAPI, PySide, HTML ou estado de requisição. A
web e o desktop podem consumir o núcleo; o núcleo não conhece as interfaces.
Uma nova ferramenta deve reutilizar a arquitetura existente antes de introduzir
processos, frameworks ou serviços adicionais.

### III. Autorização no servidor e menor privilégio

Toda operação protegida é autenticada e autorizada no servidor. Ocultar um
controle no frontend é apenas conveniência. Recursos temporários e jobs validam
seu proprietário. Identidades que assinam mutações vêm exclusivamente da sessão
autenticada. Novas permissões sensíveis não são concedidas automaticamente a
usuários existentes; administradores as recebem pelo modelo implícito atual.

### IV. Imutabilidade, versionamento e auditoria transacional

Fontes fiscais e eventos de domínio relevantes são imutáveis. Uma versão nova
nunca apaga ou sobrescreve silenciosamente uma versão anterior. Mutações
fiscais e seu evento de auditoria são gravados na mesma transação. A trilha de
uso geral complementa, mas não substitui, a trilha fiscal de domínio.

### V. Testes antes da implementação

Cada regra nova ou correção começa com teste automatizado capaz de falhar no
comportamento anterior. Parsers exigem fixtures sintéticas dos formatos
suportados; rotas exigem testes de autenticação, autorização e fluxo completo;
concorrência, idempotência e exportações exigem testes próprios. Uma feature não
é concluída enquanto a suíte anterior e a nova não passarem.

### VI. Compatibilidade e implantação simples

Uma feature não pode regredir as ferramentas existentes. O site continua sendo
implantado como um processo no servidor Windows, atualizado centralmente. Dados
persistentes ficam fora do Git e entram no procedimento de backup. Mudanças de
schema são aditivas e idempotentes. Dados reais, credenciais, bancos e uploads
nunca são versionados.

## Restrições técnicas e de segurança

- Backend web: FastAPI no processo existente; frontend: HTML/CSS/JavaScript
  estático sem etapa de build, salvo decisão futura explícita do proprietário.
- Persistência local: SQLite com chaves estrangeiras, `busy_timeout`, WAL e
  transações explícitas nas disputas de escrita.
- Arquivos não confiáveis são validados antes de bibliotecas de alto nível.
- Conteúdo textual exportado para Excel é neutralizado contra injeção de
  fórmula.
- Falhas devem ser explícitas, localizáveis e não podem produzir saída parcial
  apresentada como válida.
- Exposição fora da rede interna exige HTTPS, cookie `Secure`, proxy confiável
  e revisão de CSRF e cabeçalhos; isso não pode ser presumido apenas porque a
  aplicação funciona na LAN.

## Fluxo de desenvolvimento e qualidade

1. Especificar cenários, requisitos e resultados mensuráveis.
2. Registrar decisões, modelo de dados e contratos.
3. Escrever testes que falham para a fatia em implementação.
4. Implementar a menor mudança que satisfaça a fatia.
5. Rodar testes específicos e regressão proporcional ao impacto.
6. Revisar segurança, integridade, dados persistentes e documentação.
7. Somente então marcar tarefas e o gate de aceite como concluídos; checklists
   do Spec Kit avaliam requisitos e devem ser concluídos antes de implementar.

Pull requests devem explicar mudança funcional, migração de dados, evidência de
testes e riscos residuais. Complexidade adicional precisa ser justificada no
plano. Atalhos que removam rastreabilidade, autorização ou testes não são
aceitáveis.

## Governança

Esta constituição prevalece sobre documentos de feature quando houver conflito.
Alterações exigem justificativa, impacto e plano de migração. A versão segue
SemVer: MAJOR para remoção/redefinição incompatível de princípio, MINOR para
novo princípio/seção normativa ou expansão material e PATCH para esclarecimento
sem mudança de obrigação. Revisões devem confirmar conformidade antes do merge.
Exceções temporárias precisam de responsável, prazo e tarefa explícita de
correção.

**Versão**: 1.0.0 | **Ratificada**: 2026-08-13 | **Última alteração**: 2026-08-13
