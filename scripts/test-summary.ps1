param(
    [string]$PytestArgs = "-q",
    [string]$NpmScript = ""
)

$ErrorActionPreference = "Continue"

Write-Host "=== Compact Test Runner ==="

if (Test-Path "apps\api") {
    Push-Location "apps\api"
    Write-Host "Backend: pytest $PytestArgs"
    python -m pytest $PytestArgs
    $backendExit = $LASTEXITCODE
    Pop-Location
} else {
    $backendExit = 0
}

if ($NpmScript -and (Test-Path "apps\web")) {
    Push-Location "apps\web"
    Write-Host "Frontend: npm run $NpmScript"
    npm run $NpmScript
    $frontendExit = $LASTEXITCODE
    Pop-Location
} else {
    $frontendExit = 0
}

Write-Host "Backend exit: $backendExit"
Write-Host "Frontend exit: $frontendExit"

if (($backendExit -ne 0) -or ($frontendExit -ne 0)) { exit 1 }
exit 0
