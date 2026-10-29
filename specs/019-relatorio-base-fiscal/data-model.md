# Contratos

## Gerador

`gerar_relatorio_base_fiscal(leitura: LeituraEmpresas, *, nome_arquivo: str) -> bytes`
em `ferramentas/relatorio_base_fiscal.py`. Não conhece FastAPI ou bancos e não
altera o objeto de leitura. Falhas de representação usam ErroClientes com código
PLANILHA_INVALIDA e mensagem localizável, sem devolver saída parcial.

Abas: `Resumo`, `Conferência`, `Duplicidades`, `Correções`, `Origens`. Campos de
propostas ficam vazios; metadados e instruções distinguem relatório de fonte.
Toda ocorrência duplicada mantém ID e CNPJ; não concatenar listas de pares.

## HTTP

`POST /api/clientes/base-fiscal/relatorio`, multipart:

- `arquivo`: XLSX original, mesmos limites da prévia.
- `hash_esperado`: SHA-256 hexadecimal minúsculo de 64 caracteres, obrigatório.

Autorização: `aba.clientes` + `clientes.importar` + `clientes.exportar`.
Auditoria: ação `clientes.exportar`, detalhe `relatorio base fiscal: N linha(s)`.
Sucesso 200: MIME XLSX, `Cache-Control: no-store`, `Content-Disposition:
attachment; filename="conferencia-base-fiscal.xlsx"`.
Falhas: 401/403 acesso; 409 `BASE_FISCAL_DIVERGENTE`; 413 tamanho; 422
hash/extensão/pacote/layout/representação inválidos. Upload fechado em todo caso.

## Navegador

Botão `bf-relatorio`, texto `Baixar relatório completo (.xlsx)`, só utilizável
depois de prévia válida e com as três permissões. Reenvia apenas arquivo/hash,
sem filtros. Download só iniciado depois de conferir geração e identidade tanto
após resposta HTTP quanto após leitura do blob. URL de objeto descartada.
