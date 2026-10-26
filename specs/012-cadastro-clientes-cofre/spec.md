# Feature Specification: Cadastro de Clientes, Cofre de Senhas e Vencimentos

**Feature Branch**: `012-cadastro-clientes-cofre`

**Created**: 2026-10-22

**Status**: Implementada em 26/10/2026 com os valores padrão da seção "Pendências" (o que depende de resposta ficou configurável ou fora); esperando a revisão do dono

**Input**: três áudios da JB Fraga de 22/10/2026 e a planilha de senhas que a
equipe usa hoje. Pedidos, nas palavras dos áudios: "incluir aquela lista de
clientes [...] aquela planilha, com senhas", "fazer o controle de certificados
digitais [...] a validade, que nos avise [...] os certificados que vão vencer" e
"criar um sistema para a gente fazer aquele banco de dados, que na planilha
está muito feia". Decisão do dono (22/10/2026): **as senhas ficam no próprio
sistema, criptografadas, com permissão e registro de quem consultou**.

O terceiro pedido dos áudios — o teste de emissão de NFS-e — já tem a aba 8 e
as specs 006/008; não faz parte desta.

## Objetivo e escopo

Criar a **nona ferramenta** do Auditoria-JB, "9. Clientes", que substitui a
planilha de senhas: um cadastro único dos clientes da contabilidade, com as
inscrições, as senhas de portais guardadas num cofre criptografado e um painel
de vencimentos que avisa antes de um certificado digital (ou, se confirmado,
uma licença municipal) vencer.

Mesmo endereço, login, permissões, histórico e padrão visual das oito
ferramentas existentes. Nenhum processo, porta ou serviço novo.

### O que a planilha atual tem (lida em 22/10/2026, só a estrutura)

A leitura foi feita sem exibir nenhuma senha; os números abaixo são
contagens. A planilha real **nunca** entra no repositório (que é público) nem
nos testes.

- Uma aba, cerca de 750 clientes (uma linha por cliente), cabeçalho na
  linha 2, filtro em A2:N753, três linhas ocultas.
- Colunas com cabeçalho: nome (A, sem rótulo), CNPJ, inscrição estadual,
  inscrição municipal, **senha SEFAZ estadual**, **senha Prefeitura**, IPTU,
  TVL, vencimento da TVL, vencimento do alvará, **código de acesso**,
  publicidade, alvará saúde e legenda (O).
- Duas colunas sem cabeçalho com conteúdo: N (65 valores curtos) e P (49
  "RENOVAR" e 14 valores curtos). **A JB confirmou em 23/10/2026 que não
  têm nada de útil**: a importação as ignora.
- **A situação do cliente está na cor da linha**, não num campo. Legenda:
  vermelho = baixada, laranja = inativa, cinza = não é cliente, rosa-claro =
  Lauro de Freitas (município, não situação). Cerca de 60 linhas usam cores
  fora da legenda — pendência P-06.
- Campos misturam valor e situação: "NÃO TEM", "PENDENTE", "AGUARDANDO
  CERTIFICADO", "DEFINITIVO" (TVL), "VENCIDO"/"OK"/"RENOVANDO" (alvará saúde),
  com variações de grafia ("NAO TEM", "DEFFINITIVO", "PENTENDE").
- CNPJ gravado como número (perde zeros à esquerda); 8 CNPJs repetidos;
  algumas datas impossíveis (ano 2878).
