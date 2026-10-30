# Spec 021 — Confirmação da importação da Base Fiscal

## Objetivo

Converter a revisão da spec 020 em uma inclusão explícita e rastreável de novas
empresas. Esta rodada implementa e valida o recurso somente em ambiente local,
com dados sintéticos. Não inclui execução de carga em produção, acesso ao Linear,
commit, push, merge ou deploy.

## Cenários e critérios de aceite

1. A conferência e a prévia 020 continuam somente leitura, sem criar tokens ou
   migrar o cadastro. Preparar uma carga é ação separada, que exige cumulativamente
   `aba.clientes`, `clientes.importar` e `clientes.importar_base_fiscal`. A nova
   permissão sensível não é concedida automaticamente a usuários existentes.
2. Preparação recebe novamente fonte e relatório revisado, conferindo os dois
   hashes apresentados na prévia. O servidor relê ambos, valida suas estruturas
   e consulta um snapshot cadastral somente leitura. Não confia em linhas ou
   contagens enviadas pelo navegador. Pendências, conflitos ou ausência de novas
   empresas impedem preparar. Ignoradas justificadas podem conservar pendências.
3. A preparação devolve a prévia atualizada para nova revisão, um token aleatório
   e prazo de 30 minutos. Token pertence ao usuário, à sessão autenticada e ao
   banco de destino; guarda somente hashes e assinatura da conferência, não
   arquivos ou linhas. Memória limitada a três tokens por usuário e trinta no
   processo. Reiniciar o processo invalida preparações, sem gravar cadastro.
4. A tela exige confirmação explícita após mostrar as contagens da preparação.
   Confirmar reenvia os dois arquivos e a expressão `IMPORTAR EMPRESAS`. O servidor
   revalida arquivos, hashes, sessão e permissões. A identidade do autor vem da
   sessão; nome, CNPJ, contagens e decisões enviados à parte não são autoridade.
5. Dentro de uma única transação de escrita, comparar novamente os CNPJs,
   ausências e revisões com a conferência aprovada. Cadastro novo, removido da
   seleção, alterado ou inativado invalida a preparação, inclusive quando seus
   valores visíveis voltam a coincidir mas a revisão mudou. Exigir nova revisão.
6. Incluir apenas empresas novas com nome, CNPJ e contato. Cadastros existentes
   ficam intactos; ocorrências ignoradas não apagam nada. Não atualizar ou reativar
   clientes, acessar o cofre, associar responsáveis, configurar carteira,
   características fiscais, obrigações ou gerar tarefas. Regime, sem movimento e
   responsável permanecem informações de origem para decisões futuras.
7. Inclusões, eventos de alteração e recibo imutável são atômicos. Registrar
   hashes, arquivos, aba/linha/células, valores originais e propostos, decisões,
   justificativas, autor e resultado. Erro em qualquer etapa desfaz toda a carga.
8. Um par de hashes de fonte e correções só gera uma carga, inclusive sob
   concorrência. Repetição devolve o recibo já gravado sem criar clientes ou
   eventos novamente, mesmo se o cadastro mudou após o sucesso. O índice único
   e a transação garantem isso independentemente do controle de clique da tela.
9. Troca de arquivo, sessão ou permissão invalida preparação na interface.
   Respostas antigas não reativam ações. Conflito/expiração pede nova preparação;
   falha de rede após confirmar informa resultado incerto e permite repetição
   idempotente. Nunca afirmar que nada foi gravado apenas por falha de transporte.
10. Uploads temporários são fechados e removidos em sucesso e erro. Respostas
    têm `Cache-Control: no-store`. A trilha geral contém apenas ação e contagens,
    sem dados de empresas, hashes ou nomes de arquivos. Nenhuma saída usa dados
    reais nos testes ou no repositório público.
11. Limpar prévia remove a seleção dos arquivos e os controles da confirmação,
    além de descartar a preparação no servidor pelo endpoint existente. Se a
    preparação estiver em trânsito, descartar seu token ao receber a resposta,
    sem reativar a tela. Repetição/expiração são terminais; falhas de comunicação,
    permissão ou sessão mantêm aviso e permitem nova tentativa. Não enviar o
    token com outra identidade nem interpretar 404 como descarte confirmado.
    Se a resposta se perder sem um token utilizável, informar que o cancelamento
    não pôde ser confirmado e aguardar expiração. Descarte não desfaz uma
    confirmação já enviada; nesse caso preservar aviso explícito ao operador.

## Fora de escopo

Atualização em lote de cadastros existentes, carga parcial, associação automática
por nome, importação de carteiras ou características, mudanças de regras fiscais,
notificações por e-mail e execução operacional em produção.
