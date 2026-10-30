param(
    [ValidateRange(1024, 65535)]
    [int]$WebPort = 8080
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$outputPath = Join-Path $projectRoot '.env.deploy.local'
$templatePath = Join-Path $projectRoot 'deploy/.env.example'

if (Test-Path -LiteralPath $outputPath) {
    Write-Output 'Deployment config already exists; its contents were preserved.'
    exit 0
}

$template = [System.IO.File]::ReadAllText($templatePath)
$template = [regex]::Replace($template, '(?m)^WEB_PORT=[^\r\n]*', "WEB_PORT=$WebPort")
$template = [regex]::Replace($template, '(?m)^CORS_ORIGINS=[^\r\n]*',
    "CORS_ORIGINS=http://127.0.0.1:$WebPort,http://localhost:$WebPort")
[byte[]]$passwordBytes = New-Object byte[] 32
$randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomGenerator.GetBytes($passwordBytes)
} finally {
    $randomGenerator.Dispose()
}
$databasePassword = [System.BitConverter]::ToString($passwordBytes).Replace('-', '').ToLowerInvariant()
$template = [regex]::Replace($template, '(?m)^POSTGRES_PASSWORD=[^\r\n]*', "POSTGRES_PASSWORD=$databasePassword")

# Carry over only model settings, never local database paths or server ports.
# Keep dotenv quoting intact and never print the values.
$modelValues = @{}
foreach ($sourcePath in @((Join-Path $projectRoot '.env'), (Join-Path $projectRoot 'backend/.env'))) {
    if (Test-Path -LiteralPath $sourcePath) {
        foreach ($sourceLine in [System.IO.File]::ReadAllLines($sourcePath)) {
            if ($sourceLine -match '^\s*(?:export\s+)?(API_KEY|API_BASE_URL|CHAT_MODEL|EMBEDDING_MODEL)\s*=(.*)$') {
                $modelValues[$Matches[1]] = $Matches[2]
            }
        }
    }
}
foreach ($settingName in $modelValues.Keys) {
    $settingLine = $settingName + '=' + $modelValues[$settingName]
    $template = [regex]::Replace($template, "(?m)^$settingName=[^\r\n]*", [System.Text.RegularExpressions.MatchEvaluator]{
        param($matchedLine)
        return $settingLine
    })
}

# CreateNew refuses to overwrite a config created concurrently.
$fileStream = [System.IO.File]::Open($outputPath, [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
$writer = New-Object System.IO.StreamWriter($fileStream, (New-Object System.Text.UTF8Encoding($false)))
try {
    $writer.Write($template)
} finally {
    $writer.Dispose()
}
Write-Output 'Created .env.deploy.local with a random database password.'
Write-Output 'Existing project model settings were reused when present; no secret values were printed.'
