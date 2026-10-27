# Implementation Plan: Tarefas e Prazos

**Branch**: `013-tarefas-e-prazos` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

## Summary

Décima ferramenta no processo FastAPI existente. Setores, carteira, características e obrigações geram,
por competência, as tarefas de cada cliente. Um agendador dentro do próprio processo dispara a geração do
mês e o resumo diário por e-mail. Tudo em tabelas novas do `clientes.db` (schema 2, aditivo), em cima do
cadastro da aba 9.

## Technical Context

- Python 3.11/3.12, FastAPI, SQLite (WAL, `busy_timeout`, `BEGIN IMMEDIATE`), openpyxl, frontend
  estático sem build — o mesmo da casa.
- E-mail: `smtplib` da biblioteca padrão (STARTTLS ou SSL), configurado por variáveis de ambiente. Sem
  dependência nova.
- Planilhas `.xls` (formato antigo, como as recebidas do DP): dependência nova `xlrd>=2.0`, só leitura.
  Alternativa sem dependência: aceitar só `.xlsx` e pedir "Salvar como". Decisão: **usar `xlrd`**, porque
  são cerca de 20 planilhas e pedir conversão a cada pessoa atrasa a migração.
- Fuso: Salvador (UTC-3), como o resto do sistema.

## Constitution Check

| Princípio | Como a feature cumpre |
|---|---|
| I. Rastreabilidade | Tarefa guarda a obrigação, a regra e o ajuste que a geraram. Importação guarda hash, linha e coluna. Nenhum vencimento é inventado: sem regra cadastrada, não há tarefa. |
| II. Núcleo sem interface | Regras (vencimento, dia útil, aplicabilidade, transições, cor) em `core/`; persistência em `ferramentas/`; FastAPI só em `web/`. |
| III. Autorização no servidor | Sete slugs novos, fora do padrão. `tarefas.setor` é conferido contra o setor e a data (responsável ou substituto vigente) a cada pedido. |
| IV. Trilha transacional | Toda mudança de situação grava o evento na mesma transação. Eventos imutáveis por trigger. |
| V. Testes antes | Cada módulo nasce com o teste do comportamento; datas e feriados com relógio fixo. |
| VI. Implantação simples | Mesmo processo e mesma porta. O agendador é uma thread do processo, não um serviço novo. Schema aditivo. |

## Decisões

1. **Mesmo banco do cadastro (`clientes.db`, schema 2).** Tarefa sem cliente não existe; com o mesmo
   banco, a chave estrangeira e a transação valem. Migração aditiva: `CREATE TABLE IF NOT EXISTS` e
   colunas novas em `cliente` (`contato_nome`, `contato_email`) com `ALTER TABLE ... ADD COLUMN`,
   conferindo antes se a coluna já existe.
2. **Regra de vencimento como dado, não como código.** Formato fechado e validado:
   `{"tipo": "dia_mes_seguinte", "dia": 20}`, `{"tipo": "ultimo_dia_util_mes_seguinte"}`,
   `{"tipo": "dia_mes_fixo", "dia": 30, "mes": 4}` (anual), mais `"sem_expediente": "antecipar" | "adiar"
   | "manter"`. Tipos novos entram em `core/regras_vencimento.py` com teste.
3. **Condição de aplicação como dado.** `{"todas": [ids], "alguma": [ids], "nenhuma": [ids]}`, sobre as
   características do cliente. Vazio = todos os clientes do setor.
4. **Competência = mês de referência (`AAAA-MM`).** Trimestral: competências 03, 06, 09, 12 (ou a lista
   configurada na obrigação). Anual: uma competência por ano.
5. **Feriados**: tabela própria. Os nacionais fixos e os móveis (Carnaval segunda e terça, Sexta-feira
   Santa, Corpus Christi — calculados a partir da Páscoa) são gerados pelo sistema e marcados como
   "nacional — calculado". Estaduais e municipais entram à mão (P-08). Carnaval e Corpus Christi são
   pontos facultativos: vêm **marcados como sem expediente**, e o escritório pode desmarcar.
6. **Quem responde hoje.** Uma função `responsavel_efetivo(setor, pessoa, data)` resolve a substituição.
   É usada na geração, nos alertas e na checagem de `tarefas.setor`. A tarefa guarda o responsável
   **titular**; telas e alertas resolvem o efetivo. Assim, o fim da substituição não exige reescrever
   tarefas.
