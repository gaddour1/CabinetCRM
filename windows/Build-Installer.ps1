$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distributionRoot = Join-Path $PSScriptRoot "distribution"
$payloadRoot = Join-Path $distributionRoot "payload"
$launcherProject = Join-Path $PSScriptRoot "launcher\Cabinet.csproj"
$setupScript = Join-Path $PSScriptRoot "installer\Cabinet.iss"
$dotnetExe = Join-Path $env:LOCALAPPDATA "dotnet\dotnet.exe"
if (-not (Test-Path -LiteralPath $dotnetExe)) {
    $dotnetCommand = Get-Command "dotnet.exe" -ErrorAction SilentlyContinue
    if (-not $dotnetCommand) {
        throw "Installez le SDK .NET 8 avant de construire Cabinet."
    }
    $dotnetExe = $dotnetCommand.Source
}

if (Test-Path -LiteralPath $payloadRoot) {
    Remove-Item -LiteralPath $payloadRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $payloadRoot | Out-Null

& $dotnetExe publish $launcherProject `
    --configuration Release `
    --runtime win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $payloadRoot
if ($LASTEXITCODE -ne 0) {
    throw "La compilation de Cabinet.exe a échoué."
}
Get-ChildItem -LiteralPath $payloadRoot -File -Filter "*.pdb" |
    Remove-Item -Force

$applicationDirectories = @(
    "accounts",
    "billing",
    "cabinet_config",
    "consultations",
    "core",
    "documents",
    "patients",
    "static",
    "templates"
)
foreach ($directory in $applicationDirectories) {
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot $directory) `
        -Destination (Join-Path $payloadRoot $directory) `
        -Recurse
}

$applicationFiles = @(
    "Dockerfile",
    "docker-entrypoint.sh",
    "compose.yaml",
    "requirements.txt",
    "manage.py"
)
foreach ($file in $applicationFiles) {
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot $file) `
        -Destination $payloadRoot
}

Get-ChildItem -LiteralPath $payloadRoot -Directory -Filter "__pycache__" -Recurse |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $payloadRoot -File -Filter "*.pyc" -Recurse |
    Remove-Item -Force
if (Get-ChildItem -LiteralPath $payloadRoot -Force -Filter ".env" -Recurse) {
    throw "Le paquet ne doit jamais contenir un fichier .env."
}

$compiler = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
if (-not $compiler) {
    $compilerCandidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
    )
    $compilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
} else {
    $compilerPath = $compiler.Source
}

if (-not $compilerPath) {
    Write-Output "Cabinet.exe et ses fichiers ont été publiés dans $payloadRoot."
    Write-Output "Installez Inno Setup 6 puis compilez windows\installer\Cabinet.iss."
    exit 0
}

$setupOutput = Join-Path $distributionRoot "Cabinet-Setup-1.0.0.exe"
if (Test-Path -LiteralPath $setupOutput) {
    Remove-Item -LiteralPath $setupOutput -Force
}

& $compilerPath $setupScript
if ($LASTEXITCODE -ne 0) {
    throw "La compilation de Cabinet-Setup.exe a échoué."
}

Write-Output "Installateur créé dans $distributionRoot."
