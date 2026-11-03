# Spec 022 — Gestão da qualidade e acompanhamento operacional

Pedido aprovado em 30/10/2026: concluir as pendências do PDF de solicitação de TI
da diretoria (27/10/2026, seis páginas, dez itens). A fonte privada permanece fora
do repositório. A etapa inicial abrangeu implementação e preview locais com
dados sintéticos, sem publicação.

Em 03/11/2026, foi autorizada a publicação do código por commit, push do branch
da spec e PR para `dev`. Merge, deploy, alterações em produção e no Linear
continuam fora do escopo autorizado.

Autorização posterior em 03/11/2026: resolver os pré-requisitos do executor,
promover pelo fluxo de PR/merge commit e publicar na arm07, com backups e
validação. Não inclui importar empresas reais nem alterar o Linear. A aprovação
não distribui novas permissões a usuários nem configura um bucket S3.

## Cobertura do pedido

1. Atividades por setor: integrar clientes, setores, carteiras, tarefas avulsas e
   obrigações existentes; oferecer referências para personalizar atividades do Fiscal,
   Contábil, DP, Legalização e Administrativo, sem inventar vencimentos legais.
2. Ocorrências: data, cliente, setor, colaborador, tipo, descrição, criticidade,
   prazo e situação; comentários e histórico imutável. Erro, atraso, comunicação,
   reclamação, retrabalho, pendência, procedimento e não conformidade.
3. Prazos/produtividade: preservar agenda, distribuição, início/vencimento,
   execução e conferência existentes; acrescentar apontamentos de tempo. Custo =
   minutos / 60 × custo/hora informado em cada lançamento (decisão do usuário).
4. KPIs: entregas no prazo, conclusões por pessoa, pendências, erros/retrabalho,
   cumprimento dos prazos, reclamações, tempo médio de solução, desempenho por
   setor, não conformidades abertas/solucionadas. Exibir fórmula, denominador e
   ausência de dados; não inventar notas de produtividade ou engajamento.
5. Planos de ação: vínculo com ocorrência, causa, responsável, ação corretiva ou
   preventiva, prazo, andamento, evidências e validação da gestão. Colaborador
   solicita validação; somente gestão autorizada valida/devolve com motivo.
6. Alertas: prazos próximos, atrasos, pendências sem movimento, documentos
   aguardados, conferência pendente, não conformidades e planos vencidos; canais
   internos e resumo diário SMTP já existente, sem ativar envio neste trabalho.
7. Dashboard: semáforo, filtros por cliente, setor, colaborador, período e status.
   Operação, risco, engajamento e progresso como medidas explícitas observáveis:
   pendências/criticidade, espera por cliente, avanço/conclusão e apontamentos.
8. Relatórios: períodos diários/semanais/mensais ou personalizados, serviços,
   pendências, atrasos, produtividade, falhas e medidas; exportação Excel e PDF.
9. Acesso/histórico: novas permissões explícitas, colaborador no próprio escopo,
   líder no setor efetivo e diretoria com visão global concedida. Autor vem da
   sessão; revision obrigatório em edição/transição; eventos não editáveis.
10. Integração e implantação: IDs reais do cadastro existente, sem duplicá-lo;
    roteiro de etapas, testes, treinamento e disponibilização condicionada à
    futura aprovação de publicação/deploy e configuração operacional.

## Regras e limites

- Núcleo sem dependência web; persistência aditiva no clientes.db, transação e
  auditoria juntas. Nenhuma exclusão de registros de negócio.
- Anexos privados: PNG/JPEG/PDF/EML limitados a 10 MB, nome seguro e conteúdo
  validado; acesso autenticado e auditado, download como attachment/no-store.
  Armazenamento de objetos configurável (S3); diretório local exclusivo apenas
  em modo de desenvolvimento/teste explícito. Sem segredos ou dados reais no Git.
- Custo é Decimal, nunca float; valores ausentes permanecem indisponíveis.
- Métricas operacionais não representam parecer fiscal, avaliação automática de
  pessoas ou score opaco. Fórmulas e conjunto filtrado sempre visíveis.
- Configuração do escritório (carteiras, equipe, catálogo, SMTP/S3) é distinta da
  entrega do software; não inventar responsáveis nem ativar serviços externos.

## Aceite

- Cada item acima mapeado a código, teste e evidência de interface ou documento.
- Testes RED antes de implementar; segurança de escopo, transições, concorrência,
  anexos e exportação; regressão completa e preview navegável sintético.
- Nenhum acesso a produção ou carga real; publicação não faz parte desta entrega.