7. **Agendador no processo.** Thread iniciada no `startup` do FastAPI, acordando a cada 15 minutos:
   (a) gera a competência corrente se ainda não foi gerada; (b) envia o resumo do dia a partir do horário
   configurado, se ainda não foi enviado. As duas ações são idempotentes no banco (chaves únicas em
   `geracao` e `envio_alerta`), então dois processos não duplicam nada. O reinício diário da VM (04h45)
   não atrapalha: a próxima volta da thread retoma.
8. **E-mail por variáveis de ambiente**: `AUDITORIA_SMTP_HOST`, `_PORTA`, `_USUARIO`, `_SENHA`,
   `_REMETENTE`, `_TLS` (`starttls` | `ssl`). A senha fica fora do banco e do Git, como a chave do cofre.
   Sem configuração, o e-mail fica desligado e a tela avisa.
9. **Cores calculadas no servidor** a partir da situação, do vencimento e de "hoje", e devolvidas prontas.
   A regra fica num lugar só.
10. **Importação de carteira reaproveita o padrão da aba 9**: prévia em memória, uma transação, arquivo
    apagado. O casamento por nome usa a chave sem acento de `core/clientes.chave_texto` e sugere os 3 mais
    parecidos (`difflib`, biblioteca padrão); quem decide é a pessoa.
11. **E-mail dos usuários**: coluna opcional `usuario.email` em `auditoria_web.db`,
    adicionada sem perda e editada pela administração. O login não é presumido
    como endereço. Usuários inativos ou sem acesso à aba não recebem resumos.
12. **Validade dos ajustes**: início/fim inclusivos comparados ao primeiro dia
    da competência. Alterar uma regra não reescreve as tarefas existentes.
13. **Entrega SMTP**: reserva persistente antes da conexão evita duplicação
    entre threads, processos e reinícios. Uma interrupção após a reserva pode
    deixar entrega indeterminada; não há reenvio automático nesse dia. A
    configuração desligada e falhas ficam registradas com códigos sem segredos.
14. **Espera do cliente**: `tarefa.situacao_em` preserva o início do estado;
    comentar ou redistribuir não reinicia o contador de dias de espera.
15. **Prévia de geração**: a confirmação revalida os candidatos dentro da
    transação de escrita e recusa a prévia se a agenda mudou desde a leitura.
16. **Autorização e escrita**: rotas que alteram o domínio adquirem
    `BEGIN IMMEDIATE` antes de verificar setor/carteira. As operações internas
    usam savepoints; uma troca concorrente de responsável não atravessa a
    conferência de permissão. Ajustes aceitam edição auditada com `revision`,
    inclusive para corrigir exceções permanentes.

## Project Structure

```
src/auditoria_fiscal/core/regras_vencimento.py   competência, regra de vencimento, dia útil, Páscoa
src/auditoria_fiscal/core/tarefas.py             situações, transições, cor, atraso, aplicabilidade
src/auditoria_fiscal/core/planilha_carteira.py   leitura .xls/.xlsx das planilhas de colaborador
src/auditoria_fiscal/ferramentas/tarefas_store.py  setores, carteira, obrigações, geração, tarefas
src/auditoria_fiscal/ferramentas/alertas_email.py  resumo diário e envio SMTP
src/auditoria_fiscal/ferramentas/relatorio_tarefas.py exportação Excel
src/auditoria_fiscal/web/rotas_tarefas.py        /api/tarefas/**
src/auditoria_fiscal/web/agendador.py            thread de geração e resumo
webui/tarefas.js                                 aba 10
tests/test_regras_vencimento.py, test_tarefas.py, test_planilha_carteira.py,
tests/test_tarefas_store.py, test_alertas_email.py, test_web_tarefas.py
```

## Riscos

- **O catálogo de obrigações é o coração e ainda não existe (P-01).** Sem ele, a ferramenta funciona só
  com tarefas avulsas. A implementação pode seguir; o valor aparece quando a JB passar a lista.
- **Regra de vencimento legal muda** (por exemplo, prazos da DCTFWeb e do DAS já mudaram em anos
  anteriores). Por isso a regra é dado editável, com histórico.
- **Volume**: centenas de clientes × dezenas de obrigações dão milhares de tarefas por mês. Índices por
  (setor, responsável, situação, vencimento) e paginação desde o início.
- **E-mail com senha** é credencial: a mesma disciplina da chave do cofre (variável de ambiente, nunca no
  banco ou no log).
