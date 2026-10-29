# Spec 016 — Central operacional

## Objetivo

Transformar o início da plataforma em um ponto de trabalho diário: identificar
pendências, localizar a tarefa e agir no fluxo existente. O pedido é inspirar a
experiência em Jettax e Fivelabs, mantendo identidade e regras próprias.
Prioridade confirmada pelo usuário: gestão do escritório — painel, clientes,
tarefas e equipe.

## Referências e decisão de produto

Consultadas em 28/10/2026, apenas informações públicas dos fornecedores:

- [Jettax — Gestão de Obrigações Acessórias](https://jettax360-help.freshdesk.com/support/solutions/articles/151000235417-como-funciona-o-menu-gest%C3%A3o-de-obrigac%C3%B5es-acess%C3%B3rias): filtros por cliente/competência, totalizadores e acompanhamento de pendências.
- [Fivelabs — produto](https://conversor5.com.br/o-conversor/) e [fluxo de uso](https://conversor5.com.br/experimente-gratis-v2/): importação, configuração, conferência e exportação em etapas.

Essas referências orientam os fluxos, sem copiar marcas ou ativos. As telas
autenticadas dos fornecedores não foram inspecionadas. Não atribuir à Fivelabs
uma agenda de tarefas nem apresentar captura automática, transmissão fiscal,
inteligência artificial ou integração com ERP que a plataforma não implementa.

## Histórias e aceite

### US1 — Ver o que exige atenção

Ao abrir o Início, quem possui `aba.tarefas` vê a Central com filtros de escopo,
competência opcional, cliente, setor, responsável e busca. O padrão é todo o
escopo autorizado (`visao=cliente`), sem restringir competência: vencimentos
atrasados de competências anteriores não desaparecem na entrada.

- Totais do conjunto inteiro autorizado e filtrado, independente da página.
- Cartões de atrasadas, vencendo hoje, próximas e conferência, com contagens
  adicionais úteis de aguardando cliente, sem responsável e sem vencimento.
- Fila paginada curta de pendências com situação, prazo e responsável efetivo.
- Distribuição por responsável representa carga atual, não produtividade histórica.
- Carregamento, erro e conjunto vazio distintos; falha não vira total zero.
- Reabrir o Início ou usar Atualizar renova o catálogo antes do painel. Filtros
  ainda disponíveis são preservados; opções removidas deixam de filtrar.
- Sem acesso a Tarefas, manter início com os atalhos permitidos e não consultar
  o endpoint do painel. Todos os módulos continuam disponíveis por permissão.

### US2 — Ir do indicador à tarefa

- Cartão seleciona uma fila no painel; filtros-base continuam visíveis.
- Os indicadores não mudam com a escolha da fila: ela restringe somente a lista.
- Abrir tarefa leva ao detalhe existente, com autorização do servidor.
- Abrir lista completa conserva filtros-base e fila. Busca e filas também
  funcionam na aba Tarefas e na exportação Excel autorizada.
- Filas e métricas têm a mesma semântica no servidor; nenhuma soma da página
  atual é apresentada como total.
- Mudança de filtros limpa seleção em lote e volta à primeira página. Resposta
  antiga não substitui uma consulta mais recente.

### US3 — Importar com etapas claras

Na importação de carteira, mostrar Escolher arquivo → Conferir prévia →
Concluído. A conclusão aparece apenas após resposta de confirmação bem-sucedida.
Falha ou token inválido mantém orientação para nova prévia. Reutilizar validações,
autorização, revisão e confirmação existentes. Nenhum dado real é carregado nesta
entrega; modelo de importação e pendências da base são trabalhos separados.

### US4 — Navegar pela operação

Destacar Central, Tarefas e Clientes no grupo Gestão; manter ferramentas fiscais,
Patrimônio e Administração disponíveis em grupos claros, com slugs/permissões
existentes. Grupos sem itens acessíveis não aparecem. Atalhos e navegação por
teclado funcionam nos temas claro/escuro e em tela estreita.

## Regras de contagem

- Unidade: uma tarefa/ocorrência. Competência é independente do vencimento.
- `abertas`: situações a fazer, em andamento, aguardando cliente ou devolvida.
- `pendentes`: abertas ou concluídas que exigem conferência ainda não realizada.
- `atrasadas`: abertas com vencimento anterior a hoje.
- `vencendo_hoje`: abertas com vencimento igual a hoje.
- `proximas`: abertas com vencimento posterior a hoje até hoje + alerta_dias.
- `pendentes_conferencia`: concluída com exige_conferencia=true.
- `aguardando_cliente`: situação aguardando_cliente, mesmo sem vencimento.
- `sem_vencimento` e `sem_responsavel`: pendentes com o respectivo campo ausente.
- Concluídas/conferidas/dispensadas não entram no atraso; não há percentual de
  produtividade ou conclusão nesta entrega. Cor vermelha não define atraso.

Hoje e substituições seguem America/Bahia, capturados uma vez por consulta.
Sem movimento não significa inativo nem dispensa. As regras de negócio
confirmadas, conferência opcional e datas sem vencimento continuam preservadas.

## Limites e segurança

Somente leitura na Central. Nenhuma migração, processo, serviço ou dependência
nova. Autorização ocorre antes da agregação; filtros nunca ampliam o escopo.
Contagens globais de Clientes não são usadas como métricas da carteira.
Dados reais, nomes pessoais, documentos, credenciais e planilhas ficam fora do Git.
Produção e merge não integram esta implementação.
