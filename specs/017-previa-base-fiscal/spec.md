# Spec 017 — Conferência da base Fiscal

## Objetivo

Permitir revisar a base de empresas recebida antes da carga no cadastro e nas
carteiras. Continuação da gestão do escritório: clientes, tarefas e equipe.
O importador de senhas e o importador de carteira individual têm contratos
diferentes; esta entrega acrescenta uma conferência própria em Clientes.

## Decisões confirmadas

- Primeiro RESPONSAVEL da aba principal: responsável Fiscal do escritório.
- Segundo RESPONSAVEL: contato da empresa.
- ZERADAS: empresas sem movimento que continuam na carteira. Não significa
  inatividade, baixa nem dispensa de obrigação.
- Decisões particulares de atribuição provisória ficam na preparação privada,
  separadas do conteúdo original e fora do repositório público.

## Aceite

1. Em Clientes → Importar, quem possui `aba.clientes` e `clientes.importar`
   envia XLSX para uma prévia própria, explicitamente sem gravação cadastral.
2. Reconhecer o layout principal de seis colunas: A sem cabeçalho, B
   RESPONSAVEL, C EMPRESAS, D RESPONSAVEL, E ZERADAS ou CNPJ, F REGIME DA EMPRESA.
   Reconhecer a aba ZERADAS com A sem cabeçalho, B EMPRESA e C CNPJ. Comparação
   normaliza espaços, acentos e caixa. Cabeçalho nas primeiras dez linhas.
   Nenhuma inferência por aparência dos dados. Abas preenchidas desconhecidas
   ou cabeçalhos ambíguos são recusados; abas vazias podem ser ignoradas com aviso.
3. Ler todas as linhas úteis das abas reconhecidas, inclusive ocultas, com
   identidade aba+linha. Preservar duplicidades; informar grupos por CNPJ válido
   normalizado, inclusive entre abas. Colunas adicionais preenchidas são recusadas.
   Linha útil tem algum campo mapeado preenchido antes de propagar contato
   mesclado; a propagação nunca cria um registro em linha totalmente vazia.
4. CNPJ: validar 14 dígitos e DV; conservar informado separado do normalizado.
   Número inteiro positivo de 13 dígitos pode recuperar um zero inicial somente
   com máscara de CNPJ de 14 posições e DV válido. Booleanos, fracionários ou
   números longos não são documentos. Texto admite apenas dígitos ASCII e os
   separadores usuais (ponto, barra, hífen e espaço), em qualquer posição, antes
   de validar 14 dígitos e DV. Letras e outros sinais permanecem inválidos.
   Texto incompleto não é completado. Ausência, inválido e fórmula
   são pendências, não zero nem cadastro pronto. Não consultar titularidade.
5. Regime informado é preservado, com normalização apenas dos rótulos conhecidos
   Simples Nacional, Lucro Real e Lucro Presumido/Presumido. Desconhecido ou ausente
   permanece pendente. Responsável ausente permanece pendente, sem escolher usuário.
   `sem_movimento=true` somente no layout/aba ZERADAS; principal usa `null`,
   apesar de sua coluna E também se chamar ZERADAS.
6. Somente contato pode vir de mesclagem vertical dentro da área de dados,
   anotando célula de origem, intervalo e propagação. Mesclagens em outros campos
   relevantes ou fora da área são recusadas. Fórmulas nunca são executadas nem
   aceitas pelo valor em cache; o texto da fórmula não é devolvido na prévia.
7. Exibir contagens de linhas, CNPJs válidos distintos, documentos pendentes,
   grupos repetidos e linhas sem movimento. Filtros e busca mudam só as linhas
   exibidas. Mostrar responsável Fiscal, contato, regime, pendências e origem.
8. Estados de carregamento, erro, vazio e resultado distintos. Resposta antiga,
   troca de arquivo e encerramento/troca de sessão invalidam o resultado.
9. O upload temporário é apagado e fechado em sucesso ou erro. Nenhum token de
   confirmação, cliente, carteira, obrigação, cofre ou schema é criado/alterado.
   A trilha de uso existente registra apenas ação, resultado e contagem.
10. Manter importadores anteriores, permissões, temas e acesso por teclado.
    Testar parser, HTTP, UI e regressão com fixtures sintéticas antes do aceite.

## Limites

Aceita XLSX, até 20 MB, 10 mil linhas úteis no arquivo, 20 abas, 10.020 linhas
físicas e 32 colunas por aba. Limites físicos são conferidos antes da expansão
de células/mesclagens pelo parser de alto nível. Reutiliza a
validação segura do pacote antes de abrir com openpyxl. Sem dependências novas.
As referências cruzadas de duplicidade têm teto de 100 mil por arquivo,
calculado antes de materializar as listas. Acima disso a leitura é recusada
integralmente com mensagem explícita, evitando saída de tamanho quadrático.
Esta entrega revisa dados de origem; não executa saneamento, associações por nome,
deduplicação, carga real, geração de tarefas, merge ou implantação.
