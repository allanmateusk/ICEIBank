param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('eleicao', 'failover', 'historico', 'conflito')]
    [string]$Acao
)

$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
$arquivosCompose = @('-p', 'iceibank-evidencias', '-f',
    (Join-Path $raizProjeto 'compose.yaml'), '-f',
    (Join-Path $PSScriptRoot 'compose-evidencias-sprint3.yaml'))
$pastaLogs = Join-Path $raizProjeto '.tools/evidencias-sprint3/logs'

function Compose {
    & docker compose @arquivosCompose @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose terminou com erro $LASTEXITCODE." }
}

function Esperar-Lider([int[]]$Agencias, [int]$Lider) {
    for ($tentativa = 0; $tentativa -lt 60; $tentativa++) {
        try {
            $respostas = @($Agencias | ForEach-Object {
                Invoke-RestMethod -TimeoutSec 2 -Uri "http://127.0.0.1:$($_ + 4400)/bully/lider"
            })
            if (@($respostas | Where-Object { $_.liderId -ne $Lider -or $_.emEleicao }).Count -eq 0) {
                return $respostas
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "As agencias nao convergiram para a lider $Lider dentro do tempo de espera."
}

function Mostrar-Data {
    Write-Host 'PowerShell: Get-Date -Format o'
    Get-Date -Format o
}

Push-Location $raizProjeto
try {
    switch ($Acao) {
        'eleicao' {
            # A primeira chamada cria um projeto e volumes próprios. As demais
            # reiniciam apenas as três agências desse mesmo projeto isolado.
            Compose up -d --build --wait rabbitmq postgres agencia-0 agencia-1 agencia-2
            Compose restart agencia-0 agencia-1 agencia-2
            $respostas = Esperar-Lider @(0, 1, 2) 2
            Mostrar-Data
            Write-Host 'Eleicao inicial: respostas das tres agencias'
            $respostas | Select-Object agenciaId, liderId, emEleicao | Format-Table -AutoSize
        }
        'failover' {
            $inicial = Esperar-Lider @(0, 1, 2) 2
            try {
                Compose stop agencia-2
                $aposFalha = Esperar-Lider @(0, 1) 1
                Mostrar-Data
                Write-Host 'Lider inicial:' $inicial[0].liderId
                Write-Host 'Agencia 2 parada; lider eleita automaticamente:'
                $aposFalha | Select-Object agenciaId, liderId, emEleicao | Format-Table -AutoSize
            } finally {
                Compose start agencia-2
            }
            $retorno = Esperar-Lider @(0, 1, 2) 2
            Write-Host 'Agencia 2 religada; lider apos retorno:' $retorno[0].liderId
        }
        'historico' {
            if (-not (Test-Path -LiteralPath $pastaLogs)) {
                throw 'Execute primeiro a acao eleicao e depois failover.'
            }
            Mostrar-Data
            Write-Host 'Historico de lideres eleitas e indisponiveis:'
            & node (Join-Path $raizProjeto 'agencia/historico-lideranca.js') $pastaLogs |
                Select-String 'BULLY_LIDER_ELEITA|BULLY_LIDER_INDISPONIVEL' | Select-Object -Last 8
            if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar historico.' }
        }
        'conflito' {
            $sufixo = [guid]::NewGuid().ToString('N').Substring(0, 10)
            $usuarioTeste = "evidencia_$sufixo"
            $senhaTeste = [guid]::NewGuid().ToString('N')
            $login = @{usuario=$usuarioTeste; senha=$senhaTeste} | ConvertTo-Json -Compress
            $base = 'http://127.0.0.1:4400'
            Invoke-RestMethod -Method Post -Uri "$base/auth/cadastro" -ContentType 'application/json' -Body $login | Out-Null
            $sessao = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType 'application/json' -Body $login
            $cabecalhos = @{ Authorization = "Bearer $($sessao.access_token)" }
            $numeroConta = ([int](Get-Random -Minimum 10000000 -Maximum 99999999)) * 3
            $cadastro = @{id=$numeroConta; nomeAluno='Conta demonstracao'; saldoInicial=100} | ConvertTo-Json -Compress
            Invoke-RestMethod -Method Post -Uri "$base/contas" -ContentType 'application/json' -Headers $cabecalhos -Body $cadastro | Out-Null
            $conta = Invoke-RestMethod -Uri "$base/contas/$numeroConta" -Headers $cabecalhos
            $deposito = @{valor=10} | ConvertTo-Json -Compress
            Invoke-RestMethod -Method Post -Uri "$base/contas/$numeroConta/depositar" -ContentType 'application/json' -Headers $cabecalhos -Body $deposito | Out-Null
            $pedido = @{tipo='SAQUE'; valor=5; vetorConhecido=@($conta.vetorAtual)} | ConvertTo-Json -Compress
            try {
                Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$base/contas/$numeroConta/sincronizar" -ContentType 'application/json' -Headers $cabecalhos -Body $pedido | Out-Null
                throw 'O conflito esperado nao ocorreu.'
            } catch {
                if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 409) { throw }
                $resposta = $_.ErrorDetails.Message
                if (-not $resposta) {
                    $leitor = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
                    try { $resposta = $leitor.ReadToEnd() } finally { $leitor.Dispose() }
                }
                Mostrar-Data
                Write-Host "POST /contas/$numeroConta/sincronizar -> HTTP 409"
                $resposta | ConvertFrom-Json | ConvertTo-Json -Depth 8 -Compress
            }
        }
    }
} finally {
    Pop-Location
}
