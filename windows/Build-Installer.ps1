$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distributionRoot = Join-Path $PSScriptRoot "distribution"
$payloadRoot = Join-Path $distributionRoot "payload"
$launcherProject = Join-Path $PSScriptRoot "launcher\Cabinet.csproj"
$setupScript = Join-Path $PSScriptRoot "installer\Cabinet.iss"
$appVersion = "2.0.0"
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
    "prescriptions",
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
    ".env.example",
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
$unexpectedEnvironmentFiles = Get-ChildItem -LiteralPath $payloadRoot -Force -File -Recurse |
    Where-Object {
        $_.Name -match '^\.env($|\.)' -and $_.Name -ne ".env.example"
    }
if ($unexpectedEnvironmentFiles) {
    throw "Le paquet contient un fichier de configuration secret : $($unexpectedEnvironmentFiles[0].FullName)"
}
$forbiddenFiles = Get-ChildItem -LiteralPath $payloadRoot -File -Recurse |
    Where-Object {
        $_.Name -match '\.(sqlite3?|db|dump|pgdump|backup|sql)$' -or
        $_.Name -match '(^|[-_.])(backup|sauvegarde)([-_.]|$)' -or
        $_.Name -match '\.sql\.gz$'
    }
if ($forbiddenFiles) {
    throw "Le paquet contient un fichier de base ou de sauvegarde : $($forbiddenFiles[0].FullName)"
}
$requiredFiles = @(
    "Cabinet.exe",
    "Dockerfile",
    "docker-entrypoint.sh",
    "compose.yaml",
    ".env.example",
    "requirements.txt",
    "manage.py"
)
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $payloadRoot $file) -PathType Leaf)) {
        throw "Le paquet ne contient pas le fichier obligatoire $file."
    }
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

$setupOutput = Join-Path $distributionRoot "Cabinet-Setup-$appVersion.exe"
$stagingRoot = Join-Path $distributionRoot ("staging-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
try {
    & $compilerPath "/O$stagingRoot" $setupScript
    if ($LASTEXITCODE -ne 0) {
        throw "La compilation de Cabinet-Setup.exe a échoué."
    }

    $stagedInstaller = Join-Path $stagingRoot "Cabinet-Setup-$appVersion.exe"
    if (-not (Test-Path -LiteralPath $stagedInstaller -PathType Leaf) -or
        (Get-Item -LiteralPath $stagedInstaller).Length -eq 0) {
        throw "La compilation Inno Setup n’a pas produit un installateur valide."
    }
    if (Test-Path -LiteralPath $setupOutput) {
        $previousInstaller = Join-Path $stagingRoot "previous-installer.exe"
        Move-Item -LiteralPath $setupOutput -Destination $previousInstaller
        try {
            [System.IO.File]::Move($stagedInstaller, $setupOutput)
        }
        catch {
            Move-Item -LiteralPath $previousInstaller -Destination $setupOutput
            throw
        }
    } else {
        [System.IO.File]::Move($stagedInstaller, $setupOutput)
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

Write-Output "Installateur créé dans $distributionRoot."
