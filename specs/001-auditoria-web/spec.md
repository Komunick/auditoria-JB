# Feature Specification: Auditoria Fiscal Web (port do desktop para site)

**Feature Branch**: `dev` (fases commitadas incrementalmente)

**Created**: 2026-07-14

**Status**: Draft

**Input**: User description: "transforme todo o sistema em um site, passará por diversas mudanças e ter que enviar o novo exe todas as vezes não é prático."

> **Decisões do dono (2026-07-14)**: arquivos entram por **upload no navegador**;
> **login simples por usuário**; roda no **servidor Windows da empresa** (rede
> interna). O core Python (parser SPED, XML NF-e, composição fiscal, correções,
> livros PDF, relatórios Excel, DANFE) é reaproveitado integralmente — a única
> reescrita é a camada de interface (PySide6 → navegador).

## User Scenarios & Testing

### US1 - Plataforma: login, tema e navegação (P1)

O usuário abre o site na rede interna, faz login com usuário/senha, e vê as
mesmas cinco ferramentas do desktop como páginas: Comparador SPED×SEFAZ,
Comparador SPED×SPED, Livro de Conferência, Extração de Itens e Auditoria de
Produtos. A identidade JB Fraga é mantida, com tema claro/escuro alternável e
preferência salva (padrão da casa em todos os sistemas).

**Cenários**: login válido entra e registra o usuário para auditoria; senha
errada não entra e não revela se o usuário existe; alternância de tema persiste
entre sessões; sem sessão, qualquer página/API redireciona ao login.

### US2 - Sessão de trabalho com upload (P1)

Em cada ferramenta, o usuário envia os arquivos de entrada pelo navegador:
SPED (.txt), XMLs de NF-e (múltiplos .xml e/ou .zip com pastas dentro —
ex.: o ano inteiro), relação SEFAZ (planilha) e cadastro de produtos, conforme
a ferramenta. O processamento roda no servidor com indicador de progresso; ao
concluir, a tela mostra os resultados. Uploads e resultados ficam numa "sessão
de trabalho" no servidor, retomável enquanto não for descartada.

**Cenários**: zip com subpastas de meses carrega todas as notas (dedup por
chave); arquivo inválido explica o erro sem derrubar a sessão; duas pessoas
trabalham ao mesmo tempo sem misturar arquivos (isolamento por sessão de
trabalho).

### US3 - Livro de Conferência Fiscal completo (P1)

Tudo que o desktop faz hoje, no navegador: tabela de notas (filtro
todas/pendentes/conferidas, busca), marcar conferida com observação, correções
de CFOP/CST/alíquota (individual e em lote, com trilha de auditoria),
composição fiscal da nota com **todas as células editáveis** (correções nos
campos fiscais; sobrescritas de texto persistentes nas demais — mesma regra do
desktop), DANFE em PDF, e geração de: Livro Fiscal (PDF), Relatório de
Inconsistências (PDF) e SPED corrigido (.txt) — todos consumindo correções e
sobrescritas (o PDF sai com os textos editados).

**Cenários**: correção em lote marca todas as notas com o valor; sobrescrita
aparece em itálico/destaque e no PDF; conferência/correções/sobrescritas
persistem no servidor e aparecem para qualquer usuário autorizado; SPED
corrigido baixa como arquivo.

### US4 - Comparadores e relatórios (P2)

Comparador SPED×SEFAZ e Comparador SPED×SPED com os mesmos parâmetros e
saídas do desktop (tabelas na tela + planilhas Excel para download).

### US5 - Extração de Itens e Auditoria de Produtos (P2)

Extração de itens para Excel e auditoria de produtos (cadastro, verificação,
correções e relatórios) com paridade de recursos do desktop.

### Edge cases

- Upload grande (SPED de dezenas de MB, milhares de XMLs): processamento em
  segundo plano com polling de status; limite configurável de tamanho.
- Sessão de trabalho expirada/descartada: telas avisam e pedem novo upload.
- Dois usuários corrigindo a mesma nota: última gravação vale, com trilha de
  auditoria identificando cada um (modelo atual do SQLite).
