<#
.SYNOPSIS
  Copies this working tree to the DigitalOcean dev-environment Droplet.
  Builds a local tar.gz (excluding .git, dependency/build artifacts, and .env -- which
  holds local secrets; create a fresh, production-appropriate .env directly on the server
  instead), scp's that single file over, then extracts it remotely.

  Note: this stages via a file + scp rather than piping tar directly into ssh, because
  PowerShell's pipeline mangles binary data passed between two native executables --
  piping tar's gzip output straight into ssh corrupts the stream.

.EXAMPLE
  ./scripts/deploy-copy-to-droplet.ps1 -DropletIp 203.0.113.10
  ./scripts/deploy-copy-to-droplet.ps1 -DropletIp 203.0.113.10 -User deploy -RemotePath /home/deploy/edusphere
#>
param(
    [Parameter(Mandatory=$true)][string]$DropletIp,
    [string]$User = "deploy",
    [string]$RemotePath = "/home/deploy/edusphere"
)

$excludes = @(
    "--exclude=.git",
    "--exclude=node_modules",
    "--exclude=.next",
    "--exclude=test-results",
    "--exclude=__pycache__",
    "--exclude=.venv",
    "--exclude=.env",
    "--exclude=.claude-cache",
    "--exclude=.claude",
    "--exclude=.agents"
)

$archive = Join-Path $env:TEMP "edusphere-deploy.tar.gz"
$remoteTmp = "/tmp/edusphere-deploy.tar.gz"

Write-Host "Building archive: $archive"
& tar @excludes -czf $archive -C "$PSScriptRoot\.." .
if ($LASTEXITCODE -ne 0) { Write-Host "tar failed (exit $LASTEXITCODE)" -ForegroundColor Red; exit 1 }

Write-Host "Ensuring $RemotePath exists on server ..."
& ssh "$User@$DropletIp" "mkdir -p $RemotePath"
if ($LASTEXITCODE -ne 0) { Write-Host "ssh mkdir failed (exit $LASTEXITCODE)" -ForegroundColor Red; exit 1 }

Write-Host "Copying archive to ${User}@${DropletIp}:$remoteTmp ..."
& scp $archive "${User}@${DropletIp}:$remoteTmp"
if ($LASTEXITCODE -ne 0) { Write-Host "scp failed (exit $LASTEXITCODE)" -ForegroundColor Red; exit 1 }

Write-Host "Extracting on server ..."
& ssh "$User@$DropletIp" "tar xzf $remoteTmp -C $RemotePath && rm $remoteTmp"
$extractExit = $LASTEXITCODE

Remove-Item $archive -Force

if ($extractExit -eq 0) {
    Write-Host "Done. Next: SSH in, create .env from .env.example with production values, then:"
    Write-Host "  docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build"
} else {
    Write-Host "Extraction failed (exit code $extractExit)." -ForegroundColor Red
}
