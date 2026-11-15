param(
    [Parameter(Mandatory = $true)]
    [string]$DeviceId
)

$ErrorActionPreference = 'Stop'
$mobileDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoDir = (Resolve-Path (Join-Path $mobileDir '..')).Path
$toolsDir = Join-Path $repoDir '.tools'
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
$copia = Join-Path $toolsDir ('android-teste-' + [guid]::NewGuid().ToString('N'))
$androidCopia = Join-Path $copia 'android'
New-Item -ItemType Directory -Path $copia, $androidCopia | Out-Null

$flutter = Join-Path $toolsDir 'flutter\bin\flutter.bat'
if (-not (Test-Path -LiteralPath $flutter)) {
    $flutter = (Get-Command flutter -ErrorAction Stop).Source
}
$adb = Join-Path $toolsDir 'android-sdk\platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $adb)) {
    $adb = (Get-Command adb -ErrorAction Stop).Source
}

Copy-Item -LiteralPath (Join-Path $mobileDir 'pubspec.yaml'), (Join-Path $mobileDir 'pubspec.lock'),
    (Join-Path $mobileDir 'analysis_options.yaml') -Destination $copia
Copy-Item -LiteralPath (Join-Path $mobileDir 'lib'), (Join-Path $mobileDir 'integration_test') -Destination $copia -Recurse
Get-ChildItem -LiteralPath (Join-Path $mobileDir 'android') -Force |
    Where-Object { $_.Name -notin @('.gradle', '.kotlin') } |
    Copy-Item -Destination $androidCopia -Recurse

$gradle = Join-Path $androidCopia 'app\build.gradle.kts'
$texto = Get-Content -LiteralPath $gradle -Raw
$original = 'applicationId = "com.example.iceibank_mobile"'
$isolado = 'applicationId = "com.example.iceibank_mobile_integration"'
$namespaceOriginal = 'namespace = "com.example.iceibank_mobile"'
$namespaceIsolado = 'namespace = "com.example.iceibank_mobile_integration"'
if (-not $texto.Contains($original) -or -not $texto.Contains($namespaceOriginal)) {
    throw 'applicationId ou namespace original não encontrado; teste abortado.'
}
$texto = $texto.Replace($original, $isolado)
$texto = $texto.Replace($namespaceOriginal, $namespaceIsolado)
Set-Content -LiteralPath $gradle -Value $texto -NoNewline
$atividade = Join-Path $androidCopia 'app\src\main\kotlin\com\example\iceibank_mobile\MainActivity.kt'
$kotlin = Get-Content -LiteralPath $atividade -Raw
if (-not $kotlin.Contains('package com.example.iceibank_mobile')) {
    throw 'Pacote de MainActivity não encontrado; teste abortado.'
}
$kotlin = $kotlin.Replace('package com.example.iceibank_mobile', 'package com.example.iceibank_mobile_integration')
Set-Content -LiteralPath $atividade -Value $kotlin -NoNewline

# Não sobrescreva encaminhamentos existentes que possam pertencer a outra tarefa.
$reversos = @(& $adb -s $DeviceId reverse --list)
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível consultar o dispositivo ADB.' }
foreach ($porta in 4000..4002) {
    $destino = $porta + 200
    $existente = @($reversos | Where-Object { $_ -match "\btcp:$porta\s+tcp:\d+" })
    if ($existente.Count -gt 0 -and $existente[0] -notmatch "\btcp:$porta\s+tcp:$destino\b") {
        throw "Já existe encaminhamento diferente para tcp:$porta; teste abortado."
    }
    if ($existente.Count -eq 0) {
        & $adb -s $DeviceId reverse "tcp:$porta" "tcp:$destino"
        if ($LASTEXITCODE -ne 0) { throw "Falha ao configurar tcp:$porta." }
    }
}

Write-Host "Cópia de teste: $copia"
Write-Host 'O ensaio criará dados de teste no backend isolado das portas 4200–4202.'
$javaAnterior = $env:JAVA_HOME
$androidAnterior = $env:ANDROID_HOME
$opcoesAnteriores = $env:JAVA_TOOL_OPTIONS
try {
    $javaLocal = Join-Path $toolsDir 'java\jdk-21.0.13+9'
    $androidLocal = Join-Path $toolsDir 'android-sdk'
    if (-not $env:JAVA_HOME -and (Test-Path -LiteralPath $javaLocal)) { $env:JAVA_HOME = $javaLocal }
    if (-not $env:ANDROID_HOME -and (Test-Path -LiteralPath $androidLocal)) { $env:ANDROID_HOME = $androidLocal }
    if (-not $env:JAVA_TOOL_OPTIONS) { $env:JAVA_TOOL_OPTIONS = '-Djdk.net.unixdomain.tmpdir=C:\Windows\Temp' }
    Push-Location $copia
    & $flutter --no-version-check pub get
    if ($LASTEXITCODE -ne 0) { throw 'Flutter pub get falhou.' }
    # Evite a remoção automática do pacote ao final; preserva também a cópia
    # usada para investigar resultados e qualquer outro aplicativo no aparelho.
    & $flutter --no-version-check test --no-pub --no-uninstall -d $DeviceId integration_test/fluxo_real_test.dart
    if ($LASTEXITCODE -ne 0) { throw 'Teste de integração Android falhou.' }
} finally {
    if ((Get-Location).Path -eq $copia) { Pop-Location }
    $env:JAVA_HOME = $javaAnterior
    $env:ANDROID_HOME = $androidAnterior
    $env:JAVA_TOOL_OPTIONS = $opcoesAnteriores
}
