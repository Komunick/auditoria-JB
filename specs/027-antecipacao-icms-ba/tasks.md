# Tasks — Spec 027 (Antecipação e DIFAL do ICMS-BA)

**Input**: `spec.md` e `plan.md` desta pasta. Padrão `main()` + `OK/FALHOU` do
repositório. Evidências em `validacao.md`.

## Fase 1 — Núcleo puro

- [x] A001 `core/antecipacao_ba.py`: dois métodos de cálculo, arredondamento só
  no resultado, tabela de alíquotas por vigência e NCM, pendências (impede,
  decisão, aviso), escopo da nota, chave de acesso, competência, vencimento de
  referência, redução simulada e lançamento manual.
- [x] A002 `core/antecipacao_nfe.py`: leitor do XML a partir dos bytes, sem
  entidade externa nem rede; campo ausente continua ausente.
- [x] A003 `tests/nfe_sintetica.py` e `tests/test_antecipacao_ba.py`: exemplos
  das duas fontes, precisão conferida com frações exatas, exceções, tabela,
  chave, escopo, leitor e limite arquitetural.

## Fase 2 — Persistência

- [x] A004 `web/infra.py`: `caminho_db_antecipacao()` e
  `pasta_origens_antecipacao()`.
- [x] A005 `ferramentas/antecipacao_store.py`: schema 1 com carga inicial da
  tabela, importação sem duplicidade, recálculo que preserva decisão de
  revisor, revisão em lote, aprovação, reabertura, exclusão, totais, trilha
  append-only e triggers de imutabilidade.
- [x] A006 `tests/test_antecipacao_store.py`.

## Fase 3 — Web

- [x] A007 Seis permissões em `web/permissoes.py` e sete ações em
  `web/auditoria.py`; nenhuma no padrão de usuário novo.
- [x] A008 `web/rotas_antecipacao.py` e registro em `web/servidor.py`.
- [x] A009 `ferramentas/relatorio_antecipacao.py` (Itens, Totais, Metadados).
- [x] A010 `tests/test_web_antecipacao.py`.

## Fase 4 — Tela

- [x] A011 `webui/antecipacao.js`, botão e seção em `webui/index.html`, resumo
  na Central (`webui/inicio.js`) e regras da tabela em `webui/estilo.css`.
- [x] A012 Conferência do fluxo completo no navegador com dados sintéticos.

## Fase 5 — Documentação e regressão

- [x] A013 `README-servidor.md` (seção da aba 11, dados e backup) e `README.md`
  (lista de testes).
- [x] A014 Suíte completa antes e depois.

## Fase 6 — Integração com o redesign (spec 028)

- [x] A019 Merge da `dev` com o redesign (`65458ec`) na branch; conflitos em
  `webui/index.html` e `webui/estilo.css` resolvidos pelo lado do redesign,
  com a aba 11 no grupo "Fiscal & Emissão", número 11, e palavras-chave na
  busca rápida (`Ctrl+K`, `webui/app.js`).
- [x] A020 Teste de regressão em `test_web_antecipacao.py`: grupo, número e
  palavras-chave da aba 11 no menu novo.
- [x] A021 Ajustes visuais da memória de cálculo: espaço acima dos títulos
  internos, pendências e botões da tabela na fonte da interface.
- [x] A022 Suíte completa e conferência no navegador (desktop e celular,
  temas claro e escuro).

## Pendente (não é desta entrega)

- [ ] A015 Homologação pela equipe fiscal da JB: P-01 a P-08 da spec.
- [ ] A016 Decisão sobre antecipação total/ST (P-09) e consulta à SEFAZ pela
  chave (P-10).
- [ ] A017 Conferência com XML reais de clientes, fora do Git.
- [ ] A018 Deploy e concessão das permissões, pelo dono.
