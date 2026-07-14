"""Versao web (site interno) da Auditoria Fiscal.

Este pacote e a UNICA camada que conhece FastAPI: importa o core e as
ferramentas existentes e os expoe como API JSON + arquivos para download.
O core nunca importa daqui (specs/001-auditoria-web, FR-010).
"""
