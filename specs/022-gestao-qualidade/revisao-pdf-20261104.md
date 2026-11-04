# Revisão do pedido e próxima etapa — 04/11/2026

Escopo da etapa local original: conferir o pedido original, separar implementação de preparação
operacional e corrigir a próxima pendência encontrada com testes e preview
locais. Sem commit, push, merge, deploy, produção ou Linear. O PDF original e
as evidências privadas ficam fora deste repositório público.

## Situação dos dez itens

| Item | Cobertura no sistema | O que falta para uso real |
|---|---|---|
| 1. Atividades por setor | Modelos dos cinco setores, cadastro compartilhado, carteiras, tarefas avulsas e agenda de obrigações | Confirmar rotinas, periodicidades, responsáveis e abrangência por cliente/setor |
| 2. Ocorrências | Oito tipos, cliente, setor, responsável, data, descrição, criticidade, prazo, situação e histórico | Homologar o uso pela equipe e os responsáveis reais |
| 3. Prazos e produtividade | Prévia, geração, execução, histórico, conferência opcional e registro de tempo | Completar carteiras e responsáveis; aprovar as próximas gerações após a prévia |
| 4. Indicadores | Entregas no prazo, conclusões por pessoa, pendências, erros, reclamações, solução, setor e custos explícitos | Validar os recortes com a gestão e alimentar dados reais autorizados |
| 5. Planos de ação | Causa, ação corretiva/preventiva, responsável, prazo, andamento, evidências e validação da gestão | Preparar armazenamento privado e recuperação dos anexos antes de liberá-los |
| 6. Alertas | Alertas internos e montagem do resumo diário por e-mail | Configurar conta de envio, destinatários e homologar o envio autorizado |
| 7. Dashboard | Filtros e semáforo; divergência de cores encontrada nesta revisão e tratada na correção abaixo | Homologar a leitura dos indicadores; publicar a correção somente com autorização própria |
| 8. Relatórios | Recortes diário, semanal, mensal e personalizado; Excel e PDF | Conferir recortes e relatórios com a gestão |
| 9. Acesso e histórico | Escopo por pessoa/setor, visão global explícita, custos separados, revisões e eventos imutáveis | Aprovar e conceder a matriz de acessos reais |
| 10. Integração e implantação | Cadastro reutilizado, migração aditiva, roteiro de testes, implantação e treinamento | Definir participantes e datas, treinar a equipe, homologar a operação e ensaiar recuperação dos objetos |

Na etapa local original, não houve conferência da produção. Uma revisão
posterior, somente leitura e autorizada em 04/11/2026, confirmou que já existem
cadastros e tarefas em produção. Portanto, não se deve tratar o catálogo como
vazio nem a primeira geração real como uma etapa ainda não iniciada. O cadastro
parcial não comprova a aplicabilidade das regras nem a conclusão da carteira.
As contagens e evidências operacionais ficam fora do repositório público.

## Tarefas e prazos

O fluxo técnico de novembro/2026 foi demonstrado em base fictícia: prévia de uma
tarefa nova, geração, início, conclusão e três eventos preservados após recarga.
A repetição da prévia não propôs duplicatas e as 14 tarefas anteriores foram
preservadas. Isso comprova o exercício local, sem concluir a configuração real.

T019 da spec 013 está parcialmente configurada em produção e continua pendente
de conclusão operacional. A lista inicial de obrigações já foi recebida; faltam
completar e validar o catálogo, a aplicabilidade, a carteira e o calendário
efetivo antes das próximas cargas aprovadas. O registro histórico de
27/10 que dizia aguardar a lista não descreve sozinho o estado atual.

Decisões já respondidas não devem voltar como dúvidas: prazos mensais usam o mês
seguinte à competência; o Fiscal não exige conferência obrigatória; custo de
trabalho usa horas registradas multiplicadas pelo custo/hora informado. O
fechamento integral em 24/12 foi apenas uma hipótese da demonstração, não uma
definição do expediente real.

## Correção encontrada no item 7

A lista e o detalhe aplicavam uma regra própria no navegador: ocorrência
resolvida/encerrada ou plano validado recebiam verde mesmo quando finalizados
depois do prazo. Uma não conformidade aberta com prazo futuro também podia
aparecer amarela. O painel já classificava esses casos como vermelhos.

A correção reutiliza a classificação do núcleo no painel e nos dados retornados
pela API. Lista e detalhe usam a cor recebida, sem recalcular pelo relógio do
navegador. Datas seguem Salvador; sem informação suficiente para classificar
uma conclusão, o resultado permanece neutro. Não há migração nem mudança de
permissões, prazos, registros ou transições de negócio.

## Evidências e limites

O baseline anterior à alteração passou em 19 scripts, sem arquivos funcionais
modificados durante a execução. A regressão adicionada reproduz o problema antes
da correção. Logs, extração do documento e fixtures ficam na pasta privada
`tmp/revisao-pdf-20261104` do workspace, fora do checkout.

Após a correção, os mesmos 19 scripts passaram novamente, sem testes pulados,
falhas ou mudanças funcionais durante a execução. A revisão independente não
encontrou bloqueios no patch. Testes de núcleo e HTTP cobrem a fronteira de dia
UTC/Salvador, retorno após mutações, listas, detalhes, planos aninhados e
ausência de dados. A UI cobre as quatro cores e usa neutro quando o campo está
ausente ou inválido.

O preview em `http://127.0.0.1:8626/` usa um cliente, duas identidades, uma tarefa,
quatro ocorrências e três planos fictícios. No painel: três registros verdes,
três vermelhos e dois amarelos. Lista e detalhe conferidos: resolução/validação
tardia em vermelho, não conformidade aberta em vermelho e solução no prazo em
verde. Agendador, SMTP e S3 desligados. Os registros de exemplo usam relógio
simulado e não representam eventos reais do escritório.

## Sobreposição do menu: correção publicada

Na janela local de 1280 × 738 px, com todas as abas do administrador, os botões
Administração e Minimizar o menu se sobrepunham no rodapé da lateral. As caixas
medidas no navegador ocupam aproximadamente o mesmo espaço (x=12, y=670,
largura=223, altura=35 px), e clicar para minimizar abriu Administração.
Após aprovação específica, a navegação recebeu rolagem própria e os elementos
fixos da lateral passaram a reservar seu espaço. A correção foi conferida em
1280 × 738, 1024 × 600 e 960 × 480 px, com menu aberto e recolhido, e em
920 × 600 e 390 × 844 px no layout móvel. Administração e o botão de minimizar
ficam separados; minimizar/expandir preserva a aba atual. As 13 abas permanecem
acessíveis por mouse e teclado, com foco visível e rolagem automática.

Revisão independente sem achados bloqueantes. Evidências privadas em
`tmp/validacao-menu-20261104`; detalhes em [validacao.md](validacao.md).
O ajuste foi integrado pelo [PR #34](https://github.com/Komunick/auditoria-JB/pull/34)
e publicado pela promoção [#36](https://github.com/Komunick/auditoria-JB/pull/36),
merge `ef80d37c56a66f03689973958db60fa30ca80c8f`. A validação autenticada
de 04/11/2026 confirmou ausência de sobreposição e funcionamento da navegação.
A correção do semáforo não fez parte dessa publicação; sua preparação para PR
para `dev` é uma etapa posterior, sem autorização de merge ou deploy.

Esta revisão não configura S3 ou SMTP, não importa clientes, não concede acesso
real e não substitui o treinamento e o aceite da equipe. O roteiro de adoção
continua em [implantacao-treinamento.md](implantacao-treinamento.md).
