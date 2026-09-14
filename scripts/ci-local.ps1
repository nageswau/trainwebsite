[CmdletBinding()]
param(
    [string]$ArtifactRoot = "artifacts/ci",
    [switch]$KeepStack
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$runId = "{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $PID
$runDirectory = Join-Path $repoRoot (Join-Path $ArtifactRoot $runId)
New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runDirectory "api"), (Join-Path $runDirectory "unit"), (Join-Path $runDirectory "playwright") | Out-Null

$projectName = ("edusphere-ci-{0}-{1}" -f $PID, (Get-Random -Minimum 1000 -Maximum 9999)).ToLowerInvariant()
if ($projectName -notmatch '^edusphere-ci-[0-9]+-[0-9]{4}$') {
    throw "Refusing to use an unexpected Compose project name: $projectName"
}

$environmentSnapshot = @{
    CI_ARTIFACTS_DIR = [Environment]::GetEnvironmentVariable("CI_ARTIFACTS_DIR", "Process")
    API_PORT = [Environment]::GetEnvironmentVariable("API_PORT", "Process")
    WEB_PORT = [Environment]::GetEnvironmentVariable("WEB_PORT", "Process")
}
$artifactMount = $runDirectory.Replace('\', '/')
$env:CI_ARTIFACTS_DIR = $artifactMount
$env:API_PORT = [string](Get-Random -Minimum 21000 -Maximum 30000)
$env:WEB_PORT = [string](Get-Random -Minimum 31000 -Maximum 40000)
$composeFiles = @(
    "compose",
    "-f", (Join-Path $repoRoot "docker-compose.yml"),
    "-f", (Join-Path $repoRoot "docker-compose.ci.yml"),
    "-p", $projectName
)

$results = [System.Collections.Generic.List[object]]::new()
$hasFailure = $false
$temporaryEnvCreated = $false
function Invoke-CiCommand {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string[]]$DockerArguments
    )

    $logPath = Join-Path $runDirectory ("{0}.log" -f $Name)
    Write-Host "`n=== $Name ==="
    $started = Get-Date
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & docker @DockerArguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $output | Set-Content -Encoding utf8 $logPath
    $output | ForEach-Object { Write-Host $_ }
    $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    $status = if ($exitCode -eq 0) { "passed" } else { "failed" }
    $script:results.Add([pscustomobject]@{
        name = $Name
        status = $status
        exit_code = $exitCode
        duration_seconds = $duration
        log = (Resolve-Path -Relative $logPath)
    })
    if ($exitCode -ne 0) {
        $script:hasFailure = $true
    }
    return $exitCode
}

function Invoke-ComposeCommand {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    return Invoke-CiCommand -Name $Name -DockerArguments ($composeFiles + $Arguments)
}

function Invoke-SeedCommand {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$Service = "api",
        [switch]$OneOff
    )

    $logPath = Join-Path $runDirectory ("{0}.log" -f $Name)
    Write-Host "`n=== $Name ==="
    $started = Get-Date
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $seedArguments = if ($OneOff) {
            $composeFiles + @("--profile", "ci", "run", "--rm", "--no-deps", $Service, "python", "-m", "app.seed")
        } else {
            $composeFiles + @("exec", "-T", $Service, "python", "-m", "app.seed")
        }
        $seedOutput = & docker @seedArguments 2>&1
        $seedExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $safeOutput = $seedOutput | ForEach-Object { $_ -replace '(?i)(demo password:)\s+.*$', '$1 [REDACTED]' }
    $safeOutput | Set-Content -Encoding utf8 $logPath
    $safeOutput | ForEach-Object { Write-Host $_ }
    $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    $status = if ($seedExit -eq 0) { "passed" } else { "failed" }
    $results.Add([pscustomobject]@{
        name = $Name
        status = $status
        exit_code = $seedExit
        duration_seconds = $duration
        log = (Resolve-Path -Relative $logPath)
    })
    if ($seedExit -ne 0) {
        $script:hasFailure = $true
    }
    return $seedExit
}

function Save-ComposeFailureDiagnostics {
    param([Parameter(Mandatory)][string]$Name)

    $logPath = Join-Path $runDirectory ("{0}.log" -f $Name)
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $diagnostics = @("=== docker compose ps --all ===")
        $diagnostics += & docker @composeFiles "ps" "--all" 2>&1
        $diagnostics += ""
        $diagnostics += "=== docker compose logs api web ==="
        $diagnostics += & docker @composeFiles "logs" "--no-color" "--timestamps" "api" "web" 2>&1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $safeDiagnostics = $diagnostics | ForEach-Object {
        $_ `
            -replace '(?i)(demo password:)\s+.*$', '$1 [REDACTED]' `
            -replace '(?i)(authorization:\s*bearer\s+)\S+', '$1[REDACTED]'
    }
    $safeDiagnostics | Set-Content -Encoding utf8 $logPath
    Write-Host "Failure diagnostics saved: $logPath"
}

