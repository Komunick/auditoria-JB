# Spec 026 — Fechamento do pedido de TI da diretoria (Gestão da qualidade)

Pedido da direção da Komunick em 09/11/2026: dar foco total ao Auditoria-JB e
concluir todas as solicitações do PDF de TI da diretoria da JB Fraga (27/10/2026,
seis páginas, dez seções). A fonte privada permanece fora do repositório público.

Escopo desta etapa: auditoria independente do que as specs 022, 023 e 024 afirmam
estar pronto, correção das lacunas de software encontradas e lista objetiva do que
depende da JB. Sem carga real e sem Linear. Publicação por PR #48 para `dev`; merge e
promoção para a `main` autorizados pela direção para 09/11/2026, às 12h. O resultado
do deploy automático precisa ser conferido no servidor.

## Método

Cada marcador das dez seções do PDF foi conferido contra o código de `origin/dev`
(`4720927`): rotas, núcleo, interface, relatórios e testes. A leitura foi feita por
uma análise independente (Cursor, somente leitura) e as divergências foram
reproduzidas por teste antes de qualquer alteração.

## Resultado da auditoria

| Seção | Situação | Observação |
|---|---|---|
| 1. Atividades por setor | Lacuna de catálogo corrigida | O catálogo de referência não tinha linha própria para vários marcadores (pendências fiscais, prazos, documentos pendentes, conferência e validação, conferência do eSocial, prazos de conclusão da Legalização) |
| 2. Gestão da qualidade | Implementado | Oito tipos, campos pedidos e histórico imutável |
| 3. Prazos e produtividade | Implementado | Agenda, distribuição, execução, conferência, apontamentos |
| 4. Indicadores | Implementado | Nove indicadores do PDF, mais o total de não conformidades |
| 5. Planos de ação | Implementado | Armazenamento privado precisa ser habilitado na operação |
| 6. Alertas | Implementado nos alertas internos | Envio por e-mail depende da conta SMTP e do contrato do executor |
| 7. Dashboard | Implementado | Semáforo único; filtros por cliente, setor, colaborador, período e status |
| 8. Relatórios | Implementado | Excel e PDF com o mesmo conjunto filtrado |
| 9. Acesso e histórico | Implementado | Divergência do filtro de colaborador com substituição corrigida |
| 10. Implantação | Roteiro documentado | Treinamento, piloto e aceite são da JB |

## Lacunas de software corrigidas

1. **Filtro "Colaborador" ignorava a substituição.** Visibilidade e edição já usavam o
   responsável efetivo, mas o filtro comparava o titular gravado. Com substituto
   vigente, ao escolher o substituto no filtro os registros do titular sumiam do
   painel, das listas e dos relatórios, enquanto o módulo Tarefas os mostrava.
   Agora tarefas usam `responsavel_efetivo_id`; ocorrências e planos usam a mesma
   regra de `_proprio`; horas continuam pelo titular (lançamento pessoal).
2. **Catálogo de atividades alinhado ao PDF.** As cinco listas passam a conter
   exatamente os marcadores do pedido, sem inventar vencimentos, periodicidades ou
   responsáveis. Continua sendo referência: não cria obrigações.

## Pontos avaliados e mantidos

- O período dos relatórios e do painel aplica-se ao vencimento das tarefas e à data
  do registro das ocorrências. Isso é decisão documentada na spec 022 (`plan.md`).
  A aba "Serviços executados" por isso lista o que vence no período, e não só o que
  foi executado nele. Se a diretoria preferir o recorte por data de execução, é uma
  mudança de regra de negócio e precisa de decisão própria.
- O filtro de situação do painel é único e vale para todas as entidades, por
  desenho (comentário em `_conjunto`); a lista de situações da visão geral reúne as
  de tarefas, ocorrências e planos.

## O que depende da JB (não é software)

- Catálogo real de obrigações, periodicidades, carteiras e responsáveis por cliente e setor.
- Matriz de pessoas e permissões (`aba.qualidade`, registrar, gerir, validar, todas,
  exportar, custos) e quem pode ver custos e a visão global.
- Habilitar o armazenamento privado das evidências no serviço e definir retenção externa.
- Conta SMTP, destinatários e aceite do envio dos alertas; o executor ainda rejeita
  variáveis SMTP em produção e precisa de evolução explícita (spec 024, `operacao.md`).
- Custo/hora autorizado por função.
- Participantes e datas do treinamento, piloto e aceite do go-live
  (`specs/022-gestao-qualidade/implantacao-treinamento.md`).
