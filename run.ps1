$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Push-Location -LiteralPath $ProjectRoot
try {
    $EnvFile = Join-Path $ProjectRoot '.env'
    if (Test-Path -LiteralPath $EnvFile) {
        foreach ($Line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
            if ($Line -match '^([A-Z_][A-Z0-9_]*)=(.*)$') {
                [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process')
            }
        }
    }
    & poetry run python -m swe_agent.cli @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