function Write-CiSummary {
    $summary = [ordered]@{
        run_id = $runId
        compose_project = $projectName
        generated_at = (Get-Date).ToString("o")
        status = if ($script:hasFailure) { "failed" } else { "passed" }
        stages = $results
    }
    $summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $runDirectory "summary.json")

    $markdown = @(
        "# EduSphere CI local run $runId",
        "",
        "Overall: **$($summary.status)**",
        "",
        "| Stage | Status | Seconds |",
        "|---|---|---:|"
    )
    foreach ($result in $results) {
        $markdown += "| $($result.name) | $($result.status) | $($result.duration_seconds) |"
    }
    $markdown += ""
    $markdown += "Failure-only Playwright evidence is under `playwright/test-results` and `playwright/report`; successful runs retain structured XML and this summary."
    $markdown | Set-Content -Encoding utf8 (Join-Path $runDirectory "summary.md")
}

try {
    if (-not (Test-Path (Join-Path $repoRoot ".env"))) {
        New-Item -ItemType File -Path (Join-Path $repoRoot ".env") | Out-Null
        $temporaryEnvCreated = $true
    }

    $buildExit = Invoke-ComposeCommand -Name "00-build-ci-images" -Arguments @("--profile", "ci", "build", "api-test", "web-test")
    if ($buildExit -ne 0) {
        throw "CI test images could not be built."
    }

    Invoke-ComposeCommand -Name "01-backend-format" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "api-test", "python", "-m", "ruff", "format", "--check", "app", "tests") | Out-Null
    Invoke-ComposeCommand -Name "02-frontend-lint" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "web-test", "npm", "run", "lint") | Out-Null
    Invoke-ComposeCommand -Name "03-ruff" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "api-test", "python", "-m", "ruff", "check", ".") | Out-Null
    Invoke-ComposeCommand -Name "04-mypy" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "api-test", "python", "-m", "mypy", "app") | Out-Null
    Invoke-ComposeCommand -Name "05-frontend-typecheck" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "web-test", "npm", "run", "typecheck") | Out-Null
    Invoke-ComposeCommand -Name "06-frontend-unit" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "web-test", "npx", "vitest", "run", "--reporter=default", "--reporter=junit", "--outputFile.junit=/artifacts/unit/vitest.xml") | Out-Null

    $servicesExit = Invoke-ComposeCommand -Name "07-start-migration-services" -Arguments @("--profile", "ci", "up", "-d", "--wait", "--wait-timeout", "180", "postgres", "redis")
    if ($servicesExit -eq 0) {
        $migrationExit = Invoke-ComposeCommand -Name "08-migration-upgrade" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "api-test", "alembic", "upgrade", "head")
        $driftExit = Invoke-ComposeCommand -Name "09-migration-drift-check" -Arguments @("--profile", "ci", "run", "--rm", "--no-deps", "api-test", "alembic", "check")
        if ($migrationExit -eq 0 -and $driftExit -eq 0) {
            $seedApiExit = Invoke-SeedCommand -Name "10-seed-api" -Service "api-test" -OneOff
            if ($seedApiExit -eq 0) {
                Invoke-ComposeCommand -Name "11-targeted-api" -Arguments @(
                    "--profile", "ci", "run", "--rm", "--no-deps", "api-test",
                    "python", "-m", "pytest", "-q",
                    "tests/test_health.py",
                    "tests/test_rbac.py",
                    "tests/test_role_assignments.py",
                    "tests/test_pub_003_catalogue.py",
                    "tests/test_uuid_contracts.py",
                    "--junitxml=/artifacts/api/targeted.xml"
                ) | Out-Null
            }
        }
    }

    Invoke-ComposeCommand -Name "12-reset-isolated-stack" -Arguments @("--profile", "ci", "down", "--volumes", "--remove-orphans") | Out-Null
    $appExit = Invoke-ComposeCommand -Name "13-start-e2e-stack" -Arguments @("--profile", "ci", "up", "-d", "--build", "--wait", "--wait-timeout", "300", "postgres", "redis", "api", "web")
    if ($appExit -eq 0) {
        $seedExit = Invoke-SeedCommand -Name "14-seed-e2e"
        if ($seedExit -eq 0) {
            $playwrightExit = Invoke-ComposeCommand -Name "15-playwright" -Arguments @(
                "--profile", "ci", "run", "--rm", "--no-deps",
                "-e", "CI=true",
                "-e", "E2E_BASE_URL=http://localhost:3000",
                "-e", "PLAYWRIGHT_PROXY_TARGET=http://web:3000",
                "-e", "PLAYWRIGHT_ARTIFACT_DIR=/artifacts/playwright",
                "web-test", "npx", "playwright", "test", "--workers=1", "--grep-invert", "@external"
            )
            if ($playwrightExit -ne 0) {
                Save-ComposeFailureDiagnostics -Name "15-playwright-services"
            }
        }
    } else {
        Save-ComposeFailureDiagnostics -Name "13-start-e2e-services"
    }
} catch {
    $hasFailure = $true
    $_ | Out-String | Set-Content -Encoding utf8 (Join-Path $runDirectory "fatal.log")
    Write-Error $_ -ErrorAction Continue
} finally {
    Write-CiSummary
    if (-not $KeepStack) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & docker @composeFiles "down" "--volumes" "--remove-orphans" 2>&1 | Out-Null
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    if ($temporaryEnvCreated) {
        Remove-Item -LiteralPath (Join-Path $repoRoot ".env")
    }
    foreach ($entry in $environmentSnapshot.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            Remove-Item -Path ("Env:{0}" -f $entry.Key) -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path ("Env:{0}" -f $entry.Key) -Value $entry.Value
        }
    }
    Write-Host "`nCI evidence: $runDirectory"
}

if ($hasFailure) {
    exit 1
}
