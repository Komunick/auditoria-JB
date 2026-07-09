# Gera o executavel Windows (AuditoriaFiscal.exe) com PyInstaller.
# Uso:  .\empacotar.ps1        (a partir da pasta do projeto)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"

# Garante o PyInstaller instalado no ambiente virtual.
& $py -m pip install --quiet pyinstaller

# Gera um unico .exe, sem console, incluindo os dados do brazilfiscalreport
# (fontes usadas na geracao do DANFE) e as bases legais da auditoria de
# produtos (pasta dados/).
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name AuditoriaFiscal --paths src --collect-all brazilfiscalreport `
  --add-data "dados;dados" `
  executar.py

Write-Host ""
Write-Host "Pronto. Executavel em: $root\dist\AuditoriaFiscal.exe"
