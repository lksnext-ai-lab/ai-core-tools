# PreToolUse guard (Bash): block `git add` of secrets/specs and indiscriminate staging.
# Enforces the git-workflow rule: stage explicit application paths only. Always exits 0.
$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $data = $raw | ConvertFrom-Json } catch { exit 0 }

$cmd = $data.tool_input.command
if (-not $cmd) { exit 0 }
if ($cmd -notmatch 'git\s+add') { exit 0 }

$reason = $null
if ($cmd -match 'git\s+add\s+(-A|--all|\.)(\s|$)') {
    $reason = "Blocked: 'git add -A/./--all' stages everything indiscriminately and may include secrets or .claude/specs. Stage explicit application paths instead (see the git-workflow skill)."
}
elseif ($cmd -match '\.claude/specs' -or $cmd -match '\.env(\s|$|/|")' -or $cmd -match '\.pem' -or $cmd -match 'credentials') {
    $reason = "Blocked: refusing to stage internal/secret paths (.claude/specs, .env, *.pem, credentials). These are never committed."
}

if ($reason) {
    $out = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } }
    $out | ConvertTo-Json -Depth 5 -Compress
}
exit 0
