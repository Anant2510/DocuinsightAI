# Starts DocuInsights on this machine. Behind a reverse proxy at /docuinsights add: --root-path /docuinsights
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
$stamp = ".venv\.installed"
if (-not (Test-Path $stamp) -or ((Get-Item pyproject.toml).LastWriteTime -gt (Get-Item $stamp).LastWriteTime)) {   # first run, or the requirements changed
  & .\.venv\Scripts\python -m pip install -e ".[server,pdf]" --quiet
  Set-Content $stamp (Get-Date)
}
if (-not $env:DOCUINSIGHTS_DATA_DIR) { $env:DOCUINSIGHTS_DATA_DIR = Join-Path $PSScriptRoot "data" }
& .\.venv\Scripts\python -m docuinsights serve --host 127.0.0.1 --port 8090 @args
