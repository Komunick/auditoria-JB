# Validação local, 05/11/2026

Base: `origin/dev` em `fbdb04f74f9bb67da5f4384406f09bf5402571fc`.
Branch local: `codex/025-smtp-explicito`.

## Evidências

- Teste novo falhou antes da implementação: contrato `smtp_env` inexistente.
- Teste do instalador falhou antes da opção administrativa existir.
- Suíte de 113 scripts: 111 aprovados, 2 pulados, nenhuma falha. Os pulados
  foram `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por ausência do motor
  Firebird embedded. `test_ui_smoke.py` passou no ambiente local.
- Hashes de fontes, testes, scripts do executor e frontend permaneceram iguais
  durante a suíte completa. Ambiente sem variáveis AUDITORIA herdadas, dados
  temporários e saída de cada teste guardada fora do Git.
- Na revisão final, dois testes adicionais reproduziram aceitação de arquivo
  SMTP dentro de um venv separado e erro não tratado de arquivo inexistente
  no instalador. Ambos foram corrigidos.
- Após esses ajustes finais, os cinco scripts `test_autodeploy.py`,
  `test_autodeploy_install.py`, `test_autodeploy_smtp.py`,
  `test_smtp_autenticacao.py` e `test_alertas_email.py` passaram novamente.
- `git diff --check` aprovado; o instalador também passou em `bash -n`.

## Contratos cobertos

- Modo padrão desligado, inclusive rejeição de variável SMTP vazia.
- Autorização explícita, seis variáveis completas e correspondência entre
  arquivo privado e processo. Valores extras, divergentes ou inválidos rejeitados.
- Portas/TLS, autenticação obrigatória, arquivo root 0600 e pasta root 0700;
  arquivo ausente, dono incorreto, symlink/hardlink e permissões abertas rejeitados.
- Separação na configuração de backup e caminho inacessível no sandbox.
- Instalador não inicia aplicação, runner ou timer; opção recusada em `enable`.
- Contexto TLS verifica hostname e certificado; login ocorre após STARTTLS.
- Falhas de TLS, autenticação, envio e encerramento não persistem segredo.
- Reservas SQLite impedem duplicação após falha e reabertura do banco;
  o teste anterior também cobre concorrência entre emissores.

## Limites

SMTP foi simulado e o servidor do teste legado escutou somente em loopback.
Não houve autenticação no provedor, e-mail real, instalação na arm07, reinício,
alteração de produção, commit, push, merge ou ação no Linear. Os contratos de
root/systemd foram simulados no Windows; a instalação Linux e o primeiro ciclo
real precisam de validação na manutenção futura.

O health check valida a configuração do processo, sem comprovar conectividade
ou entrega SMTP. A promoção futura será bloqueada pelo executor atual até a
instalação administrativa do novo pacote com OID revisado.
