# Plano

1. Especificar contrato e revisar requisitos antes do código.
2. Escrever testes RED do gerador puro, da rota e do fluxo de download.
3. Implementar gerador em `ferramentas/relatorio_base_fiscal.py` usando openpyxl,
   recebendo `LeituraEmpresas`; texto literal, linhas completas e propostas vazias.
4. Adicionar rota multipart protegida em `rotas_clientes.py`, relendo a fonte,
   comparando hash e retornando bytes. Não abrir o store de clientes.
5. Adicionar controle de download no módulo BaseFiscalUI, com os mesmos guardas
   de arquivo/sessão da prévia; guardar apenas o File selecionado em memória.
6. Rodar testes específicos, suíte anterior, revisão independente e verificação
   visual sintética; registrar evidências e limitações.

Sem migração, serviço novo ou alteração do controlador de deploy. Desenvolvimento
no branch `codex/019-relatorio-base-fiscal`, baseado em `dev@76dd669`.
