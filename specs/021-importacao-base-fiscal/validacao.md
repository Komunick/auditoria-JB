# Validação

Concluída localmente em 30/10/2026. Somente dados sintéticos, sem acesso ao
Linear ou à produção, commit, push, merge ou deploy.

## Testes antes da implementação

- Importador: RED por módulo ausente; GREEN para inclusões, preservação de
  existentes, ignoradas justificadas, proveniência, snapshots e revisões.
- HTTP: RED por rota ausente; GREEN para autorização cumulativa, token preso a
  sessão/banco, expiração, limites, revalidação dos arquivos, descarte e limpeza.
- Interface: RED por ausência da preparação; GREEN para nova permissão,
  prévia atualizada, aceite explícito, duplo clique, recibo, falha de rede,
  troca de arquivos/sessão/permissões e respostas atrasadas.
- Contagens divergentes no retorno foram reproduzidas em RED e recusadas na UI.

## Integridade, concorrência e revisão

| Critério | Verificação | Resultado |
|---|---|---|
| Carga atômica | Falhas no segundo cliente, trilha e recibo | Rollback completo |
| Snapshot | Revisão, situação, ausência e CNPJ alterados | Confirmação recusada sem carga |
| Repetição | Duas confirmações concorrentes do mesmo par de hashes e retry posterior | Um recibo e nenhuma duplicação |
| Revisões concorrentes | Dois relatórios distintos disputando os mesmos novos CNPJs | Um sucesso; outro exige nova revisão |
| Autoridade após espera | Revogação/descarte durante abertura; expiração aguardando trava real SQLite | 403/410 e domínio sem alteração |
| Recibo imutável | UPDATE/DELETE e reabertura do banco | Operações recusadas; schema preservado |
| Construtor com falha | Migração lança erro após abrir conexão | Conexão fechada |
| Dados temporários | Arquivos em sucesso/erro, token só com metadados | Uploads removidos; sem linhas/arquivos no token |
| Menor privilégio | Ausência individual dos slugs, outra sessão, revogação e logout | Acesso recusado |
| Respostas | Auth, validação, erros de banco e falha interna | `no-store`, sem detalhes privados |

A revisão independente encontrou uma janela entre a checagem da autorização e
a aquisição da trava SQLite. Foi corrigida por callback injetada, executada
dentro de `BEGIN IMMEDIATE` antes de consultar o recibo ou incluir clientes.
O teste RED reproduziu a gravação indevida; o GREEN comprova sua recusa. Outra
correção fecha a conexão quando a construção do store falha. Re-revisão sem
outros achados acionáveis.

## Regressão final

Executados os **91** scripts `tests/test_*.py` com Python 3.11.9 do venv do
projeto e ambiente de dados descartável:

- **89 aprovados**, **2 pulados**, **0 falhas**.
- Pulados somente `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por motor
  Firebird opcional indisponível nesta máquina.
- Desktop/PySide6, Node, ferramentas anteriores e novas rotas/UI passaram.
- Manifestos do código e dos testes idênticos antes/depois: `changed_during_run=[]`.
- `git diff --check` aprovado; avisos de conversão LF/CRLF sem erro de diff.

Logs privados fora do Git:
`tmp/validacao-spec021-20261030-101644/` na pasta de trabalho.

## Navegador local

Servidor exclusivo em `127.0.0.1:8621`, pasta descartável e conta sintética.
Fonte com sete ocorrências e relatório com pendências bloquearam a preparação.
Após resolver as propostas, a tela apresentou quatro inclusões, duas empresas
existentes e uma ocorrência ignorada. Prévia e preparação conservaram o dump
lógico do cadastro. O botão de confirmar permaneceu desabilitado sem aceite.

A confirmação gerou recibo 1: **4 incluídas, 2 preservadas, 1 ignorada**. A lista
de Clientes passou de dois para seis registros. As duas empresas anteriores
conservaram suas revisões; as sete origens constam no recibo. Resultado no banco:
seis clientes, sete eventos de alteração, um recibo; `integrity_check=ok` e zero
violações de chaves estrangeiras. Carteira, características, tarefas, gerações,
segredos e certificados continuaram vazios. Console sem erros/avisos. Aba e
processos exclusivos de QA encerrados ao final.

Evidências privadas: `tmp/qa-spec021/aceite-navegador.json`, snapshots antes,
após prévias/preparação e depois da confirmação, e `confirmacao-local.png`.

## Limites e pendência local

Carga real não executada. A base precisa de aprovação do escritório e execução
autorizada. Carteira, responsáveis e características continuam fora deste
importador. Preparações expiram em 30 minutos ou no reinício do processo; os
arquivos originais e revisados devem ser mantidos pelo operador para conferência.

Dois bancos inteiramente sintéticos de uma reprodução ad hoc permaneceram em
uma pasta temporária do Windows após falha de limpeza. A revisão automática
bloqueou a remoção com motivo genérico `blocked by policy`; não houve contorno.
O caminho e os arquivos estão no registro privado
`tmp/pendencia-limpeza-spec021.txt`, fora do repositório. Isso não afeta o sistema,
a suíte final ou os bancos de produção.
