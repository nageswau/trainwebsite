$ErrorActionPreference = "Stop"

$commands = @("git","node","npm","npx","python","docker","claude")
$missing = @()

foreach ($cmd in $commands) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $cmd"
    } else {
        Write-Host "[MISSING] $cmd"
        $missing += $cmd
    }
}

if ($missing.Count -gt 0) {
    throw "Install missing prerequisites before continuing: $($missing -join ', ')"
}

Write-Host ""
Write-Host "Claude Code:"
claude --version

Write-Host ""
Write-Host "IMPORTANT:"
Write-Host "- Do not run stack-specific skill installation until DEC-TECH-001 is confirmed."
Write-Host "- Do not delete .claude-cache routinely."
Write-Host "- Start with prompts/00_BOOTSTRAP_AND_EVIDENCE_INVENTORY.md."
