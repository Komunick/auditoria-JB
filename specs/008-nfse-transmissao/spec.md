# Feature Specification: Emissão de NFS-e — Fase 2 (transmissão à produção restrita)

**Feature Branch**: `008-nfse-transmissao`
**Criada em**: 16/10/2026
**Status**: implementada contra servidor falso; transmissão real depende do A1 (JB-1)
**Base**: spec 006 (Fase 1), "Fica para a Fase 2" do `plan.md` dela

## Resumo

A Fase 1 gera, na aprovação do lote, uma DPS por linha, validada no XSD e
**sem efeito fiscal**. Esta fase assina essas DPS com o certificado A1 da
escola e as transmite à **Sefin Nacional em produção restrita** (`tpAmb = 2`),
guarda a NFS-e devolvida e acompanha a situação de cada nota. Produção
(`tpAmb = 1`) continua fora: é a Fase 3, com autorização explícita.

Nada de produção restrita tem valor fiscal. Ela serve para provar, com o
certificado real, que o que o sistema monta é aceito pelo Sistema Nacional
antes de qualquer nota de verdade.

### Incluído

- Leitura do certificado A1 (`.pfx` + senha) enviado junto com o pedido de
  transmissão, conferido antes do envio (validade, CNPJ igual ao do perfil,
  uso para assinatura e autenticação de cliente). O certificado vive só na
  memória do processo enquanto o lote é transmitido e é descartado no fim.
- Assinatura XMLDSig de cada DPS no momento do envio.
- `POST /nfse` com mTLS, uma DPS por vez, num job em segundo plano.
- Situação por DPS: `gerada`, `enviando`, `autorizada`, `rejeitada`, `incerta`.
- Resultado incerto (tempo esgotado, erro 5xx, conexão caída) nunca é
  reenviado às cegas: antes, a DPS é consultada (`GET /dps/{id}`).
- Guarda da NFS-e devolvida (XML) e, quando disponível, do DANFSe (PDF).
- Trilha de cada tentativa com o XML assinado exatamente como foi enviado.
- Tela de transmissão no lote aprovado e downloads da NFS-e.
- Permissão nova `nfse.transmitir`, não concedida automaticamente.

### Fora do escopo

- Produção (`tpAmb = 1`) e devolução das notas à escola (Fase 3, JB-5).
- Guardar o A1 no servidor (depende de a escola autorizar, JB-1).
- Certificado A3 (exige assinador na máquina do usuário).
- Cancelamento, substituição e eventos (Fase 4, JB-7).
- Regerar a DPS com outra `dhEmi` (não é preciso: ver research.md, R-1).

## User Stories

### US1 — Transmitir um lote aprovado à produção restrita (P1)

Como JB, quero mandar as DPS de um lote aprovado para a produção restrita
com o certificado da escola, para ver cada uma virar NFS-e ou ser rejeitada
com o motivo oficial.

**Aceite**

1. Lote aprovado + `.pfx` válido do CNPJ do perfil + senha certa → um job
   transmite as DPS em ordem de número; cada autorizada guarda chave de
   acesso e XML da NFS-e.
2. Rejeição (HTTP 400) guarda os códigos e descrições oficiais e marca a DPS
   como `rejeitada`; as demais seguem.
3. Senha errada, arquivo que não é PKCS#12, certificado vencido, sem chave,
   de AC, ou de outro CNPJ → recusa antes de qualquer conexão, sem gravar nada.
4. Lote em revisão ou descartado → recusa.
5. Usuário sem `nfse.transmitir` → 403 (trilha registra a tentativa).
6. O certificado não fica em disco nem no banco; a trilha guarda só CNPJ,
   titular, validade e impressão digital.

### US2 — Nunca emitir duas vezes a mesma DPS (P1)

1. Tempo esgotado, 5xx ou conexão caída → DPS `incerta` e o job para (não
   insiste com o servidor fora).
2. Na transmissão seguinte, cada DPS `incerta` é consultada primeiro: se a
   NFS-e existe, é baixada e a DPS vira `autorizada` **sem novo envio**; se
   não existe, é enviada.
3. Rejeição E0014 (série e número já usados) → consulta e baixa a NFS-e
   existente.
