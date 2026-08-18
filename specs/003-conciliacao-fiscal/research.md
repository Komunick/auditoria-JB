# Research: Conciliação Fiscal — Receita e DIMP

## R1 — Forma de integração

**Decision**: Implementar como sexta ferramenta nativa no FastAPI e frontend
estático do Auditoria-JB.

**Rationale**: O sistema já tem login, RBAC por aba/ação, auditoria, sessões,
jobs, downloads e registro modular de abas. O porte nativo preserva uma única
identidade, trilha, implantação, tema e processo.

**Alternatives considered**:

- **Flask em segunda porta**: rejeitado por duplicar autenticação, operação,
  backup e superfícies de segurança.
- **Iframe/reverse proxy**: rejeitado por manter dois estados e duas trilhas,
  além de criar problemas de cookie, navegação e UX.
- **Reescrever todo o Auditoria-JB**: fora de escopo e desnecessário.

## R2 — Uso opcional do protótipo

**Decision**: Reimplementar parser, validação, regras financeiras e exportação
conforme os contratos; quando o protótipo estiver disponível localmente, usar
suas partes puras somente como referência auxiliar. Reescrever store e rotas
para o padrão atual em todos os casos.

**Rationale**: O protótipo já validou regras contra as fontes reais, mas pode
não acompanhar o pacote enviado ao Claude e não é fonte de verdade. Os
contratos deste diretório devem permitir implementação independente.

**Descartar**: `app/__init__.py`, `routes.py`, templates Jinja, sessão/login,
Waitress, Docker separado, `current_app`, `g` e campos livres de ator.

## R3 — Modelo de versionamento

**Decision**: `CNPJ + competência` identifica a conciliação; cada fonte cria
uma versão. Existe uma versão vigente e podem existir candidatas.

**Rationale**: Retificações não podem sobrescrever evidência. O protótipo atual
guarda o candidato como JSON de conflito, o que não preserva movimentos e fatos
completos nem permite promovê-lo com segurança. Versão normalizada torna a
comparação e promoção explícitas.

**Alternatives considered**:

- **UNIQUE(cnpj,period) e candidato JSON**: suficiente para alerta simples,
  insuficiente para promoção, auditoria e proveniência completa.
- **Última importação vence**: rejeitado por risco fiscal.

## R4 — Dinheiro

**Decision**: `Decimal` com duas casas no domínio; centavos `INTEGER` no banco;
Decimal na saída Excel.

**Rationale**: Evita resíduos binários observados nos XLSX, mantém comparação e
soma exatas e segue a implementação validada do protótipo.

## R5 — Banco e arquivos

**Decision**: Banco `dados_web/conciliacao.db` e originais imutáveis em
`dados_web/conciliacao/origens/<sha256>.xlsx`.

**Rationale**: Sessões temporárias podem ser descartadas. Fonte fiscal precisa
permanecer junto da proveniência. Banco dedicado isola o domínio sem criar novo
serviço e continua incluído no backup de `dados_web`.

**Alternative**: guardar só em `sessoes/<id>` foi rejeitado porque a própria
documentação permite limpar essa pasta.

## R6 — Auditoria

**Decision**: Manter duas trilhas complementares.

- `auditoria_web.db/evento`: uso da aplicação, IP, HTTP e tentativas negadas.
- `conciliacao.db/evento_fiscal`: evento de domínio imutável e transacional.

**Rationale**: O middleware geral captura muito bem acesso e resultado, mas seu
registrador deliberadamente não derruba a funcionalidade se falhar. Uma decisão
fiscal exige atomicidade com a mudança de estado.

## R7 — Propriedade de sessões e jobs

**Decision**: Corrigir globalmente antes do módulo fiscal. `obter_sessao` recebe
o login esperado e, quando aplicável, a ferramenta; `obter_job` verifica a
sessão e proprietário. Recurso alheio responde como não encontrado.

**Rationale**: Hoje IDs têm alta entropia, mas são tratados como autorização.
Conhecer um ID permite a outro usuário autenticado consultar ou descartar o
recurso. O novo módulo não deve perpetuar isso, e a correção central protege as
cinco ferramentas.

## R8 — Processamento em segundo plano

**Decision**: Reusar jobs atuais, mantendo um worker Uvicorn. Persistir o
resultado por arquivo antes de o job ser marcado como concluído e tornar a
importação idempotente.

**Rationale**: É o padrão da aplicação e suficiente para a escala. Reinício
perde o objeto job, mas não pode perder resultado persistido nem deixar lote
eternamente em execução.

**Evolução possível**: fila persistente externa somente se escala ou múltiplos
workers forem necessários.

## R9 — Validação de XLSX

**Decision**: Validar o contêiner ZIP antes do openpyxl.

Verificações: estrutura mínima, extensão, número de entradas, tamanho total
descompactado, razão de compressão, nomes de caminhos, `vbaProject.bin` e
`xl/externalLinks/`.

**Rationale**: Extensão e MIME não provam que o arquivo é seguro. O upload ZIP
genérico do Auditoria-JB foi feito para XML/FDB e não é o contrato adequado
para XLSX fiscal.

## R10 — Campo histórico “cartão”

**Decision**: O nome canônico é `total_nao_pix`. O cálculo é `Total DIMP − PIX`.
No export legado, usar “Cartão/outros (não PIX)” enquanto houver necessidade de
compatibilidade.

**Rationale**: As fontes demonstram voucher, transferência e outras operações;
por exemplo, PLUXEE aparece como voucher. Rotular tudo como cartão é
semanticamente incorreto.

## R11 — Planilha-mestre

**Decision**: Um CNPJ por operação, somente versão vigente/aprovada por padrão.
Pendentes exigem permissão adicional; rejeitados nunca entram.

**Rationale**: O modelo fornecido representa uma empresa e blocos anuais.
Preencher múltiplos CNPJs silenciosamente criaria mistura fiscal.

## R12 — Frontend

**Decision**: Nova aba `conciliacao` com subtelas internas Visão geral,
Conciliações, Exceções e Exportar. Usar as primitivas atuais de API, jobs,
permissões, toast, confirmação e escape de HTML.

**Rationale**: Mantém o padrão sem framework/build e reduz código novo.

## R13 — Permissões padrão

**Decision**: Admin recebe tudo implicitamente. Usuário comum novo recebe
exatamente aba + importar; revisar, aprovar, resolver exceções, exportar,
preencher modelo e incluir pendentes ficam fora. Usuários existentes não são
alterados automaticamente.

**Rationale**: Menor privilégio e coerência com a política atual de que saídas
oficiais e mutações fiscais exigem liberação.

## R14 — Backup SQLite em WAL

**Decision**: Atualizar a documentação: copiar `dados_web` somente com o
servidor parado/checkpoint feito ou usar a API de backup do SQLite.

**Rationale**: Uma cópia de arquivos durante escrita em WAL pode não representar
um snapshot consistente. Implementar backup online é uma feature separada; esta
entrega não deve repetir uma garantia excessiva.

## R15 — Dados e testes

**Decision**: Versionar fixtures sintéticas representativas e um inventário
sanitizado da estrutura/classificação das amostras, não as planilhas, CNPJ,
razão social ou valores reais.

**Rationale**: Os relatórios contêm dados fiscais. Fixtures sintéticas permitem
CI e revisão; a comparação privada com os originais e a planilha-mestre permite
validação local explícita sem incorporar dados de cliente ao repositório.
