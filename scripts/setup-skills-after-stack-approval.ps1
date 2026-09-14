param(
    [switch]$InstallProposedNextFastAPIStack
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx is required."
}

if (-not $InstallProposedNextFastAPIStack) {
    Write-Host "No skills installed."
    Write-Host ""
    Write-Host "This project is in NO-ASSUMPTION mode."
    Write-Host "First confirm DEC-TECH-001."
    Write-Host ""
    Write-Host "If Next.js + FastAPI is explicitly approved, run:"
    Write-Host "  .\scripts\setup-skills-after-stack-approval.ps1 -InstallProposedNextFastAPIStack"
    exit 0
}

Write-Host "Installing curated skills for the explicitly approved Next.js + FastAPI stack..."

npx skills add https://github.com/fastapi/fastapi --skill fastapi
npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices
npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-composition-patterns
npx skills add https://github.com/vercel-labs/openreview --skill next-best-practices
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines
npx skills add https://github.com/anthropics/skills --skill webapp-testing

Write-Host ""
Write-Host "Review installed SKILL.md files before use."
Write-Host "Start a NEW Claude Code session after installation."