4. DPS `enviando` há mais de 10 minutos (processo caiu no meio) conta como
   `incerta`.
5. Duas transmissões simultâneas do mesmo lote não mandam a mesma DPS duas
   vezes.

### US3 — Acompanhar e baixar (P2)

1. A tela do lote mostra a situação de cada DPS, a chave de acesso e o motivo
   da rejeição.
2. Download do XML da NFS-e e do DANFSe, marcados
   "PRODUCAO-RESTRITA-SEM-VALOR-FISCAL".
3. `rejeitada` só é reenviada se o pedido marcar "incluir rejeitadas" (a
   DPS é a mesma; reenviar só faz sentido depois de corrigir algo fora do
   sistema, como o cadastro no CNC).

### US4 — Proteger o que já foi emitido (P2)

1. Lote com DPS `autorizada`, `enviando` ou `incerta` não pode ser
   descartado (cancelamento é da Fase 4).

## Requisitos

- **FR-201**: Só `tpAmb = 2` e só hosts `*.producaorestrita.nfse.gov.br`
  (ou loopback, para os testes). Qualquer outro destino é recusado.
- **FR-202**: O `.pfx` chega no mesmo pedido da transmissão, tem no máximo
  50 KB, é lido em memória e descartado no fim do job. Para montar o TLS, a
  chave vai para um arquivo temporário **cifrado com senha aleatória**, numa
  pasta privada, apagado logo depois de carregado.
- **FR-203**: Antes de conectar: validade, CNPJ do certificado (OID
  2.16.76.1.3.3) igual ao do perfil, `KeyUsage` com assinatura digital,
  certificado que não é de AC. Falha = erro com código, nada gravado.
- **FR-204**: Assinatura XMLDSig envelopada sobre `infDPS` (research.md, R-3).
  O XML assinado continua válido no XSD oficial.
- **FR-205**: A DPS assinada vai compactada em gzip e em Base64 no campo
  `dpsXmlGZipB64` do JSON.
- **FR-206**: Cada tentativa é uma linha imutável com o XML assinado, o
  resultado, o HTTP, os erros/alertas oficiais, o certificado (sem segredo) e
  quem pediu. A situação da DPS e a tentativa mudam na mesma transação.
- **FR-207**: `autorizada` é terminal. A chave de acesso é única.
- **FR-208**: 403 da Sefin (certificado de transmissão) ou resultado incerto
  interrompem o job; as DPS que faltavam continuam como estavam.
- **FR-209**: O servidor da Sefin é verificado pelos CAs do sistema, com
  bundle extra opcional (`AUDITORIA_NFSE_CA_EXTRA`). A verificação não pode
  ser desligada.
- **FR-210**: Nenhum dado do certificado nem da NFS-e vai para a trilha geral
  além de IDs e contagens.

## Critérios de sucesso

- **SC-201**: Com o servidor falso, um lote de 3 DPS vira 3 NFS-e, e a
  assinatura de cada uma confere com o certificado.
- **SC-202**: Depois de um 500 e de um tempo esgotado, a nova transmissão não
  gera segundo `POST` para a DPS que já tinha virado nota.
- **SC-203**: Toda a suíte existente continua passando.
- **SC-204**: Primeira transmissão real (quando houver A1): pelo menos uma DPS
  autorizada em produção restrita. **Não verificável sem o certificado.**

## Pendências

| # | O quê | Efeito |
|---|---|---|
| JB-1 | A1 da escola e a senha; a escola autoriza guardar? | Sem ele não há transmissão real (SC-204). Guardar fica fora desta fase |
| R-3 | Algoritmo da assinatura: SHA-256 (padrão aqui) ou SHA-1 | Fontes divergem; trocar é uma variável de ambiente. Confirmar na 1ª transmissão |
| R-5 | Endereço do DANFSe na produção restrita | Download do PDF é tentativa; falha não muda a situação da nota |
| R-6 | Campos exatos do JSON de erro | Leitura tolerante a maiúsculas e variações; confirmar na 1ª rejeição real |
| JB-10 | Jira (AJB-1) ou Linear | Nome do PR |