- **Não há coluna de certificado digital.** O certificado só aparece como
  motivo de senha pendente ("AGUARDANDO CERTIFICADO", "NÃO TEM
  CERTIFICADO"). Os dados de certificado vêm da pasta descrita abaixo.

### Onde estão os certificados hoje (fotos e áudio da JB, 22/10/2026)

- Pasta compartilhada do servidor de arquivos da JB, na rede do escritório:
  `Public\CERTIFICADOS DIGITAIS ATUALIZADOS`, com **uma subpasta por
  cliente**, nomeada pela razão social ou pelo nome do responsável.
- Em cada subpasta, em geral: o certificado A1 (`.pfx`), a chave privada
  (`.key`) e um texto `_info` com razão social, nome fantasia, CNPJ,
  **validade** e **a senha do certificado em texto aberto**. Algumas têm
  lixo de sistema (`GPUCache`).
- O `_info` é digitado à mão: a validade dele pode estar desatualizada em
  relação ao certificado. No exemplo fotografado, a validade era de 2023.
- Pedido do áudio: hoje "tem essa informação [...] onde tem a gente vai
  colocar na validade", "porém eu queria um controle maior [...] acompanhar a
  validade desses ativos".
- **Observação de segurança (fora do escopo, a repassar à JB):** uma pasta
  chamada `Public` guarda chaves privadas e senhas de certificados em texto
  aberto. Qualquer pessoa ou programa com acesso à rede do escritório pode
  copiar os certificados e assinar em nome dos clientes. Restringir o
  compartilhamento só a quem precisa é urgente, com ou sem este sistema.
- Há formatação condicional que pinta de vermelho datas da semana seguinte em
  poucas células: a equipe já tentou montar o aviso de vencimento na planilha.

### Incluído

- Cadastro de clientes: identificação, inscrições, município, situação e
  observações.
- Importação da planilha atual com **tela de conferência** antes de gravar.
- Cofre de senhas por cliente (SEFAZ estadual, Prefeitura, código de acesso e
  outros portais), criptografado, com permissão própria e trilha de consulta.
- Cadastro de certificados digitais por cliente, com validade.
- Painel de vencimentos com faixas de antecedência e aviso dentro do sistema.
- Exportação do cadastro em Excel **sem** nenhuma senha.
- Controle de acesso e auditoria integrados ao Auditoria-JB.

### Fora do escopo inicial

- Aviso por e-mail ou WhatsApp (o sistema não tem envio de e-mail hoje;
  depende de SMTP — pendência P-03).
- Guardar o arquivo do certificado (.pfx/.cer) no sistema. A v1 guarda só os
  dados do certificado; o arquivo continua onde está hoje.
- Ler a pasta de rede direto do servidor: ele roda fora da rede da JB (VM
  na nuvem) e não a alcança. A leitura é feita pelo **coletor local** (US8),
  rodado num computador do escritório.
- Login automático nos portais com a senha guardada.
- Licenças municipais (alvará, TVL, alvará saúde, publicidade) no painel de
  vencimentos: a planilha já traz essas datas, mas o pedido falou de
  certificados. Entram só se o dono confirmar — pendência P-07. Os dados são
  importados de qualquer forma, para não se perderem.

## User Scenarios & Testing

Testes automatizados são obrigatórios para todas as histórias P1 e para os
casos de autorização, criptografia, importação e exportação. Fixtures são
**sintéticas**: nomes, CNPJs e senhas inventados.

### User Story 1 — Acessar a nona ferramenta com segurança (P1)

Como usuário autorizado, quero abrir "9. Clientes" no mesmo Auditoria-JB.

**Independent Test**: usuário com `aba.clientes` abre a aba; usuário sem ela
não vê o botão e recebe 403 em chamada direta, com a tentativa auditada.

**Acceptance Scenarios**:

1. Usuário com acesso vê a ferramenta e consegue abri-la.
2. Usuário sem acesso não vê a aba nem obtém dados por chamada direta.
3. Permissão retirada durante a sessão vale na operação seguinte.
4. `aba.clientes` **não** dá acesso a senha nenhuma (ver US4).

### User Story 2 — Manter o cadastro de clientes (P1)

Como atendente, quero consultar e corrigir os dados de um cliente num lugar
só, em vez de procurar na planilha.

**Independent Test**: cadastrar, editar e mudar a situação de um cliente,
conferindo validação do CNPJ, histórico das alterações e busca.

**Acceptance Scenarios**:

1. Cliente tem nome, CNPJ ou CPF (validados pelo dígito verificador, guardados
   só com dígitos e exibidos formatados), inscrição estadual, inscrição
   municipal, município, inscrição do IPTU, situação e observações.
2. Cada inscrição aceita um valor **ou** uma situação — "não tem", "pendente",
   "baixada" — nunca os dois misturados num texto livre.
3. Situação do cliente: ativo, inativo, baixado ou não é mais cliente.
   Mudar a situação exige motivo e não apaga nada.
4. Busca por nome, CNPJ ou inscrição; filtro por situação e município.
5. CNPJ repetido é recusado, salvo se o dono decidir que filiais e matriz
   compartilham o cadastro (pendência P-08).
6. Toda alteração grava autor (da sessão), data/hora, campo, valor anterior e
   novo, na mesma transação.
7. Excluir cliente não existe; o que existe é mudar a situação.

### User Story 3 — Importar a planilha atual com conferência (P1)

Como administrador, quero trazer os clientes da planilha sem redigitar e sem
importar lixo.

**Independent Test**: importar uma planilha sintética com os mesmos defeitos
da real (CNPJ numérico, cores, "NÃO TEM", datas impossíveis, duplicados,
linhas ocultas) e conferir o relatório da conferência e o resultado gravado.

**Acceptance Scenarios**:

1. O arquivo é validado antes do openpyxl (tamanho, tipo, zip seguro), como
   nos demais uploads.
2. A importação gera uma **prévia**, sem gravar nada: por linha, o que vai
   ser criado, o que foi normalizado e o que exige decisão.
3. Normalizações mostradas na prévia: CNPJ numérico vira 14 dígitos com zeros
   à esquerda; cor da linha vira situação pela legenda; rosa-claro vira
   município "Lauro de Freitas"; "NÃO TEM", "PENDENTE" e variações de grafia
   viram situação do campo; data impossível vira "data inválida — revisar".
4. Vão para "exige decisão": CNPJ com dígito verificador inválido, CNPJ
   repetido, cor fora da legenda, linha oculta, valor em coluna sem cabeçalho
   e data impossível.
5. Nada é gravado até o administrador confirmar. A confirmação grava tudo
   numa transação; falha no meio desfaz tudo.
6. As senhas da planilha são cifradas **antes** de tocar o disco. A prévia
   mostra só "senha presente" ou "ausente", nunca o valor. O arquivo enviado e
   qualquer área temporária com texto aberto são apagados ao fim, com sucesso
   ou erro.
7. Cada valor importado registra a origem (hash do arquivo, linha e coluna),
   conforme o princípio I da constituição; o arquivo em si não é guardado.
8. Importar o mesmo arquivo de novo não duplica clientes: casa pelo CNPJ e
   mostra o que mudaria.

### User Story 4 — Consultar uma senha com segurança (P1)

Como atendente autorizado, quero ver a senha do portal de um cliente quando
preciso dela, e o escritório quer saber quem viu o quê.

**Independent Test**: com e sem a permissão, revelar uma senha; conferir 403
sem permissão, o registro na trilha com permissão e que o valor não aparece em
lista, exportação, log nem resposta de outras rotas.

**Acceptance Scenarios**:

1. Na ficha do cliente as senhas aparecem mascaradas, com a indicação de
   presença e a data da última alteração. A lista de clientes nunca traz
   senha.
2. Revelar exige `cofre.ver` e é um pedido próprio, por cliente e por campo
   (uma senha por vez). Não há rota que devolva várias senhas.
3. Cada revelação grava na trilha: quem, quando, cliente, qual campo e IP —
   na mesma transação da leitura. O valor nunca vai para a trilha.
4. O valor revelado some da tela sozinho depois de 30 segundos e há botão de
   copiar.
5. Proposta (pendência P-04): antes da primeira revelação da sessão, e
   depois a cada 15 minutos, o sistema pede a senha do próprio usuário de
   novo.
6. Limite de revelações por usuário (proposta: 30 por hora). Acima disso
   responde 429 e registra o bloqueio.
7. O administrador consulta o relatório "quem consultou senhas", com filtro
   por usuário, cliente e período.
8. Exportação em Excel, impressão e qualquer relatório **nunca** incluem
   senha.

### User Story 5 — Cadastrar e trocar senhas (P1)

Como atendente autorizado, quero atualizar a senha quando o cliente ou o
portal a muda.

**Independent Test**: gravar, trocar e remover uma senha; conferir que o banco
guarda só o texto cifrado e que a trilha registra a troca sem o valor.

**Acceptance Scenarios**:

1. Gravar ou trocar exige `cofre.editar`. Quem só tem `cofre.ver` não altera.
2. Campos do cofre: senha SEFAZ estadual, senha Prefeitura, código de acesso
   e "outro portal" (nome do portal + usuário + senha), quantos forem
   precisos.
3. A troca grava autor, data/hora, cliente e campo; o valor anterior **não**
   fica guardado.
4. Cada campo pode estar como "pendente", "aguardando certificado" ou "não
   tem", sem valor, para não se perder a informação que a planilha guarda
   hoje.

### User Story 6 — Controlar os certificados digitais (P1)

Como responsável, quero cadastrar os certificados digitais dos clientes e
saber quais vão vencer.

**Independent Test**: cadastrar certificados com validades em diversas faixas
e conferir a classificação no painel e no cálculo dos dias restantes.

**Acceptance Scenarios**:

1. Certificado pertence a um cliente e tem: tipo (A1, A3 ou outro), titular
   (CNPJ ou CPF), autoridade certificadora, início e fim da validade, número
   de série, onde está guardado (texto livre, por exemplo o caminho na rede) e
   observação.
2. Um cliente pode ter mais de um certificado (e-CNPJ, e-CPF do sócio).
3. Os dados podem ser digitados ou lidos de um arquivo enviado: `.cer` (sem
   senha) ou `.pfx` com a senha. O arquivo e a senha do `.pfx` ficam só na
   memória do pedido e são descartados; nada é guardado além dos dados lidos.
4. Renovar cria um certificado novo e marca o anterior como substituído; o
   histórico fica.
5. Certificado vencido continua listado como vencido até ser substituído ou
   marcado como "não renovar".
6. Cada certificado mostra a origem dos dados: digitado, lido do arquivo ou
   trazido pelo coletor (com a data da coleta).

### User Story 7 — Ser avisado antes do vencimento (P1)

Como equipe, queremos saber com antecedência o que vai vencer, sem precisar
lembrar de olhar.

**Independent Test**: com o relógio fixo nos testes, conferir as faixas,
o aviso no topo e a ordenação do painel.

**Acceptance Scenarios**:

1. Painel "Vencimentos" com as faixas: vencido, vence em até 15 dias, até 20
   e até 30. Os prazos são configuráveis pelo administrador; os valores
   iniciais esperam a confirmação da JB (pendência P-02).
2. Ao entrar no sistema, quem tem `aba.clientes` vê um aviso no topo com a
   quantidade de itens vencidos e a vencer na faixa mais curta.
3. O painel ordena pelo mais urgente e filtra por faixa, tipo e cliente.
4. Marcar "renovação em andamento" tira o item do aviso no topo, mas não do
   painel; a marcação tem autor e data.
5. O fuso usado para "hoje" é America/Bahia, o mesmo do servidor.

### User Story 8 — Trazer os certificados da pasta da rede (P1)

Como administrador, quero carregar de uma vez os certificados que já estão na
pasta do escritório, com a validade **real** de cada um, sem digitar.

**Independent Test**: rodar o coletor numa pasta sintética com os casos
abaixo e importar o resultado, conferindo o relatório e o que foi gravado.

**Acceptance Scenarios**:

1. O coletor é um comando de linha do próprio repositório, rodado à mão num
   computador do escritório com acesso à pasta. Não é serviço, não abre porta
   e não fica rodando.
2. Para cada subpasta, ele lê o `_info`, abre o `.pfx` com a senha do `_info`
   e tira do certificado: titular (CNPJ/CPF e nome), AC, início e fim da
   validade e número de série.
3. O resultado é um arquivo de coleta com esses dados, o nome da subpasta e
   o hash do `.pfx`. **Não leva** o `.pfx`, a chave privada nem a senha
   (salvo decisão contrária na pendência P-13).
4. O relatório aponta, por subpasta: sem `.pfx`; `.pfx` que não abre com a
   senha do `_info`; sem `_info`; validade do `_info` diferente da do
   certificado; CNPJ do `_info` diferente do certificado; mais de um `.pfx`.
5. O arquivo de coleta é enviado na aba 9 e passa pela mesma prévia da US3:
   casa cada certificado com o cliente **pelo CNPJ do certificado** (não pelo
   nome da pasta) e mostra os que não casam.
6. Coletar de novo não duplica: o mesmo número de série atualiza a coleta;
   série nova para o mesmo cliente vira renovação (US6).
7. A validade que vale no sistema é a do certificado. A do `_info` só aparece
   como divergência, para a equipe corrigir o texto se quiser.

### Edge Cases

- Chave do cofre ausente ou inválida na partida: o cofre fica **indisponível**
  com mensagem clara, e o resto do sistema funciona. Nunca há modo "sem
  criptografia".
- Chave errada (texto cifrado não confere): erro explícito, sem devolver
  lixo, e registro na trilha técnica.
- Duas pessoas editando o mesmo cliente: a segunda recebe conflito, não
  sobrescreve.
- Senha com espaços, acentos ou começando por `=`: guardada exatamente como
  digitada; na tela, nunca interpretada como HTML.
- Cliente baixado: ficha e senhas continuam consultáveis por quem tem
  permissão; certificado de cliente baixado sai do aviso.
- `.pfx` com senha errada ou arquivo corrompido: erro claro, nada gravado.
- Importação interrompida: nada parcial gravado e nenhum texto aberto
  esquecido em disco.
- `_info` com formato diferente (rótulos em outra ordem, sem acento, linha
  em branco): o coletor reconhece pelos rótulos, não pela posição; o que não
  reconhece vai para o relatório.
- Certificado A3 (token ou cartão) não tem `.pfx`: aparece como "sem
  arquivo" e é cadastrado à mão.

## Requirements

### Functional Requirements

- **FR-001**: O sistema DEVE oferecer a ferramenta "9. Clientes" atrás da
  permissão `aba.clientes`.
- **FR-002**: O sistema DEVE validar CNPJ e CPF pelo dígito verificador e
  guardá-los só com dígitos.
- **FR-003**: O sistema DEVE separar, em cada inscrição e senha, o valor da
  situação do campo (não tem, pendente, aguardando certificado, baixada).
- **FR-004**: O sistema DEVE importar a planilha com prévia, decisões por linha
  e gravação numa única transação, sem guardar o arquivo enviado.
- **FR-005**: O sistema DEVE cifrar cada senha com AES-256-GCM, nonce único por
  gravação e dados associados (cliente + campo) que impeçam trocar o texto
  cifrado de lugar.
- **FR-006**: A chave DEVE vir de variável de ambiente
  (`AUDITORIA_COFRE_CHAVE`), nunca do banco, do Git ou de arquivo dentro da
  pasta de dados; cada texto cifrado DEVE registrar a versão da chave, para
  permitir troca de chave sem perder senhas.
- **FR-007**: Revelar senha DEVE exigir `cofre.ver`, ser um pedido por campo e
  gravar o registro de acesso na mesma transação.
- **FR-008**: Gravar ou trocar senha DEVE exigir `cofre.editar`.
- **FR-009**: Nenhuma rota, exportação, log ou mensagem de erro DEVE conter
  senha em texto aberto, salvo a resposta da revelação.
- **FR-010**: O sistema DEVE limitar a quantidade de revelações por usuário e
  período.
- **FR-011**: O sistema DEVE manter certificados por cliente com validade e
  histórico de renovação.
- **FR-012**: O sistema DEVE ler validade, titular, AC e número de série de
  `.cer` ou `.pfx` enviado, sem guardar o arquivo nem a senha.
- **FR-013**: O sistema DEVE classificar vencimentos em faixas configuráveis e
  mostrar o aviso no topo para quem tem `aba.clientes`.
- **FR-014**: Toda mutação DEVE registrar autor da sessão, data/hora e valores
  anterior e novo (exceto senhas), na mesma transação.
- **FR-015**: A exportação em Excel DEVE usar `core/planilha_segura.py` e não
  conter senhas.
- **FR-016**: O sistema DEVE oferecer um coletor de linha de comando que lê a
  pasta de certificados e gera um arquivo de coleta sem `.pfx`, chave privada
  nem senha.
- **FR-017**: A importação da coleta DEVE casar certificado e cliente pelo
  CNPJ do certificado e apontar divergências com o `_info`.

### Permissões novas

| Slug | Rótulo | O que libera |
|---|---|---|
| `aba.clientes` | 9. Clientes | Abrir a aba, ver cadastro, certificados e vencimentos |
| `clientes.editar` | Editar clientes e certificados | Criar e alterar cliente e certificado |
| `clientes.importar` | Importar planilha de clientes | Prévia e confirmação da importação |
| `cofre.ver` | Ver senhas de clientes | Revelar uma senha por vez, com registro |
| `cofre.editar` | Gravar e trocar senhas | Alterar o cofre |
| `clientes.exportar` | Exportar o cadastro | Baixar o Excel (nunca traz senha) |
| `vencimentos.configurar` | Configurar prazos de aviso | Mudar as faixas |

Como manda o princípio III, nenhuma dessas é dada automaticamente a usuário
existente. Administradores as têm de forma implícita, o que inclui
`cofre.ver` — pendência P-04 pergunta se o dono quer exceção a isso.

### Key Entities

- **Cliente**: identificação, documento, inscrições (valor + situação),
  município, situação, observações, origem da importação.
- **Segredo do cliente**: cliente, tipo do campo, nome do portal e usuário
  (quando "outro"), texto cifrado, nonce, versão da chave, situação do campo,
  autor e data da última alteração.
- **Acesso ao cofre**: usuário, cliente, campo, data/hora, IP, resultado
  (revelado, negado, bloqueado por limite).
- **Certificado**: cliente, tipo, titular, AC, validade, série, local de
  guarda, situação (vigente, substituído, não renovar), certificado que o
  substituiu.
- **Licença municipal** (importada; painel depende de P-07): cliente, tipo
  (TVL, alvará, alvará saúde, publicidade), número, vencimento ou situação
  ("definitivo", "não tem").
- **Importação**: hash do arquivo, autor, data, contagens por resultado e
  decisões tomadas — sem o conteúdo.
- **Alteração**: trilha de mutações do cadastro.

Banco próprio `dados_web/clientes.db`, como `patrimonio.db` e `nfse.db`:
ciclo de vida, trilha e backup próprios. Schema aditivo e idempotente.

## Segurança e operação

- O repositório é público: nenhum dado real em fixture, exemplo, captura ou
  descrição de PR.
- A **chave do cofre e o backup do banco não podem ficar juntos**: backup de
  `clientes.db` sem a chave é inútil para quem o roubar; chave perdida
  significa senhas perdidas. Guardar a chave num lugar à parte, conhecido pelo
  dono (pendência P-10).
- Na VM, a chave entra pelo drop-in do systemd, como as variáveis do
  endurecimento de segurança; o deploy é do dono.
- Dependência nova: `cryptography` (a mesma que o PR #6 já traz).
- Depois da importação confirmada, a planilha original deve sair de
  circulação (pastas compartilhadas, e-mail, Downloads) — decisão da JB
  (pendência P-09).

## Success Criteria

- **SC-001**: Os clientes da planilha estão no sistema, com cada linha
  importada, descartada ou decidida — nenhuma ignorada em silêncio.
- **SC-002**: Nenhuma senha em texto aberto no banco, nos logs, nas
  exportações ou na pasta de dados (teste procura os valores sintéticos em
  todos os arquivos gerados).
- **SC-003**: Toda revelação de senha aparece no relatório de acessos.
- **SC-004**: Um certificado que vence dentro da faixa configurada aparece no
  aviso do topo no mesmo dia.
- **SC-005**: A suíte existente continua passando, mais os testes novos.

## Pendências (perguntas à JB e ao dono)

**Como ficou enquanto não há resposta (26/10/2026):** P-02 — faixas 15/20/30,
configuráveis na tela; P-03 — só aviso dentro do sistema; P-04 — administrador
vê (regra atual), confirmação da própria senha e limite de 30/hora ligados;
P-06 — cor fora da legenda entra como ativo com pendência; P-07 — licenças
importadas e visíveis na ficha, fora do painel; P-08 — a primeira linha do
CNPJ entra e as seguintes vêm para ignorar; P-09/P-10 — documentado no
README-servidor; P-11 — rótulo "Código de acesso"; P-13 — a coleta não leva
a senha do certificado; P-14 — só "renovação em andamento" e "não renovar".
Uma resposta diferente muda configuração ou um trecho pequeno, não a estrutura.


- ~~**P-01**: O que são as colunas N e P.~~ Respondida em 23/10/2026: não têm
  nada; a importação ignora.
- **P-02**: Prazos do aviso. A transcrição do áudio ficou ambígua; a proposta
  é 30, 20 e 15 dias antes. Confirmar.
- **P-03**: Aviso só dentro do sistema na v1, ou o e-mail é indispensável? Se
  for, qual conta de envio.
- **P-04**: Quem pode ver senhas. Administrador vê por padrão (regra atual do
  sistema) — o dono quer exceção? Aprova pedir a senha do usuário de novo
  antes de revelar e o limite de 30 por hora?
- **P-05**: ~~Onde estão os certificados.~~ Respondida em 22/10/2026 (pasta
  da rede, uma subpasta por cliente). Falta saber: há certificado A3 (token ou
  cartão)? E quem vai rodar o coletor no escritório?
- **P-06**: O que significam as cores fora da legenda (cerca de 60 linhas).
- **P-07**: Alvará, TVL, alvará saúde e publicidade entram no painel de
  vencimentos? "DEFINITIVO" na TVL quer dizer que não vence?
- **P-08**: Os 8 CNPJs repetidos são erro ou matriz/filial que deve ficar
  junta?
- **P-09**: O que fazer com a planilha original depois da importação.
- **P-10**: Quem guarda a cópia da chave do cofre, e onde.
- **P-11**: "Código de acesso" é o do Simples Nacional? (Define o rótulo e a
  ajuda na tela.)
- ~~**P-12**: O que significa "RENOVAR" na coluna P.~~ Respondida junto com
  a P-01.
- **P-13**: A **senha do certificado** também vai para o cofre? A aba 8 (NFS-e)
  pede o `.pfx` e a senha a cada envio; com a senha no cofre, quem tem
  `cofre.ver` a consulta em vez de abrir o `_info`. Se sim, o coletor passa a
  levar a senha, cifrada no envio.
- **P-14**: O que mais é o "controle maior" do áudio? Proposta: responsável
  pela renovação de cada certificado, situação da renovação (avisado o
  cliente, comprado, instalado) e histórico. Confirmar o que a JB espera.