- Servidor reiniciado no meio de um processamento: job marcado como falho com
  mensagem clara; uploads preservados para reprocessar.
- PDFs/Excel são gerados em arquivos temporários por requisição e baixados —
  nunca gravados por cima dos de outro usuário.

## Requirements

- **FR-001** Login por usuário/senha (hash+salt no SQLite); primeiro acesso
  cria o admin via variável de ambiente ou tela de bootstrap; sessão por
  cookie assinado. O usuário logado assina conferências, correções e
  sobrescritas (substitui o `getpass.getuser()` do desktop).
- **FR-002** Tema claro/escuro JB Fraga com preferência persistida
  (localStorage + atributo no root), como nos demais sistemas da casa.
- **FR-003** Sessões de trabalho: upload de SPED/.txt, XMLs (.xml múltiplos ou
  .zip com subpastas) e demais insumos; armazenadas no servidor por ferramenta;
  lista/retomada/descarte. Dedup de notas por chave de acesso (regra atual).
- **FR-004** Processamentos rodam fora do ciclo de request (thread/job) com
  status consultável; resultados viram JSON para as tabelas da tela.
- **FR-005** Livro de Conferência: paridade total com o desktop (US3), usando
  os módulos existentes (`conferencia_store`, `correcoes`, `composicao_fiscal`,
  `livro_fiscal`, `livro_inconsistencias`, `sped_corrigido`, `danfe`) sem
  alterar a semântica fiscal.
- **FR-006** Downloads: Livro Fiscal PDF, Inconsistências PDF, SPED corrigido,
  planilhas Excel dos comparadores/extração/produtos, DANFE PDF por nota.
- **FR-007** Comparadores/Extração/Produtos: mesmos parâmetros e colunas do
  desktop (mapa de superfície na pasta desta spec).
- **FR-008** API JSON sob `/api/**` com autenticação obrigatória; frontend
  estático (HTML/CSS/JS puro, sem build) servido pelo mesmo servidor — padrão
  de manutenção da casa.
- **FR-009** Implantação: um processo Python (uvicorn) no servidor Windows;
  script `servidor.ps1` para iniciar; atualização = `git pull` + reiniciar.
  O exe desktop continua existindo até o site cobrir tudo (transição).
- **FR-010** O core (`src/auditoria_fiscal/core` e `ferramentas`) não ganha
  dependência de framework web; a camada web importa o core, nunca o
  contrário.

## Success Criteria

- **SC-001** Um auditor completa no navegador o ciclo do Livro de Conferência
  (upload → conferir → corrigir → editar composição → PDF com os textos
  editados) sem tocar no exe.
- **SC-002** Atualização do sistema = atualizar o servidor uma única vez;
  nenhuma distribuição de exe.
- **SC-003** As cinco ferramentas produzem, para os mesmos insumos, os mesmos
  PDFs/Excel/SPED que o desktop (validado com os testes existentes + fixtures).
- **SC-004** 100% das mutações (conferência, correção, sobrescrita) atribuídas
  ao usuário logado.
- **SC-005** Dois usuários simultâneos não interferem um no outro (sessões de
  trabalho isoladas; banco compartilhado apenas onde é a regra — conferência).

## Assumptions

- Rede interna confiável (mesmo pressuposto dos outros sistemas); HTTPS pode
  ser adicionado por proxy depois.
- SQLite (WAL) atende a equipe pequena; o banco passa a viver no servidor
  (`%LOCALAPPDATA%\AuditoriaFiscal` do usuário que roda o serviço ou pasta
  `dados/` do projeto — decisão no plano).
- Frontend sem framework/build (vanilla JS + fetch), espelhando o padrão dos
  sistemas da casa; tabelas grandes paginadas/virtualizadas quando necessário.
- Fases: P1 (US1-US3) primeiro; P2 (US4-US5) em seguida. O desktop continua
  funcionando durante a transição (mesmo repo, mesma lógica).
