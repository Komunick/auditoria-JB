# Plano técnico — Gestão da qualidade

Implementação local autorizada em 30/10/2026. Base: dev após PR #28,
merge `15d90f17d7c4a41390df7f56ff21ff1c8621cada`. Em 03/11/2026, foi autorizada
a publicação do branch por commit, push e PR para `dev`, sem merge ou deploy.
Posteriormente, no mesmo dia, foram autorizadas a correção do executor, promoção
por PR/merge commit e implantação verificada na arm07. A transição administrativa
de dependências e sua ordem operacional estão no README do autodeploy e no roteiro.

## Arquitetura e dados

- `core/qualidade.py`: validação, transições e custo decimal.
- `QualidadeStore(TarefasStore)`: reutiliza clientes, setores, carteiras e tarefas.
  Adiciona cinco tabelas `qualidade_*` no mesmo clientes.db, com schema 4.
  Migração idempotente e transacional; erro não deixa schema parcialmente aplicado.
- Ocorrência → planos corretivos/preventivos → validação da gestão; evidências
  e histórico de antes/depois. Ocorrências encerradas e planos validados não
  aceitam alterações/comentários. Reabertura de ocorrência resolvida é explícita.
- Apontamento: minutos, data, autor da sessão, atividade e custo/hora opcional.
  Original imutável; cancelamento justificado conserva a trilha. Limite diário
  de 1.440 minutos por pessoa validado sob transação, inclusive em concorrência.
- Anexos: objeto privado no S3 e recibo no SQLite. Upload valida o formato e
  revalida sessão/permissões depois do armazenamento; uma recusa remove o objeto
  sem registrar o anexo. Falha da compensação gera evento técnico genérico nos
  logs para reconciliação administrativa. Download confere hash e tamanho.
  Testes/preview usam adaptador de diretório local habilitado explicitamente.
- `core/qualidade_indicadores.py`: funções puras sobre dados já autorizados.
  Ausência de informação permanece indisponível; fórmulas e amostras explícitas.
- `relatorio_qualidade.py`: XLSX com nove abas e PDF paginado; fórmulas de Excel
  neutralizadas, custos removidos sem permissão. Reutiliza openpyxl/fpdf2.
- `rotas_qualidade.py`: mesmas sessões, autorização por registro, revisão,
  transação, audit trail de uso sem descrições privadas e respostas no-store.
- `webui/qualidade.js` e CSS: aba estática, sem build, com modos claro/escuro e
  layout responsivo; integra Central e Tarefas e prazos sem duplicar cadastros.
- Resumo SMTP do agendador existente recebe sete classes de alerta; mesmo envio
  por pessoa/dia, escopo efetivo e sem custos. Nenhum serviço ou cron adicional.

## Acesso

`aba.qualidade` é o portão. `registrar`, `gerir`, `validar`, `todas`, `exportar`
e `custos` são concessões independentes. Não entram nas permissões padrão.
Colaborador vê suas atribuições efetivas; líder autorizado vê seus setores,
inclusive substituições válidas. A visão global não concede mutação nem custos.
Encerrar ocorrência, validar/devolver plano exige `qualidade.validar` e gestão
efetiva do setor (ou visão global explicitamente combinada com essa permissão).
Apontamentos pertencem ao autor histórico, sem transferi-los com substituições.

## Recortes e indicadores

Datas e relógio de negócio usam America/Bahia. O período aplica-se ao vencimento
(ou início sem vencimento) das tarefas e à data do registro nas ocorrências,
planos e horas. Status filtra os tipos compatíveis; horas não têm esse filtro.
Semana = segunda a domingo; mês = calendário. Pendência inclui execução que
ainda aguarda conferência. Autoria da conclusão vem de `concluida_por`, nunca da
carteira atual. Custo total fica indisponível quando há apontamento sem custo.

## Validação e implantação

Testes são scripts `tests/test_*.py`, não pytest. Testes RED anteriores à
implementação, depois fluxos HTTP, concorrência, permissões, UI e regressão total.
Ver [validacao.md](validacao.md) para resultados e correspondência com o PDF.

O executor ensaia a migração com QualidadeStore na cópia do backup. Essa alteração
do código administrativo exige reinstalar o executor em uma futura implantação
aprovada; não executar agora. Roteiro, dependências operacionais, recuperação e
treinamento em [implantacao-treinamento.md](implantacao-treinamento.md).
