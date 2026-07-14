# Sobe a Auditoria Fiscal Web na rede interna (porta padrao 8600).
# Atualizacao do sistema = git pull + reiniciar este script.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    Write-Host "Criando ambiente virtual..."
    python -m venv .venv
}
& .venv\Scripts\python -m pip install -r requirements.txt --quiet
Write-Host "Iniciando Auditoria Fiscal Web em http://localhost:$($env:AUDITORIA_WEB_PORTA ?? 8600) ..."
& .venv\Scripts\python servidor.py
