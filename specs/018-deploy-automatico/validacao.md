# Validação — spec 018

Em preparação em 28/10/2026. Resultados finais de publicação e ativação serão
registrados após observação; este documento não presume ativação.

| Critério | Verificação | Resultado atual |
|---|---|---|
| Instalador antes da implementação | RED por arquivo ausente; testes sintéticos de host, unit, conta, caminhos e configuração | GREEN |
| Pacote de controle aprovado | Digest calculado sem Git privilegiado, comparado com árvore Git de fixture | GREEN |
| Ativação separada | Comandos simulados: install não habilita timer; enable exige check aprovado | GREEN |
| Sintaxe | bash -n e git diff --check | Aprovado |
| Executor antes da implementação | RED por módulo ausente; testes de etapas, falhas e interrupção | GREEN após correções da revisão |
| Isolamento Linux real | Unit transitória com UID sem privilégios, NoNewPrivileges, capabilities vazias, rede privada, home protegido e bind somente leitura do venv | Aprovado |
| Units no sistema real | systemd-analyze verify das units copiadas a diretório temporário, sem ativação | Exit 0; temporários removidos |
| Revisão independente | Limites de privilégio, links/TOCTOU, backups, inventários, prazo e estados de falha | Sem bloqueios conhecidos no código final |
| Regressão local final | 78 scripts executados individualmente; hashes de fontes/testes mantidos durante toda a execução | 76 aprovados, 2 pulados, 0 falhas |
| Privacidade | Revisão dos 14 arquivos novos/alterados, com fixtures e dados sintéticos | Nenhum conteúdo sensível identificado |

Os pulos são `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por ausência do
motor Firebird opcional. A execução final ocorreu após as correções da revisão;
uma execução anterior também passou, mas foi substituída como evidência final
porque o executor e seu teste mudaram durante aquela rodada.

As regressões específicas incluem criação exclusiva de baseline em diretório
controlado pelo usuário de teste, transporte sem seguir links, rejeição por SHA,
preservação do diagnóstico original e último deploy, schema esperado obtido do
candidato, preservação de identidades e conteúdo imutável, limites do sandbox e
prazo global da manutenção. A parada de emergência tem orçamento próprio de
90 segundos após falha; o prazo normal de 900 segundos não promete recuperação
nem disponibilidade dentro desse intervalo.

No canário Linux, o UID foi 65534 e NoNewPrivs foi 1. O processo carregou
FastAPI, httpx e openpyxl pelo bind do venv; acesso aos dados produtivos e ao
arquivo do cofre foi negado. A conexão externa retornou ENETUNREACH. Nenhum
conteúdo protegido foi lido. Unit transitória e diretório do canário foram
encerrados e removidos. Esse ensaio precede a validação do runner completo.

O canário identificou que o executável do bind não existe no host quando o
cliente systemd-run resolve o comando. A execução usa `/usr/bin/env` como
entrada e resolve o Python após a montagem no namespace.

## Referências de infraestrutura

- [Ambiente e isolamento de processos no systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
- [Agendamento de timers no systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).

Comportamento deve ser validado no systemd instalado na VM; documentação da
versão mais recente não substitui o ensaio no ambiente real.
