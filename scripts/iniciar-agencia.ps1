param([ValidateRange(0,2)][int]$Agencia = 0, [int]$Offset = 0)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$env:AGENCIA_ID = [string]$Agencia
$env:OFFSET = [string]$Offset
if (-not $env:RABBITMQ_URL) {
    $env:RABBITMQ_URL = 'amqp://iceibank:iceibank-dev@127.0.0.1:5678/'
}
Write-Host "Agencia $Agencia na porta $(4000 + $Offset + $Agencia)"
Get-Date
Push-Location (Join-Path $repo 'agencia')
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv run uvicorn src.main:app --host 127.0.0.1 --port (4000 + $Offset + $Agencia)
    } elseif (Test-Path -LiteralPath (Join-Path $repo '.tools/bin/uv.exe')) {
        & (Join-Path $repo '.tools/bin/uv.exe') run uvicorn src.main:app --host 127.0.0.1 --port (4000 + $Offset + $Agencia)
    } else { throw 'Instale uv ou configure-o no PATH antes de iniciar.' }
}
finally { Pop-Location }
