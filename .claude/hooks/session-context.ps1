# SessionStart: inject current git branch, short working-tree status, and active specs as context.
$ErrorActionPreference = 'SilentlyContinue'

$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = (Get-Location).Path }
Set-Location $projDir

$branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
$status = (& git status --short 2>$null | Select-Object -First 15 | Out-String)

$specs = ''
$specDir = Join-Path $projDir '.claude\specs'
if (Test-Path $specDir) {
    $names = Get-ChildItem -Directory $specDir -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    if ($names) { $specs = ($names -join ', ') }
}

$lines = @()
$lines += "Claude Code agent system active (.claude/). Entry commands: /spec, /solve-issue, /fix, /implement, /review, /production-audit, /ship."
if ($branch) { $lines += "Git branch: $branch" }
if ($status.Trim()) { $lines += "Working tree:`n$($status.Trim())" }
if ($specs) { $lines += "Active specs: $specs" }

$ctx = $lines -join "`n"
$out = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } }
$out | ConvertTo-Json -Depth 5 -Compress
exit 0
