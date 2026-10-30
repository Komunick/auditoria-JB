# Spec 020 — Correções e prévia de importação da Base Fiscal

## Objetivo

Receber as propostas preenchidas na aba Correções do relatório 019 e mostrar
o resultado de uma futura importação de empresas. A planilha original permanece
imutável e precisa acompanhar o relatório. Esta entrega não grava cadastros,
carteiras, características, tarefas nem decisões; não oferece confirmação de carga.

## Cenários e aceite

1. Depois da conferência da fonte, enviar o relatório corrigido e gerar uma
   prévia. O servidor exige `aba.clientes` e `clientes.importar`, relê a fonte e
   confere o SHA esperado e o SHA registrado no relatório. Sem confiança nas
   linhas ou contagens enviadas pelo navegador.
2. Aceitar os relatórios existentes da 019. Validar os 13 cabeçalhos de Correções,
   o conjunto completo de IDs e as seis colunas originais por ID. Linhas podem
   mudar de ordem; IDs ausentes, extras, repetidos ou originais alterados recusam
   o arquivo inteiro. Outras abas são material de consulta, nunca fonte da carga.
3. Proposta vazia preserva o valor original; texto preenchido propõe substituição.
   Não existe comando implícito para apagar um campo. Mostrar original, proposta,
   valor efetivo e célula de revisão. Nome/contato/responsável até 160 caracteres;
   observação até 2.000. CNPJ válido de 14 dígitos, sem completar zeros perdidos;
   regimes limitados aos reconhecidos pelo leitor. Erros de valor bloqueiam a
   linha e ficam explícitos; não substituem silenciosamente a proposta pelo original.
4. Decisões aceitas: vazio, `manter`, `ignorar` (comparação sem acento/caixa).
   Ignorar requer observação. Recalcular duplicidades pelo CNPJ efetivo, inclusive
   colisões criadas pelas correções. Para resolver um grupo é preciso exatamente
   uma ocorrência marcada manter e todas as demais ignorar com justificativa,
   se alguma delas for considerada para inclusão. Também é possível ignorar o
   grupo inteiro explicitamente, justificando cada ocorrência.
   Nenhuma fusão automática ou escolha pela ordem. Linhas ignoradas permanecem
   visíveis com origem e motivo; ignorar não exclui cadastro existente. Uma linha
   ignorada com decisão/justificativa válidas pode conservar dados pendentes,
   exibidos para conferência, sem exigir que o usuário invente dados para descartá-la.
5. Classificar cada linha em incluir, existente, conflito, pendente ou ignorar.
   Validar campos e fórmulas da fonte ainda não resolvidas. Coluna ausente em
   ZERADAS não vira campo faltante; sem movimento continua na carteira. Texto de
   responsável não cria vínculo de usuário; regime e sem movimento são propostas
   informativas, não características ou obrigações aplicadas.
6. Consultar somente colunas mínimas de clientes por CNPJ em conexão SQLite
   `mode=ro`, com snapshot consistente, sem inicializar store/migração nem acessar
   cofre. Banco inexistente é informado; banco existente ilegível/incompatível
   recusa a consulta. Nome/contato divergente ou cliente não ativo são conflitos;
   contato inexistente no layout e sem proposta preserva o valor cadastrado.
   cadastros coincidentes são existentes e não serão recriados. Sem atualização,
   reativação, associação por nome nem sobrescrita. A consulta é uma fotografia e
   teria de ser refeita antes de qualquer futura gravação.
7. Validar ambos os XLSX antes do leitor de alto nível; recusar macros, vínculos,
   XML hostil, fórmulas/erros na aba Correções, mesclagens ambíguas e limites
   excedidos. Até 20 MB por arquivo, 10 mil registros. A aba Origens pode ter
   cinco vezes esse número; dimensões declaradas não são autoridade. Fechar e
   remover uploads em sucesso e erro; resposta no-store, sem token persistente.
   Marcadores de erro preservados como texto nas colunas originais continuam
   aceitos quando idênticos à fonte; assim o usuário pode corrigir o documento
   sem adulterar seu histórico. Células efetivamente de erro/fórmula são recusadas.
8. Tela com instruções, contagens, busca/filtros/paginação e detalhes antes/depois,
   pendências, origem e confronto cadastral. Sem botão de importar/confirmar.
   Troca de arquivo, nova leitura, limpeza ou sessão/permissão invalida respostas
   antigas. Conteúdo de arquivos sempre tratado como texto, nunca HTML.
9. Trilha geral registra somente ação, resultado e contagem. Testes exclusivamente
   sintéticos demonstram ausência de alterações nos bancos cadastrais, tokens,
   schema e arquivos residuais; importadores anteriores continuam funcionando.

## Fora de escopo

Carga efetiva, persistência de decisões, associação de contas/carteiras, alterações
de regime no cadastro, novas obrigações, mudanças na produção, push, merge e deploy.
O relatório da 019 continua utilizável como documento de revisão; esta etapa só
adiciona interpretação das propostas e simulação da futura carga.
